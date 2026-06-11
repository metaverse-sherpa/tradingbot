import os
import sys
import sqlite3
import asyncio
import logging
import requests
from datetime import datetime, timezone

# Add parent directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import database
import utils_gcp

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BroadcastMissedFreeSignals")

USER_DB_PATH = os.path.join(BASE_DIR, "data", "bot_users.db")
TELEGRAM_TOKEN = utils_gcp.get_secret("TELEGRAM_BOT_TOKEN")

async def send_telegram_message(chat_id, text, entities=None):
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not found in environment.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if entities:
        payload["entities"] = [
            {
                "type": e.type,
                "offset": e.offset,
                "length": e.length,
                **({"value": e.value} if getattr(e, "value", None) is not None else {}),
            }
            for e in entities
        ]
    else:
        payload["parse_mode"] = "Markdown"
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: requests.post(url, json=payload, timeout=10))
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")

async def main():
    logger.info("Starting public free signals broadcast recovery...")
    
    # 1. Fetch today's theoretical trades
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT symbol, entry_price, tp_price, sl_price, open_time 
            FROM TheoreticalTrades 
            WHERE strategy = 'Sherpa Velocity Pullback' AND status = 'open'
        """)
        theoretical_trades = c.fetchall()
        
    if not theoretical_trades:
        logger.info("No open theoretical trades found to broadcast.")
        return
        
    # 2. Get all target users for broadcasting
    all_targets = database.get_all_broadcast_targets()
    if not all_targets:
        logger.info("No broadcast targets found.")
        return
        
    logger.info(f"Broadcasting {len(theoretical_trades)} signals to {len(all_targets)} users.")
    
    from telegram import MessageEntity
    
    for t in theoretical_trades:
        sym = t['symbol']
        o_price = t['entry_price']
        tp_price = t['tp_price']
        sl_price = t['sl_price']
        open_time = t['open_time']
        
        # Calculate theoretical size info
        bal = 1000.0  # Default theoretical balance
        risk_amt = bal * 0.02
        price_diff = o_price - sl_price
        shares = risk_amt / price_diff if price_diff > 0 else 0
        position_size_usd = shares * o_price
        
        now_dt = datetime.fromtimestamp(open_time, tz=timezone.utc)
        
        entry_text_before = (
            "🏔️ *NEW FREE SIGNAL* 🏔️\n"
            "───────────────────────────────\n"
            f"Symbol:        `{sym}`\n"
            "Strategy:      Sherpa Velocity Pullback\n"
            "Direction:     LONG 📈\n"
            "Risk Setting:  2.0%\n\n"
            f"Free Entry: ${o_price:.2f}\n"
            f"Take Profit (TP): ${tp_price:.2f}\n"
            f"Stop Loss (SL):   ${sl_price:.2f}\n\n"
            f"Free Position Size: {shares:.4f} shares (~${position_size_usd:.2f} USD)\n"
            "───────────────────────────────\n"
            f"Current Free Balance: ${bal:,.2f} USD\n\n"
            "Signal time: "
        )
        placeholder = now_dt.strftime("%Y-%m-%d %H:%M UTC")
        entry_entity = MessageEntity(
            type=MessageEntity.DATE_TIME,
            offset=len(entry_text_before),
            length=len(placeholder),
            unix_time=now_dt,
        )
        entry_msg = entry_text_before + placeholder
        
        # Send Telegram message to all targets
        for target_id in all_targets:
            try:
                logger.info(f"Sending signal alert for {sym} to Telegram chat {target_id}...")
                await send_telegram_message(target_id, entry_msg, entities=[entry_entity])
            except Exception as b_err:
                logger.warning(f"Failed to send free signal broadcast to {target_id}: {b_err}")
                
        # Send Email alerts for entry
        try:
            from web_api.db_web import get_users_for_email_alerts
            from web_api.email_service import send_alert_email, get_signal_alert_html
            rt_users = get_users_for_email_alerts("realtime")
            if rt_users:
                subject = f"🛰️ New Alpha Signal: {sym} (LONG)"
                for ru in rt_users:
                    if ru.get("email"):
                        html_content = get_signal_alert_html(
                            symbol=sym,
                            side="LONG",
                            strategy="Sherpa Velocity Pullback",
                            entry=o_price,
                            tp=tp_price,
                            sl=sl_price,
                            is_premium_user=ru.get("is_premium_user", False)
                        )
                        send_alert_email(ru["email"], subject, html_content)
                logger.info(f"Email notifications sent for {sym}")
        except Exception as email_err:
            logger.error(f"Failed to dispatch entry email alerts for {sym}: {email_err}")
            
    logger.info("Public free signals broadcast recovery completed!")

if __name__ == "__main__":
    asyncio.run(main())
