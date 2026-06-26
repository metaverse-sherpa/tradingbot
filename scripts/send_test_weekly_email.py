#!/usr/bin/env python3
"""
Send Test Weekly Audit Emails
==============================
Run on the VPS to send test copies of the weekly email to a target address.
Sends both a FREE and PREMIUM version using real data from the database.

For the premium version, looks up the specified premium account (by email)
to pull real portfolio stats and open trades from their connected exchanges.

Usage:
    source venv/bin/activate
    python3 scripts/send_test_weekly_email.py
    python3 scripts/send_test_weekly_email.py --to someone@example.com --premium-account metaversesherpa@gmail.com
"""
import os
import sys
import time
import asyncio
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
from bot.config import is_stock

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_weekly_email")

DEFAULT_RECIPIENT = "gilesasp@gmail.com"
DEFAULT_PREMIUM_ACCOUNT = "metaversesherpa@gmail.com"


async def fetch_premium_data(premium_email):
    """
    Look up the premium account by email and fetch real portfolio
    stats and open trades from their connected exchanges.
    Returns (has_stock, stock_portfolio, stock_trades, has_crypto, crypto_portfolio, crypto_trades).
    """
    from web_api.db_web import get_web_user_by_email
    from bot.engines.system import (
        fetch_weekly_stock_stats,
        fetch_premium_crypto_stats,
        fetch_premium_open_trades,
    )

    web_user = get_web_user_by_email(premium_email)
    if not web_user:
        logger.error(f"❌ Could not find WebUser with email: {premium_email}")
        return False, None, None, False, None, None

    tg_id = web_user.get("telegram_chat_id")
    logger.info(f"Found WebUser id={web_user.get('id')}, telegram_chat_id={tg_id}")

    tg_user = database.get_user(tg_id) if tg_id else None
    if not tg_user:
        logger.error(f"❌ Could not find telegram User for chat_id: {tg_id}")
        return False, None, None, False, None, None

    # Determine which exchanges are linked
    has_stock = bool(tg_user.get("alpaca_api_key") and tg_user.get("alpaca_api_secret"))
    has_crypto = bool(tg_user.get("api_key") and tg_user.get("api_secret"))

    stock_portfolio = None
    stock_trades = None
    crypto_portfolio = None
    crypto_trades = None

    if has_stock:
        logger.info("📈 Fetching stock portfolio stats...")
        stock_portfolio = await fetch_weekly_stock_stats(tg_user)
        logger.info(f"   Stock equity: ${stock_portfolio.get('equity', 0):,.2f}, weekly PnL: {stock_portfolio.get('weekly_pnl_pct', 0):+.2f}%")
        stock_trades = await fetch_premium_open_trades(tg_user, "stock")
        logger.info(f"   Stock open trades: {len(stock_trades)}")
    else:
        logger.info("📈 No stock exchange linked for this account")

    if has_crypto:
        logger.info("₿ Fetching crypto portfolio stats...")
        crypto_portfolio = await fetch_premium_crypto_stats(tg_user)
        logger.info(f"   Crypto equity: ${crypto_portfolio.get('equity', 0):,.2f}, weekly PnL: {crypto_portfolio.get('weekly_pnl_pct', 0):+.2f}%")
        crypto_trades = await fetch_premium_open_trades(tg_user, "crypto")
        logger.info(f"   Crypto open trades: {len(crypto_trades)}")
    else:
        logger.info("₿ No crypto exchange linked for this account")

    return has_stock, stock_portfolio, stock_trades, has_crypto, crypto_portfolio, crypto_trades


async def main_async(args):
    tz = ZoneInfo("US/Eastern")
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")

    logger.info(f"🏔️ Preparing test weekly audit emails for {args.to}")
    logger.info(f"   Date: {date_str}")
    logger.info(f"   Premium account: {args.premium_account}")

    # Fetch hypothetical strategy stats (used for free version)
    stock_hypothetical = database.get_theoretical_stats_by_strategy("Sherpa Velocity Pullback")
    crypto_hypothetical = database.get_theoretical_stats_by_strategy("Valkyrie Elite Scalper")
    logger.info(f"Stock hypothetical: {stock_hypothetical}")
    logger.info(f"Crypto hypothetical: {crypto_hypothetical}")

    # Fetch real premium data
    has_stock, stock_portfolio, stock_trades, has_crypto, crypto_portfolio, crypto_trades = \
        await fetch_premium_data(args.premium_account)

    from web_api.email_service import send_alert_email, get_combined_weekly_summary_html

    # --- FREE version (hypothetical stats, no exchange data) ---
    logger.info("📧 Generating FREE version...")
    html_free = get_combined_weekly_summary_html(
        is_premium=False,
        has_stock_exchange=False,
        stock_portfolio_data=None,
        stock_open_trades=None,
        stock_hypothetical_data=stock_hypothetical,
        has_crypto_exchange=False,
        crypto_portfolio_data=None,
        crypto_open_trades=None,
        crypto_hypothetical_data=crypto_hypothetical,
    )
    subject_free = f"🏔️ [TEST - FREE] Metaverse Sherpa Weekly Audit - {date_str}"
    send_alert_email(args.to, subject_free, html_free)
    logger.info(f"✅ FREE version queued for {args.to}")

    # --- PREMIUM version (real exchange data from the specified account) ---
    logger.info("📧 Generating PREMIUM version...")
    html_premium = get_combined_weekly_summary_html(
        is_premium=True,
        has_stock_exchange=has_stock,
        stock_portfolio_data=stock_portfolio,
        stock_open_trades=stock_trades,
        stock_hypothetical_data=stock_hypothetical,
        has_crypto_exchange=has_crypto,
        crypto_portfolio_data=crypto_portfolio,
        crypto_open_trades=crypto_trades,
        crypto_hypothetical_data=crypto_hypothetical,
    )
    subject_premium = f"🏔️ [TEST - PREMIUM] Metaverse Sherpa Weekly Audit - {date_str}"
    send_alert_email(args.to, subject_premium, html_premium)
    logger.info(f"✅ PREMIUM version queued for {args.to}")

    # --- PREMIUM (No Exchange) version ---
    logger.info("📧 Generating PREMIUM (No Exchange) version...")
    html_premium_no_exch = get_combined_weekly_summary_html(
        is_premium=True,
        has_stock_exchange=False,
        stock_portfolio_data=None,
        stock_open_trades=None,
        stock_hypothetical_data=stock_hypothetical,
        has_crypto_exchange=False,
        crypto_portfolio_data=None,
        crypto_open_trades=None,
        crypto_hypothetical_data=crypto_hypothetical,
    )
    subject_no_exch = f"🏔️ [TEST - PREMIUM NO EXCHANGE] Metaverse Sherpa Weekly Audit - {date_str}"
    send_alert_email(args.to, subject_no_exch, html_premium_no_exch)
    logger.info(f"✅ PREMIUM (No Exchange) version queued for {args.to}")

    # Wait for the email worker thread to flush
    logger.info("⏳ Waiting for email queue to flush...")
    time.sleep(8)
    logger.info("🎉 Done! Check your inbox at %s", args.to)


def main():
    parser = argparse.ArgumentParser(description="Send test weekly audit emails with real data")
    parser.add_argument("--to", default=DEFAULT_RECIPIENT, help=f"Recipient email (default: {DEFAULT_RECIPIENT})")
    parser.add_argument(
        "--premium-account",
        default=DEFAULT_PREMIUM_ACCOUNT,
        help=f"Email of the premium account to pull real portfolio data from (default: {DEFAULT_PREMIUM_ACCOUNT})",
    )
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
