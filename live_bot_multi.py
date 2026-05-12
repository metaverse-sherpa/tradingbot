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

def create_exchange():
    return ccxt.blofin({
        "apiKey": os.getenv("BLOFIN_API_KEY"),
        "secret": os.getenv("BLOFIN_API_SECRET"),
        "password": os.getenv("BLOFIN_API_PASSWORD"),
        "options": {"defaultType": "swap"},
    })

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
    side = strat.check_signal(df)
    
    if not side:
        return None
        
    # Standardize output for the engine
    cfg = SYMBOL_CONFIGS[symbol_name]
    
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


def place_order(exchange, symbol, signal, equity):
    try:
        market = exchange.market(symbol)
        ticker = exchange.fetch_ticker(symbol)
        lp = ticker["last"]
        if abs(lp - signal["entry"]) / signal["entry"] > 0.01: return None
        sl_dist, rr = signal["sl_dist"], signal["rr"]
        sl, tp = lp - sl_dist, lp + (sl_dist * rr)
        contract_size = float(market.get('contractSize') or 1)
        if contract_size <= 0: contract_size = 1
        
        raw_size = (equity * RISK_PER_TRADE) / (sl_dist * contract_size)
        
        limits = market.get('limits', {})
        max_market = limits.get('market', {}).get('amount', {}).get('max')
        if max_market is None: 
            max_market = limits.get('amount', {}).get('max')
        if max_market is None:
            max_market = 999999999.0 # Safe fallback
            
        max_leverage_size = (equity * LEVERAGE) / (lp * contract_size)
        size = round(min(float(raw_size), float(max_market), float(max_leverage_size)), 3)
        if size <= 0: return None
        log.info("🔔 SIGNAL on %s: BUY | Entry: %.8f | SL: %.8f | TP: %.8f", symbol, lp, sl, tp)
        if DRY_RUN: return None
        try: exchange.set_leverage(LEVERAGE, symbol, params={"marginMode": "isolated"})
        except: pass
        try: exchange.set_position_mode(False, symbol)
        except: pass
        limit_price = lp * 1.01
        params = {"marginMode": "isolated", "positionSide": "net", "stopLoss": {"triggerPrice": sl}, "takeProfit": {"triggerPrice": tp}}
        exchange.create_order(symbol, "limit", "buy", size, limit_price, params=params)
        log.info("✅ Order placed for %s", symbol)
        return {"symbol": symbol.split("/")[0], "side": "BUY", "size": size, "entry": lp, "tp": tp, "sl": sl}
    except Exception as e:
        log.error("❌ Order failed for %s: %s", symbol, e)
        return None

def run():
    log.info("═"*60 + "\n  Multi-Symbol BB Scalper (Global API Fix) \n" + "═"*60)
    exchange = create_exchange()
    exchange.load_markets()
    errors, now = [], datetime.now(timezone.utc)
    try:
        balance = exchange.fetch_balance(params={"type": "futures"})
        equity = float(balance.get("USDT", {}).get("total", 0))
        log.info("── Pass Start | Equity: $%.2f ──", equity)
        trades_executed = []
        for symbol in SYMBOLS:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=CANDLE_LIMIT)
                df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                signal = compute_signal(df, symbol.split("/")[0])
                if signal:
                    pos = exchange.fetch_positions([symbol])
                    if not any(float(p.get("contracts", 0) or 0) != 0 for p in pos):
                        res = place_order(exchange, symbol, signal, equity)
                        if res: trades_executed.append(res)
            except Exception as e: 
                if "code" not in str(e): errors.append(f"{symbol}: {e}")
        
        # (README Update Removed)
        
        if trades_executed:
            sym_list = ", ".join([t['symbol'] for t in trades_executed])
            rows = [f"| {t['symbol']} | {t['side']} | {t['size']} | {t['entry']:.8f} | {t['tp']:.8f} | {t['sl']:.8f} |" for t in trades_executed]
            body = "### 📈 New Trades\n| Symbol | Side | Size | Entry | TP | SL |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n" + "\n".join(rows)
            create_github_issue(f"🚀 New Trades: {sym_list}", body)
        elif now.hour == 0 and now.minute < 6:
            if stats:
                body = f"### 📊 Daily Performance Recap\n\n* **Total Trades Opened:** {stats['opened']}\n* **Win Rate:** {stats['wr']:.1f}%\n* **Wins:** {stats['wins']} | **Losses:** {stats['losses']}\n* **All-Time PnL:** {stats['cum_pnl']:+.2f}%\n\nView the full history in the [repository README](https://github.com/{os.getenv('GITHUB_REPOSITORY')})."
                create_github_issue(f"📅 Daily Recap: {stats['cum_pnl']:+.2f}% PnL", body)
            else:
                create_github_issue("📅 Daily Recap", "Bot is running. Check README for stats.")
    except Exception as e: errors.append(f"Critical: {e}")
    finally:
        if errors: create_github_issue("🚨 Bot Error", "\n".join(errors))
        log.info("═"*60 + "\n  Pass Complete \n" + "═"*60)

if __name__ == "__main__":
    run()
