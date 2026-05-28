import os
import sys
import time
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import database
from bot.config import SUPER_ADMIN_ID, logger, get_master_wallet
from bot.ui.keyboards import (
    get_nav_buttons,
    get_main_inline_menu,
    safe_edit_text,
    get_admin_keyboard
)
from bot.ui.dashboards import build_forward_test_stats_block

async def show_refer_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified helper to show the Institutional Recruitment Dashboard."""
    chat_id = update.effective_chat.id
    bot_username = (await context.bot.get_me()).username
    stats = database.get_referral_stats(chat_id)
    
    invite_link = f"https://t.me/{bot_username}?start=ref_{chat_id}"
    web_invite_link = f"https://bot.metaversesherpa.io/#/register?ref={chat_id}"
    
    refer_msg = (
        "🏔️ *Institutional Recruitment Dashboard*\n\n"
        "Expand the trail and unlock the **23x Wealth Gap** for free!\n\n"
        f"📊 *Your Status:* `{stats}` Recruits\n"
        f"📈 *Next Reward:* `{3 - (stats % 3)}` more for **30 Days Premium**\n\n"
        "🔗 *Your Institutional Invite Link (Telegram):*\n"
        f"`{invite_link}`\n\n"
        "🌐 *Your Institutional Invite Link (Web):*\n"
        f"`{web_invite_link}`\n\n"
        "💡 _Every 3 recruits who join the trail instantly unlocks 30 days of full 'Sherpa Basket' access._"
    )
    
    kb = [
        [InlineKeyboardButton("📱 Share Telegram Link", url=f"https://t.me/share/url?url={invite_link}&text=Unlock%20the%20Institutional%20Wealth%20Gap%20with%20the%20Metaverse%20Sherpa%20Trading%20Bot!%20🏔️")],
        [InlineKeyboardButton("🌐 Share Web Link", url=f"https://t.me/share/url?url={web_invite_link}&text=Unlock%20the%20Institutional%20Wealth%20Gap%20with%20the%20Metaverse%20Sherpa%20Trading%20Bot!%20🏔️")]
    ]
    await safe_edit_text(update, context, refer_msg, reply_markup=InlineKeyboardMarkup(kb))

async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Super Admin only: Promotes a user to Admin."""
    chat_id = update.effective_chat.id
    if chat_id != SUPER_ADMIN_ID: return
    
    if not context.args:
        await update.message.reply_text("Usage: `/promote <chat_id>`", parse_mode="Markdown")
        return
        
    try:
        target_id = int(context.args[0])
        database.set_admin_status(target_id, True)
        await update.message.reply_text(f"✅ User `{target_id}` promoted to Admin.", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_id, text="💎 *Promotion Success*\nYou have been granted Admin privileges by the Super Admin.", parse_mode="Markdown")
        except: pass
    except:
        await update.message.reply_text("❌ Invalid Chat ID.")

