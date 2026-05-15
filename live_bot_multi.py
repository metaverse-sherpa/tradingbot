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
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

SYMBOL_CONFIGS = {
    "BTC":  {"bb": 2.7, "atr": 6.0, "rr": 1.25, "adx": 25, "rsi": 30, "rvol": 1.5},
    "ETH":  {"bb": 2.7, "atr": 5.0, "rr": 1.25, "adx": 25, "rsi": 30, "rvol": 1.5},
    "SOL":  {"bb": 2.5, "atr": 4.0, "rr": 1.25, "adx": 25, "rsi": 30, "rvol": 1.5},
    "DOGE": {"bb": 2.5, "atr": 5.0, "rr": 1.25, "adx": 20, "rsi": 30, "rvol": 1.8, "long_only": True},
    "ADA":  {"bb": 2.7, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 35, "rvol": 1.5},
    "LINK": {"bb": 2.5, "atr": 6.0, "rr": 1.0,  "adx": 25, "rsi": 30, "rvol": 1.5},
    "DOT":  {"bb": 2.7, "atr": 4.0, "rr": 1.25, "adx": 25, "rsi": 30, "rvol": 1.5},
    "TON":  {"bb": 2.5, "atr": 4.0, "rr": 1.25, "adx": 25, "rsi": 30, "rvol": 1.5},
    "ZEC":  {"bb": 2.5, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30, "rvol": 1.5},
    "PEPE": {"bb": 2.5, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30, "rvol": 2.0},
    "BNB":  {"bb": 2.7, "atr": 4.0, "rr": 1.25, "adx": 25, "rsi": 30, "rvol": 1.5},
    "NEAR": {"bb": 2.7, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30, "rvol": 1.5},
    "SUI":  {"bb": 2.5, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30, "rvol": 1.5},
    "NOT":  {"bb": 2.5, "atr": 6.0, "rr": 1.25, "adx": 20, "rsi": 30, "rvol": 2.0},
    "TAO":  {"bb": 2.5, "atr": 5.0, "rr": 1.25, "adx": 20, "rsi": 30, "rvol": 1.5},
    "ONDO": {"bb": 2.7, "atr": 5.0, "rr": 1.25, "adx": 20, "rsi": 30, "rvol": 1.5},
    "ENA":  {"bb": 2.5, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30, "rvol": 1.5},
    "FET":  {"bb": 2.5, "atr": 6.0, "rr": 1.0,  "adx": 25, "rsi": 30, "rvol": 1.5},
    "WIF":  {"bb": 2.7, "atr": 5.0, "rr": 1.25, "adx": 25, "rsi": 30, "rvol": 2.0},
    "SHIB": {"bb": 2.7, "atr": 6.0, "rr": 1.25, "adx": 20, "rsi": 30, "rvol": 1.8},
}

SYMBOLS = [f"{s}/USDT:USDT" for s in SYMBOL_CONFIGS.keys()]
BAD_HOURS_UTC = {4, 12}
TIMEFRAME     = "15m"
LEVERAGE      = 20
RISK_PER_TRADE = 0.01
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
    if symbol_name not in SYMBOL_CONFIGS: return None
    cfg = SYMBOL_CONFIGS[symbol_name]
    
    strat = strategies.get_strategy(strategy_name)
    # 🏔️ Institutional Pass: Feed full symbol config into the momentum engine
    side = strat.check_signal(df, config=cfg)
    
    if not side:
        return None
        
    # ATR for SL calculation
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


def place_order(exchange, symbol, signal, equity, risk_pct=None):
    try:
        # Use user-specific risk or fallback to global default
        risk_val = (risk_pct / 100.0) if risk_pct is not None else RISK_PER_TRADE
        
        market = exchange.market(symbol)
        ticker = exchange.fetch_ticker(symbol)
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
            exchange.set_leverage(LEVERAGE, symbol)
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
        exchange.create_order(symbol, "limit", order_side, size, limit_price, params=params)
            
        log.info("✅ Order placed for %s on %s", symbol, exchange.id)
        return {"symbol": symbol.split("/")[0], "side": "BUY", "size": size, "entry": lp, "tp": tp, "sl": sl}
    except Exception as e:
        log.error("❌ Order failed for %s: %s", symbol, e)
        return None

def run():
    log.info("═"*60 + "\n  Multi-Exchange Metaverse Sherpa Engine \n" + "═"*60)
    import database
    active_users = database.get_all_active_users()
    if not active_users:
        log.info("No active users found. Skipping pass.")
        return

    # Use a shared public exchange for market data to save rate limits
    market_data_ex = ccxt.blofin() 
    market_data_ex.load_markets()
    
    # 🕵️ Sync Position Status for all users first
    for user in active_users:
        try:
            ex = get_exchange_client(user)
            # Fetch all open positions to update the "Panic Button" status
            pos = ex.fetch_positions()
            has_active = any(float(p.get("contracts", 0) or 0) != 0 for p in pos)
            database.update_position_status(user['telegram_chat_id'], has_active)
        except Exception as e:
            log.error("Position sync failed for %s: %s", user['telegram_chat_id'], e)

    errors = []

    for symbol in SYMBOLS:
        try:
            ohlcv = market_data_ex.fetch_ohlcv(symbol, TIMEFRAME, limit=CANDLE_LIMIT)
            df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
            
            # Compute signals for all strategies used by users
            # (In the future we can optimize by only computing strategies currently active)
            signal = compute_signal(df, symbol.split("/")[0])
            
            if signal:
                for user in active_users:
                    # 💎 Institutional Gating
                    is_prem = database.is_premium(user)
                    sym_name = symbol.split("/")[0]
                    
                    # 🥈 Standard Tier Limits
                    if not is_prem:
                        # 1. Basket Limit: Only top 5 "Safe" symbols
                        if sym_name not in ["BTC", "ETH", "SOL", "XRP", "BNB"]:
                            continue
                        # 2. Risk Limit: Force 1%
                        risk_val = 0.01
                    else:
                        # 💎 Premium Tier: Full settings
                        risk_val = user.get('risk_pct', 0.015)

                    if sym_name not in user.get('enabled_symbols', []):
                        continue
                    
                    try:
                        ex = get_exchange_client(user)
                        norm_sym = normalize_symbol(symbol, ex.id)
                        
                        # Check existing positions
                        pos = ex.fetch_positions([norm_sym])
                        if not any(float(p.get("contracts", 0) or 0) != 0 for p in pos):
                            place_order(ex, norm_sym, signal, user['equity'], risk_pct=risk_val)
                    except Exception as ue:
                        log.error("User %s error on %s: %s", user['telegram_chat_id'], symbol, ue)
                        
        except Exception as e:
            log.error("Global signal error for %s: %s", symbol, e)

    log.info("═"*60 + "\n  Multi-Exchange Pass Complete \n" + "═"*60)

if __name__ == "__main__":
    run()
