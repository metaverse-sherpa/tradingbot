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

def update_readme(equity, exchange, new_trades_count):
    try:
        with open("README.md", "r") as f: content = f.read()
        
        start_equity = float(re.search(r"STARTING_EQUITY: ([\d\.]+)", content).group(1))
        opened = int(re.search(r"ALL_TIME_OPENED: (\d+)", content).group(1))
        wins = int(re.search(r"ALL_TIME_WINS: (\d+)", content).group(1))
        losses = int(re.search(r"ALL_TIME_LOSSES: (\d+)", content).group(1))
        cum_pnl = float(re.search(r"ALL_TIME_CUMULATIVE_PNL: ([\-\d\.]+)", content).group(1))
        last_ts = int(re.search(r"LAST_FETCH_TIMESTAMP: (\d+)", content).group(1))
        
        if start_equity <= 0: start_equity = equity
        # If timestamp is old/missing, look back 48h
        if last_ts < (time.time() - 172800) * 1000:
            last_ts = int((time.time() - 172800) * 1000)
            log.info("⏰ Performing a 48-hour history catch-up...")
        
        opened += new_trades_count
        now_ts = int(time.time() * 1000)
        
        # 2. Fetch Position History via Trades
        for symbol in SYMBOLS:
            try:
                trades = exchange.fetch_my_trades(symbol, last_ts)
                for t in trades:
                    if t['timestamp'] <= last_ts: continue
                    
                    info = t.get("info", {})
                    # Blofin specifically uses 'fillPnl' to report gross profit on exit fills
                    gross_pnl = float(info.get("fillPnl") or 0)
                    
                    if gross_pnl != 0:
                        # Estimate round-trip fee by doubling the exit fee
                        fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                        net_pnl = gross_pnl - (fee * 2)
                        
                        # Calculate ROE exactly like Blofin UI (Net PnL / Initial Margin)
                        try:
                            market = exchange.market(symbol)
                            contract_size = float(market.get('contractSize', 1))
                            price = float(t['price'])
                            size = float(t['amount'])
                            initial_margin = (price * size * contract_size) / LEVERAGE
                            roe_pct = (net_pnl / initial_margin) * 100 if initial_margin > 0 else 0
                        except:
                            roe_pct = 0
                            
                        cum_pnl += net_pnl # Add actual USDT profit, not the leveraged ROE %
                        if net_pnl > 0: wins += 1
                        else: losses += 1
                        log.info("📊 Found closed trade: %s | Net PnL: $%.2f | Blofin ROE: %.2f%%", symbol, net_pnl, roe_pct)
            except Exception as e:
                log.debug("⚠️ Trade fetch failed for %s: %s", symbol, e)
        
        # 3. Update Table
        wr = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        account_pnl_pct = (cum_pnl / start_equity) * 100 if start_equity > 0 else 0
        
        perf_text = (f"| Total Trades | Wins | Losses | Win Rate | Total PnL (%) |\n| :--- | :--- | :--- | :--- | :--- |\n"
                     f"| {opened} | {wins} | {losses} | {wr:.1f}% | {account_pnl_pct:+.2f}% |\n\n"
                     f"**Last Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        
        content = re.sub(r"<!-- PERFORMANCE_START -->.*?<!-- PERFORMANCE_END -->", f"<!-- PERFORMANCE_START -->\n{perf_text}\n<!-- PERFORMANCE_END -->", content, flags=re.DOTALL)
        
        # 4. Save Back
        content = re.sub(r"STARTING_EQUITY: [\d\.]+", f"STARTING_EQUITY: {start_equity}", content)
        content = re.sub(r"ALL_TIME_OPENED: \d+", f"ALL_TIME_OPENED: {opened}", content)
        content = re.sub(r"ALL_TIME_WINS: \d+", f"ALL_TIME_WINS: {wins}", content)
        content = re.sub(r"ALL_TIME_LOSSES: \d+", f"ALL_TIME_LOSSES: {losses}", content)
        content = re.sub(r"ALL_TIME_CUMULATIVE_PNL: [\-\d\.]+", f"ALL_TIME_CUMULATIVE_PNL: {cum_pnl}", content)
        content = re.sub(r"LAST_FETCH_TIMESTAMP: \d+", f"LAST_FETCH_TIMESTAMP: {now_ts}", content)
        
        with open("README.md", "w") as f: f.write(content)
        log.info("📝 README.md updated. Wins: %d, Losses: %d, Account PnL: %.2f%%", wins, losses, account_pnl_pct)
        
        # Return stats so the main loop can use them for emails
        return {"opened": opened, "wins": wins, "losses": losses, "wr": wr, "account_pnl_pct": account_pnl_pct}
    except Exception as e: 
        log.error("❌ README Error: %s", e)
        return None

def place_order(exchange, symbol, signal, equity):
    try:
        market = exchange.market(symbol)
        ticker = exchange.fetch_ticker(symbol)
        lp = ticker["last"]
        if abs(lp - signal["entry"]) / signal["entry"] > 0.01: return None
        sl_dist, rr = signal["sl_dist"], signal["rr"]
        sl, tp = lp - sl_dist, lp + (sl_dist * rr)
        contract_size = market.get('contractSize', 1)
        if contract_size <= 0: contract_size = 1
        raw_size = (equity * RISK_PER_TRADE) / (sl_dist * contract_size)
        limits = market.get('limits', {})
        max_market = limits.get('market', {}).get('amount', {}).get('max')
        if max_market is None: max_market = limits.get('amount', {}).get('max', float('inf'))
        max_leverage_size = (equity * LEVERAGE) / (lp * contract_size)
        size = round(min(raw_size, max_market, max_leverage_size), 3)
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
        
        stats = update_readme(equity, exchange, len(trades_executed))
        
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
