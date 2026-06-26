#!/usr/bin/env python3
"""
Send Test Daily Digest Emails
==============================
Run on the VPS to send test copies of the daily email to a target address.
Sends both a FREE and PREMIUM version using real data from the database.

Usage:
    python3 scripts/send_test_daily_email.py
    python3 scripts/send_test_daily_email.py --to someone@example.com
"""
import os
import sys
import time
import sqlite3
import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

# --- Path Setup (match bot/config.py conventions) ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import database
import requests
from bot.config import is_stock, CRYPTO_LEVERAGE

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_daily_email")

DEFAULT_RECIPIENT = "gilesasp@gmail.com"


def fetch_signals(days_back=1):
    """
    Fetch open + recently closed signals from TheoreticalTrades,
    exactly as daily_combined_email_engine does.
    """
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - (days_back * 24 * 60 * 60 * 1000)

    with database.db_session() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT * FROM TheoreticalTrades WHERE status = 'open' OR (close_time >= ? AND status != 'open')",
            (since_ms,),
        )
        rows = c.fetchall()

    signals = [dict(r) for r in rows]
    stock_signals = [s for s in signals if is_stock(s["symbol"])]
    crypto_signals = [s for s in signals if not is_stock(s["symbol"])]

    logger.info(f"Fetched {len(signals)} signals ({len(stock_signals)} stock, {len(crypto_signals)} crypto)")
    return stock_signals, crypto_signals, since_ms


def fetch_live_stock_prices(symbols):
    """Fetch live stock prices from Alpaca snapshots API."""
    import utils_gcp

    live_prices = {}
    if not symbols:
        return live_prices

    try:
        alpaca_key = utils_gcp.get_secret("ALPACA_API_KEY") or os.getenv("ALPACA_API_KEY")
        alpaca_secret = utils_gcp.get_secret("ALPACA_API_SECRET") or os.getenv("ALPACA_API_SECRET")
        if alpaca_key and alpaca_secret:
            headers = {"APCA-API-KEY-ID": alpaca_key, "APCA-API-SECRET-KEY": alpaca_secret}
            sym_str = ",".join(symbols)
            resp = requests.get(
                f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={sym_str}",
                headers=headers,
                timeout=5,
            )
            if resp.status_code == 200:
                for sym, snapshot in resp.json().items():
                    curr = snapshot.get("latestTrade", {}).get("p", 0.0)
                    daily_open = snapshot.get("dailyBar", {}).get("o", 0.0)
                    d_change = ((curr - daily_open) / daily_open) * 100 if daily_open > 0 else 0.0
                    live_prices[sym] = {"price": curr, "daily": d_change}
                logger.info(f"Fetched live stock prices for {len(live_prices)} symbols")
            else:
                logger.warning(f"Alpaca snapshots returned {resp.status_code}")
    except Exception as e:
        logger.error(f"Error fetching stock prices: {e}")

    return live_prices


