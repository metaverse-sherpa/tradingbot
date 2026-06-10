from telegram import Update
from telegram.ext import ContextTypes

import database
from bot.ui.keyboards import get_settings_ui

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = database.get_user(chat_id)
    if not user:
        await update.effective_message.reply_text("You are not set up yet. Tap /setup to begin.")
        return
        
    expired_alert = ""
    if user.get('had_premium_before') and not database.is_premium(user):
        expired_alert = "⚠️ *Your Premium Access Has Expired*\nYour autopilot is currently paused. Please renew to resume live trading.\n\n"
        
    msg, reply_markup = get_settings_ui(user)
    if expired_alert:
        msg = f"{expired_alert}{msg}"
        
    await update.effective_message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
