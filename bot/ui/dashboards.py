import os
import sys
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import database
from bot.config import SUPER_ADMIN_ID
from bot.ui.keyboards import escape_md_v2, get_nav_buttons

logger = logging.getLogger(__name__)

async def render_history_dashboard(update, context, last_10, chat_id, user):
    """Renders the final history message from trade data."""
    history_text = "📜 *Metaverse Sherpa History*\n\n"
    buttons = []
    
    for i, t in enumerate(last_10):
        dt_raw = datetime.fromtimestamp(t['timestamp']/1000).strftime('%m-%d %H:%M')
        dt = escape_md_v2(dt_raw)
        
        sym_v2 = escape_md_v2(t['symbol'].split("/")[0])
        dir_icon = "📈" if t['side'] == "l" else "📉"
        roe_v2 = escape_md_v2(f"{t['roe_val']:+.1f}%")
        pnl_val_v2 = escape_md_v2(f"${t['net_pnl']:+.2f}")
        status_icon = "🏆" if t['net_pnl'] > 0 else "❌"
        
        history_text += (
            f"{i+1}\\. *{sym_v2}* {dir_icon} \\| _{dt}_\n"
            f"{status_icon} PnL: ||{pnl_val_v2}|| \\(*{roe_v2}*\\)\n"
            f"\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n"
        )
        
        win_icon = " 🏆" if t['net_pnl'] > 0 else ""
        cb_data = f"shc_{t['symbol']}_{t['side']}_{t['roe_val']:.2f}_{t['price']:.4f}_{t['price']:.4f}_{t['net_pnl']:.2f}"
        buttons.append(InlineKeyboardButton(f"{i+1}-{sym_v2}{win_icon}", callback_data=cb_data))
        
    history_text += "\n*Tap a button below to Share & Earn 📸*"
    
    is_admin = (chat_id == SUPER_ADMIN_ID or user.get('is_admin')) and not user.get('undercover_mode')
    grid = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    grid.append([InlineKeyboardButton(" ", callback_data="none")])
    grid.extend(get_nav_buttons(user.get('has_open_positions', False), is_admin=is_admin))
    
    await update.effective_message.reply_text(
        history_text, 
        reply_markup=InlineKeyboardMarkup(grid),
        parse_mode="MarkdownV2"
    )
