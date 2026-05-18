#!/usr/bin/env python3
"""
Multi-Symbol BB Scalper — Precision Analytics Edition (Blofin Global Fix)
------------------------------------------------------
- Feature: Fetches entire account position history in one call.
- Feature: Improved symbol matching and PnL parsing.
"""

import os
import time
import logging
import requests
import re
import asyncio
import ccxt.async_support as ccxt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

SYMBOL_CONFIGS = {
    "BTC":  {"bb": 2.5, "atr": 6.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "ETH":  {"bb": 2.5, "atr": 5.0, "rr": 1.25, "adx": 25, "rsi": 30},
    "SOL":  {"bb": 2.0, "atr": 4.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "DOGE": {"bb": 2.0, "atr": 5.0, "rr": 1.25, "adx": 0,  "rsi": 30, "long_only": True},
    "ADA":  {"bb": 2.5, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 40},
    "LINK": {"bb": 2.0, "atr": 6.0, "rr": 1.0,  "adx": 20, "rsi": 30},
    "DOT":  {"bb": 2.5, "atr": 4.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "TON":  {"bb": 2.0, "atr": 4.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "ZEC":  {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 20, "rsi": 30},
    "PEPE": {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "BNB":  {"bb": 2.5, "atr": 4.0, "rr": 1.25, "adx": 25, "rsi": 30},
    "NEAR": {"bb": 3.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "SUI":  {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "NOT":  {"bb": 2.0, "atr": 6.0, "rr": 1.25, "adx": 0,  "rsi": 30},
    "TAO":  {"bb": 2.0, "atr": 5.0, "rr": 1.25, "adx": 0,  "rsi": 30},
    "ONDO": {"bb": 2.5, "atr": 5.0, "rr": 1.25, "adx": 0,  "rsi": 30},
    "ENA":  {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "FET":  {"bb": 2.0, "atr": 6.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "WIF":  {"bb": 3.0, "atr": 5.0, "rr": 1.25, "adx": 25, "rsi": 30},
    "SHIB": {"bb": 2.5, "atr": 6.0, "rr": 1.25, "adx": 15, "rsi": 30},
}

# Optimized Valkyrie Elite Scalper individual symbol configurations
VALKYRIE_SYMBOL_CONFIGS = {
    "SOL":  {"bb": 2.4, "atr": 3.5, "rr": 1.0, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "LINK": {"bb": 2.6, "atr": 3.5, "rr": 1.0, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "BTC":  {"bb": 2.2, "atr": 3.5, "rr": 1.0, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "ADA":  {"bb": 2.4, "atr": 3.5, "rr": 0.8, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "DOT":  {"bb": 2.6, "atr": 3.0, "rr": 0.8, "adx": 25, "rsi_low": 25, "rsi_high": 75}
}

SYMBOLS = [f"{s}/USDT:USDT" for s in SYMBOL_CONFIGS.keys()]
BAD_HOURS_UTC = {4, 12}
TIMEFRAME     = "15m"
LEVERAGE      = 20
RISK_PER_TRADE = 0.015         # Default 1.5% compounding risk (Valkyrie Sweet Spot)
CANDLE_LIMIT   = 250
DRY_RUN        = os.getenv("BLOFIN_DRY_RUN", "true").lower() == "true"

os.makedirs("results", exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("results/live_log.txt"), logging.StreamHandler()])
log = logging.getLogger("Bot")

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

import database
from database import get_exchange_client, normalize_symbol

class MarketDataManager:
    """
    Centralized market data fetcher to save rate limits and ensure consistency.
    """
    def __init__(self, exchange_id='blofin'):
        self.exchange_id = exchange_id
        self.exchange = getattr(ccxt, exchange_id)({"options": {"defaultType": "swap"}})
        self.ohlcv_cache = {}

    async def fetch_ohlcv(self, symbol, timeframe, limit=250):
        if symbol not in self.ohlcv_cache:
            try:
                ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                self.ohlcv_cache[symbol] = df
            except Exception as e:
                log.error(f"MarketData fetch failed for {symbol}: {e}")
                return None
        return self.ohlcv_cache[symbol]

    async def close(self):
        await self.exchange.close()

def create_github_issue(subject, body):
    token, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not token or not repo: return
    owner = repo.split("/")[0]
    try:
        requests.post(f"https://api.github.com/repos/{repo}/issues", json={"title": subject, "body": body, "assignees": [owner]}, headers={"Authorization": f"token {token}"})
    except: pass

import strategies

def compute_signal(df, symbol_name, strategy_name="Mean Reversion Scalper"):
    """
    Modular signal computation using the selected strategy.
    """
    strat = strategies.get_strategy(strategy_name)
    side = strat.check_signal(df, symbol_name)
    
    if not side:
        return None
        
    # Standardize output using strategy-specific configurations
    if strategy_name == "Valkyrie Elite Scalper":
        cfg = VALKYRIE_SYMBOL_CONFIGS.get(symbol_name)
        if not cfg:
            return None
    else:
        cfg = SYMBOL_CONFIGS.get(symbol_name)
        if not cfg:
            return None
    
    # ATR for SL calculation (common across strategies)
    tr = pd.concat([df["high"] - df["low"], abs(df["high"] - df["close"].shift()), abs(df["low"] - df["close"].shift())], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    last = df.iloc[-2]
    
    if datetime.now(timezone.utc).hour in BAD_HOURS_UTC: 
        return None
        
    return {
        "side": "buy" if side == "LONG" else "sell", 
        "entry": last["close"], 
        "sl_dist": atr.iloc[-2] * cfg["atr"], 
        "rr": cfg["rr"]
    }


async def place_order(exchange, symbol, signal, equity, risk_pct=None):
    try:
        # Use user-specific risk or fallback to global default
        risk_val = (risk_pct / 100.0) if risk_pct is not None else RISK_PER_TRADE
        
        market = exchange.market(symbol)
        ticker = await exchange.fetch_ticker(symbol)
        lp = ticker["last"]
        if abs(lp - signal["entry"]) / signal["entry"] > 0.01: return None
        sl_dist, rr = signal["sl_dist"], signal["rr"]
        sl, tp = lp - sl_dist, lp + (sl_dist * rr)
        contract_size = float(market.get('contractSize') or 1)
        if contract_size <= 0: contract_size = 1
        
        raw_size = (equity * risk_val) / (sl_dist * contract_size)
        
        limits = market.get('limits', {})
        max_market = limits.get('market', {}).get('amount', {}).get('max')
        if max_market is None: 
            max_market = limits.get('amount', {}).get('max')
        if max_market is None:
            max_market = 999999999.0 # Safe fallback
            
        max_leverage_size = (equity * LEVERAGE) / (lp * contract_size)
        size = round(min(float(raw_size), float(max_market), float(max_leverage_size)), 3)
        if size <= 0: return None

        # 🛡️ FORCED LEVERAGE SYNC
        try:
            await exchange.set_leverage(LEVERAGE, symbol)
        except Exception as le:
            log.warning("⚠️ Leverage set failed for %s: %s. Continuing with caution.", symbol, le)

        # Risk Check: Liquidation vs Stop Loss
        # Institutional Buffer: Entry * (1 - 1/Lev + 2.5% Safety Margin)
        liq_buffer = (1 / LEVERAGE) - 0.025 
        if signal["side"] == "buy":
            est_liq = lp * (1 - liq_buffer)
            if sl <= est_liq:
                log.warning("⚠️ RISK ALERT: %s Long SL (%.4f) is beyond safety Liq (%.4f). Skipping.", symbol, sl, est_liq)
                return None
        else: # Short
            est_liq = lp * (1 + liq_buffer)
            if sl >= est_liq:
                log.warning("⚠️ RISK ALERT: %s Short SL (%.4f) is beyond safety Liq (%.4f). Skipping.", symbol, sl, est_liq)
                return None

        log.info("🔔 SIGNAL on %s: %s | Entry: %.8f | SL: %.8f | TP: %.8f", symbol, signal["side"].upper(), lp, sl, tp)
        if DRY_RUN: return None

        # Integrated exchanges like Blofin
        limit_price = lp * 1.01 if signal["side"] == "buy" else lp * 0.99
        order_side = "buy" if signal["side"] == "buy" else "sell"
        params = {
            "marginMode": "isolated", 
            "positionSide": "net", 
            "stopLoss": {"triggerPrice": sl}, 
            "takeProfit": {"triggerPrice": tp}
        }
        await exchange.create_order(symbol, "limit", order_side, size, limit_price, params=params)
            
        log.info("✅ Order placed for %s on %s", symbol, exchange.id)
        return {"symbol": symbol.split("/")[0], "side": "BUY", "size": size, "entry": lp, "tp": tp, "sl": sl}
    except Exception as e:
        log.error("❌ Order failed for %s: %s", symbol, e)
        return None


async def process_user_on_symbol(user, symbol, signal):
    """
    Processes a single user's trade logic for a specific symbol.
    """
    try:
        # 💎 Institutional Gating
        is_prem = database.is_premium(user)
        sym_name = symbol.split("/")[0]
        
        # 🥈 Standard Tier Limits
        if not is_prem:
            if sym_name not in ["BTC", "ETH", "SOL", "XRP", "BNB"]:
                return
            risk_val = 0.01
        else:
            risk_val = user.get('risk_pct', 0.015)

        if sym_name not in user.get('enabled_symbols', []):
            return
        
        # Capital Allocation Override
        eq_type = user.get('custom_equity_type', 'all')
        eq_val = user.get('custom_equity_value')
        
        effective_equity = user.get('equity', 10000.0)
        if eq_type == 'amount' and eq_val is not None:
            effective_equity = min(float(eq_val), user.get('equity', 10000.0))
        elif eq_type == 'pct' and eq_val is not None:
            effective_equity = user.get('equity', 10000.0) * (float(eq_val) / 100.0)
        
        ex = get_exchange_client(user)
        try:
            norm_sym = normalize_symbol(symbol, ex.id)
            # Check existing positions
            pos = await ex.fetch_positions([norm_sym])
            if not any(float(p.get("contracts", 0) or 0) != 0 for p in pos):
                await place_order(ex, norm_sym, signal, effective_equity, risk_pct=risk_val)
        finally:
            await ex.close()
    except Exception as ue:
        log.error("User %s error on %s: %s", user['telegram_chat_id'], symbol, ue)


async def run():
    log.info("═"*60 + "\n  Multi-Exchange Metaverse Sherpa Engine (ASYNC) \n" + "═"*60)
    import database
    active_users = database.get_all_active_users()
    if not active_users:
        log.info("No active users found. Skipping pass.")
        return

    mdm = MarketDataManager()
    try:
        # 🕵️ Sync Position Status for all users first (Parallelized)
        async def sync_user_pos(user):
            try:
                ex = get_exchange_client(user)
                try:
                    pos = await ex.fetch_positions()
                    has_active = any(float(p.get("contracts", 0) or 0) != 0 for p in pos)
                    database.update_position_status(user['telegram_chat_id'], has_active)
                finally:
                    await ex.close()
            except Exception as e:
                log.error("Position sync failed for %s: %s", user['telegram_chat_id'], e)

        await asyncio.gather(*(sync_user_pos(u) for u in active_users))

        # Parallelize Market Data Fetching
        market_data_tasks = [mdm.fetch_ohlcv(sym, TIMEFRAME, limit=CANDLE_LIMIT) for sym in SYMBOLS]
        await asyncio.gather(*market_data_tasks)

        # Parallelize Signal Computation and User Processing by grouping users by strategy
        strategy_groups = {}
        for user in active_users:
            strat = user.get("strategy", "Mean Reversion Scalper")
            if strat not in strategy_groups:
                strategy_groups[strat] = []
            strategy_groups[strat].append(user)
            
        processing_tasks = []
        for strat_name, users in strategy_groups.items():
            for symbol in SYMBOLS:
                df = await mdm.fetch_ohlcv(symbol, TIMEFRAME)
                if df is not None:
                    signal = compute_signal(df, symbol.split("/")[0], strategy_name=strat_name)
                    if signal:
                        for user in users:
                            processing_tasks.append(process_user_on_symbol(user, symbol, signal))

        if processing_tasks:
            await asyncio.gather(*processing_tasks)
    finally:
        await mdm.close()
    log.info("═"*60 + "\n  Multi-Exchange Pass Complete \n" + "═"*60)


if __name__ == "__main__":
    asyncio.run(run())
