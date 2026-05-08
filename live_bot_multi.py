#!/usr/bin/env python3
"""
Multi-Symbol BB Scalper — Optimized 20-Symbol Basket
------------------------------------------------------
Monitors 20 liquid assets on Blofin perps with per-symbol optimized parameters.
Includes Full Optimization (Variant C):
  - ADX Upper Cap (35)
  - DOGE Longs-Only
  - Session Filter (Skip 04:00 & 12:00 UTC)

Risk: 1% per symbol | Leverage: 20x
"""

import os
import time
import logging
import requests
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

# Strategy parameters — Verified via 3-year portfolio backtest
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

# Construct Blofin symbol list
SYMBOLS = [f"{s}/USDT:USDT" for s in SYMBOL_CONFIGS.keys()]

ADX_UPPER_CAP  = 35
BAD_HOURS_UTC  = {4, 12}
TIMEFRAME      = "15m"
LEVERAGE       = 20
CANDLE_LIMIT   = 300
RISK_PER_TRADE = 0.01
POLL_SECONDS   = 60
DRY_RUN        = os.getenv("BLOFIN_DRY_RUN", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE = os.path.join("results", "live_log.txt")
os.makedirs("results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exchange & Indicators
# ---------------------------------------------------------------------------

def create_exchange() -> ccxt.blofin:
    exchange = ccxt.blofin({
        "apiKey":    os.getenv("BLOFIN_API_KEY"),
        "secret":    os.getenv("BLOFIN_API_SECRET"),
        "password":  os.getenv("BLOFIN_API_PASSWORD"),
        "options":   {"defaultType": "swap"},
    })
    
    log.info("🔴 PRODUCTION BOT STARTING — Connected to Blofin")

    if DRY_RUN:
        log.info("🛡️  DRY RUN enabled — signals logged, NO orders placed")

    return exchange

def calc_ema(s, p): return s.ewm(span=p, adjust=False).mean()
def calc_rsi(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(span=p, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(span=p, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))
def calc_atr(df, p=14):
    hl, hc, lc = df["high"]-df["low"], (df["high"]-df["close"].shift()).abs(), (df["low"]-df["close"].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(span=p, adjust=False).mean()
def calc_adx(df, p=14):
    pdm, ndm = df["high"].diff().clip(lower=0), (-df["low"].diff()).clip(lower=0)
    pdm, ndm = pdm.where(pdm > ndm, 0.0), ndm.where(ndm > pdm, 0.0)
    atr = calc_atr(df, p)
    pdi = 100 * pdm.ewm(span=p, adjust=False).mean() / atr
    ndi = 100 * ndm.ewm(span=p, adjust=False).mean() / atr
    dx = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
    return dx.ewm(span=p, adjust=False).mean()

def compute_signal(df: pd.DataFrame, symbol: str) -> dict | None:
    short_name = symbol.split("/")[0]
    cfg = SYMBOL_CONFIGS.get(short_name)
    if not cfg: return None

    # Filters
    now_utc = datetime.now(timezone.utc)
    if now_utc.hour in BAD_HOURS_UTC:
        log.debug("%s: skip (session hour filter)", symbol)
        return None

    d = df.copy()
    d["ema"] = calc_ema(d["close"], 200)
    d["rsi"] = calc_rsi(d["close"])
    d["atr"] = calc_atr(d)
    d["adx"] = calc_adx(d)
    mid = d["close"].rolling(20).mean()
    std = d["close"].rolling(20).std()
    d["bb_top"] = mid + cfg["bb"] * std
    d["bb_bot"] = mid - cfg["bb"] * std

    last = d.iloc[-2]
    if any(pd.isna(last[c]) for c in ["ema","rsi","atr","adx","bb_top","bb_bot"]):
        return None

    # ADX Filters
    if cfg["adx"] > 0 and last["adx"] < cfg["adx"]: return None
    if last["adx"] > ADX_UPPER_CAP:
        log.debug("%s: skip (ADX %.1f > %d cap)", symbol, last["adx"], ADX_UPPER_CAP)
        return None

    sl_dist = last["atr"] * cfg["atr"]
    rsi_u = 100 - cfg["rsi"]

    # LONG
    if (last["close"] > last["ema"] and last["close"] < last["bb_bot"] and last["rsi"] < cfg["rsi"]):
        return {"side": "buy", "entry": last["close"], "sl": last["close"] - sl_dist, "tp": last["close"] + sl_dist * cfg["rr"], "sl_dist": sl_dist}

    # SHORT
    if (last["close"] < last["ema"] and last["close"] > last["bb_top"] and last["rsi"] > rsi_u):
        if cfg.get("long_only"):
            log.debug("%s: skip short (long-only symbol)", symbol)
            return None
        return {"side": "sell", "entry": last["close"], "sl": last["close"] + sl_dist, "tp": last["close"] - sl_dist * cfg["rr"], "sl_dist": sl_dist}

    return None

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def create_github_issue(subject, body):
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY") # Automatically provided by GitHub Actions
    if not token or not repo:
        return

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {"title": subject, "body": body}

    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 201:
            log.info("🎫 GitHub Issue created for notification")
        else:
            log.error("❌ Failed to create GitHub Issue: %s", response.text)
    except Exception as e:
        log.error("❌ GitHub API Error: %s", e)

def place_order(exchange, symbol, signal, equity):
    side = signal["side"]
    risk_amount = equity * RISK_PER_TRADE
    size = risk_amount / signal["sl_dist"]
    max_size = (equity * LEVERAGE) / signal["entry"]
    size = round(min(size, max_size), 3)

    if size <= 0: return None

    log.info("🔔 SIGNAL on %s: %s | Size: %.4f | SL: %.4f | TP: %.4f", symbol, side.upper(), size, signal["sl"], signal["tp"])
    if DRY_RUN:
        log.info("🛡️  DRY RUN — order NOT placed.")
        return None

    try:
        exchange.create_order(symbol=symbol, type="market", side=side, amount=size,
            params={"marginMode": "cross", "positionSide": "net", "takeProfitPrice": signal["tp"], "stopLossPrice": signal["sl"]})
        log.info("✅ Order placed for %s", symbol)
        
        return {
            "symbol": symbol,
            "side": side.upper(),
            "size": size,
            "entry": signal["entry"],
            "sl": signal["sl"],
            "tp": signal["tp"]
        }
    except Exception as e:
        log.error("❌ Order failed for %s: %s", symbol, e)
        return None

def run():
    log.info("═"*60 + "\n  Multi-Symbol BB Scalper (One-Shot Mode) \n" + "═"*60)
    exchange = create_exchange()
    
    # Pre-set leverage
    for sym in SYMBOLS:
        try:
            exchange.set_leverage(LEVERAGE, sym, params={"marginMode": "cross"})
        except: pass

    try:
        balance = exchange.fetch_balance(params={"type": "futures"})
        equity = float(balance.get("USDT", {}).get("total", 0))
        log.info("── Pass Start | Equity: $%.2f | %s ──", equity, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        
        trades_executed = []
        if equity > 1.0:
            for symbol in SYMBOLS:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=CANDLE_LIMIT)
                    df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                    signal = compute_signal(df, symbol)
                    if signal:
                        pos = exchange.fetch_positions([symbol])
                        if not any(float(p.get("contracts", 0) or 0) != 0 for p in pos):
                            trade_res = place_order(exchange, symbol, signal, equity)
                            if trade_res:
                                trades_executed.append(trade_res)
                except Exception as e:
                    log.error("%s Error: %s", symbol, e)
            
            # If trades were made, send a single summary issue
            if trades_executed:
                count = len(trades_executed)
                subject = f"🚀 {count} New Trade{'s' if count > 1 else ''} Opened"
                
                rows = []
                for t in trades_executed:
                    rows.append(f"| {t['symbol']} | {t['side']} | {t['size']} | {t['entry']:.4f} | {t['tp']:.4f} | {t['sl']:.4f} |")
                
                body = (f"### 📈 Execution Summary\n\n"
                        f"| Symbol | Side | Size | Entry | TP | SL |\n"
                        f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                        + "\n".join(rows) + 
                        f"\n\n**Time:** {datetime.now(timezone.utc)}")
                
                create_github_issue(subject, body)
        else:
            log.warning("Equity too low ($%.2f). Skip trading.", equity)

    except Exception as e:
        log.error("Execution Error: %s", e)

    log.info("═"*60 + "\n  Pass Complete \n" + "═"*60)

if __name__ == "__main__":
    run()