async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Super Admin only: Demotes a user from Admin status."""
    chat_id = update.effective_chat.id
    if chat_id != SUPER_ADMIN_ID: return
    
    if not context.args:
        await update.message.reply_text("Usage: `/demote <chat_id>`", parse_mode="Markdown")
        return
        
    try:
        target_id = int(context.args[0])
        database.set_admin_status(target_id, False)
        await update.message.reply_text(f"✅ User `{target_id}` demoted from Admin.", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Invalid Chat ID.")

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_refer_dashboard(update, context)

async def show_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the Institutional Premium Upgrade dashboard."""
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user: return
    
    wallet_val = user.get('source_wallet')
    is_premium = database.is_premium(user)
    
    # We no longer return early here, so the user can always see the infographic and benefits

    credits = user.get('referral_credits', 0.0)
    final_price = max(0.0, 20.0 - credits)
    
    credit_msg = f"💰 *Available Credit:* `${credits:.2f}`\n" if credits > 0 else ""
    price_msg = f"💳 *Institutional Access Fee:* ~~[ $20 ]~~ **${final_price:.2f} USDT** / 30 Days\n" if credits > 0 else f"💳 *Institutional Access Fee:* **$20 USDT / 30 Days**\n"

    premium_msg = (
        "💎 *Go Premium: Unlock the 23x Wealth Gap*\n\n"
        "Unlock professional-grade tools used by elite traders:\n\n"
        "🏔️ *Premium Tier Benefits:*\n"
        "• *Full Autopilot*: Live auto-trading directly on your exchange.\n"
        "• *Full Sherpa Basket*: Trade all 19+ premium symbols.\n"
        "• *Advanced Risk*: Set custom risk-per-trade percentages.\n"
        "• *Priority Execution*: Priority in the engine's background loop.\n\n"
        "🎁 *Get it for FREE!*\n"
        "Invite 3 friends to unlock *1 Month Free*. Tap /refer!\n\n"
        f"{credit_msg}"
        f"{price_msg}\n"
    )

    from bot.ui.keyboards import send_cached_photo
    premium_photo_path = os.path.join(BASE_DIR, "images", "premium_infographic.png")

    if not wallet_val:
        premium_msg += (
            "⚠️ *Source Wallet Required*\n\n"
            "To unlock Premium, set your **Source Wallet Address** so the Sherpa can verify payment.\n"
            "Tap the button below."
        )
        kb = [[InlineKeyboardButton("👛 Set Wallet", callback_data="prompt_set_wallet")]]
        kb.append([InlineKeyboardButton("🔙 Return to Settings", callback_data="settings_menu")])
        await send_cached_photo(update, context, premium_photo_path, caption=premium_msg, reply_markup=InlineKeyboardMarkup(kb))
    else:
        # Send top features infographic
        await send_cached_photo(update, context, premium_photo_path, caption=premium_msg)
        
        # Send bottom payment infographic with action buttons
        payment_msg = (
            "📥 *Upgrade Path:*\n"
            "1. Copy the Treasury Address below.\n"
            f"2. Send **${final_price:.2f} USDT** via **TRON (TRC-20)**.\n"
            "3. Tap 'Audit My Payment'.\n\n"
            f"🏛️ *Treasury (TRC-20):* `{get_master_wallet()}`\n\n"
            "⚠️ _Activation is automated within 1-3 mins._"
        )
        
        kb = []
        if final_price == 0:
            kb.append([InlineKeyboardButton("🚀 Activate with Credits", callback_data="activate_with_credits")])
        else:
            kb.append([InlineKeyboardButton("🔎 Audit My Payment & Unlock", callback_data="check_payment")])
        
        kb.append([InlineKeyboardButton("👛 Change My Linked Wallet", callback_data="prompt_set_wallet")])
        kb.append([InlineKeyboardButton("🔙 Return to Settings", callback_data="settings_menu")])
        
        payment_photo_path = os.path.join(BASE_DIR, "images", "payment_steps_infographic.png")
        await send_cached_photo(update, context, payment_photo_path, caption=payment_msg, reply_markup=InlineKeyboardMarkup(kb))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a Telegram message to the Super Admin."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Send trace to Super Admin
    import traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    
    err_msg = (
        f"🚨 *HANDLER CRASH*\n\n"
        f"Update: `{update}`\n\n"
        f"*Error:* `{context.error}`\n\n"
        f"*Traceback:*\n```\n{tb_string[:3500]}\n```"
    )
    try:
        await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=err_msg, parse_mode="Markdown")
    except: pass