def fetch_live_crypto_prices(symbols):
    """Fetch live crypto prices from Binance + Blofin, exactly as the engine does."""
    live_prices = {}
    if not symbols:
        return live_prices

    try:
        # Try Binance first
        r = requests.get("https://api.binance.us/api/v3/ticker/24hr", timeout=3)
        if r.status_code != 200:
            r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=3)
        if r.status_code == 200:
            binance_prices = {
                item["symbol"]: {"price": float(item["lastPrice"]), "daily": float(item["priceChangePercent"])}
                for item in r.json()
            }
            for sym in symbols:
                clean = sym.split(":")[0].replace("/", "")
                if clean in binance_prices:
                    live_prices[sym] = binance_prices[clean]

        # Fallback to Blofin for remaining symbols
        remaining = [sym for sym in symbols if sym not in live_prices]
        if remaining:
            resp = requests.get("https://openapi.blofin.com/api/v1/market/tickers?instType=SWAP", timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                price_map = {}
                for item in data:
                    curr = float(item.get("last", 0))
                    open24 = float(item.get("open24h", curr))
                    change = ((curr - open24) / open24) * 100 if open24 > 0 else 0.0
                    price_map[item["instId"]] = {"price": curr, "daily": change}
                for sym in remaining:
                    clean_sym = sym.split(":")[0].replace("/", "-")
                    if clean_sym in price_map:
                        live_prices[sym] = price_map[clean_sym]

        logger.info(f"Fetched live crypto prices for {len(live_prices)}/{len(symbols)} symbols")
    except Exception as e:
        logger.error(f"Error fetching crypto prices: {e}")

    return live_prices


def process_stock_signals(stock_signals, since_ms):
    """
    Process stock signals: compute PnL with live prices.
    Returns (stock_opened, stock_closed) lists ready for the HTML template.
    """
    stock_opened = [s for s in stock_signals if s["status"] == "open"]
    stock_closed = [s for s in stock_signals if (s.get("close_time") or 0) >= since_ms and s["status"] != "open"]

    stock_open_symbols = list(set([s["symbol"] for s in stock_opened]))
    live_prices = fetch_live_stock_prices(stock_open_symbols)

    for s in stock_opened:
        if s["status"] != "open":
            s["current_pnl_pct"] = s.get("pnl_pct", 0.0)
            s["target_tp_pct"] = 0.0
            s["daily_pnl_pct"] = 0.0
            continue

        sym = s["symbol"]
        entry_price = s["entry_price"]
        tp_price = s.get("tp_price") or 0.0
        price_info = live_prices.get(sym, {"price": entry_price, "daily": 0.0})
        curr_price = price_info["price"]
        daily_change = price_info["daily"]
        is_long = s["side"].upper() in ["BUY", "LONG"]

        if entry_price > 0:
            if is_long:
                pnl = ((curr_price - entry_price) / entry_price) * 100
                tp = ((tp_price - entry_price) / entry_price) * 100 if tp_price > 0 else 0.0
            else:
                pnl = ((entry_price - curr_price) / entry_price) * 100
                tp = ((entry_price - tp_price) / entry_price) * 100 if tp_price > 0 else 0.0
        else:
            pnl = 0.0
            tp = 0.0

        s["current_pnl_pct"] = pnl
        s["target_tp_pct"] = tp
        s["daily_pnl_pct"] = daily_change if is_long else -daily_change

    logger.info(f"Stock signals: {len(stock_opened)} open, {len(stock_closed)} closed")
    return stock_opened, stock_closed


def process_crypto_signals(crypto_signals, since_ms):
    """
    Process crypto signals: compute PnL with live prices and leverage.
    Returns (crypto_opened, crypto_closed) lists ready for the HTML template.
    """
    # Apply leverage to closed crypto signals (same as engine)
    for s in crypto_signals:
        if s["status"] != "open" and (s.get("close_time") or 0) >= since_ms:
            s["pnl_pct"] = s.get("pnl_pct", 0.0) * CRYPTO_LEVERAGE

    crypto_opened = [s for s in crypto_signals if s["status"] == "open"]
    crypto_closed = [s for s in crypto_signals if (s.get("close_time") or 0) >= since_ms and s["status"] != "open"]

    crypto_open_symbols = list(set([s["symbol"] for s in crypto_opened]))
    live_prices = fetch_live_crypto_prices(crypto_open_symbols)

    for s in crypto_opened:
        if s["status"] != "open":
            s["current_pnl_pct"] = s.get("pnl_pct", 0.0) * CRYPTO_LEVERAGE
            s["target_tp_pct"] = 0.0
            s["daily_pnl_pct"] = 0.0
            continue

        sym = s["symbol"]
        entry_price = s["entry_price"]
        tp_price = s.get("tp_price") or 0.0
        price_info = live_prices.get(sym, {"price": entry_price, "daily": 0.0})
        curr_price = price_info["price"]
        daily_change = price_info["daily"]
        is_long = s["side"].upper() in ["BUY", "LONG"]

        if entry_price > 0:
            if is_long:
                pnl = ((curr_price - entry_price) / entry_price) * 100
                tp = ((tp_price - entry_price) / entry_price) * 100 if tp_price > 0 else 0.0
            else:
                pnl = ((entry_price - curr_price) / entry_price) * 100
                tp = ((entry_price - tp_price) / entry_price) * 100 if tp_price > 0 else 0.0
        else:
            pnl = 0.0
            tp = 0.0

        pnl *= CRYPTO_LEVERAGE
        tp *= CRYPTO_LEVERAGE
        s["current_pnl_pct"] = pnl
        s["target_tp_pct"] = tp
        s["daily_pnl_pct"] = (daily_change * CRYPTO_LEVERAGE) if is_long else (-daily_change * CRYPTO_LEVERAGE)

    logger.info(f"Crypto signals: {len(crypto_opened)} open, {len(crypto_closed)} closed")
    return crypto_opened, crypto_closed


def main():
    parser = argparse.ArgumentParser(description="Send test daily digest emails with real data")
    parser.add_argument("--to", default=DEFAULT_RECIPIENT, help=f"Recipient email (default: {DEFAULT_RECIPIENT})")
    parser.add_argument("--days-back", type=int, default=1, help="How many days back to look for closed signals (default: 1)")
    args = parser.parse_args()

    tz = ZoneInfo("US/Eastern")
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")

    logger.info(f"🏔️ Preparing test daily digest emails for {args.to}")
    logger.info(f"   Date: {date_str} | Days back: {args.days_back}")

    # 1. Fetch signals from DB
    stock_signals, crypto_signals, since_ms = fetch_signals(days_back=args.days_back)

    if not stock_signals and not crypto_signals:
        logger.warning("⚠️ No signals found. Emails will show empty tables but will still be sent.")

    # 2. Process signals with live prices (creates separate copies for each email)
    import copy
    stock_signals_copy = copy.deepcopy(stock_signals)
    crypto_signals_copy = copy.deepcopy(crypto_signals)

    stock_opened, stock_closed = process_stock_signals(stock_signals, since_ms)
    crypto_opened, crypto_closed = process_crypto_signals(crypto_signals, since_ms)

    # Make a second copy for the second email (since processing mutates the dicts)
    stock_opened_2, stock_closed_2 = process_stock_signals(stock_signals_copy, since_ms)
    crypto_opened_2, crypto_closed_2 = process_crypto_signals(crypto_signals_copy, since_ms)

    # 3. Generate HTML and send
    from web_api.email_service import send_alert_email, get_combined_daily_summary_html

    # --- FREE version ---
    logger.info("📧 Generating FREE version...")
    html_free = get_combined_daily_summary_html(
        stock_opened, stock_closed,
        crypto_opened, crypto_closed,
        is_premium=False,
    )
    subject_free = f"🏔️ [TEST - FREE] Metaverse Sherpa Daily Digest - {date_str}"
    send_alert_email(args.to, subject_free, html_free)
    logger.info(f"✅ FREE version queued for {args.to}")

    # --- PREMIUM version ---
    logger.info("📧 Generating PREMIUM version...")
    html_premium = get_combined_daily_summary_html(
        stock_opened_2, stock_closed_2,
        crypto_opened_2, crypto_closed_2,
        is_premium=True,
    )
    subject_premium = f"🏔️ [TEST - PREMIUM] Metaverse Sherpa Daily Digest - {date_str}"
    send_alert_email(args.to, subject_premium, html_premium)
    logger.info(f"✅ PREMIUM version queued for {args.to}")

    # 4. Wait for the email worker thread to flush
    logger.info("⏳ Waiting for email queue to flush...")
    time.sleep(8)
    logger.info("🎉 Done! Check your inbox at %s", args.to)


if __name__ == "__main__":
    main()
