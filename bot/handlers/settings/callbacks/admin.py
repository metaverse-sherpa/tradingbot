import os
import time
import sqlite3
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database
from bot.config import (
    SUPER_ADMIN_ID,
    logger,
    get_master_wallet,
    format_price,
    get_currency,
    is_stock,
    CRYPTO_LEVERAGE
)
from bot.ui.keyboards import (
    escape_md_v2,
    safe_edit_text,
    get_admin_keyboard
)
from bot.handlers.settings.helpers import clear_input_states
import charting
import live_bot_multi

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

async def handle_admin_callback(query, update, context, user, chat_id) -> bool:
    if query.data == "admin_get_link":
        if chat_id != SUPER_ADMIN_ID: return True
        await query.answer()
        bot_username = (await context.bot.get_me()).username
        deep_link = f"https://t.me/{bot_username}?start=guide_blofin"
        msg = (
            "🔗 *Marketing Deep-Link*\n\n"
            "This link will instantly deliver the Blofin Guide to prospective users.\n\n"
            "Tap to Copy:\n"
            f"`{deep_link}`"
        )
        await query.message.reply_text(msg, parse_mode="Markdown")
        return True

    if query.data == "admin_command":
        if chat_id != SUPER_ADMIN_ID: return True
        from bot.handlers.admin import admin_command
        await admin_command(update, context)
        return True

    if query.data == "admin_user_audit":
        if chat_id != SUPER_ADMIN_ID: return True
        await query.answer("📊 Generating Audit...")
        report = database.get_detailed_user_report()

        total = len(report)
        premium_count = sum(1 for u in report if u['is_premium'])
        active_count = sum(1 for u in report if u['is_active'])
        free_count = total - premium_count

        header = (
            "🏔️ *Sherpa Institutional User Audit*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Total Users: *{total}*  •  "
            f"🟢 Active: *{active_count}*\n"
            f"💎 Premium: *{premium_count}*  •  "
            f"🥈 Free: *{free_count}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        cards = []
        user_lookup = {u['telegram_chat_id']: u for u in report}
        
        for i, u in enumerate(report, 1):
            tier_icon = "💎" if u['is_premium'] else "🥈"
            tier_label = "Premium" if u['is_premium'] else "Free"
            status_icon = "🟢" if u['is_active'] else "⚫"
            status_label = "Active" if u['is_active'] else "Setup"

            name = escape_md_v2(u.get('full_name') or "Unknown")
            uname = escape_md_v2(f"@{u['username']}") if u.get('username') else escape_md_v2("no username")

            # Last-Mile Identity Fetch
            if name == "Unknown":
                try:
                    member = await context.bot.get_chat_member(chat_id=u['telegram_chat_id'], user_id=u['telegram_chat_id'])
                    name = escape_md_v2(member.user.full_name)
                    uname = escape_md_v2(f"@{member.user.username}") if member.user.username else escape_md_v2("no username")
                except: pass

            card = (
                f"┌─ *{name}*\n"
                f"│  `{u['telegram_chat_id']}`  ·  {uname}\n"
                f"│  {status_icon} {status_label}  ·  {tier_icon} {tier_label}\n"
            )

            if u.get('is_web_linked'):
                esc_email = escape_md_v2(u['web_email'])
                card += f"│  🌐 *Web Linked:* Yes \\({esc_email}\\)\n"
            else:
                card += f"│  🌐 *Web Linked:* No\n"

            if u.get('referred_by'):
                referrer = user_lookup.get(u['referred_by'])
                if referrer:
                    ref_name = escape_md_v2(referrer.get('full_name') or "Unknown")
                    ref_uname = escape_md_v2(f"@{referrer['username']}") if referrer.get('username') else ""
                    ref_id = escape_md_v2(str(referrer['telegram_chat_id']))
                    card += f"│  🔗 *Referred by:* {ref_name} {ref_uname} `{ref_id}`\n"
                else:
                    ref_id = escape_md_v2(str(u['referred_by']))
                    card += f"│  🔗 *Referred by:* `{ref_id}`\n"

            if u.get('recruit_list'):
                card += f"│  🤝 *Recruits \\({len(u['recruit_list'])}\\):*\n"
                for rec in u['recruit_list']:
                    r_name = escape_md_v2(rec.get('full_name') or "Unknown")
                    r_uname = escape_md_v2(f"@{rec['username']}") if rec.get('username') else ""
                    r_id = escape_md_v2(str(rec['telegram_chat_id']))
                    card += f"│  └ {r_name} {r_uname} `{r_id}`\n"
            else:
                card += "│  🤝 No recruits yet\n"

            card += "└─────────────────────"
            cards.append(card)

        msg = header + "\n\n".join(cards)

        footer = "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n👑 *Sherpa Overlord Mission Control*"
        footer_kb = InlineKeyboardMarkup(get_admin_keyboard(get_master_wallet()))

        if len(msg) > 4000:
            parts = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
            for i, p in enumerate(parts):
                if i == len(parts) - 1:
                    await context.bot.send_message(chat_id=chat_id, text=p + footer, parse_mode="MarkdownV2", reply_markup=footer_kb)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=p, parse_mode="MarkdownV2")
        else:
            await query.message.reply_text(msg + footer, parse_mode="MarkdownV2", reply_markup=footer_kb)
        return True

    if query.data == "admin_broadcast_prompt":
        if chat_id != SUPER_ADMIN_ID: return True
        clear_input_states(context)
        context.user_data['admin_broadcasting'] = True
        await query.message.reply_text(
            "📢 *Institutional Broadcast Mode*\n\n"
            "Please type the message you would like to send to **ALL** users. "
            "You can use Markdown for formatting.\n\n"
            "Tap /cancel to abort.",
            parse_mode="Markdown"
        )
        return True

    if query.data == "admin_gift_prompt":
        clear_input_states(context)
        context.user_data['admin_gifting'] = True
        await query.message.reply_text(
            "🎁 *Institutional Gifting Center*\n\n"
            "Please enter the **Telegram Chat ID** or **@username** of the user you wish to gift a free month of Premium access to.\n\n"
            "Alternatively, type **`ANY`** to generate a universal unreserved gift code/link that can be redeemed on either the Web App or the Telegram bot.\n\n"
            "Tap /cancel to abort.",
            parse_mode="Markdown"
        )
        return True

    if query.data == "admin_direct_gift_prompt":
        if chat_id != SUPER_ADMIN_ID: return True
        clear_input_states(context)
        context.user_data['admin_direct_gifting'] = True
        await query.message.reply_text(
            "💎 *Direct Premium Extension*\n\n"
            "Please enter the **Telegram Chat ID** or **@username** of the user whose Premium access you wish to directly extend/grant:\n\n"
            "Tap /cancel to abort.",
            parse_mode="Markdown"
        )
        return True

    if query.data.startswith("admin_dg_dur_"):
        if chat_id != SUPER_ADMIN_ID: return True
        await query.answer()
        
        dur_type = query.data.split("_")[-1]
        target_id = context.user_data.get('direct_gift_target_id')
        if not target_id:
            await query.message.reply_text("❌ Session expired or target user ID not found. Please start over.")
            from bot.handlers.admin import show_admin_dashboard
            await show_admin_dashboard(update, context)
            return True
            
        if dur_type == "custom":
            clear_input_states(context)
            context.user_data['direct_gift_target_id'] = target_id
            context.user_data['admin_direct_gifting_custom'] = True
            await query.message.reply_text(
                "⚙️ *Custom Days Extension*\n\n"
                "Please enter the custom number of days you wish to grant:\n\n"
                "Tap /cancel to abort.",
                parse_mode="Markdown"
            )
            return True
            
        try:
            days = int(dur_type)
            database.add_premium_days(target_id, days)
            
            try:
                msg_user = f"💎 *Premium Access Granted/Extended!*\n\nThe Sherpa Overlord has directly granted/extended your Premium Institutional Access by *{days} days*."
                await context.bot.send_message(chat_id=target_id, text=msg_user, parse_mode="Markdown")
                user_notified = "and user has been notified directly"
            except Exception as notify_err:
                user_notified = f"but failed to notify user directly ({notify_err})"
                
            await query.message.reply_text(f"✅ Successfully granted *{days} days* of Premium access to user `{target_id}` {user_notified}.", parse_mode="Markdown")
            context.user_data.pop('direct_gift_target_id', None)
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to extend premium access: {e}")
            
        from bot.handlers.admin import show_admin_dashboard
        await show_admin_dashboard(update, context)
        return True

    if query.data == "admin_revoke_prompt":
        if chat_id != SUPER_ADMIN_ID: return True
        clear_input_states(context)
        context.user_data['admin_revoking'] = True
        await query.message.reply_text(
            "🚫 *Revoke Premium Access*\n\n"
            "Please enter the **Telegram Chat ID** or **@username** of the user whose Premium access you want to revoke.\n\n"
            "Tap /cancel to abort.",
            parse_mode="Markdown"
        )
        return True

    if query.data.startswith("admin_revoke_confirm_"):
        if chat_id != SUPER_ADMIN_ID: return True
        target_id = int(query.data.split("_")[-1])
        database.revoke_premium(target_id)
        
        await query.message.edit_text(
            f"✅ Premium access for user `{target_id}` has been successfully revoked.", 
            parse_mode="Markdown"
        )
        try:
            revoke_msg = "🚫 *Premium Access Revoked*\n\nYour institutional Premium access has been revoked by the Overlord. Your active automation has been paused."
            await context.bot.send_message(chat_id=target_id, text=revoke_msg, parse_mode="Markdown")
        except:
            pass
        return True

    if query.data == "view_logs":
        if chat_id != SUPER_ADMIN_ID: return True
        await query.answer("🔍 Fetching Mission Logs...")
        try:
            import subprocess
            from telegram.helpers import escape_markdown
            logs = subprocess.check_output(["journalctl", "-u", "tradingbot", "-n", "50", "--no-pager"], text=True)
            safe_logs = escape_markdown(logs, version=2)
            
            kb = [[InlineKeyboardButton("🔄 Refresh Logs", callback_data="view_logs")],
                  [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_command")]]
            
            msg = f"📋 *Sherpa Operational Logs* \\(Last 50 Lines\\)\n\n```\n{safe_logs}\n```"
            
            if query.message.text and "Operational Logs" in query.message.text:
                await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="MarkdownV2")
            else:
                await query.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            await query.message.reply_text(f"❌ Failed to fetch logs: {e}")
        return True

    if query.data == "prompt_admin_wallet":
        if chat_id != SUPER_ADMIN_ID: return True
        clear_input_states(context)
        context.user_data['setting_admin_wallet'] = True
        await query.message.reply_text(
            "👑 *Overlord: Update Treasury Address*\n\n"
            "Please send the new **Master USDT (TRC-20) Address** below.\n\n"
            "⚠️ _This will instantly update the destination for all new institutional upgrades._",
            parse_mode="Markdown"
        )
        await query.answer()
        return True

    if query.data == "toggle_undercover":
        if chat_id != SUPER_ADMIN_ID: return True
        database.toggle_undercover(chat_id)
        await query.answer("🔄 Identity Toggled!")
        from bot.handlers.admin import show_admin_dashboard
        await show_admin_dashboard(update, context)
        return True

    if query.data == "toggle_emails_premium":
        if chat_id != SUPER_ADMIN_ID: return True
        current = database.get_config("emails_premium_only", "0")
        new_val = "1" if current == "0" else "0"
        database.update_config("emails_premium_only", new_val)
        await query.answer(f"📧 Alerts Tier: {'Premium Only' if new_val == '1' else 'Everyone'}")
        from bot.handlers.admin import show_admin_dashboard
        await show_admin_dashboard(update, context)
        return True

    if query.data == "admin_manage_strategies":
        if chat_id != SUPER_ADMIN_ID: return True
        await query.answer()
        disabled = database.get_disabled_strategies()
        
        mr_status = "🔴 Retired" if "Mean Reversion Scalper" in disabled else "🟢 Active"
        vk_status = "🔴 Retired" if "Valkyrie Elite Scalper" in disabled else "🟢 Active"
        svp_status = "🔴 Retired" if "Sherpa Velocity Pullback" in disabled else "🟢 Active"
        
        msg = (
            "🎯 *Sherpa Strategy Disablement Center*\n\n"
            "Enable or disable strategies globally. Disabling a strategy will gracefully close active trades before fully retiring the model. No new entry signals will be triggered for retired strategies."
        )
        
        kb = [
            [InlineKeyboardButton(f"📈 Mean Reversion ({mr_status})", callback_data="admin_toggle_strategy_mr")],
            [InlineKeyboardButton(f"🛡️ Valkyrie Elite ({vk_status})", callback_data="admin_toggle_strategy_vk")],
            [InlineKeyboardButton(f"🦙 Stock Pullback ({svp_status})", callback_data="admin_toggle_strategy_svp")],
            [InlineKeyboardButton("🔙 Back to Admin Console", callback_data="admin_command")]
        ]
        await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(kb))
        return True

    if query.data.startswith("admin_toggle_strategy_"):
        if chat_id != SUPER_ADMIN_ID: return True
        strat_key = query.data.split("_")[-1]
        
        strat_mapping = {
            "mr": "Mean Reversion Scalper",
            "vk": "Valkyrie Elite Scalper",
            "svp": "Sherpa Velocity Pullback"
        }
        strat_name = strat_mapping.get(strat_key)
        if strat_name:
            is_now_disabled = database.toggle_strategy(strat_name)
            action_str = "Retired (Disabled)" if is_now_disabled else "Activated (Enabled)"
            await query.answer(f"✅ {strat_name} is now {action_str}!", show_alert=True)
            
            disabled = database.get_disabled_strategies()
            mr_status = "🔴 Retired" if "Mean Reversion Scalper" in disabled else "🟢 Active"
            vk_status = "🔴 Retired" if "Valkyrie Elite Scalper" in disabled else "🟢 Active"
            svp_status = "🔴 Retired" if "Sherpa Velocity Pullback" in disabled else "🟢 Active"
            
            msg = (
                "🎯 *Sherpa Strategy Disablement Center*\n\n"
                "Enable or disable strategies globally. Disabling a strategy will gracefully close active trades before fully retiring the model. No new entry signals will be triggered for retired strategies."
            )
            
            kb = [
                [InlineKeyboardButton(f"📈 Mean Reversion ({mr_status})", callback_data="admin_toggle_strategy_mr")],
                [InlineKeyboardButton(f"🛡️ Valkyrie Elite ({vk_status})", callback_data="admin_toggle_strategy_vk")],
                [InlineKeyboardButton(f"🦙 Stock Pullback ({svp_status})", callback_data="admin_toggle_strategy_svp")],
                [InlineKeyboardButton("🔙 Back to Admin Console", callback_data="admin_command")]
            ]
            await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(kb))
        return True

    if query.data == "admin_view_free_trades":
        if chat_id != SUPER_ADMIN_ID and not (user and user.get('is_admin')): return True
        
        await query.answer("Fetching free signals...")
        open_sim_trades = database.get_open_theoretical_trades()
        trades = database.get_recent_theoretical_trades(10)
        
        photo_ids = []
        
        if open_sim_trades:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🛰️ *Live Free Signals Found: {len(open_sim_trades)}*\nGenerating progress charts...",
                parse_mode="Markdown"
            )
            
            mdm = live_bot_multi.MarketDataManager()
            try:
                for t in open_sim_trades:
                    sym = t['symbol']
                    side = t['side']
                    entry = t['entry_price']
                    tp = t['tp_price']
                    sl = t['sl_price']
                    open_ts = t['open_time']
                    pos_size = t['position_size']
                    strat = t['strategy']
                    
                    if is_stock(sym):
                        try:
                            import pandas as pd
                            conn = sqlite3.connect("data/stock_daily_cache.db")
                            df_chart = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC", conn, params=(sym,))
                            conn.close()
                            if not df_chart.empty:
                                df_chart['timestamp'] = pd.to_datetime(df_chart['date']).astype('datetime64[ms]').astype('int64')
                                df_chart = df_chart.copy()
                            else:
                                df_chart = None
                        except Exception as stock_db_err:
                            logger.error(f"Failed to fetch stock daily cache for {sym}: {stock_db_err}")
                            df_chart = None
                    else:
                        df_chart = await mdm.fetch_ohlcv(sym, "15m")
                        
                    if df_chart is None or (hasattr(df_chart, 'empty') and df_chart.empty):
                        continue
                        
                    current = float(df_chart['close'].iloc[-1])
                    side_lower = str(side).lower()
                    pnl_raw = current - entry if side_lower in ['buy', 'long'] else entry - current
                    pnl_pct = (pnl_raw / entry) * 100
                    
                    currency = get_currency(sym)
                    if is_stock(sym):
                        pnl_val = pos_size * (pnl_pct / 100)
                    else:
                        pnl_pct *= CRYPTO_LEVERAGE
                        pnl_val = pos_size * pnl_raw
                    
                    side_str = "LONG" if side_lower in ['buy', 'long'] else "SHORT"
                    
                    chart_file = None
                    try:
                        tf = "1D" if is_stock(sym) else "15M"
                        curr = "USD" if is_stock(sym) else "USDT"
                        chart_file = await asyncio.to_thread(
                            charting.generate_trade_chart,
                            sym,
                            df_chart,
                            entry,
                            tp,
                            sl,
                            side_str,
                            open_ts=open_ts,
                            timeframe=tf,
                            currency=curr,
                            strategy=strat
                        )
                    except Exception as chart_err:
                        logger.error(f"Free chart generation failed for {sym}: {chart_err}")
                    
                    caption = (
                        f"🧪 *ACTIVE FREE SIGNAL* \n"
                        f"🤖 Strategy: *{strat}*\n\n"
                        f"{'🟢' if side_str == 'LONG' else '🔴'} *{sym} ({side_str})*\n"
                        f"PnL: ||{pnl_pct:+.2f}% ({pnl_val:+.2f} {currency})|| of target\n"
                        f"• Entry: `{format_price(entry, sym)}` | SL: `{format_price(sl, sym)}` | TP: `{format_price(tp, sym)}`"
                    )
                    
                    kb = [[InlineKeyboardButton("🔙 Back to Admin Control", callback_data="admin_command")]]
                    
                    if chart_file and os.path.exists(chart_file):
                        with open(chart_file, 'rb') as photo:
                            msg = await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=photo,
                                caption=caption,
                                parse_mode="Markdown",
                                reply_markup=InlineKeyboardMarkup(kb)
                            )
                            photo_ids.append(msg.message_id)
                    else:
                        msg = await context.bot.send_message(
                            chat_id=chat_id,
                            text=caption,
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
            finally:
                await mdm.close()
                
            if photo_ids:
                context.user_data['admin_free_photo_ids'] = photo_ids
                
        if not trades:
            msg = (
                "🔬 *Recent Free Forward Trades*\n\n"
                "No free signals have been opened or resolved yet on this platform! ⏳\n\n"
                "Once the 15-minute engine completes signal passes and places free signals, they will be logged here."
            )
        else:
            msg_parts = ["🔬 *Recent Free Forward Trades Summary*\n_Showing last 10 activities_\n"]
            for t in trades:
                open_time_str = "???"
                if t.get('open_time'):
                    open_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t['open_time'] / 1000))
                
                direction = "LONG 📈" if t['side'] in ['buy', 'long', 'LONG'] else "SHORT 📉"
                strat_name = t['strategy']
                if "Mean Reversion" in strat_name:
                    strat_icon = "📈"
                    strat_short = "Mean Rev"
                elif "Valkyrie" in strat_name:
                    strat_icon = "🛡️"
                    strat_short = "Valkyrie"
                else:
                    strat_icon = "🏔️"
                    strat_short = "Pullback"
                
                curr = get_currency(t['symbol'])
                if t['status'] == 'open':
                    status_line = "⏳ *OPEN POSITION*"
                    pnl_line = ""
                    price_line = f"• Entry: `{format_price(t['entry_price'], t['symbol'])}` | SL: `{format_price(t['sl_price'], t['symbol'])}` | TP: `{format_price(t['tp_price'], t['symbol'])}`"
                else:
                    status_icon = "✅ Take Profit" if t['status'] == 'tp' else ("❌ Stop Loss" if t['status'] == 'sl' else f"⚠️ {t['status'].upper()}")
                    status_line = f"Resolved: *{status_icon}*"
                    pnl_line = f"\n  PnL: *{t['pnl_pct']:+.2f}% ({t['pnl_usdt']:+.2f} {curr})*"
                    exit_price = t['tp_price'] if t['status'] == 'tp' else t['sl_price']
                    price_line = f"• Entry: `{format_price(t['entry_price'], t['symbol'])}` | Exit: `{format_price(exit_price, t['symbol'])}`"
                
                msg_parts.append(
                    f"• *{t['symbol']}* ({direction}) | {strat_icon} _{strat_short}_\n"
                    f"  {status_line}{pnl_line}\n"
                    f"  {price_line}\n"
                    f"  Opened: _{open_time_str}_\n"
                )
            msg = "\n".join(msg_parts)
            
        kb = [[InlineKeyboardButton("🔙 Back to Admin Control", callback_data="admin_command")]]
        
        if open_sim_trades:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            await safe_edit_text(update, context, msg, reply_markup=InlineKeyboardMarkup(kb))
        return True

    if query.data.startswith("admin_approve_strat_"):
        if chat_id != SUPER_ADMIN_ID: return True
        strat_id = query.data.replace("admin_approve_strat_", "")
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("UPDATE UserStrategies SET sharing_status = 'approved' WHERE id = ?", (strat_id,))
        await query.answer("Strategy approved!")
        await safe_edit_text(update, context, f"Strategy ID {strat_id} has been approved for the marketplace.")
        return True
        
    if query.data.startswith("admin_reject_strat_"):
        if chat_id != SUPER_ADMIN_ID: return True
        strat_id = query.data.replace("admin_reject_strat_", "")
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("UPDATE UserStrategies SET sharing_status = 'rejected' WHERE id = ?", (strat_id,))
        await query.answer("Strategy rejected!")
        await safe_edit_text(update, context, f"Strategy ID {strat_id} has been rejected from the marketplace.")
        return True

    return False