async def show_admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gated dashboard for the Sherpa Overlord."""
    chat_id = update.effective_chat.id
    if chat_id != SUPER_ADMIN_ID: return
    
    user = database.get_user(chat_id)
    if not user: return

    stats = database.get_platform_stats()
    master_wallet = get_master_wallet()
    
    # Query Wallet Balances via TronGrid and Price via CCXT
    total_val = 0.0
    trx_bal = 0.0
    usdt_bal = 0.0
    try:
        import requests
        url = f"https://api.trongrid.io/v1/accounts/{master_wallet}"
        resp = requests.get(url, timeout=7)
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            if data:
                acc = data[0]
                # TRX Balance (6 decimals)
                trx_bal = float(acc.get('balance', 0)) / 10**6
                
                # USDT Balance (TRC-20)
                trc20_tokens = acc.get('trc20', [])
                for token_map in trc20_tokens:
                    for contract, raw_bal in token_map.items():
                        # Official USDT TRC-20 Contract
                        if contract == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t":
                            usdt_bal = float(raw_bal) / 10**6
                            break
        
        # Fetch Real-Time TRX Price via TronScan (matches your dashboard)
        try:
            price_url = "https://apilist.tronscan.org/api/token/price?token=trx"
            price_resp = requests.get(price_url, timeout=5)
            trx_price = float(price_resp.json().get('price', 0.35))
        except:
            trx_price = 0.35 # Future-proof fallback based on your reality
            
        total_val = (trx_bal * trx_price) + usdt_bal
        balance_display = f"${total_val:,.2f}"
    except Exception as e:
        logger.error(f"Treasury Sync Error: {e}")
        balance_display = "??? (Offline)"

    admin_status = "🕵️‍♂️ Undercover" if user.get('undercover_mode') else "👑 Overlord"
    
    # 🧪 Simulated Forward Testing — shared analytics block
    forward_test_block = await build_forward_test_stats_block()
    
    last_sync = time.strftime('%H:%M:%S')
    admin_msg = (
        "👑 *Sherpa Overlord Mission Control*\n\n"
        f"Identity Status: *{admin_status}*\n\n"
        "📊 *Platform Analytics*\n"
        f"• Total Users: `{stats['total_users']}`\n"
        f"• Total Referrals: `{stats['total_referrals']}`\n"
        f"• Active Premium: `{stats['premium_users']}`\n"
        f"• Last Deploy: *2026-05-14 10:08*\n\n"
        f"{forward_test_block}\n\n"
        "💰 *Total Treasury Value*\n"
        f"• Master Wallet: `{master_wallet}`\n"
        f"• TRX: `{trx_bal:,.1f}` | USDT: `${usdt_bal:,.2f}`\n"
        f"• **Live Balance: {balance_display}**\n\n"
        f"🕒 _Last Sync: {last_sync}_"
    )
    
    kb = get_admin_keyboard(master_wallet)
    await safe_edit_text(update, context, admin_msg, reply_markup=InlineKeyboardMarkup(kb))

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_admin_dashboard(update, context)

async def sql_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    target = update.effective_message
    
    # 🔒 STRICT Security Check: Only the SUPER_ADMIN_ID can run this!
    if chat_id != SUPER_ADMIN_ID:
        await target.reply_text("❌ Permission Denied: Only the Sherpa Overlord can execute custom database queries.")
        return

    # Extract the query
    if not context.args:
        await target.reply_text(
            "📖 *Usage*: `/sql <SQL Query>`\n\n"
            "Example:\n"
            "`/sql SELECT telegram_chat_id, exchange_id, is_active, active_crypto_strategy, active_stock_strategy FROM Users`",
            parse_mode="Markdown"
        )
        return
        
    query = " ".join(context.args)
    status_msg = await target.reply_text("⏳ *Executing query on VPS Database...*", parse_mode="Markdown")
    
    try:
        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(query)
        
        # Check if it was a SELECT query or other
        is_select = query.strip().upper().startswith("SELECT")
        
        if is_select:
            rows = cursor.fetchall()
            if not rows:
                await status_msg.edit_text("✅ Query executed successfully. *No rows returned.*", parse_mode="Markdown")
                conn.close()
                return
                
            # Get columns
            columns = rows[0].keys()
            
            # Format rows
            header = " | ".join(columns)
            separator = "-|-".join(["---" for _ in columns])
            
            result_lines = [f"| {header} |", f"| {separator} |"]
            
            # Sensitive columns to mask
            sensitive_cols = {'blofin_api_key', 'blofin_api_secret', 'blofin_api_password', 
                              'alpaca_api_key', 'alpaca_api_secret', 'api_key', 'api_secret', 
                              'api_password', 'password'}
            
            for row in rows[:50]: # Limit to 50 rows for Telegram
                formatted_values = []
                for col in columns:
                    val = row[col]
                    if val is None:
                        formatted_values.append("NULL")
                    elif col.lower() in sensitive_cols:
                        val_str = str(val)
                        if len(val_str) > 8:
                            formatted_values.append(f"{val_str[:4]}...{val_str[-4:]}")
                        else:
                            formatted_values.append("*****")
                    else:
                        formatted_values.append(str(val))
                result_lines.append(f"| {' | '.join(formatted_values)} |")
                
            formatted_table = "\n".join(result_lines)
            
            # Split if message exceeds Telegram's 4096 character limit
            if len(formatted_table) > 4000:
                formatted_table = formatted_table[:3900] + "\n... (truncated)"
                
            await status_msg.edit_text(
                f"📊 *Query Results (Top 50 rows)*:\n\n```\n{formatted_table}\n```",
                parse_mode="Markdown"
            )
        else:
            conn.commit()
            changes = conn.changes()
            await status_msg.edit_text(f"✅ *Database Updated Successfully.*\n• Rows affected: `{changes}`", parse_mode="Markdown")
            
        conn.close()
    except Exception as e:
        clean_err = str(e).replace("`", "").replace("*", "").replace("_", "")
        await status_msg.edit_text(f"❌ *SQLite Error*:\n`{clean_err}`", parse_mode="Markdown")

async def dbinspect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    target = update.effective_message
    
    # 🔒 STRICT Security Check: Only the SUPER_ADMIN_ID can run this!
    if chat_id != SUPER_ADMIN_ID:
        await target.reply_text("❌ Permission Denied: Only the Sherpa Overlord can run database diagnostics.")
        return

    status_msg = await target.reply_text("🕵️ *Running VPS Database Inspection...*", parse_mode="Markdown")
    
    try:
        conn = sqlite3.connect(database.DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        report = ["📋 *Sherpa VPS Database Diagnostic Report*", ""]
        
        # 1. Database File Info
        db_size = os.path.getsize(database.DB_PATH) if os.path.exists(database.DB_PATH) else 0
        report.append(f"📂 *Database File Details*:")
        report.append(f"• Path: `{database.DB_PATH}`")
        report.append(f"• Size: `{db_size / 1024:.2f} KB`")
        report.append("")
        
        # 2. Schema and Tables list
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in c.fetchall()]
        report.append(f"📊 *Tables Exist in DB*: `{', '.join(tables)}`")
        report.append("")
        
        # 3. User Statistics
        c.execute("SELECT COUNT(*) as cnt FROM Users")
        total_users = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) as cnt FROM Users WHERE is_active = 1")
        active_users = c.fetchone()['cnt']
        report.append(f"👥 *User Accounts Summary*:")
        report.append(f"• Total Users: `{total_users}`")
        report.append(f"• Active Trading Users: `{active_users}`")
        
        # 4. Super Admin Profile Verification
        c.execute("SELECT * FROM Users WHERE telegram_chat_id = ?", (SUPER_ADMIN_ID,))
        admin_row = c.fetchone()
        
        report.append("")
        report.append("👑 *Super Admin (`1567788633`) Profile State*:")
        if admin_row:
            admin_data = dict(admin_row)
            
            # Crypto strategy and keys check
            crypto_strat = admin_data.get('active_crypto_strategy', 'None')
            has_crypto_key = bool(admin_data.get('blofin_api_key'))
            report.append(f"• Crypto Strategy: `{crypto_strat}`")
            report.append(f"• Crypto Keys Configured: `{'✅ Yes' if has_crypto_key else '❌ No'}`")
            report.append(f"• Exchange: `{admin_data.get('exchange_id', 'blofin').upper()}`")
            
            # Stock strategy and keys check
            stock_strat = admin_data.get('active_stock_strategy', 'None')
            has_stock_key = bool(admin_data.get('alpaca_api_key'))
            report.append(f"• Stock Strategy: `{stock_strat}`")
            report.append(f"• Stock Keys Configured: `{'✅ Yes' if has_stock_key else '❌ No'}`")
            report.append(f"• Alpaca Endpoint: `{admin_data.get('alpaca_endpoint', 'None')}`")
            
            # Connection settings check
            is_active = bool(admin_data.get('is_active'))
            report.append(f"• Active Trading Status: `{'🟢 ACTIVE' if is_active else '🔴 PAUSED'}`")
            
            # Check key decryption works fine
            try:
                decrypted_key = database.decrypt(admin_data['blofin_api_key']) if has_crypto_key else None
                report.append("• Key Decryption Test: `✅ Passed`")
            except Exception as dec_err:
                report.append(f"• Key Decryption Test: `❌ Failed` (Error: {str(dec_err)})")
        else:
            report.append("• Super Admin row: `❌ NOT FOUND IN DATABASE` (Run /setup inside the bot first)")
            
        # 5. Global Config Checks
        report.append("")
        report.append("⚙️ *Global System Configurations*:")
        c.execute("SELECT key, value FROM Config")
        configs = c.fetchall()
        for cfg in configs:
            report.append(f"• `{cfg['key']}`: `{cfg['value']}`")
            
        # 6. Theoretical Trades
        c.execute("SELECT COUNT(*) as cnt FROM TheoreticalTrades")
        t_trades = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) as cnt FROM TheoreticalTrades WHERE status = 'open'")
        o_t_trades = c.fetchone()['cnt']
        report.append("")
        report.append(f"🔬 *Simulated Trade Engine stats*:")
        report.append(f"• Total Saved Trades: `{t_trades}`")
        report.append(f"• Currently Open: `{o_t_trades}`")
        
        conn.close()
        await status_msg.edit_text("\n".join(report), parse_mode="Markdown")
        
    except Exception as e:
        clean_err = str(e).replace("`", "").replace("*", "").replace("_", "")
        await status_msg.edit_text(f"❌ *Diagnostic Error*:\n`{clean_err}`", parse_mode="Markdown")
