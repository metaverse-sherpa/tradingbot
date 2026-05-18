import os
import sys
import time
import asyncio
from dotenv import load_dotenv

# Ensure projects directory is in path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path.append(project_root)

load_dotenv()

import database
import live_bot_multi
import charting
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

# Resolve super admin id
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))

def get_nav_buttons(has_open=False, is_admin=False):
    """Duplicates navigation helper for inline keyboards."""
    from telegram_bot import get_nav_buttons as t_nav
    return t_nav(has_open, is_admin)

async def main():
    print("🏔️ Starting manual Forward Test alert trigger script...")
    
    # 1. Initialize DB and gather targets
    database.init_db()
    all_targets = database.get_all_broadcast_targets()
    if not all_targets:
        print("❌ No registered users found in the bot users database!")
        print("💡 Please start your bot and run /start in Telegram first to register your user.")
        return
        
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("❌ TELEGRAM_TOKEN not found in environment!")
        return
        
    bot = Bot(token=token)
    print(f"📡 Found {len(all_targets)} registered target chat(s) to receive alerts.")
    
    # 2. Setup mock trade params
    symbol = "SOL/USDT"
    strategy_name = "Mean Reversion Scalper"
    entry = 120.50
    tp = 135.00
    sl = 110.00
    side = "buy"
    open_ts = int(time.time() * 1000)
    
    # 3. Size and insert theoretical trade
    sim_balance = database.get_theoretical_balance()
    risk_val = 0.015
    sl_dist = abs(entry - sl)
    position_size_usd = (sim_balance * risk_val) / (sl_dist / entry)
    position_size_units = position_size_usd / entry
    
    # Clean previous mock trades on SOL/USDT to avoid state overlap
    open_trades = database.get_open_theoretical_trades()
    for t in open_trades:
        if t['symbol'] == symbol:
            database.close_theoretical_trade(t['id'], entry, open_ts, "cancelled", 0.0, 0.0, 0.0)
            
    database.add_theoretical_trade(
        symbol=symbol,
        strategy=strategy_name,
        side=side,
        entry_price=entry,
        tp_price=tp,
        sl_price=sl,
        open_time=open_ts,
        position_size=position_size_units
    )
    print("📝 Opened mock simulated trade SOL/USDT in database.")
    
    # 4. Generate visual chart overlay using public market feed
    print("📊 Generating simulated signal chart...")
    mdm = live_bot_multi.MarketDataManager()
    df_chart = await mdm.fetch_ohlcv(symbol, timeframe='15m')
    await mdm.close()
    
    chart_file = None
    try:
        chart_file = await asyncio.to_thread(
            charting.generate_trade_chart,
            symbol,
            df_chart,
            entry,
            tp,
            sl,
            "LONG",
            open_ts=open_ts
        )
        print(f"🎨 Visual chart generated successfully: {chart_file}")
    except Exception as e:
        print(f"⚠️ Chart generation failed (falling back to text-only alert): {e}")

    # 5. Broadcast simulated entry alert
    entry_msg = (
        f"🏔️ *NEW SIMULATED SIGNAL!* (Forward Test)\n"
        f"🤖 *Strategy:* `{strategy_name}`\n\n"
        f"Symbol: *{symbol}*\n"
        f"Direction: *LONG 📈*\n"
        f"Risk Setting: `1.5%`\n"
        f"Simulated Entry: `{entry:.8f}`\n"
        f"Take Profit (TP): `{tp:.8f}`\n"
        f"Stop Loss (SL): `{sl:.8f}`\n\n"
        f"Simulated Position Size: `{position_size_units:.4f}` units (~${position_size_usd:.2f} USD)\n"
        f"Current Simulated Balance: *${sim_balance:,.2f} USDT*"
    )
    
    print("📣 Broadcasting Entry alert to Telegram...")
    for target_id in all_targets:
        try:
            is_adm = (target_id == SUPER_ADMIN_ID)
            u = database.get_user(target_id)
            if u:
                is_adm = (target_id == SUPER_ADMIN_ID or u.get('is_admin')) and not u.get('undercover_mode')
            kb = get_nav_buttons(is_admin=is_adm)
            
            if chart_file and os.path.exists(chart_file):
                with open(chart_file, 'rb') as photo:
                    await bot.send_photo(
                        chat_id=target_id,
                        photo=photo,
                        caption=entry_msg,
                        reply_markup=InlineKeyboardMarkup(kb),
                        parse_mode="Markdown"
                    )
            else:
                await bot.send_message(
                    chat_id=target_id,
                    text=entry_msg,
                    reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode="Markdown"
                )
        except Exception as e:
            print(f"⚠️ Failed send to {target_id}: {e}")

    # 6. Sleep for 8 seconds to let user view entry
    print("⏳ Sleeping 8 seconds before triggering simulated Take Profit (TP)...")
    await asyncio.sleep(8)
    
    # 7. Settle theoretical trade (TP win)
    close_time = int(time.time() * 1000)
    pnl_raw = tp - entry
    pnl_pct = (pnl_raw / entry) * 100
    pnl_usdt = position_size_units * pnl_raw
    new_bal = sim_balance + pnl_usdt
    
    database.update_theoretical_balance(new_bal)
    
    open_trades = database.get_open_theoretical_trades()
    mock_trade_id = [t['id'] for t in open_trades if t['symbol'] == symbol][-1]
    database.close_theoretical_trade(mock_trade_id, tp, close_time, "tp", pnl_raw, pnl_pct, pnl_usdt)
    print("📝 Settled mock trade inside database as Take Profit (TP).")
    
    # 8. Broadcast simulated exit resolution alert
    exit_msg = (
        f"🔔 *SIMULATED TRADE CLOSED!* (Forward Test)\n"
        f"🏔️ _Global strategy tracker resolution_\n\n"
        f"Symbol: *{symbol}*\n"
        f"Direction: *LONG 📈*\n"
        f"Exit Trigger: *TAKE PROFIT (TP)*\n\n"
        f"Entry Price: `{entry:.8f}`\n"
        f"Exit Price: `{tp:.8f}`\n"
        f"Trade PnL: *{pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)*\n\n"
        f"Simulated Balance: *${new_bal:,.2f} USDT*"
    )
    
    print("📣 Broadcasting Exit alert to Telegram...")
    for target_id in all_targets:
        try:
            is_adm = (target_id == SUPER_ADMIN_ID)
            u = database.get_user(target_id)
            if u:
                is_adm = (target_id == SUPER_ADMIN_ID or u.get('is_admin')) and not u.get('undercover_mode')
            kb = get_nav_buttons(is_admin=is_adm)
            await bot.send_message(
                chat_id=target_id,
                text=exit_msg,
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"⚠️ Failed exit send to {target_id}: {e}")
            
    print("💎 Manual simulated forward test alerts cycle completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
