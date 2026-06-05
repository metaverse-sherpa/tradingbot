import os
import sys
import sqlite3
import asyncio
import logging
import time
import requests
from datetime import datetime, timezone

# Add parent directory to sys.path so we can import database and web_api modules
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
logger = logging.getLogger("RecoverMissedTrades")

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
        # entities is a list of MessageEntity objects — serialise to dicts for the raw HTTP call
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
    logger.info("Starting Alpaca Trades Recovery Process...")
    
    # 1. Fetch the open theoretical trades for Sherpa Velocity Pullback
    # (since the engine opened them but the real trader failed)
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
        logger.info("No open theoretical trades found to recover.")
        return
        
    logger.info(f"Found {len(theoretical_trades)} theoretical trades to process.")
    for t in theoretical_trades:
        logger.info(f"  - Symbol: {t['symbol']}, Entry: {t['entry_price']}, SL: {t['sl_price']}, TP: {t['tp_price']}")
        
    # 2. Get all active Alpaca users
    with sqlite3.connect(USER_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT telegram_chat_id 
            FROM Users 
            WHERE is_active = 1 
              AND alpaca_api_key IS NOT NULL 
              AND alpaca_api_key != ''
        """)
        user_rows = c.fetchall()
        
    if not user_rows:
        logger.info("No active Alpaca users found.")
        return
        
    logger.info(f"Found {len(user_rows)} active Alpaca users.")
    
    for r in user_rows:
        chat_id = r['telegram_chat_id']
        user = database.get_user(chat_id)
        if not user or user.get("active_stock_strategy") != "Sherpa Velocity Pullback":
            continue
            
        logger.info(f"Processing recovery for user chat_id={chat_id}...")
        
        # Fetch current positions on Alpaca to avoid duplication
        try:
            positions = await database.make_alpaca_request_async(user, "GET", "/v2/positions")
            active_positions = {p['symbol']: p for p in positions if float(p.get("qty", 0)) != 0}
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca positions for user {chat_id}: {e}")
            continue
            
        for t in theoretical_trades:
            sym = t['symbol']
            o_price = t['entry_price']
            tp_price = t['tp_price']
            sl_price = t['sl_price']
            
            # Check if user already has an active trade for this symbol in local DB
            with sqlite3.connect(USER_DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT 1 FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND symbol = ? AND status = 'open'", (chat_id, sym))
                local_trade_exists = c.fetchone()
                
            if sym in active_positions or local_trade_exists:
                logger.info(f"User {chat_id} already has an active position/trade for {sym}. Skipping.")
                continue
                
            try:
                account = await database.make_alpaca_request_async(user, "GET", "/v2/account")
                equity = float(account.get("equity", 0) or account.get("portfolio_value", 0))
                
                user_risk = float(user.get('stock_risk_pct', 2.0)) / 100.0
                risk_amt = equity * user_risk
                
                # Sizing quantity: risk_amt / (3.0 * atr)
                # entry_price - sl_price = 3.0 * atr
                price_diff = o_price - sl_price
                if price_diff <= 0:
                    logger.error(f"Invalid price diff for {sym}: entry_price={o_price}, sl_price={sl_price}")
                    continue
                    
                qty = risk_amt / price_diff
                qty = round(qty, 4)
                
                if qty <= 0:
                    logger.warning(f"Sizing quantity is 0 for {sym} (Chat ID: {chat_id}). Risk amount ${risk_amt:.2f} is too small.")
                    continue
                    
                order_payload = {
                    "symbol": sym,
                    "qty": str(qty),
                    "side": "buy",
                    "type": "market",
                    "time_in_force": "day"
                }
                
                logger.info(f"Submitting recovery market order for user {chat_id} symbol {sym}: {order_payload}")
                res = await database.make_alpaca_request_async(user, "POST", "/v2/orders", json_data=order_payload)
                
                # Store in local tracking DB
                open_ts = int(time.time() * 1000)
                database.add_alpaca_active_trade(
                    chat_id=chat_id,
                    symbol=sym,
                    qty=qty,
                    entry_price=o_price,
                    tp_price=tp_price,
                    sl_price=sl_price,
                    open_time=open_ts
                )
                logger.info(f"Successfully created active trade in local DB for {sym}")
                
                # Send Telegram notification
                from telegram import MessageEntity
                now_ts = int(time.time())
                now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
                buy_text_before = (
                    "🦙 *Alpaca Stock Strategy: Buy Signal Triggered* (Recovered) 🦙\n\n"
                    f"Entered **{sym}** LONG at today's open.\n"
                    f"• Symbol: `{sym}`\n"
                    f"• Qty: `{qty}` shares\n"
                    f"• Entry Price: `${o_price:.2f}`\n"
                    f"• Take Profit: `${tp_price:.2f}`\n"
                    f"• Stop Loss: `${sl_price:.2f}`\n"
                    f"• Risk Allocated: `${risk_amt:.2f}` ({user.get('stock_risk_pct', 2.0)}% of equity)\n\n"
                    "Signal time: "
                )
                placeholder = now_dt.strftime("%Y-%m-%d %H:%M UTC")
                buy_entity = MessageEntity(
                    type=MessageEntity.DATE_TIME,
                    offset=len(buy_text_before),
                    length=len(placeholder),
                    unix_time=now_dt,
                )
                buy_msg = buy_text_before + placeholder
                await send_telegram_message(chat_id, buy_msg, entities=[buy_entity])
                
                # Send Email Alert if enabled
                with sqlite3.connect(USER_DB_PATH) as conn:
                    c = conn.cursor()
                    c.execute("SELECT email, email_notifications FROM WebUsers WHERE telegram_chat_id = ?", (chat_id,))
                    web_user_row = c.fetchone()
                    
                if web_user_row and web_user_row[0] and web_user_row[1] == 1:
                    user_email = web_user_row[0]
                    from web_api.email_service import send_alert_email, get_signal_alert_html
                    html_content = get_signal_alert_html(
                        symbol=sym,
                        side="LONG",
                        strategy="Sherpa Velocity Pullback",
                        entry=o_price,
                        tp=tp_price,
                        sl=sl_price,
                        resolution="open",
                        is_premium_user=True
                    )
                    subject = f"🔔 BUY SIGNAL: {sym} LONG at ${o_price:.2f}"
                    send_alert_email(user_email, subject, html_content)
                    logger.info(f"Email dispatched to {user_email}")
                    
            except requests.exceptions.HTTPError as he:
                resp_text = he.response.text if he.response is not None else "No response body"
                logger.error(f"Failed to execute recovery trade for user {chat_id} symbol {sym}: {he} - Response: {resp_text}")
                await send_telegram_message(chat_id, f"⚠️ *Alpaca Recovery Alert*: Buy signal for {sym} failed to execute during recovery: {he} ({resp_text})")
            except Exception as e:
                logger.error(f"Failed to execute recovery trade for user {chat_id} symbol {sym}: {e}")
                await send_telegram_message(chat_id, f"⚠️ *Alpaca Recovery Alert*: Buy signal for {sym} failed to execute during recovery: {e}")

if __name__ == "__main__":
    asyncio.run(main())
