from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bot.handlers.system import start, setup, cancel_command, docs, stop_bot, resume_bot, diagnose_command
from bot.handlers.auth import handle_message
from bot.handlers.trading import stats, stats_simulated, open_trades, list_trades, backtest, balance_command, share_callback, privacy_command
from bot.handlers.strategy import strategy_command, strategy_guide_command, strategy_callback
from bot.handlers.admin import promote_command, demote_command, admin_command, sql_command, dbinspect_command, refer_command, show_premium_menu
from bot.handlers.settings import settings_command, settings_callback

def register_handlers(app):
    # Register Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("refer", refer_command))
    app.add_handler(CommandHandler("premium", show_premium_menu))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("docs", docs))
    app.add_handler(CommandHandler("help", docs))
    app.add_handler(CommandHandler("setup", setup))
    app.add_handler(CommandHandler("reset", setup))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("forwardtest", stats_simulated))
    app.add_handler(CommandHandler("fstats", stats_simulated))
    app.add_handler(CommandHandler("opentrades", open_trades))
    app.add_handler(CommandHandler("list", list_trades))
    app.add_handler(CommandHandler("backtest", backtest))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("diagnose", diagnose_command))
    app.add_handler(CommandHandler("sql", sql_command))
    app.add_handler(CommandHandler("dbinspect", dbinspect_command))
    app.add_handler(CommandHandler("strategy", strategy_command))
    app.add_handler(CommandHandler("strategyguide", strategy_guide_command))
    app.add_handler(CommandHandler("promote", promote_command))
    app.add_handler(CommandHandler("demote", demote_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("resume", resume_bot))

    # Register Callback Query Handlers
    app.add_handler(CallbackQueryHandler(strategy_callback, pattern="^set_strat_"))
    app.add_handler(CallbackQueryHandler(share_callback, pattern="^sh"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^capital_menu|^set_cap_all|^set_cap_amount_prompt|^set_cap_pct_prompt|^run_backtest|^admin_get_link|^send_blofin_guide|^apply_symbol_audit|^toggle_privacy|^strategy_menu|^toggle_active|^set_risk|^set_risk_to_|^manage_symbols|^tsym_|^back_to_settings|^setex_|^check_balance_setup|^opentrades_menu|^history_menu|^stats_menu|^help_menu|^settings_menu|^contact_menu|^refer_menu|^referral_menu|^confirm_panic|^panic_execute|^confirm_close_|^execute_close_|^admin_user_audit|^admin_broadcast_prompt|^admin_command|^admin_gift_prompt|^view_logs|^prompt_admin_wallet|^toggle_undercover|^close_admin|^premium_menu|^check_payment|^prompt_set_wallet|^activate_with_credits|^admin_view_simulated_trades|^view_strategy_guide|^switch_exchange_prompt|^dummy_spacer|^virtual_active|^virtual_closed"))

    # Catch all non-command messages (used for the setup step flow)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
