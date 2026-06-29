import time
import asyncio
import ccxt.async_support as ccxt

import database
from bot.config import logger
from bot.engines.base import SHARED_MARKETS, SHARED_MARKETS_TIME, SHARED_MARKETS_LOCK
from utils_error import send_telegram_alert

async def handle_auth_failure(user, exception_str, application):
    """
    Detects if an exception is an unrecoverable auth error.
    If so, clears credentials, alerts the user, and sends a system alert.
    """
    auth_keywords = [
        "AuthenticationError", "PermissionDenied", "403 Forbidden", "401 Unauthorized",
        "10024", "Unmatched IP", "regulatory restrictions", "Invalid API-key", "Invalid API Key"
    ]
    if any(k.lower() in exception_str.lower() for k in auth_keywords):
        chat_id = user.get('telegram_chat_id')
        web_user_id = user.get('web_user_id')
        
        database.invalidate_exchange_credentials(chat_id=chat_id, web_user_id=web_user_id)
        
        ex_id = user.get('exchange_id', 'exchange').capitalize()
        user_id_str = str(chat_id) if chat_id else f"Web_{web_user_id}"
        
        # Notify admins using global exception handler formatting
        error_msg = f"User {user_id_str} API Key unlinked due to authentication failure.\\nExchange: {ex_id}\\nReason: {exception_str}"
        logger.warning(error_msg)
        send_telegram_alert("API Key Auto-Revoked", error_msg, tb_string="")
        
        # Notify user if they are a telegram user
        if chat_id and application:
            user_msg = (
                f"⚠️ **API Key Revoked**\\n\\n"
                f"We couldn't connect to your **{ex_id}** exchange account. "
                f"Your API credentials have been unlinked for your security and to prevent background errors.\\n\\n"
                f"**Reason:** `{exception_str}`\\n\\n"
                f"Please verify your API Key and Secret, ensure the IPs are correctly whitelisted, and add them again via the /keys command or Web App.\\n\\n"
                f"If you believe this is an error, please take a screenshot of this message and notify the system admins for support."
            )
            try:
                await application.bot.send_message(chat_id=chat_id, text=user_msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send API revocation notice to {chat_id}: {e}")

async def sync_engine(application):
    """
    Sentinel Sync Task (60s loop)
    
    Responsibilities:
    - Iterates over all active users with connected API keys.
    - Asynchronously fetches their current futures/swap account balance via CCXT.
    - Updates the database with their current equity to ensure PnL stats in the UI are accurate.
    - Uses asyncio.gather for parallel network requests to prevent blocking.
    """
    logger.debug("📡 Starting Sentinel Sync Task (60s Notifications)...")
    while True:
        try:
            active_users = database.get_all_active_users()
            if not active_users:
                await asyncio.sleep(60)
                continue
            
            sem = asyncio.Semaphore(3)
            async def sync_user(user):
                async with sem:
                    try:
                        chat_id = user.get('telegram_chat_id')
                        web_user_id = user.get('web_user_id')
                        
                        # 1. Sync Crypto
                        if user.get('api_key'):
                            ex_id = user.get('exchange_id', 'blofin')
                            if ex_id == 'alpaca': ex_id = 'blofin'
                            futures_type = user.get('bingx_futures_type', 'standard') or 'standard'
                            try:
                                async with database.get_exchange_client(user) as user_ex:
                                    async with SHARED_MARKETS_LOCK:
                                        cache_time = SHARED_MARKETS_TIME.get(user_ex.id, 0)
                                        if user_ex.id in SHARED_MARKETS and (time.time() - cache_time) < 900:
                                            user_ex.markets = SHARED_MARKETS[user_ex.id]
                                        else:
                                            await user_ex.load_markets()
                                            SHARED_MARKETS[user_ex.id] = user_ex.markets
                                            SHARED_MARKETS_TIME[user_ex.id] = time.time()
                                    
                                    bal_params = database.get_exchange_balance_params(user_ex.id, futures_type=futures_type)
                                    balance = await user_ex.fetch_balance(params=bal_params)
                                    if user_ex.id == 'coinbase':
                                        usd_bal = balance.get('USD', {})
                                        usdc_bal = balance.get('USDC', {})
                                        if not isinstance(usd_bal, dict): usd_bal = {}
                                        if not isinstance(usdc_bal, dict): usdc_bal = {}
                                        equity = float(usd_bal.get("total") or usd_bal.get("free") or balance.get("free", {}).get("USD") or balance.get("total", {}).get("USD") or 0.0) + float(usdc_bal.get("total") or usdc_bal.get("free") or balance.get("free", {}).get("USDC") or balance.get("total", {}).get("USDC") or 0.0)
                                    else:
                                        asset = 'USDT'
                                        equity = float(balance.get(asset, {}).get("total", 0) or balance.get(asset, {}).get("free", 0) or 0.0)
                                    await database.update_user_stats_from_engine(chat_id, equity, user_ex, application, web_user_id=web_user_id)
                            except Exception as e:
                                e_str = str(e)
                                logger.error(f"Sync error for user {chat_id or f'web_{web_user_id}'} on exchange {ex_id} ({futures_type} futures): {e}")
                                await handle_auth_failure(user, e_str, application)
                                
                        # 2. Sync Stocks
                        if user.get('alpaca_api_key'):
                            # Stocks stats update logic can be minimal as Alpaca provides portfolio value directly
                            pass
                    except Exception as e:
                        logger.error(f"General sync error for user {user.get('telegram_chat_id') or 'web_' + str(user.get('web_user_id', '?'))}: {e}")

            await asyncio.gather(*(sync_user(u) for u in active_users))
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Sentinel critical failure: {e}")
            await asyncio.sleep(60)
