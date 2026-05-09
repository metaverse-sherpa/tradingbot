#!/usr/bin/env python3
"""
Multi-Symbol BB Scalper — Complete Edition
-------------------------------------------
- Persistent Tracking: Wins, Losses, and Total Trades Opened.
- Automated Reporting: Daily recaps and auto-assigned notifications.
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
ADX_UPPER_CAP = 35
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

def compute_signal(df, symbol_name):
    cfg = SYMBOL_CONFIGS[symbol_name]
    df["ema"] = df["close"].ewm(span=200, adjust=False).mean()
    df["bb_mid"] = df["close"].rolling(20).mean()
    std = df["close"].rolling(20).std()
    df["bb_bot"] = df["bb_mid"] - (cfg["bb"] * std)
    tr = pd.concat([df["high"] - df["low"], abs(df["high"] - df["close"].shift()), abs(df["low"] - df["close"].shift())], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    last = df.iloc[-2]
    if datetime.now(timezone.utc).hour in BAD_HOURS_UTC: return None
    if last["close"] > last["ema"] and last["close"] < last["bb_bot"] and rsi.iloc[-2] < cfg["rsi"]:
        return {"side": "buy", "entry": last["close"], "sl_dist": atr.iloc[-2] * cfg["atr"], "rr": cfg["rr"]}
    return None

def update_readme(equity, exchange, new_trades_count):
    try:
        with open("README.md", "r") as f: content = f.read()
        start_equity = float(re.search(r"STARTING_EQUITY: ([\d\.]+)", content).group(1))
        opened = int(re.search(r"ALL_TIME_OPENED: (\d+)", content).group(1))
        wins = int(re.search(r"ALL_TIME_WINS: (\d+)", content).group(1))
        losses = int(re.search(r"ALL_TIME_LOSSES: (\d+)", content).group(1))
        
        if start_equity <= 0: start_equity = equity
        opened += new_trades_count
        
        since = (int(time.time()) - 900) * 1000
        for symbol in SYMBOLS:
            try:
                trades = exchange.fetch_my_trades(symbol, since)
                for t in trades:
                    val = float(t.get("info", {}).get("realizedPnl", 0))
                    if val > 0: wins += 1
                    elif val < 0: losses += 1
            except: pass
        
        pnl_pct = ((equity - start_equity) / start_equity * 100) if start_equity > 0 else 0
        wr = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        perf_text = (f"| Total Trades | Wins | Losses | Win Rate | Total PnL (%) |\n| :--- | :--- | :--- | :--- | :--- |\n"
                     f"| {opened} | {wins} | {losses} | {wr:.1f}% | {pnl_pct:+.2f}% |\n\n"
                     f"**Last Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        
        content = re.sub(r"<!-- PERFORMANCE_START -->.*?<!-- PERFORMANCE_END -->", f"<!-- PERFORMANCE_START -->\n{perf_text}\n<!-- PERFORMANCE_END -->", content, flags=re.DOTALL)
        content = re.sub(r"STARTING_EQUITY: [\d\.]+", f"STARTING_EQUITY: {start_equity}", content)
        content = re.sub(r"ALL_TIME_OPENED: \d+", f"ALL_TIME_OPENED: {opened}", content)
        content = re.sub(r"ALL_TIME_WINS: \d+", f"ALL_TIME_WINS: {wins}", content)
        content = re.sub(r"ALL_TIME_LOSSES: \d+", f"ALL_TIME_LOSSES: {losses}", content)
        with open("README.md", "w") as f: f.write(content)
    except Exception as e: log.error("❌ README Error: %s", e)

def place_order(exchange, symbol, signal, equity):
    try:
        ticker = exchange.fetch_ticker(symbol)
        lp = ticker["last"]
        if abs(lp - signal["entry"]) / signal["entry"] > 0.01: return None
        sl_dist, rr = signal["sl_dist"], signal["rr"]
        sl, tp = lp - sl_dist, lp + (sl_dist * rr)
        size = round(min((equity * RISK_PER_TRADE) / sl_dist, (equity * LEVERAGE) / lp), 3)
        if size <= 0: return None
        log.info("🔔 SIGNAL on %s: BUY | Entry: %.4f | SL: %.4f | TP: %.4f", symbol, lp, sl, tp)
        if DRY_RUN: return None
        try: exchange.set_leverage(LEVERAGE, symbol, params={"marginMode": "isolated"})
        except: pass
        try: exchange.set_position_mode(False, symbol)
        except: pass
        params = {"marginMode": "isolated", "positionSide": "net", "stopLoss": {"triggerPrice": sl}, "takeProfit": {"triggerPrice": tp}}
        exchange.create_order(symbol, "market", "buy", size, params=params)
        log.info("✅ Order placed for %s", symbol)
        return {"symbol": symbol, "side": "BUY", "size": size, "entry": lp, "tp": tp, "sl": sl}
    except Exception as e:
        log.error("❌ Order failed for %s: %s", symbol, e)
        return None

def run():
    log.info("═"*60 + "\n  Multi-Symbol BB Scalper (Complete) \n" + "═"*60)
    exchange = create_exchange()
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
        
        if trades_executed or (now.hour == 0 and now.minute < 6):
            update_readme(equity, exchange, len(trades_executed))
            if trades_executed:
                rows = [f"| {t['symbol']} | {t['side']} | {t['size']} | {t['entry']:.4f} | {t['tp']:.4f} | {t['sl']:.4f} |" for t in trades_executed]
                body = "### 📈 New Trades\n| Symbol | Side | Size | Entry | TP | SL |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n" + "\n".join(rows)
                create_github_issue("🚀 New Trades", body)
            elif now.hour == 0:
                create_github_issue("📅 Daily Recap", "Bot is running. Stats updated in README.")
    except Exception as e: errors.append(f"Critical: {e}")
    finally:
        if errors: create_github_issue("🚨 Bot Error", "\n".join(errors))
        log.info("═"*60 + "\n  Pass Complete \n" + "═"*60)

if __name__ == "__main__":
    run()
