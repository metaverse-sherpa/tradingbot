import os
import sys
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import database
from bot.config import SUPER_ADMIN_ID, logger
from bot.ui.keyboards import (
    get_nav_buttons,
    get_main_inline_menu,
    get_admin_keyboard,
    get_settings_ui
)

async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🌍 Select Your Exchange"""
    keyboard = [
        [InlineKeyboardButton("🏔️ Blofin", callback_data="setex_blofin")],
        [InlineKeyboardButton("🔶 Binance", callback_data="setex_binance")],
        [InlineKeyboardButton("💠 MEXC", callback_data="setex_mexc")],
        [InlineKeyboardButton("🔷 Bitget", callback_data="setex_bitget")],
        [InlineKeyboardButton("🟦 BingX", callback_data="setex_bingx")],
        [InlineKeyboardButton("🦙 Alpaca Stocks", callback_data="setex_alpaca")],
        [InlineKeyboardButton("📖 Download Blofin Guide (PDF)", callback_data="send_blofin_guide")]
    ]
    
    await update.effective_message.reply_text(
        "🌍 *Select Your Exchange*\n\n"
        "Which exchange would you like to link to the Metaverse Sherpa?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.effective_message.text.strip()
    
    # --- Capital Fixed Amount Input Validation ---
    if context.user_data.get('setting_cap_amount'):
        try:
            val = float(text)
            if val <= 0:
                raise ValueError()
        except ValueError:
            await update.effective_message.reply_text("❌ *Invalid Amount*: Please enter a valid positive number (e.g. `500`):", parse_mode="Markdown")
            return
            
        # Get actual balance
        user = database.get_user(chat_id)
        actual_balance = user.get('equity') or 0.0
        if val > actual_balance:
            await update.effective_message.reply_text(
                f"❌ *Value Exceeds Balance*\n\n"
                f"You specified **${val:,.2f} USDT**, which exceeds your current exchange account balance of **${actual_balance:,.2f} USDT**.\n\n"
                "Please specify a lower amount (or tap /cancel to abort):",
                parse_mode="Markdown"
            )
            return
            
        database.update_user_preference(chat_id, "custom_equity_type", "amount")
        database.update_user_preference(chat_id, "custom_equity_value", val)
        context.user_data['setting_cap_amount'] = False
        
        await update.effective_message.reply_text(
            f"✅ *Capital Allocation Updated!*\n\n"
            f"The bot will now trade with a fixed capital limit of **${val:,.2f} USDT**.",
            parse_mode="Markdown"
        )
        # Display settings menu
        user = database.get_user(chat_id)
        msg, markup = get_settings_ui(user)
        await update.effective_message.reply_text(msg, reply_markup=markup, parse_mode="Markdown")
        return

    # --- Capital Percentage Input Validation ---
    if context.user_data.get('setting_cap_pct'):
        try:
            val = float(text)
            if val <= 0 or val > 100:
                raise ValueError()
        except ValueError:
            await update.effective_message.reply_text("❌ *Invalid Percentage*: Please enter a valid number between `1` and `100` (e.g. `50`):", parse_mode="Markdown")
            return
            
        database.update_user_preference(chat_id, "custom_equity_type", "pct")
        database.update_user_preference(chat_id, "custom_equity_value", val)
        context.user_data['setting_cap_pct'] = False
        
        await update.effective_message.reply_text(
            f"✅ *Capital Allocation Updated!*\n\n"
            f"The bot will now trade with **{val:.1f}%** of your account balance.",
            parse_mode="Markdown"
        )
        # Display settings menu
        user = database.get_user(chat_id)
        msg, markup = get_settings_ui(user)
        await update.effective_message.reply_text(msg, reply_markup=markup, parse_mode="Markdown")
        return

    # --- 1. Handle Institutional Wallet Setup ---
    if context.user_data.get('setting_wallet'):
        # Basic TRON (TRC-20) Validation: Starts with T, length 34
        if text.startswith('T') and len(text) == 34:
            database.update_user_wallet(chat_id, text)
            context.user_data['setting_wallet'] = False
            
            # Descriptive Onboarding Step
            await update.effective_message.reply_text(
                "✅ *Institutional Wallet Linked & Verified!*\n\n"
                "Your identity is now synchronized with the institutional audit engine. You are now ready to cross the **23x Wealth Gap**.\n\n"
                "🏔️ *The Path to Institutional Access:*\n"
                "1️⃣ **Transfer $20 USDT** via the TRON (TRC-20) network to the Master Treasury.\n"
                "2️⃣ **Blockchain Audit**: The Sherpa's engine will automatically detect your transfer from your linked wallet.\n"
                "3️⃣ **Full Unlock**: Your account will instantly gain access to the complete 'Sherpa Basket' and professional risk controls.\n\n"
                "Tap below to view the Treasury Address and finalize your upgrade.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💎 Finalize Institutional Upgrade", callback_data="premium_menu")
                ]])
            )
            return
        else:
            await update.effective_message.reply_text(
                "❌ *Invalid TRC-20 Address*\n\n"
                "Institutional USDT (TRC-20) addresses must start with 'T' and be 34 characters long.\n"
                "Please check your address and try again.",
                parse_mode="Markdown"
            )
            return

    # --- 2. Handle Admin Master Wallet Setup ---
    if context.user_data.get('setting_admin_wallet') and chat_id == SUPER_ADMIN_ID:
        if text.startswith('T') and len(text) == 34:
            database.update_config('master_usdt_wallet', text)
            context.user_data['setting_admin_wallet'] = False
            await update.effective_message.reply_text(
                f"👑 *Overlord: Treasury Updated!*\n\n"
                f"New Master Wallet: `{text}`\n\n"
                "All institutional upgrades will now be directed to this address.",
                parse_mode="Markdown"
            )
            from bot.handlers.admin import show_admin_dashboard
            await show_admin_dashboard(update, context)
            return
        else:
            await update.effective_message.reply_text("❌ Invalid TRC-20 address for Treasury. Must start with 'T' and be 34 chars.")
            return

    step = context.user_data.get('setup_step', 0)
    
    if step == 101:
        context.user_data['alpaca_endpoint'] = text.strip()
        context.user_data['setup_step'] = 102
        try: await update.effective_message.delete()
        except: pass
        await update.effective_message.reply_text("✅ Endpoint Base URL received.\n\nNow, please paste your **Alpaca API Key ID**:")
        return
        
    elif step == 102:
        context.user_data['alpaca_api_key'] = text.strip()
        context.user_data['setup_step'] = 103
        try: await update.effective_message.delete()
        except: pass
        await update.effective_message.reply_text("✅ Key ID received and wiped from chat history.\n\nFinally, please paste your **Alpaca API Secret Key**:")
        return
        
    elif step == 103:
        alpaca_secret = text.strip()
        try: await update.effective_message.delete()
        except: pass
        
        # Save to DB and Activate
        database.update_user_preference(chat_id, "alpaca_endpoint", context.user_data['alpaca_endpoint'])
        database.update_user_preference(chat_id, "alpaca_api_key", context.user_data['alpaca_api_key'])
        database.update_user_preference(chat_id, "alpaca_api_secret", alpaca_secret)
        database.update_user_preference(chat_id, "strategy", "Sherpa Velocity Pullback")
        database.set_active(chat_id, True)
        database.reset_stock_stats(chat_id)
        
        # Admin Alert
        try:
            user_info = update.effective_user
            full_name = user_info.full_name
            import html
            safe_name = html.escape(str(full_name))
            if user_info.username:
                username_clean = user_info.username
                safe_username = html.escape(f"@{username_clean}")
                user_display = f"<a href=\"https://t.me/{username_clean}\">{safe_username}</a>"
            else:
                user_display = "No Username"
            act_msg = (
                "🦙 <b>Alpaca Stocks Activated!</b>\n\n"
                f"User: <b>{safe_name}</b> ({user_display})\n"
                f"ID: <code>{chat_id}</code>\n\n"
                "🚀 <i>Member has configured Alpaca and is now LIVE in the SVP Stock strategy.</i>"
            )
            await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=act_msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error sending Alpaca Stocks Activation admin alert: {e}")
        
        context.user_data.clear()
        
        await update.effective_message.reply_text(
            "🎊 *Setup Complete!*\n\n"
            "The Sherpa is now tracking your Alpaca Stock account. Trades will execute daily at **9:31 AM EST**.\n\n"
            "Your bot is now active and the *Sherpa Velocity Pullback* strategy has been automatically enabled! 🦙📈",
            parse_mode="Markdown"
        )
        
        # Send persistent footer dashboard
        await update.effective_message.reply_text(
            "🛰️ *Main Menu Activated*",
            reply_markup=get_main_inline_menu(chat_id),
            parse_mode="Markdown"
        )
        return

    if step == 1:
        context.user_data['api_key'] = text
        context.user_data['setup_step'] = 2
        # Delete user's message so their key isn't sitting in chat history
        try: await update.effective_message.delete()
        except: pass
        await update.effective_message.reply_text("✅ Key received and wiped from chat history.\n\nNow, please paste your **API Secret**:")
        
    elif step == 2:
        context.user_data['api_secret'] = text
        context.user_data['setup_step'] = 3
        try: await update.effective_message.delete()
        except: pass
        await update.effective_message.reply_text("✅ Secret received and wiped.\n\nFinally, please provide your **API Password / Passphrase**:")
        
    elif step == 3:
        context.user_data['api_pass'] = text
        context.user_data['api_password'] = text
        try: await update.effective_message.delete()
        except: pass
        
        # Save to DB and Activate
        database.upsert_user(
            chat_id, 
            context.user_data['api_key'],
            context.user_data['api_secret'],
            context.user_data['api_password'],
            exchange_id=context.user_data.get('exchange_id', 'blofin'),
            is_active=True
        )
        
        # 💎 Stage 2 Admin Alert: Institutional Activation
        try:
            user_info = update.effective_user
            full_name = user_info.full_name
            import html
            safe_name = html.escape(str(full_name))
            if user_info.username:
                username_clean = user_info.username
                safe_username = html.escape(f"@{username_clean}")
                user_display = f"<a href=\"https://t.me/{username_clean}\">{safe_username}</a>"
            else:
                user_display = "No Username"
            act_msg = (
                "💎 <b>Institutional Access Activated!</b>\n\n"
                f"User: <b>{safe_name}</b> ({user_display})\n"
                f"ID: <code>{chat_id}</code>\n\n"
                "🚀 <i>Member has configured API and is now LIVE in the engine.</i>"
            )
            await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=act_msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error sending Institutional Activation admin alert: {e}")
        
        context.user_data.clear()
        keyboard = [[InlineKeyboardButton("💰 Check My Balance", callback_data="check_balance_setup")]]
        await update.effective_message.reply_text(
            "🎊 *Setup Complete!*\n\n"
            "The Sherpa is now tracking your account. Trading will begin on the next engine cycle.\n\n"
            "Tap the button below to verify your connection and check your trading funds.", 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        # Also send the persistent footer dashboard
        await update.effective_message.reply_text(
            "🛰️ *Main Menu Activated*",
            reply_markup=get_main_inline_menu(chat_id),
            parse_mode="Markdown"
        )
        return

    elif context.user_data.get('setting_crypto_risk'):
        try:
            val = float(text.replace("%", ""))
            if 0.01 <= val <= 100.0:
                database.update_user_preference(chat_id, "risk_pct", val)
                context.user_data.pop('setting_crypto_risk', None)
                keyboard = [
                    [InlineKeyboardButton("🔬 Run Crypto Backtest", callback_data="run_backtest_crypto")],
                    [InlineKeyboardButton("🔙 Skip and Return to Settings", callback_data="back_to_settings")]
                ]
                await update.effective_message.reply_text(
                    f"✅ Crypto Risk updated to *{val:.2f}%*\n\n"
                    "Would you like to run a backtest on your crypto strategy to see how this new risk level performs?", 
                    reply_markup=InlineKeyboardMarkup(keyboard), 
                    parse_mode="Markdown"
                )
            else:
                await update.effective_message.reply_text("❌ Please enter a value between 0.01 and 100.")
        except:
            await update.effective_message.reply_text("❌ Invalid number. Please enter a value like `1.5`.")

    elif context.user_data.get('setting_stock_risk'):
        try:
            val = float(text.replace("%", ""))
            if 0.01 <= val <= 100.0:
                database.update_user_preference(chat_id, "stock_risk_pct", val)
                context.user_data.pop('setting_stock_risk', None)
                keyboard = [
                    [InlineKeyboardButton("🔬 Run Stock Backtest", callback_data="run_backtest_stock")],
                    [InlineKeyboardButton("🔙 Skip and Return to Settings", callback_data="back_to_settings")]
                ]
                await update.effective_message.reply_text(
                    f"✅ Stock Risk updated to *{val:.2f}%*\n\n"
                    "Would you like to run a backtest on your stock strategy to see how this new risk level performs?", 
                    reply_markup=InlineKeyboardMarkup(keyboard), 
                    parse_mode="Markdown"
                )
            else:
                await update.effective_message.reply_text("❌ Please enter a value between 0.01 and 100.")
        except:
            await update.effective_message.reply_text("❌ Invalid number. Please enter a value like `1.5`.")
            
    elif context.user_data.get('admin_gifting'):
        context.user_data.pop('admin_gifting', None)
        try:
            target_input = text.strip()
            target_id = None
            target_username = None
            is_universal = False
            
            if target_input.upper() == 'ANY':
                is_universal = True
            elif target_input.startswith('@') or not target_input.isdigit():
                target_id = database.get_chat_id_by_username(target_input)
                if not target_id:
                    target_username = target_input.lstrip('@')
            else:
                target_id = int(target_input)

            code = database.create_gift_code(target_id, target_username)
            bot_username = (await context.bot.get_me()).username
            
            # Universal gift or targeted gift links
            web_gift_url = f"https://bot.metaversesherpa.io/#/landing?gift={code}"
            tg_gift_url = f"https://t.me/{bot_username}?start=gift_{code}"
            
            if target_id:
                display_target = str(target_id)
            elif target_username:
                display_target = f"@{target_username} (Reserved)"
            else:
                display_target = "ANY (Universal)"
                
            safe_id = escape_markdown(display_target, version=2)
            safe_code = escape_markdown(code, version=2)
            
            if is_universal:
                header_txt = "🎁 Universal Gift Code Generated"
            elif target_username:
                header_txt = "🎁 Reserved Gift Generated"
            else:
                header_txt = "🎁 Targeted Gift Generated"
                
            safe_header = escape_markdown(header_txt, version=2)
            
            safe_web_url = escape_markdown(web_gift_url, version=2)
            safe_tg_url = escape_markdown(tg_gift_url, version=2)
            
            msg = (
                f"*{safe_header}*\n\n"
                f"Target: `{safe_id}`\n"
                f"Gift Code: `{safe_code}`\n\n"
                f"🌐 *Web App Gift Link*:\n"
                f"`{safe_web_url}`\n\n"
                f"🤖 *Telegram Bot Gift Link*:\n"
                f"`{safe_tg_url}`"
            )
            
            if target_username and not target_id:
                msg += escape_markdown("\n\n⚠️ Note: This user is not in the DB yet, but this link is LOCKED to their username. Only they can redeem it.", version=2)
            
            await update.message.reply_text(msg, parse_mode="MarkdownV2")

            # 🎁 Direct Notification (Only if already in DB)
            if target_id:
                try:
                    safe_gift_header = escape_markdown("🎁 Institutional Gift Received!", version=2)
                    safe_gift_desc1 = escape_markdown("The Sherpa Overlord has granted you 30 Days of Premium Institutional Access.", version=2)
                    safe_gift_desc2 = escape_markdown("Tap the link below to activate your account and unlock the full Sherpa Basket:", version=2)
                    safe_gift_url = escape_markdown(tg_gift_url, version=2)

                    user_msg = (
                        f"*{safe_gift_header}*\n\n"
                        f"{safe_gift_desc1}\n\n"
                        f"{safe_gift_desc2}\n\n"
                        f"{safe_gift_url}"
                    )
                    await context.bot.send_message(chat_id=target_id, text=user_msg, parse_mode="MarkdownV2")
                    await update.message.reply_text(f"✅ User `{target_id}` has been notified directly.")
                except Exception as notify_err:
                    await update.message.reply_text(f"⚠️ Gift generated, but could not notify user directly: {notify_err}")

        except ValueError:
            await update.message.reply_text("❌ Invalid Input. Please enter a numerical ID, @username, or ANY.")
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to generate gift: {e}")
        
        from bot.handlers.admin import show_admin_dashboard
        await show_admin_dashboard(update, context)
        return

    elif context.user_data.get('admin_revoking'):
        context.user_data.pop('admin_revoking', None)
        try:
            target_input = text.strip()
            target_id = None
            target_username = None
            
            if target_input.startswith('@') or not target_input.isdigit():
                target_id = database.get_chat_id_by_username(target_input)
                if not target_id:
                    target_username = target_input.lstrip('@')
            else:
                target_id = int(target_input)

            if target_id:
                keyboard = [
                    [InlineKeyboardButton("✅ Confirm Revoke", callback_data=f"admin_revoke_confirm_{target_id}")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="admin_command")]
                ]
                await update.message.reply_text(
                    f"⚠️ *Confirm Revocation*\n\nAre you sure you want to instantly revoke Premium access for user `{target_id}`?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"❌ User '{target_input}' not found in the database. Cannot revoke.", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to revoke premium: {e}")
        
        from bot.handlers.admin import show_admin_dashboard
        await show_admin_dashboard(update, context)
        return

    elif context.user_data.get('admin_broadcasting'):
        context.user_data.pop('admin_broadcasting', None)
        text = update.message.text
        users = database.get_all_users()
        count = 0
        for u in users:
            target_id = u['telegram_chat_id']
            try:
                await context.bot.send_message(chat_id=target_id, text=text, parse_mode="Markdown")
                count += 1
            except Exception as e:
                logger.warning(f"Failed broadcast to {target_id}: {e}")
        footer = "\n\n───────────────────\n👑 *Sherpa Overlord Mission Control*"
        from bot.config import MASTER_USDT_WALLET
        master_wallet = database.get_config('master_usdt_wallet', MASTER_USDT_WALLET)
        footer_kb = InlineKeyboardMarkup(get_admin_keyboard(master_wallet))
        await update.message.reply_text(f"📢 Broadcast sent to {count} users.{footer}", parse_mode="Markdown", reply_markup=footer_kb)
