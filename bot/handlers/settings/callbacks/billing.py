import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database
from bot.config import (
    SUPER_ADMIN_ID,
    logger,
    get_master_wallet
)
from bot.ui.keyboards import (
    get_settings_ui,
    safe_edit_text,
    get_main_inline_menu,
    get_nav_buttons
)
from bot.handlers.settings.helpers import clear_input_states

async def handle_billing_callback(query, update, context, user, chat_id) -> bool:
    if query.data == "activate_with_credits":
        credits = user.get('referral_credits', 0.0)
        if credits < 20.0:
            await query.answer("❌ Insufficient credits.", show_alert=True)
            return True
            
        await query.answer("🚀 Activating with Credits...")
        database.consume_referral_credits(chat_id, 20.0)
        database.add_premium_days(chat_id, 30)
        database.set_active(chat_id, True)
        
        referrer_id = user.get('referred_by')
        if referrer_id:
            reward_granted = database.award_premium_referral(referrer_id)
            if reward_granted:
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text="🎉 *PREMIUM MILESTONE REACHED!*\n\nYou've successfully recruited 3 Premium members. Your **Premium access** has been activated/extended for 30 days!\n\n🏔️ _The Sherpa honors your leadership._",
                        parse_mode="Markdown"
                    )
                except: pass

        await query.message.reply_text("💎 *PREMIUM ACCESS ACTIVATED!*\nSuccessfully used $20.00 in referral credits.", parse_mode="Markdown")
        msg, rm = get_settings_ui(user)
        await safe_edit_text(update, context, msg, reply_markup=rm)
        return True

    if query.data == "check_payment":
        await query.answer("🔎 Auditing Blockchain...")
        source_wallet = user.get('source_wallet')
        
        if not source_wallet:
            await query.message.reply_text("❌ No source wallet linked. Please set your wallet first.")
            return True

        if source_wallet == get_master_wallet() and chat_id != SUPER_ADMIN_ID:
            await query.message.reply_text(
                "❌ *Invalid Source Wallet*\n\n"
                "You cannot use the Master Treasury address as your source wallet. Please link your personal USDT (TRC-20) address in Settings.",
                parse_mode="Markdown"
            )
            return True
            
        await query.message.reply_text("🔎 *Auditing Blockchain for your transfer...*\n\nThis usually takes 1-3 minutes. Please wait and click again if activation is not instant.", parse_mode="Markdown")
        
        url = "https://apilist.tronscan.org/api/token_trc20/transfers"
        params = {
            "limit": 20,
            "start": 0,
            "direction": 1,
            "address": get_master_wallet(),
            "relatedAddress": source_wallet
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            transfers = data.get('token_transfers', [])
            
            credits = user.get('referral_credits', 0.0)
            required_price = max(0.1, 20.0 - credits)
            
            found = False
            for tx in transfers:
                if tx.get('contract_address') == 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t':
                    amount = float(tx.get('quant')) / 10**6
                    if (required_price - 0.5) <= amount <= (required_price + 0.5):
                        found = True
                        break
            
            if found:
                database.add_premium_days(chat_id, 30)
                database.set_active(chat_id, True)
                
                if credits > 0:
                    database.consume_referral_credits(chat_id, 20.0)
                
                referrer_id = user.get('referred_by')
                if referrer_id:
                    reward_granted = database.award_premium_referral(referrer_id)
                    if reward_granted:
                        try:
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text="🎉 *PREMIUM MILESTONE REACHED!*\n\nYou've successfully recruited 3 Premium members. Your **Premium access** has been activated/extended for 30 days!\n\n🏔️ _The Sherpa honors your leadership._",
                                parse_mode="Markdown"
                            )
                        except: pass

                try:
                    import html
                    if update.effective_user.username:
                        username_clean = update.effective_user.username
                        safe_username = html.escape(f"@{username_clean}")
                        user_display = f"<a href=\"https://t.me/{username_clean}\">{safe_username}</a>"
                    else:
                        user_display = f"ID: <code>{chat_id}</code>"
                    
                    await context.bot.send_message(
                        chat_id=SUPER_ADMIN_ID,
                        text=(
                            "💰 <b>INSTITUTIONAL REVENUE CONFIRMED!</b>\n\n"
                            f"User: {user_display}\n"
                            f"Required: <b>${required_price:.2f} USDT</b>\n\n"
                            "📈 <i>The treasury is growing.</i>"
                        ),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error sending institutional revenue admin alert: {e}")

                await query.message.reply_text(
                    "💎 *PREMIUM ACCESS ACTIVATED!*\n\n"
                    "Congratulations. Your account has been upgraded to the Premium Tier for **30 days**.\n\n"
                    "🏔️ *Power Unlocked:*\n"
                    "• Full 19+ Symbol Basket enabled.\n"
                    "• Custom Risk Management enabled.\n"
                    "• Priority Background Processing enabled.\n\n"
                    "The Sherpa engine is now live on your account. Happy climbing!",
                    parse_mode="Markdown"
                )
                msg, markup = get_settings_ui(database.get_user(chat_id))
                await query.message.reply_text(msg, reply_markup=markup, parse_mode="Markdown")
            else:
                await query.message.reply_text(
                    "❌ *No matching transfer found yet.*\n\n"
                    "On-chain confirmation can take a few minutes. Please wait and try again shortly.\n\n"
                    f"ℹ️ _Looking for $20 USDT from_ `{source_wallet}` _to_ `{get_master_wallet()}`",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            logger.error(f"Error checking payment: {e}")
            await query.message.reply_text("⚠️ _Blockchain audit engine is busy. Please try again in 60 seconds._")
        return True

    if query.data == "prompt_set_wallet":
        clear_input_states(context)
        context.user_data['setting_wallet'] = True
        await query.message.reply_text(
            "👛 *Institutional Wallet Setup*\n\n"
            "Please send your **USDT (TRC-20) Address** below.\n\n"
            "This address will be used to automatically verify your subscription payments and enable frictionless future renewals.",
            parse_mode="Markdown"
        )
        await query.answer()
        return True

    if query.data == "refer_menu":
        from bot.handlers.admin import show_refer_dashboard
        await show_refer_dashboard(update, context)
        await query.answer()
        return True

    if query.data == "referral_menu":
        await query.answer()
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{chat_id}"
        count = database.get_referral_stats(chat_id)
        
        msg = (
            "🤝 *Sherpa Referral Program*\n\n"
            "Grow the community and earn **Free Premium Days**!\n\n"
            "Your Link (Tap to Copy):\n"
            f"`{ref_link}`\n\n"
            f"Total Referrals: *{count}*\n\n"
            "Share this link with your friends. For every friend who sets up their API keys, you both get **5 bonus days** of unlimited usage!"
        )
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_to_settings")],
            *get_nav_buttons(user.get('has_open_positions', False))
        ]
        await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    if query.data == "premium_menu":
        from bot.handlers.admin import show_premium_menu
        await show_premium_menu(update, context)
        await query.answer()
        return True

    return False
