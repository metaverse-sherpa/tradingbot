import os
import sys
import sqlite3
import logging
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

import database
from bot.config import SUPER_ADMIN_ID, get_currency, is_stock, CRYPTO_LEVERAGE, get_symbol_link
from bot.ui.keyboards import escape_md_v2, get_nav_buttons

logger = logging.getLogger(__name__)

async def render_history_dashboard(update, context, last_10, chat_id, user):
    """Renders the final history message from trade data."""
    last_10 = last_10[:10]
    history_text = "📜 *Metaverse Sherpa History*\n\n"
    buttons = []
    
    for i, t in enumerate(last_10):
        dt_raw = datetime.fromtimestamp(t['timestamp']/1000).strftime('%m-%d %H:%M')
        dt = escape_md_v2(dt_raw)
        
        sym_raw = t['symbol'].split("/")[0]
        sym_v2 = escape_md_v2(sym_raw)
        
        is_stk = is_stock(t['symbol'])
        asset_icon = "🦙" if is_stk else "🪙"
        
        strat = user.get('active_stock_strategy') if is_stk else user.get('active_crypto_strategy')
        if not strat or strat == 'None':
            strat = "Manual"
        strat_v2 = escape_md_v2(strat)

        dir_icon = "📈" if t['side'] == "l" else "📉"
        roe_v2 = escape_md_v2(f"{t['roe_val']:+.1f}%")
        pnl_val_v2 = escape_md_v2(f"${t['net_pnl']:+.2f}")
        status_icon = "🏆" if t['net_pnl'] > 0 else "❌"
        
        sym_link = get_symbol_link(t['symbol'], text=f"*{sym_v2}*")
        
        history_text += (
            f"{i+1}\\. {asset_icon} {sym_link} {dir_icon} \\| _{dt}_\n"
            f"🧠 _{strat_v2}_\n"
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


async def build_forward_test_stats_block():
    """
    Shared helper that computes simulated forward testing analytics for
    Sherpa Velocity Pullback on US equities with independent $1,000 allocation,
    live unrealized PnL for open trades, and per-trade breakdowns.
    
    Returns a formatted Markdown text block ready to embed in any message.
    """
    open_sim_trades = database.get_open_theoretical_trades()
    disabled = database.get_disabled_strategies()
    
    svp_stats = database.get_theoretical_stats_by_strategy("Sherpa Velocity Pullback")
    
    # Group open trades for Sherpa Velocity Pullback
    strategy_name = "Sherpa Velocity Pullback"
    strategy_open_trades = [t for t in open_sim_trades if t.get('strategy') == strategy_name]
    
    # Fetch live stock prices for open trades to compute unrealized PnL
    stock_symbols = [t['symbol'] for t in strategy_open_trades if is_stock(t['symbol'])]
    stock_prices = {}
    if stock_symbols:
        try:
            import aiohttp
            from utils_gcp import get_secret
            sym_str = ",".join(set(stock_symbols))
            url = f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={sym_str}"
            headers = {
                "APCA-API-KEY-ID": get_secret("ALPACA_API_KEY"),
                "APCA-API-SECRET-KEY": get_secret("ALPACA_API_SECRET")
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for sym, snapshot in data.items():
                            daily_bar = snapshot.get("dailyBar", {})
                            latest_trade = snapshot.get("latestTrade", {})
                            close_price = daily_bar.get("c") or latest_trade.get("p")
                            if close_price:
                                stock_prices[sym] = float(close_price)
        except Exception as e:
            logger.error(f"Error fetching Alpaca snapshots for stats: {e}")

    strategy_unrealized = 0.0
    strategy_trade_lines = []
    
    for t in strategy_open_trades:
        sym = t['symbol']
        side = t['side']
        entry = t['entry_price']
        pos_size = t['position_size']
        current = stock_prices.get(sym, entry)
        
        side_lower = str(side).lower()
        is_long = side_lower in ['buy', 'long', 'l']
        pnl_raw = current - entry if is_long else entry - current
        pnl_pct = (pnl_raw / entry) * 100
        pnl_val = pos_size * (pnl_pct / 100)
        
        tp_price = t.get('tp_price', 0)
        target_pct_str = ""
        if tp_price and tp_price > 0:
            target_pnl_raw = tp_price - entry if is_long else entry - tp_price
            target_pct = (target_pnl_raw / entry) * 100
            target_pct_str = f" of {target_pct:+.2f}% (target)"

        strategy_unrealized += pnl_val
        direction = "⬆️" if is_long else "⬇️"
        sym_link = get_symbol_link(sym)
        strategy_trade_lines.append(
            f"  {direction} {sym_link}: `{pnl_pct:+.2f}%`{target_pct_str}"
        )
    
    starting_capital = 1000.0
    realized_pct = (svp_stats['cumulative_pnl'] / starting_capital) * 100
    open_count = len(strategy_open_trades)
    
    block = (
        f"🦙 *Sherpa Velocity Pullback (US Equities)*\n"
        f"• Win Rate: `{svp_stats['win_rate']:.2f}%` ({svp_stats['wins']} W | {svp_stats['losses']} L)\n"
        f"• Realized PnL: `{realized_pct:+.2f}%`\n"
    )
    if open_count > 0:
        unrealized_pct = (strategy_unrealized / starting_capital) * 100
        block += f"• Active Signals: `{open_count}`"
        if unrealized_pct != 0:
            block += f" (Unrealized: `{unrealized_pct:+.2f}%`)"
        block += "\n"
        for line in strategy_trade_lines:
            block += f"{line}\n"
    else:
        block += "• Active Signals: `0`\n"
    
    text = (
        "🧪 *Equities Forward Testing*\n"
        f"• Open Stock Signals: `{open_count}`\n\n"
        + block
    )
    
    return text
