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
from bot.config import SUPER_ADMIN_ID, get_currency, is_stock, CRYPTO_LEVERAGE
from bot.ui.keyboards import escape_md_v2, get_nav_buttons

logger = logging.getLogger(__name__)

async def render_history_dashboard(update, context, last_10, chat_id, user):
    """Renders the final history message from trade data."""
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
        
        history_text += (
            f"{i+1}\\. {asset_icon} *{sym_v2}* {dir_icon} \\| _{dt}_\n"
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
    Shared helper that computes simulated forward testing analytics with
    independent $1,000 allocations per strategy, live unrealized PnL for
    open trades, and per-trade breakdowns.
    
    Returns a formatted Markdown text block ready to embed in any message.
    """
    import live_bot_multi
    
    open_sim_trades = database.get_open_theoretical_trades()
    
    mr_stats = database.get_theoretical_stats_by_strategy("Mean Reversion Scalper")
    vk_stats = database.get_theoretical_stats_by_strategy("Valkyrie Elite Scalper")
    svp_stats = database.get_theoretical_stats_by_strategy("Sherpa Velocity Pullback")
    
    # Group open trades by strategy
    strategy_names = ["Mean Reversion Scalper", "Valkyrie Elite Scalper", "Sherpa Velocity Pullback"]
    strategy_open_trades = {s: [] for s in strategy_names}
    for t in open_sim_trades:
        strat = t.get('strategy', '')
        if strat in strategy_open_trades:
            strategy_open_trades[strat].append(t)
    
    # Fetch live prices for open trades to compute unrealized PnL
    strategy_unrealized = {s: 0.0 for s in strategy_names}
    strategy_trade_lines = {s: [] for s in strategy_names}
    
    mdm = live_bot_multi.MarketDataManager()
    try:
        for strat_name in strategy_names:
            for t in strategy_open_trades[strat_name]:
                sym = t['symbol']
                side = t['side']
                entry = t['entry_price']
                pos_size = t['position_size']
                
                if is_stock(sym):
                    try:
                        import pandas as pd
                        conn = sqlite3.connect("data/stock_daily_cache.db")
                        df_chart = pd.read_sql_query(
                            "SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                            conn, params=(sym,)
                        )
                        conn.close()
                        current = float(df_chart['close'].iloc[0]) if not df_chart.empty else entry
                    except Exception:
                        current = entry
                else:
                    df = await mdm.fetch_ohlcv(sym, "15m")
                    current = float(df['close'].iloc[-1]) if df is not None and not df.empty else entry
                
                side_lower = str(side).lower()
                is_long = side_lower in ['buy', 'long', 'l']
                pnl_raw = current - entry if is_long else entry - current
                pnl_pct = (pnl_raw / entry) * 100
                
                currency = get_currency(sym)
                if is_stock(sym):
                    pnl_val = pos_size * (pnl_pct / 100)
                else:
                    pnl_pct *= CRYPTO_LEVERAGE
                    pnl_val = pos_size * pnl_raw
                
                strategy_unrealized[strat_name] += pnl_val
                
                direction = "⬆️" if is_long else "⬇️"
                strategy_trade_lines[strat_name].append(
                    f"  {direction} `{sym}`: {pnl_pct:+.2f}% ({pnl_val:+.2f} {currency})"
                )
    except Exception as e:
        logger.error(f"Error fetching live prices for forward test stats: {e}")
    finally:
        await mdm.close()
    
    # Each strategy starts with its own $1,000 allocation
    starting_capital = 1000.0
    all_stats = {
        "Mean Reversion Scalper": mr_stats,
        "Valkyrie Elite Scalper": vk_stats,
        "Sherpa Velocity Pullback": svp_stats
    }
    strategy_icons = {
        "Mean Reversion Scalper": "📈",
        "Valkyrie Elite Scalper": "🛡️",
        "Sherpa Velocity Pullback": "🦙"
    }
    
    balances = {}
    growths = {}
    for s in strategy_names:
        balances[s] = starting_capital + all_stats[s]['cumulative_pnl'] + strategy_unrealized[s]
        growths[s] = ((balances[s] - starting_capital) / starting_capital) * 100
    
    total_balance = sum(balances.values())
    total_growth = ((total_balance - (starting_capital * 3)) / (starting_capital * 3)) * 100
    
    # Build per-strategy sections
    def _build_strategy_block(name):
        stats = all_stats[name]
        icon = strategy_icons[name]
        balance = balances[name]
        growth = growths[name]
        open_trades = strategy_open_trades[name]
        trade_lines = strategy_trade_lines[name]
        unrealized = strategy_unrealized[name]
        open_count = len(open_trades)
        
        block = (
            f"{icon} *{name}*\n"
            f"• Balance: *${balance:,.2f}* ({growth:+.2f}%)\n"
            f"• Win Rate: `{stats['win_rate']:.1f}%` ({stats['wins']} W | {stats['losses']} L)\n"
            f"• Realized PnL: `{stats['cumulative_pnl']:+.2f} USDT`\n"
        )
        if open_count > 0:
            block += f"• Active Signals: `{open_count}`"
            if unrealized != 0:
                block += f" (Unrealized: `{unrealized:+.2f} USDT`)"
            block += "\n"
            for line in trade_lines:
                block += f"{line}\n"
        else:
            block += "• Active Signals: `0`\n"
        return block
    
    mr_block = _build_strategy_block("Mean Reversion Scalper")
    vk_block = _build_strategy_block("Valkyrie Elite Scalper")
    svp_block = _build_strategy_block("Sherpa Velocity Pullback")
    
    text = (
        "🧪 *Free Forward Testing*\n"
        f"• Combined Balance: *${total_balance:,.2f} USDT* ({total_growth:+.2f}%)\n"
        f"• Open Free Signals: `{len(open_sim_trades)}`\n\n"
        f"{mr_block}\n"
        f"{vk_block}\n"
        f"{svp_block}\n"
        f"_Each strategy starts with an independent $1,000 allocation_"
    )
    
    return text
