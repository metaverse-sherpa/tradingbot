import time
import asyncio
import ccxt.async_support as ccxt

import database
from bot.config import logger
from bot.engines.base import SHARED_MARKETS, SHARED_MARKETS_TIME, SHARED_MARKETS_LOCK

async def sync_engine(application):
    """
    Sentinel Sync Task (60s loop)
    
    Responsibilities:
    - Iterates over all active users with connected API keys.
    - Asynchronously fetches their current futures/swap account balance via CCXT.
    - Updates the database with their current equity to ensure PnL stats in the UI are accurate.
    - Uses asyncio.gather for parallel network requests to prevent blocking.
    """
    logger.info("📡 Starting Sentinel Sync Task (60s Notifications)...")
    while True:
        try:
            active_users = database.get_all_active_users()
            if not active_users:
                await asyncio.sleep(60)
                continue
            
            async def sync_user(user):
                try:
                    chat_id = user.get('telegram_chat_id')
                    web_user_id = user.get('web_user_id')
                    
                    # 1. Sync Crypto
                    if user.get('api_key'):
                        ex_id = user.get('exchange_id', 'blofin')
                        if ex_id == 'alpaca': ex_id = 'blofin'
                        futures_type = user.get('bingx_futures_type', 'standard') or 'standard'
                        default_type = 'swap'
                        ex_class = getattr(ccxt, ex_id)
                        try:
                            async with ex_class({
                                "apiKey": user['api_key'],
                                "secret": user['api_secret'],
                                **({"password": user['api_password']} if user['api_password'] else {}),
                                "options": {"defaultType": default_type},
                            }) as user_ex:
                                async with SHARED_MARKETS_LOCK:
                                    cache_time = SHARED_MARKETS_TIME.get(ex_id, 0)
                                    if ex_id in SHARED_MARKETS and (time.time() - cache_time) < 900:
                                        user_ex.markets = SHARED_MARKETS[ex_id]
                                    else:
                                        await user_ex.load_markets()
                                        SHARED_MARKETS[ex_id] = user_ex.markets
                                        SHARED_MARKETS_TIME[ex_id] = time.time()
                                
                                bal_params = database.get_exchange_balance_params(ex_id, futures_type=futures_type)
                                balance = await user_ex.fetch_balance(params=bal_params)
                                if ex_id == 'coinbase':
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
                            logger.error(f"Sync error for user {chat_id or f'web_{web_user_id}'} on exchange {ex_id} ({futures_type} futures): {e}")
                            
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
