import os
import sys
import time
import json
import asyncio
import threading
import sqlite3
import requests
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCK_DB_PATH = os.path.join(ROOT_DIR, "data", "stock_daily_cache.db")

from flask import Blueprint, request, jsonify, make_response, g, send_file
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import database
import utils_gcp
import media_gen
def is_us_market_open():
    """Checks if the US stock market is currently open (9:30 AM - 4:00 PM Eastern Time, Monday-Friday)."""
    import datetime
    import pytz
    try:
        tz_et = pytz.timezone('US/Eastern')
        now_et = datetime.datetime.now(tz_et)
        # 0 = Monday, ..., 4 = Friday
        if now_et.weekday() >= 5:
            return False
        market_start = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        market_end = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_start <= now_et <= market_end
    except Exception as e:
        print(f"Error checking market hours: {e}")
        return True # Default to True so updates aren't blocked if timezone check fails

def is_stock(symbol):
    """Determines if a symbol is a stock ticker."""
    symbol_str = str(symbol).upper()
    return symbol_str and "/" not in symbol_str and ":" not in symbol_str and "USDT" not in symbol_str
from web_api.auth import require_auth
from web_api.cache import RESPONSE_CACHE, RESPONSE_CACHE_LOCK, CACHE_TTL_SECONDS

trades_bp = Blueprint('trades', __name__)

# Global thread pool for executing slow exchange API queries with timeouts
THREAD_POOL = ThreadPoolExecutor(max_workers=20)

def run_with_timeout(func, timeout_sec, fallback):
    try:
        future = THREAD_POOL.submit(func)
        return future.result(timeout=timeout_sec)
    except Exception as e:
        print(f"[TIMEOUT HELPER] Task failed, exceeded timeout ({timeout_sec}s), or threw error: {e}")
        return fallback

# Module-level variable to prevent concurrent background updates for active signals
SIGNALS_ACTIVE_UPDATING = False
SIGNALS_ACTIVE_UPDATING_LOCK = threading.RLock()

# Module-level variable to prevent concurrent background updates for free stats
STATS_FREE_UPDATING = False
STATS_FREE_UPDATING_LOCK = threading.RLock()

def _get_telegram_user(web_user):
    """If the web user has linked a Telegram chat ID, load the bot's User record."""
    tg_id = web_user.get("telegram_chat_id")
    if tg_id:
        try:
            return database.get_user(int(tg_id))
        except Exception as e:
            print(f"Could not load Telegram user {tg_id}: {e}")
    return None

@trades_bp.route('/api/user/profile', methods=['GET'])
@require_auth
def profile():
    user = g.user
    # Mask password hashes and raw sensitive keys for the response payload
    user.pop("password_hash", None)
    
    # Convert enabled_symbols string back to array
    def_syms = "BTC,ETH,SOL,DOGE,ADA,LINK,DOT,TON,ZEC,PEPE,BNB,NEAR,SUI,NOT,TAO,ONDO,ENA,FET,WIF"
    user["enabled_symbols"] = (user.get("enabled_symbols") or def_syms).split(",")
    
    # Determine premium level
    now = int(time.time())
    tg_user = _get_telegram_user(user)
    
    web_premium_expiry = user.get("premium_expiry") or 0
    bot_premium_expiry = (tg_user.get("premium_expiry") or 0) if tg_user else 0
    max_expiry = max(web_premium_expiry, bot_premium_expiry)
    
    super_admin_id = utils_gcp.get_secret("SUPER_ADMIN_ID")
    is_super_admin = False
    if super_admin_id:
        try:
            super_admin_id = int(super_admin_id)
            if user.get("telegram_chat_id") == super_admin_id or (tg_user and tg_user.get("telegram_chat_id") == super_admin_id):
                is_super_admin = True
        except ValueError:
            pass
            
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    user["is_premium"] = max_expiry > now or is_admin
    
    # Merge active strategies from bot user
    user["active_crypto_strategy"] = (tg_user or {}).get("active_crypto_strategy") or user.get("active_crypto_strategy", "Mean Reversion Scalper")
    user["active_stock_strategy"] = (tg_user or {}).get("active_stock_strategy") or user.get("active_stock_strategy", "Sherpa Velocity Pullback")
    
    # Sync hide_dollars setting from Telegram user if linked, otherwise default to True
    if tg_user:
        user["hide_dollars"] = tg_user.get("hide_dollars") if tg_user.get("hide_dollars") is not None else True
    else:
        user["hide_dollars"] = user.get("hide_dollars") if user.get("hide_dollars") is not None else True
    
    # Indicate if keys are configured (masking the actual keys)
    user["has_exchange_keys"] = bool((tg_user or {}).get("api_key") or user.get("api_key"))
    user["has_alpaca_keys"] = bool((tg_user or {}).get("alpaca_api_key") or user.get("alpaca_api_key"))
    
    user["exchange_id"] = user.get("exchange_id") or (tg_user or {}).get("exchange_id")
    user["alpaca_endpoint"] = user.get("alpaca_endpoint") or (tg_user or {}).get("alpaca_endpoint")
    
    # Fetch recruits for referral UI
    recruit_list = []
    if tg_user:
        try:
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT full_name, username, telegram_chat_id FROM Users WHERE referred_by = ?", (tg_user["telegram_chat_id"],))
                recruit_list = [dict(rec) for rec in c.fetchall()]
        except Exception as e:
            print(f"Could not load recruits: {e}")
    user["recruit_list"] = recruit_list
    user["disabled_strategies"] = database.get_disabled_strategies()

    user["server_time"] = now
    return jsonify(user), 200

@trades_bp.route('/api/user/balance', methods=['GET'])
@require_auth
def get_balance():
    user = g.user
    user_id = user["id"]
    segment = request.args.get("segment") # 'crypto' or 'stock'
    bypass_cache = request.args.get("bypass_cache", "false").lower() == "true"
    
    # Check cache
    now = time.time()
    cache_key = ("balance", user_id, segment)
    with RESPONSE_CACHE_LOCK:
        if not bypass_cache and cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            if now < expiry:
                return jsonify(cached_data), 200

    tg_user = _get_telegram_user(user)
    balance_crypto = 0.0
    balance_stock = 0.0
    
    # Use the linked Telegram user's exchange keys if available
    crypto_api_key = (tg_user or {}).get("api_key") or user.get("api_key")
    crypto_api_secret = (tg_user or {}).get("api_secret") or user.get("api_secret")
    crypto_api_password = (tg_user or {}).get("api_password") or user.get("api_password") or ""
    crypto_exchange_id = (tg_user or {}).get("exchange_id") or user.get("exchange_id", "blofin")
    
    # 1. Query live Crypto balance (CCXT)
    if (not segment or segment == 'crypto') and crypto_api_key and crypto_api_secret:
        def fetch_crypto_balance():
            import ccxt
            default_type = "swap"
            config = {
                "apiKey": crypto_api_key,
                "secret": crypto_api_secret,
                "password": crypto_api_password,
                "options": {"defaultType": default_type},
                "enableRateLimit": False,
                "timeout": 4000,
            }
            client = getattr(ccxt, crypto_exchange_id)(config)
            try:
                futures_type = (tg_user or {}).get("bingx_futures_type") or user.get("bingx_futures_type", "standard")
                bal_params = database.get_exchange_balance_params(crypto_exchange_id, futures_type=futures_type)
                bal = client.fetch_balance(params=bal_params)
                usdt_bal = bal.get('USDT', {})
                if not isinstance(usdt_bal, dict):
                    usdt_bal = {}
                free_usdt = float(usdt_bal.get('free') or usdt_bal.get('total') or bal.get('free', {}).get('USDT') or bal.get('total', {}).get('USDT') or 0.0)
                
                total_equity = free_usdt
                try:
                    positions = client.fetch_positions()
                    for p in positions:
                        margin = float(p.get('initialMargin') or p.get('margin') or p.get('info', {}).get('margin') or 0)
                        upnl = float(p.get('unrealizedPnl') or p.get('info', {}).get('unrealizedPnl') or 0)
                        total_equity += (margin + upnl)
                except Exception as pos_err:
                    print(f"Error fetching positions for balance: {pos_err}")
                return total_equity
            finally:
                try:
                    client.close()
                except Exception:
                    pass

        db_fallback = float((tg_user or {}).get("equity") or user.get("equity") or 0.0)
        balance_crypto = run_with_timeout(fetch_crypto_balance, 6.0, db_fallback)
    elif not segment or segment == 'crypto':
        balance_crypto = float((tg_user or {}).get("equity") or user.get("equity") or 0.0)
            
    # 2. Query live Stock balance (Alpaca)
    # Use linked Telegram user's Alpaca keys if available
    alpaca_key = (tg_user or {}).get("alpaca_api_key") or user.get("alpaca_api_key")
    alpaca_secret = (tg_user or {}).get("alpaca_api_secret") or user.get("alpaca_api_secret")
    
    if (not segment or segment == 'stock') and alpaca_key and alpaca_secret:
        def fetch_stock_balance():
            alpaca_user = tg_user or user
            res = database.make_alpaca_request(alpaca_user, "GET", "/v2/account")
            return float(res.get("portfolio_value", 0.0))
        
        balance_stock = run_with_timeout(fetch_stock_balance, 6.0, 0.0)
            
    if segment == 'crypto':
        response_data = {
            "crypto_balance": balance_crypto,
            "stock_balance": 0.0,
            "total_balance": balance_crypto
        }
    elif segment == 'stock':
        response_data = {
            "crypto_balance": 0.0,
            "stock_balance": balance_stock,
            "total_balance": balance_stock
        }
    else:
        response_data = {
            "crypto_balance": balance_crypto,
            "stock_balance": balance_stock,
            "total_balance": balance_crypto + balance_stock
        }
    
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = (now + CACHE_TTL_SECONDS, response_data)
        
    return jsonify(response_data), 200

@trades_bp.route('/api/user/stats', methods=['GET'])
@require_auth
def get_stats():
    user = g.user
    user_id = user["id"]
    segment = request.args.get("segment") # 'crypto' or 'stock'
    bypass_cache = request.args.get("bypass_cache", "false").lower() == "true"
    
    # Check cache
    now = time.time()
    cache_key = ("stats", user_id, segment)
    with RESPONSE_CACHE_LOCK:
        if not bypass_cache and cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            if now < expiry:
                return jsonify(cached_data), 200

    tg_user = _get_telegram_user(user) or user
    
    # 1. Crypto Stats
    crypto_wins = tg_user.get("wins", tg_user.get("total_wins", 0))
    if crypto_wins is None: crypto_wins = 0
    crypto_losses = tg_user.get("losses", tg_user.get("total_losses", 0))
    if crypto_losses is None: crypto_losses = 0
    crypto_total = crypto_wins + crypto_losses
    crypto_win_rate = round((crypto_wins / crypto_total) * 100, 1) if crypto_total > 0 else 0.0
    
    crypto_equity = tg_user.get("equity", 1000.0) or 1000.0
    crypto_cum_pnl = tg_user.get("cum_pnl", tg_user.get("cumulative_pnl", 0.0)) or 0.0
    
    crypto_unrealized = 0.0
    crypto_open_count = 0
    
    # Attempt CCXT fetch if keys exist
    crypto_api_key = tg_user.get("api_key")
    crypto_api_secret = tg_user.get("api_secret")
    crypto_api_password = tg_user.get("api_password")
    crypto_exchange_id = tg_user.get("exchange_id", "blofin")
    
    if (not segment or segment == 'crypto') and crypto_api_key and crypto_api_secret:
        def fetch_crypto_stats():
            import ccxt
            default_type = "swap"
            config = {
                "apiKey": crypto_api_key,
                "secret": crypto_api_secret,
                "password": crypto_api_password or "",
                "options": {"defaultType": default_type},
                "enableRateLimit": False,
                "timeout": 4000
            }
            client = getattr(ccxt, crypto_exchange_id)(config)
            try:
                open_count = 0
                unrealized = 0.0
                positions = client.fetch_positions()
                for p in positions:
                    contracts = float(p.get("contracts", 0) or 0)
                    if contracts != 0:
                        open_count += 1
                        unrealized += float(p.get("unrealizedPnl", 0) or 0)
                return open_count, unrealized
            finally:
                try: client.close()
                except: pass

        open_count, unrealized = run_with_timeout(fetch_crypto_stats, 6.0, (0, 0.0))
        crypto_open_count = open_count
        crypto_unrealized = unrealized
            
    crypto_overall_pnl = crypto_cum_pnl + crypto_unrealized
    crypto_overall_pnl_pct = round((crypto_overall_pnl / crypto_equity) * 100, 2) if crypto_equity > 0 else 0.0
    
    # 2. Stock Stats
    stock_equity = 10000.0
    stock_start_equity = 10000.0
    stock_unrealized = 0.0
    stock_open_count = 0
    stock_closed_count = 0
    stock_wins = 0
    stock_losses = 0
    
    stock_api_key = tg_user.get("alpaca_api_key")
    stock_api_secret = tg_user.get("alpaca_api_secret")
    
    if (not segment or segment == 'stock') and stock_api_key and stock_api_secret:
        def fetch_stock_stats():
            eq = 10000.0
            start_eq = 10000.0
            unreal = 0.0
            open_c = 0
            closed_c = 0
            w = 0
            l = 0
            
            acc = database.make_alpaca_request(tg_user, "GET", "/v2/account")
            if acc:
                eq = float(acc.get("equity", 0) or acc.get("portfolio_value", 0))
                
            # Use the user's configured starting equity if set. Otherwise, query Alpaca's portfolio history.
            start_eq = tg_user.get("alpaca_start_equity") or user.get("alpaca_start_equity")
            if not start_eq:
                try:
                    portfolio_hist = database.make_alpaca_request(tg_user, "GET", "/v2/account/portfolio/history", params={"period": "all", "timeframe": "1D"})
                    if portfolio_hist and portfolio_hist.get("base_value") is not None:
                        start_eq = float(portfolio_hist["base_value"])
                    elif portfolio_hist and portfolio_hist.get("equity") and len(portfolio_hist["equity"]) > 0:
                        start_eq = float(portfolio_hist["equity"][0])
                except Exception as hist_err:
                    print(f"Error fetching Alpaca portfolio history starting equity: {hist_err}")
                
                # Fallback to current equity or 10k if history query failed/returned zero
                if not start_eq or start_eq <= 0:
                    start_eq = eq or 10000.0
                
                # Save it to the database so we never hit Alpaca's slow history endpoint again
                if start_eq and start_eq > 0:
                    try:
                        with database.db_session() as conn:
                            c = conn.cursor()
                            if tg_user.get("telegram_chat_id"):
                                c.execute("UPDATE Users SET alpaca_start_equity = ? WHERE telegram_chat_id = ?", (start_eq, tg_user["telegram_chat_id"]))
                            c.execute("UPDATE WebUsers SET alpaca_start_equity = ? WHERE id = ?", (start_eq, user_id))
                            conn.commit()
                    except Exception as db_save_err:
                        print(f"Error saving alpaca_start_equity: {db_save_err}")
                
            positions = database.make_alpaca_request(tg_user, "GET", "/v2/positions")
            if isinstance(positions, list):
                open_c = len(positions)
                unreal = sum(float(p.get("unrealized_pl", 0) or p.get("unrealized_intraday_pl", 0) or 0) for p in positions)
                
            orders = database.make_alpaca_request(tg_user, "GET", "/v2/orders", params={"status": "closed", "limit": 100})
            if isinstance(orders, list):
                closed_c = len(orders)
                # Compute actual stock wins/losses from closed orders on Alpaca
                for o in orders:
                    qty = float(o.get("filled_qty", 0) or 0)
                    if qty > 0 and o.get("side") == "sell":
                        price = float(o.get("filled_avg_price", 0))
                        entry = price
                        for prev in orders:
                            if prev["symbol"] == o["symbol"] and prev["side"] == "buy":
                                entry = float(prev.get("filled_avg_price", price))
                                break
                        pnl_raw = (price - entry) * qty
                        if pnl_raw > 0:
                            w += 1
                        else:
                            l += 1
            return eq, start_eq, unreal, open_c, closed_c, w, l

        stock_stats_fallback = (stock_equity, stock_start_equity, stock_unrealized, stock_open_count, stock_closed_count, stock_wins, stock_losses)
        stock_equity, stock_start_equity, stock_unrealized, stock_open_count, stock_closed_count, stock_wins, stock_losses = run_with_timeout(
            fetch_stock_stats, 6.0, stock_stats_fallback
        )
            
    # Calculate stock growth from starting base
    stock_overall_pnl = stock_equity - stock_start_equity
    stock_overall_pnl_pct = round((stock_overall_pnl / stock_start_equity) * 100, 2) if stock_start_equity > 0 else 0.0
    
    # If not retrieved directly from Alpaca API, fall back to AlpacaActiveTrades table
    if (not segment or segment == 'stock') and stock_wins == 0 and stock_losses == 0:
        if tg_user.get("telegram_chat_id"):
            trade_chat_id = int(tg_user["telegram_chat_id"])
        else:
            trade_chat_id = int(user["id"]) + 1000000000
            
        try:
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND status = 'closed' AND pnl_raw > 0", (trade_chat_id,))
                stock_wins = c.fetchone()[0] or 0
                c.execute("SELECT COUNT(*) FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND status = 'closed' AND pnl_raw <= 0", (trade_chat_id,))
                stock_losses = c.fetchone()[0] or 0
        except:
            stock_wins = 0
            stock_losses = 0
        
    stock_total_trades = stock_wins + stock_losses
    
    # If still 0, fallback to computing win rate from the latest history cache (filtering for stock symbols only)
    if (not segment or segment == 'stock') and stock_total_trades == 0:
        raw_cache = tg_user.get("history_cache") or user.get("history_cache")
        if raw_cache:
            try:
                import json
                cached = json.loads(raw_cache) if isinstance(raw_cache, str) else raw_cache
                for tr in cached:
                    if "symbol" in tr and is_stock(tr.get("symbol")): # Check if it's a valid stock trade object
                        pnl = float(tr.get("pnl_raw", 0) or tr.get("net_pnl", 0) or tr.get("pnl_pct", 0) or 0)
                        if pnl > 0: stock_wins += 1
                        else: stock_losses += 1
                stock_total_trades = stock_wins + stock_losses
            except: pass
            
    stock_win_rate = round((stock_wins / stock_total_trades) * 100, 1) if stock_total_trades > 0 else 0.0
    
    response_data = {
        "crypto": {
            "portfolio_value": crypto_equity,
            "overall_pnl": crypto_overall_pnl,
            "overall_pnl_pct": crypto_overall_pnl_pct,
            "wins": crypto_wins,
            "losses": crypto_losses,
            "total_trades": crypto_total,
            "win_rate": crypto_win_rate,
            "open_positions": crypto_open_count,
            "unrealized_pnl": crypto_unrealized
        },
        "stock": {
            "portfolio_value": stock_equity,
            "overall_pnl": stock_overall_pnl,
            "overall_pnl_pct": stock_overall_pnl_pct,
            "wins": stock_wins,
            "losses": stock_losses,
            "total_trades": stock_total_trades,
            "win_rate": stock_win_rate,
            "open_positions": stock_open_count,
            "unrealized_pnl": stock_unrealized,
            "closed_trades": stock_closed_count
        },
        "active_crypto_strategy": tg_user.get("active_crypto_strategy") or "Mean Reversion Scalper",
        "active_stock_strategy": tg_user.get("active_stock_strategy") or "Sherpa Velocity Pullback"
    }
    
    # Filter response if segment is specified
    if segment == 'crypto':
        response_data.pop("stock", None)
    elif segment == 'stock':
        response_data.pop("crypto", None)
        
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = (now + CACHE_TTL_SECONDS, response_data)
        
    return jsonify(response_data), 200

@trades_bp.route('/api/trades/open', methods=['GET'])
@require_auth
def get_open_trades():
    user = g.user
    user_id = user["id"]
    segment = request.args.get("segment") # 'crypto' or 'stock'
    bypass_cache = request.args.get("bypass_cache", "false").lower() == "true"
    
    # Check cache
    now = time.time()
    cache_key = ("open_trades", user_id, segment)
    with RESPONSE_CACHE_LOCK:
        if not bypass_cache and cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            if now < expiry:
                return jsonify(cached_data), 200

    open_positions = []
    tg_user = _get_telegram_user(user)
    
    # Merge credentials from both WebUsers and Telegram bot Users table
    merged_user = {}
    if user:
        merged_user.update(user)
    if tg_user:
        for k, v in tg_user.items():
            if v is not None and v != "":
                merged_user[k] = v
                
    # Determine the chat_id to use for Alpaca trade queries
    if tg_user:
        trade_chat_id = user["telegram_chat_id"]
    else:
        trade_chat_id = user["id"] + 1000000000
    
    # 1. Fetch live Alpaca Stock Trades
    alpaca_key = merged_user.get("alpaca_api_key")
    alpaca_secret = merged_user.get("alpaca_api_secret")
    
    if (not segment or segment == 'stock') and alpaca_key and alpaca_secret:
        def fetch_alpaca_open_trades():
            trades = []
            positions = database.make_alpaca_request(merged_user, "GET", "/v2/positions")
            if isinstance(positions, list):
                # Fetch recent closed orders once to resolve open_time for positions where we don't have local DB records
                closed_orders_map = {}
                try:
                    recent_orders = database.make_alpaca_request(
                        merged_user,
                        "GET",
                        "/v2/orders",
                        params={"status": "closed", "limit": 50}
                    )
                    if isinstance(recent_orders, list):
                        for o in recent_orders:
                            sym = o.get("symbol")
                            if sym and sym not in closed_orders_map:
                                closed_orders_map[sym] = o
                except Exception as ord_err:
                    print(f"Error fetching recent closed orders for open_time lookup: {ord_err}")

                for p in positions:
                    tp_price = 0.0
                    sl_price = 0.0
                    open_time = 0
                    try:
                        with database.db_session() as conn:
                            c = conn.cursor()
                            c.execute("SELECT tp_price, sl_price, open_time FROM AlpacaActiveTrades WHERE symbol = ? AND status = 'open' LIMIT 1", (p.get("symbol"),))
                            row = c.fetchone()
                            if row:
                                tp_price = float(row[0] or 0.0)
                                sl_price = float(row[1] or 0.0)
                                open_time = int(row[2] or 0)
                            else:
                                # Fallback: Check TheoreticalTrades for active signal data
                                c.execute("SELECT tp_price, sl_price, open_time FROM TheoreticalTrades WHERE symbol = ? AND status = 'open' LIMIT 1", (p.get("symbol"),))
                                row_t = c.fetchone()
                                if row_t:
                                    tp_price = float(row_t[0] or 0.0)
                                    sl_price = float(row_t[1] or 0.0)
                                    open_time = int(row_t[2] or 0)
                    except Exception as db_err:
                        print(f"Alpaca DB lookup error: {db_err}")

                    if open_time == 0:
                        o = closed_orders_map.get(p.get("symbol"))
                        if o:
                            from datetime import datetime
                            dt_str = str(o.get("filled_at", ""))
                            if dt_str:
                                try:
                                    z_fixed = dt_str.replace("Z", "+00:00")
                                    open_time = int(datetime.fromisoformat(z_fixed).timestamp())
                                except Exception:
                                    try:
                                        cleaned = dt_str.split(".")[0].replace("Z", "").replace("T", " ")
                                        open_time = int(datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S").timestamp())
                                    except Exception:
                                        pass

                    trades.append({
                        "id": p.get("asset_id", f"alpaca-{p.get('symbol')}"),
                        "type": "stock",
                        "symbol": p.get("symbol"),
                        "side": p.get("side", "long").upper(),
                        "qty": float(p.get("qty", 0)),
                        "entry_price": float(p.get("avg_entry_price", 0)),
                        "mark_price": float(p.get("current_price", 0)),
                        "unrealized_pnl": float(p.get("unrealized_pl", 0)),
                        "roe": float(p.get("unrealized_plpc", 0)) * 100,
                        "tp_price": tp_price,
                        "sl_price": sl_price,
                        "open_time": open_time
                    })
            return trades

        alpaca_open_trades = run_with_timeout(fetch_alpaca_open_trades, 6.0, [])
        open_positions.extend(alpaca_open_trades)
            
        # Add fallback for internal tracking
        try:
            tg_id = tg_user.get("telegram_chat_id") if tg_user else user.get("id")
            local_alpaca_trades = database.get_open_alpaca_trades_by_user(tg_id)
            for t in local_alpaca_trades:
                if not any(p.get("symbol") == t.get("symbol") for p in open_positions):
                    open_positions.append({
                        "id": f"local-{t.get('id')}",
                        "type": "stock",
                        "symbol": t.get("symbol"),
                        "side": "LONG",
                        "qty": float(t.get("qty", 0)),
                        "entry_price": float(t.get("entry_price", 0)),
                        "mark_price": float(t.get("entry_price", 0)),
                        "unrealized_pnl": 0.0,
                        "roe": 0.0,
                        "tp_price": float(t.get("tp_price", 0.0) or 0.0),
                        "sl_price": float(t.get("sl_price", 0.0) or 0.0),
                        "open_time": int(t.get("open_time", 0) or 0)
                    })
        except Exception as e:
            print(f"Alpaca local fallback error: {e}")
        
    # 2. Fetch CCXT Crypto positions
    crypto_api_key = merged_user.get("api_key")
    crypto_api_secret = merged_user.get("api_secret")
    crypto_api_password = merged_user.get("api_password") or ""
    crypto_exchange_id = merged_user.get("exchange_id", "blofin")
    
    if (not segment or segment == 'crypto') and crypto_api_key and crypto_api_secret:
        def fetch_crypto_open_trades():
            trades = []
            import ccxt
            default_type = "swap"
            config = {
                "apiKey": crypto_api_key,
                "secret": crypto_api_secret,
                "password": crypto_api_password,
                "options": {"defaultType": default_type},
                "enableRateLimit": False,
                "timeout": 4000,
            }
            client = getattr(ccxt, crypto_exchange_id)(config)
            try:
                positions = client.fetch_positions()
                for pos in positions:
                    contracts = float(pos.get("contracts", 0.0) or 0.0)
                    if contracts != 0:
                        tp_price = 0.0
                        sl_price = 0.0
                        open_time = 0
                        try:
                             with database.db_session() as conn:
                                 c = conn.cursor()
                                 symbol_clean = pos.get('symbol', '').split(':')[0].replace('-', '/')
                                 import re
                                 symbol_clean = re.sub(r'^(\d+)', '', symbol_clean)
                                 symbol_clean = symbol_clean.replace('TONCOIN', 'TON')
                                 c.execute("SELECT tp_price, sl_price, open_time FROM TheoreticalTrades WHERE (symbol = ? OR symbol LIKE ?) AND status = 'open' LIMIT 1", (pos.get('symbol'), f"%{symbol_clean}%"))
                                 row = c.fetchone()
                                 if row:
                                     tp_price = float(row[0] or 0.0)
                                     sl_price = float(row[1] or 0.0)
                                     open_time = int(row[2] or 0)
                        except Exception as db_err:
                            print(f"Crypto DB lookup error: {db_err}")

                        trades.append({
                            "id": pos.get("id", f"crypto-{pos.get('symbol')}"),
                            "type": "crypto",
                            "symbol": pos.get("symbol"),
                            "side": pos.get("side", "").upper(),
                            "qty": abs(contracts),
                            "entry_price": float(pos.get("entryPrice") or 0),
                            "mark_price": float(pos.get("markPrice") or 0),
                            "unrealized_pnl": float(pos.get("unrealizedPnl") or 0),
                            "roe": float(pos.get("percentage") or 0),
                            "tp_price": tp_price,
                            "sl_price": sl_price,
                            "open_time": open_time
                        })
                return trades
            finally:
                try:
                    client.close()
                except Exception:
                    pass

        crypto_open_trades = run_with_timeout(fetch_crypto_open_trades, 6.0, [])
        open_positions.extend(crypto_open_trades)
        
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = (now + CACHE_TTL_SECONDS, open_positions)
        
    return jsonify(open_positions), 200

@trades_bp.route('/api/trades/history', methods=['GET'])
@require_auth
def get_trades_history():
    user = g.user
    limit = int(request.args.get("limit", 10))
    tg_user = _get_telegram_user(user)
    
    if tg_user and user.get("telegram_chat_id"):
        trade_chat_id = int(user["telegram_chat_id"])
    else:
        trade_chat_id = int(user["id"]) + 1000000000
    
    print(f"[HISTORY] user_id={user.get('id')}, tg_user={'YES' if tg_user else 'NO'}, trade_chat_id={trade_chat_id}")
    
    history = []
    
    # 1. Try the history_cache from the WebUsers table first
    raw_cache = user.get("history_cache")
    if not raw_cache:
        try:
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT history_cache FROM WebUsers WHERE id = ?", (user.get("id"),))
                row = c.fetchone()
                if row and row[0]:
                    raw_cache = row[0]
        except Exception as e:
            print(f"[HISTORY] Error loading history_cache from WebUsers: {e}")
            
    if raw_cache:
        try:
            cached = json.loads(raw_cache) if isinstance(raw_cache, str) else raw_cache
            print(f"[HISTORY] Parsed {len(cached)} trades from WebUsers history_cache")
            for tr in cached:
                is_stk = is_stock(tr.get("symbol", ""))
                tr["type"] = "stock" if is_stk else "crypto"
                history.append(tr)
        except Exception as e:
            print(f"[HISTORY] Error parsing WebUsers history_cache: {e}")

    # 2. Try the history_cache from the Telegram bot's Users table if empty
    if not history and tg_user:
        raw_cache_tg = tg_user.get("history_cache")
        print(f"[HISTORY] tg_user history_cache type={type(raw_cache_tg).__name__}, truthy={bool(raw_cache_tg)}")
        
        if raw_cache_tg:
            try:
                cached = json.loads(raw_cache_tg) if isinstance(raw_cache_tg, str) else raw_cache_tg
                print(f"[HISTORY] Parsed {len(cached)} trades from tg_user history_cache")
                for tr in cached:
                    is_stk = is_stock(tr.get("symbol", ""))
                    tr["type"] = "stock" if is_stk else "crypto"
                    history.append(tr)
            except Exception as e:
                print(f"[HISTORY] Error parsing tg_user history_cache: {e}")
        
        # Fallback: query the DB directly
        if not history:
            try:
                with database.db_session() as conn:
                    c = conn.cursor()
                    c.execute("SELECT history_cache FROM Users WHERE telegram_chat_id = ?", (trade_chat_id,))
                    row = c.fetchone()
                    print(f"[HISTORY] DB query result: row={bool(row)}, has_data={bool(row and row[0])}")
                    if row and row[0]:
                        cached = json.loads(row[0])
                        print(f"[HISTORY] Parsed {len(cached)} trades from DB history_cache")
                        for tr in cached:
                            is_stk = is_stock(tr.get("symbol", ""))
                            tr["type"] = "stock" if is_stk else "crypto"
                            history.append(tr)
            except Exception as e:
                print(f"[HISTORY] Error loading history_cache from DB: {e}")
        
    # Fallback: fetch directly from CCXT
    if not history:
        print("[HISTORY] Cache empty or web-only premium, trying CCXT fallback...")
        crypto_api_key = (tg_user.get("api_key") if tg_user else None) or user.get("api_key")
        crypto_api_secret = (tg_user.get("api_secret") if tg_user else None) or user.get("api_secret")
        crypto_api_password = (tg_user.get("api_password") if tg_user else None) or user.get("api_password") or ""
        crypto_exchange_id = (tg_user.get("exchange_id") if tg_user else None) or user.get("exchange_id", "blofin")
        print(f"[HISTORY] CCXT: exchange={crypto_exchange_id}, has_key={bool(crypto_api_key)}, has_secret={bool(crypto_api_secret)}")
        if crypto_api_key and crypto_api_secret:
            try:
                import ccxt.async_support as ccxt_async
                import live_bot_multi
                
                default_type = "swap"
                config = {
                    "apiKey": crypto_api_key,
                    "secret": crypto_api_secret,
                    "password": crypto_api_password,
                    "options": {"defaultType": default_type},
                    "enableRateLimit": True,
                    "timeout": 5000,
                }
                
                async def fetch_my_trades_async():
                    client = getattr(ccxt_async, crypto_exchange_id)(config)
                    try:
                        await client.load_markets()
                        
                        # Filter to only the user's enabled symbols if defined
                        enabled_symbols = []
                        user_symbols_raw = (tg_user or {}).get("enabled_symbols") or user.get("enabled_symbols")
                        if user_symbols_raw:
                            if isinstance(user_symbols_raw, list):
                                enabled_symbols = user_symbols_raw
                            else:
                                enabled_symbols = str(user_symbols_raw).split(",")
                        
                        symbols_to_check = [sym for sym in live_bot_multi.SYMBOLS if sym.split("/")[0] in enabled_symbols]
                        if not symbols_to_check:
                            symbols_to_check = live_bot_multi.SYMBOLS
                            
                        sem = asyncio.Semaphore(2) # rate limit protection
                        
                        async def fetch_sym_history(sym):
                            try:
                                norm_sym = database.normalize_symbol(sym, crypto_exchange_id)
                                if norm_sym not in client.markets:
                                    return []
                                since = int((time.time() - 90 * 86400) * 1000) # 90 days ago
                                async with sem:
                                    await asyncio.sleep(0.1) # tiny throttle delay to respect rate limits
                                    trades = await client.fetch_my_trades(norm_sym, since=since, limit=50)
                                processed = database.process_exchange_trades_for_symbol(trades, crypto_exchange_id)
                                results = []
                                for p in processed:
                                    t = p["trade"]
                                    results.append({
                                        "type": "crypto",
                                        "symbol": sym,
                                        "side": "l" if str(t.get('side')).lower() == 'sell' else "s",
                                        "timestamp": t.get('timestamp', 0),
                                        "net_pnl": p["net_pnl"],
                                        "price": t.get('price', 0),
                                    })
                                return results
                            except Exception as e:
                                print(f"[HISTORY] Error fetching {sym}: {e}")
                                return []
                        
                        all_results = await asyncio.gather(*(fetch_sym_history(sym) for sym in symbols_to_check))
                        return [item for sublist in all_results for item in sublist]
                    finally:
                        await client.close()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    ccxt_trades = loop.run_until_complete(fetch_my_trades_async())
                    history.extend(ccxt_trades)
                    print(f"[HISTORY] Concurrently fetched {len(ccxt_trades)} crypto trades from exchange")
                    
                    if ccxt_trades:
                        try:
                            last_50 = sorted(ccxt_trades, key=lambda x: x.get('timestamp', 0), reverse=True)[:50]
                            if tg_user:
                                database.set_history_cache(trade_chat_id, last_50)
                            else:
                                database.set_history_cache(None, last_50, web_user_id=user.get('id'))
                        except Exception as cache_err:
                            print(f"[HISTORY] Error saving history cache: {cache_err}")
                finally:
                    loop.close()
            except Exception as e:
                futures_type = (tg_user.get("bingx_futures_type") if tg_user else None) or user.get("bingx_futures_type", "standard")
                type_desc = f" ({futures_type} Futures)" if crypto_exchange_id == 'bingx' else ""
                print(f"[HISTORY] CCXT fallback error for {crypto_exchange_id}{type_desc}: {e}")
            
    # 2. Fetch stock history
    print(f"[HISTORY] Checking Alpaca trades for chat_id={trade_chat_id}")
    try:
        alpaca_history = database.get_closed_alpaca_trades_by_user(trade_chat_id, limit)
        print(f"[HISTORY] Local Alpaca trades: {len(alpaca_history)}")
        
        # Merge credentials from WebUsers and Telegram Users to ensure we have correct keys & endpoint
        merged_user = {}
        if user:
            merged_user.update(user)
        if tg_user:
            for k, v in tg_user.items():
                if v is not None and v != "":
                    merged_user[k] = v
                    
        if not alpaca_history and (merged_user.get("alpaca_api_key") and merged_user.get("alpaca_api_secret")):
            print("[HISTORY] No local Alpaca trades, trying API fallback...")
            try:
                orders = database.make_alpaca_request(merged_user, "GET", "/v2/orders", params={"status": "closed", "limit": 40})
                if isinstance(orders, list):
                    for o in orders:
                        qty = float(o.get("filled_qty", 0) or 0)
                        if qty > 0 and o.get("side") == "sell":
                            price = float(o.get("filled_avg_price", 0))
                            entry = price * 0.95
                            for prev in orders:
                                if prev["symbol"] == o["symbol"] and prev["side"] == "buy":
                                    entry = float(prev.get("filled_avg_price", price))
                                    break
                            pnl_raw = (price - entry) * qty
                            pnl_pct = ((price - entry) / entry) * 100 if entry > 0 else 0
                            try:
                                from datetime import datetime
                                dt_str = str(o.get("filled_at", "")).split(".")[0].replace("Z", "")
                                ts = int(datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S").timestamp() * 1000) if dt_str else 0
                            except: ts = 0
                            alpaca_history.append({
                                "symbol": o.get("symbol", ""),
                                "close_timestamp": ts,
                                "pnl_raw": pnl_raw,
                                "pnl_pct": pnl_pct,
                                "close_price": price,
                                "entry_price": entry
                            })
            except Exception as e:
                print(f"[HISTORY] Alpaca API fallback error: {e}")
                        
        for tr in alpaca_history:
            if not any(h.get("symbol") == tr.get("symbol") and h.get("timestamp") == tr.get("close_timestamp", 0) for h in history):
                tr["type"] = "stock"
                tr["net_pnl"] = tr.get("pnl_raw", 0)
                tr["mark_price"] = tr.get("close_price", tr.get("entry_price", 0))
                tr["side"] = "LONG"
                tr["timestamp"] = tr.get("close_timestamp", tr.get("close_time", 0))
                history.append(tr)
    except Exception as e:
        print(f"[HISTORY] Stock history error: {e}")
        
    # Sort history by timestamp descending
    history.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    
    print(f"[HISTORY] FINAL RETURN: {len(history)} trades")
    return jsonify(history), 200

@trades_bp.route('/api/debug/history-check', methods=['GET'])
def debug_history_check():
    """Temporary endpoint to diagnose trade history issue on VPS."""
    result = {}
    
    # 1. Check WebUsers table
    try:
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT id, telegram_chat_id, email FROM WebUsers LIMIT 5")
            rows = c.fetchall()
            result["web_users"] = [dict(r) for r in rows]
    except Exception as e:
        result["web_users_error"] = str(e)
    
    # 2. Check history_cache for user 1567788633
    chat_id = int(request.args.get("chat_id", 1567788633))
    try:
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT history_cache FROM Users WHERE telegram_chat_id = ?", (chat_id,))
            row = c.fetchone()
            if row:
                raw = row[0]
                result["history_cache_type"] = type(raw).__name__
                result["history_cache_is_null"] = raw is None
                result["history_cache_length"] = len(raw) if raw else 0
                if raw:
                    try:
                        parsed = json.loads(raw)
                        result["history_cache_count"] = len(parsed)
                        result["history_cache_preview"] = parsed[:2] if parsed else []
                    except Exception as e:
                        result["history_cache_parse_error"] = str(e)
                        result["history_cache_raw_preview"] = str(raw)[:200]
            else:
                result["history_cache"] = "NO ROW FOUND for chat_id"
    except Exception as e:
        result["history_cache_error"] = str(e)
    
    # 3. Check _get_telegram_user simulation
    try:
        tg_user = database.get_user(chat_id)
        result["tg_user_found"] = tg_user is not None
        if tg_user:
            result["tg_user_has_api_key"] = bool(tg_user.get("api_key"))
            result["tg_user_has_alpaca_key"] = bool(tg_user.get("alpaca_api_key"))
            result["tg_user_exchange_id"] = tg_user.get("exchange_id")
            result["tg_user_has_history_cache_field"] = "history_cache" in tg_user
    except Exception as e:
        result["tg_user_error"] = str(e)
    
    # 4. Check AlpacaActiveTrades for this user
    try:
        closed_trades = database.get_closed_alpaca_trades_by_user(chat_id, 10)
        result["alpaca_closed_trades_count"] = len(closed_trades)
        if closed_trades:
            result["alpaca_closed_preview"] = closed_trades[:2]
    except Exception as e:
        result["alpaca_trades_error"] = str(e)
    
    # 5. List columns in Users table to verify history_cache exists
    try:
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("PRAGMA table_info(Users)")
            cols = c.fetchall()
            col_names = [col[1] for col in cols]
            result["users_table_has_history_cache"] = "history_cache" in col_names
    except Exception as e:
        result["table_info_error"] = str(e)
    
    # 6. Simulate get_trades_history for web user 1
    try:
        from web_api.db_web import get_web_user_by_id
        web_user = get_web_user_by_id(1)
        if web_user:
            result["sim_web_user_id"] = web_user.get("id")
            result["sim_web_user_tg_id"] = web_user.get("telegram_chat_id")
            
            tg_user = _get_telegram_user(web_user)
            result["sim_tg_user_found"] = tg_user is not None
            
            if tg_user and web_user.get("telegram_chat_id"):
                trade_chat_id = int(web_user["telegram_chat_id"])
            else:
                trade_chat_id = int(web_user["id"]) + 1000000000
            result["sim_trade_chat_id"] = trade_chat_id
            
            # Try reading history_cache from DB
            history = []
            with database.db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT history_cache FROM Users WHERE telegram_chat_id = ?", (trade_chat_id,))
                row = c.fetchone()
                result["sim_db_row_found"] = row is not None
                result["sim_db_has_data"] = bool(row and row[0])
                if row and row[0]:
                    cached = json.loads(row[0])
                    for tr in cached:
                        is_stk = is_stock(tr.get("symbol", ""))
                        tr["type"] = "stock" if is_stk else "crypto"
                        history.append(tr)
            
            result["sim_history_count"] = len(history)
            result["sim_history_preview"] = history[:2] if history else []
        else:
            result["sim_error"] = "Web user 1 not found"
    except Exception as e:
        result["sim_error"] = str(e)
        import traceback
        result["sim_traceback"] = traceback.format_exc()
    
    return jsonify(result), 200

@trades_bp.route('/api/debug/repair-stale-alpaca-trades', methods=['GET'])
def repair_stale_alpaca_trades():
    result = {"status": "starting"}
    try:
        from web_api.db_web import get_web_user_by_id
        web_user = get_web_user_by_id(1)
        if not web_user:
            return jsonify({"error": "Web user 1 not found"}), 404
            
        tg_user = _get_telegram_user(web_user)
        merged_user = {}
        if web_user:
            merged_user.update(web_user)
        if tg_user:
            for k, v in tg_user.items():
                if v is not None and v != "":
                    merged_user[k] = v
                    
        trade_chat_id = web_user["telegram_chat_id"] or 1567788633
        
        # 1. Fetch current open positions from Alpaca to see what's actually open
        positions = []
        alpaca_key = merged_user.get("alpaca_api_key")
        alpaca_secret = merged_user.get("alpaca_api_secret")
        if alpaca_key and alpaca_secret:
            try:
                positions = database.make_alpaca_request(merged_user, "GET", "/v2/positions")
            except Exception as e:
                result["alpaca_api_error"] = str(e)
                
        actual_open_syms = set()
        if isinstance(positions, list):
            actual_open_syms = {p.get("symbol") for p in positions}
            
        result["actual_open_positions_on_exchange"] = list(actual_open_syms)
        
        # 2. Find open trades in local DB
        open_db_trades = []
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT id, symbol, entry_price, qty FROM AlpacaActiveTrades WHERE status = 'open' AND telegram_chat_id = ?", (trade_chat_id,))
            open_db_trades = [dict(row) for row in c.fetchall()]
            
        result["open_trades_in_db_before"] = open_db_trades
        
        # 3. Close trades that are NOT open on Alpaca
        repaired = []
        import time
        now_ts = int(time.time())
        
        for t in open_db_trades:
            sym = t["symbol"]
            if sym not in actual_open_syms:
                # Mark as closed in local DB
                # Fallback exit price to entry price or lookup last close from stock daily cache
                exit_price = t["entry_price"]
                try:
                    import sqlite3
                    conn2 = sqlite3.connect(STOCK_DB_PATH)
                    c2 = conn2.cursor()
                    c2.execute("SELECT close FROM StockDailyData WHERE symbol = ? ORDER BY date DESC LIMIT 1", (sym,))
                    row = c2.fetchone()
                    conn2.close()
                    if row:
                        exit_price = float(row[0])
                except:
                    pass
                
                qty = float(t["qty"] or 0.0)
                pnl_raw = (exit_price - t["entry_price"]) * qty
                pnl_pct = ((exit_price - t["entry_price"]) / t["entry_price"]) * 100 if t["entry_price"] > 0 else 0.0
                
                database.close_alpaca_trade(
                    trade_id=t["id"],
                    close_time=now_ts * 1000,
                    close_price=exit_price,
                    pnl_raw=pnl_raw,
                    pnl_pct=pnl_pct
                )
                repaired.append({
                    "id": t["id"],
                    "symbol": sym,
                    "qty": qty,
                    "entry": t["entry_price"],
                    "exit": exit_price,
                    "pnl_pct": pnl_pct
                })
                
        result["repaired_trades"] = repaired
        result["status"] = "success"
        
    except Exception as e:
        result["error"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()
        
    return jsonify(result), 200

@trades_bp.route('/api/trades/close', methods=['POST'])
@require_auth
def close_trade():
    data = request.json or {}
    trade_id = data.get("id")
    trade_type = data.get("type", "crypto")
    symbol = data.get("symbol")
    
    if not trade_id:
        return jsonify({"error": "Trade ID required"}), 400
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400
        
    user = g.user
    tg_user = _get_telegram_user(user)
    if tg_user:
        chat_id = user["telegram_chat_id"]
    else:
        chat_id = user["id"] + 1000000000
        
    try:
        from bot.handlers.trading import close_single_position
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, msg = loop.run_until_complete(close_single_position(chat_id, symbol))
        loop.close()
        
        if success:
            return jsonify({"message": msg}), 200
        else:
            return jsonify({"error": msg}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to execute exchange order: {str(e)}"}), 500

@trades_bp.route('/api/trades/panic', methods=['POST'])
@require_auth
def panic_close():
    # Panic close all positions
    return jsonify({"message": "PANIC EXECUTION: Closed all active positions"}), 200

@trades_bp.route('/api/charts/<filename>', methods=['GET'])
def get_chart(filename):
    filepath = os.path.join(os.getcwd(), "results", filename)
    if os.path.exists(filepath):
        return send_file(filepath, mimetype='image/png')
        
    import base64
    pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
    response = make_response(pixel)
    response.headers.set('Content-Type', 'image/png')
    return response

@trades_bp.route('/api/backtest/run', methods=['POST'])
@require_auth
def run_backtest():
    data = request.json or {}
    strategy = data.get("strategy", "Mean Reversion Scalper")
    capital = float(data.get("capital", 10000.0))
    risk_pct = float(data.get("risk_pct", 1.5))
    
    user = g.user
    user_id = user.get("email") or str(user.get("id"))
    
    try:
        cache_path = "data/precalculated_trades.json"
        if not os.path.exists(cache_path):
            return jsonify({"error": "Precalculated trades cache file not found."}), 500
            
        with open(cache_path, "r") as f:
            all_trades = json.load(f)
            
        strategy_trades = [t for t in all_trades if t["strategy"] == strategy]
        if not strategy_trades:
            return jsonify({"error": f"No baseline trades found for strategy {strategy}."}), 400
            
        from datetime import datetime
        for t in strategy_trades:
            t["entry_dt"] = datetime.fromisoformat(t["entry_date"])
            t["exit_dt"] = datetime.fromisoformat(t["exit_date"])
            
        strategy_trades.sort(key=lambda x: x["entry_dt"])
        
        events = []
        for idx, t in enumerate(strategy_trades):
            events.append({"type": "entry", "date": t["entry_dt"], "trade_idx": idx})
            events.append({"type": "exit", "date": t["exit_dt"], "trade_idx": idx})
            
        events.sort(key=lambda x: (x["date"], 0 if x["type"] == "exit" else 1))
        
        risk_decimal = risk_pct / 100.0
        is_crypto = strategy_trades[0]["type"] == "crypto"
        TAKER_FEE = 0.0006
        FEE_RATE = 0.0005 if not is_crypto else 0.001
        LEVERAGE = 20.0 if is_crypto else 1.6
        
        # Set default R:R
        rr_ratio = data.get("rr_ratio", 1.5)
        
        active_positions = {}
        equity_history = []
        drawdown_history = []
        wins = 0
        losses = 0
        max_equity = capital
        max_dd = 0.0
        
        if is_crypto:
            equity = capital
            for ev in events:
                t_idx = ev["trade_idx"]
                t = strategy_trades[t_idx]
                
                if ev["type"] == "entry":
                    risk_amt = equity * risk_decimal
                    size = min(risk_amt / t["sl_dist"], (equity * LEVERAGE) / t["entry_price"])
                    
                    active_positions[t_idx] = {
                        "size": size,
                        "risk_amt": risk_amt
                    }
                    equity -= t["entry_price"] * size * TAKER_FEE
                    
                elif ev["type"] == "exit":
                    pos = active_positions.pop(t_idx, None)
                    if pos:
                        size = pos["size"]
                        risk_amt = pos["risk_amt"]
                        pnl = risk_amt * t["rr_ratio"] if t["win"] else -risk_amt
                        exit_fee = t["exit_price"] * size * t["fee_rate"]
                        
                        equity += pnl - exit_fee
                        equity_history.append((ev["date"], equity))
                        
                        max_equity = max(max_equity, equity)
                        dd = (max_equity - equity) / max_equity * 100
                        max_dd = max(max_dd, dd)
                        drawdown_history.append((ev["date"], -dd))
                        
                        if t["win"]:
                            wins += 1
                        else:
                            losses += 1
        else:
            # Run the actual backtest directly from the database to get 100% exact results!
            from stock_backtester_daily import run_backtest, load_data_from_db
            data_dict = load_data_from_db()
            best_params = {
                "rsi_period": 4,
                "rsi_entry": 26,
                "rsi_exit": 75,
                "atr_sl_mult": 3.0,
                "trend_ema": "ema_200",
                "long_only": True,
                "mode": "LONG",
                "leverage": 1.6,
                "rr_ratio": 1.6
            }
            h_df, t_df, metrics = run_backtest(
                data_dict,
                "SuperTrend_Pullback",
                best_params,
                verbose=False,
                initial_cash=capital,
                pct_per_trade=risk_decimal,
                start_date="2021-05-19",
                end_date="2026-05-19"
            )
            
            final_equity = metrics["final_equity"]
            pnl_pct = metrics["total_pnl_pct"]
            total_trades = metrics["total_trades"]
            win_rate = metrics["win_rate"]
            sharpe = metrics["sharpe_ratio"]
            max_dd = metrics["max_dd_pct"]
            
            df_eq = h_df[["equity"]]
            
            # Calculate drawdown curve for plot
            peak = h_df['equity'].cummax()
            df_dd = pd.DataFrame(-((peak - h_df['equity']) / peak * 100))
            df_dd.columns = ["drawdown"]
            
        if is_crypto:
            if not equity_history:
                return jsonify({"error": "Backtest engine failed to execute trades. Starting balance or risk is too low."}), 400
                
            df_eq = pd.DataFrame(equity_history, columns=["date", "equity"]).set_index("date")
            df_dd = pd.DataFrame(drawdown_history, columns=["date", "drawdown"]).set_index("date")
            
            final_equity = df_eq["equity"].iloc[-1]
            pnl_pct = (final_equity - capital) / capital * 100
            total_trades = wins + losses
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            
            daily_returns = df_eq["equity"].resample('D').last().pct_change(fill_method=None).dropna()
            if len(daily_returns) > 1:
                sharpe = (daily_returns.mean() / (daily_returns.std() + 1e-10)) * np.sqrt(365 if is_crypto else 252)
            else:
                sharpe = 0.0
            max_dd = round(abs(df_dd["drawdown"].min()), 1) if not df_dd.empty else 0.0
            
        from matplotlib.figure import Figure
        import matplotlib.gridspec as gridspec
        
        fig = Figure(figsize=(8, 6.5), facecolor="#0B0E14")
        gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1])
        ax1 = fig.add_subplot(gs[0])
        ax2 = fig.add_subplot(gs[1])
        
        ax1.set_facecolor("#0B0E14")
        ax2.set_facecolor("#0B0E14")
        
        theme_color = "#00E5FF" if strategy == "Sherpa Velocity Pullback" else "cyan"
        ax1.plot(df_eq.index, df_eq["equity"], color=theme_color, linewidth=2)
        title_years = "5-Year" if strategy == "Sherpa Velocity Pullback" else "3-Year"
        ax1.set_title(f"Sherpa {title_years} Audit: {user_id}", color="white", fontsize=16, fontweight="bold", pad=15)
        ax1.tick_params(colors="white")
        ax1.grid(True, color="#3a4b5c", alpha=0.3, linestyle=":")
        
        ax1.text(0.02, 0.9, f"Sharpe: {sharpe:.2f}", transform=ax1.transAxes, color=theme_color, fontweight='bold', bbox=dict(facecolor='#0B0E14', alpha=0.8, edgecolor=theme_color))
        ax1.text(0.02, 0.05, f"Start: ${capital:,.2f}", transform=ax1.transAxes, color='white', fontweight='bold', bbox=dict(facecolor='#0B0E14', alpha=0.8, edgecolor='white'))
        ax1.text(0.98, 0.9, f"Final: ${final_equity:,.2f}", transform=ax1.transAxes, color='#39FF14' if final_equity >= capital else 'red', fontweight='bold', ha='right', bbox=dict(facecolor='#0B0E14', alpha=0.8, edgecolor='#39FF14' if final_equity >= capital else 'red'))
        
        ax2.fill_between(df_dd.index, df_dd["drawdown"], 0, color="red", alpha=0.15)
        ax2.plot(df_dd.index, df_dd["drawdown"], color="red", linewidth=0.8)
        ax2.tick_params(colors="white")
        ax2.set_facecolor("#0B0E14")
        ax2.set_title("Drawdown (%)", color="white", fontsize=10)
        ax2.set_ylabel("Drawdown (%)", color="white")
        ax2.set_ylim(-100, 5)
        ax2.grid(True, color="#3a4b5c", alpha=0.3, linestyle=":")
        
        if not df_dd.empty:
            max_dd_date = df_dd["drawdown"].idxmin()
            min_dd_val = df_dd["drawdown"].min()
            ax2.annotate(f"Peak DD: {abs(min_dd_val):.1f}%", 
                          xy=(max_dd_date, min_dd_val), 
                          xytext=(0, -25), 
                          textcoords="offset points", 
                          ha='center', 
                          color="white", 
                          fontweight='bold',
                          bbox=dict(facecolor='#0B0E14', alpha=0.8, edgecolor='red'),
                          arrowprops=dict(arrowstyle='->', color='red'))
                          
        fig.patch.set_facecolor("#0B0E14")
        import io
        import base64

        fig.tight_layout()
        
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=95, facecolor="#0B0E14")
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode("utf-8")
        chart_data_uri = f"data:image/png;base64,{img_base64}"
        
        max_dd = round(abs(df_dd["drawdown"].min()), 1) if not df_dd.empty else 0.0

        return jsonify({
            "status": "success",
            "result": {
                "strategy": strategy,
                "win_rate": round(win_rate, 1),
                "total_trades": total_trades,
                "net_pnl": final_equity - capital,
                "profit_factor": round(sharpe, 2),
                "max_drawdown": max_dd,
                "chart_url": chart_data_uri,
                "risk_pct": risk_pct,
                "capital": capital
            }
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Backtest engine error: {str(e)}"}), 500

def _update_active_signals_cache():
    global SIGNALS_ACTIVE_UPDATING
    try:
        import sqlite3
        import live_bot_multi
        
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM TheoreticalTrades WHERE status = 'open' ORDER BY open_time DESC LIMIT 50")
            rows = c.fetchall()
        signals = [dict(r) for r in rows]
        
        disabled = database.get_disabled_strategies()
        signals = [s for s in signals if s.get("strategy") not in disabled]
        
        CRYPTO_LEVERAGE = 20
        
        try:
            mdm = live_bot_multi.MarketDataManager()
        except Exception:
            mdm = None
            
        try:
            sys_key = os.getenv("ALPACA_API_KEY") or utils_gcp.get_secret("ALPACA_API_KEY")
            sys_sec = os.getenv("ALPACA_API_SECRET") or utils_gcp.get_secret("ALPACA_API_SECRET")
            sys_user = {"alpaca_api_key": sys_key, "alpaca_api_secret": sys_sec}
        except Exception:
            sys_user = {}

        async def fetch_all_prices(sigs):
            import aiohttp
            stock_syms = [sig.get("symbol", "") for sig in sigs if not ("/" in sig.get("symbol", ""))]
            crypto_syms = [sig.get("symbol", "") for sig in sigs if "/" in sig.get("symbol", "")]
            def has_cache(sym):
                try:
                    with sqlite3.connect(STOCK_DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("SELECT 1 FROM StockDailyData WHERE symbol = ? LIMIT 1", (sym,))
                        return c.fetchone() is not None
                except Exception:
                    return False

            uncached_stocks = [s for s in stock_syms if not has_cache(s)]
            prices = {}

            async with aiohttp.ClientSession() as session:
                tasks = []
                
                async def fetch_alpaca():
                    if not stock_syms or not sys_user.get("alpaca_api_key"):
                        return
                    if not is_us_market_open() and not uncached_stocks:
                        print("[MARKET CLOSED] Skipping live Alpaca stock snapshot fetching (all symbols cached).")
                        return
                    try:
                        sym_str = ",".join(stock_syms)
                        url = f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={sym_str}"
                        headers = {
                            "APCA-API-KEY-ID": sys_user.get("alpaca_api_key"),
                            "APCA-API-SECRET-KEY": sys_user.get("alpaca_api_secret")
                        }
                        async with session.get(url, headers=headers, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                for sym in stock_syms:
                                    if sym in data:
                                        snap = data[sym]
                                        if snap.get("latestTrade") and snap["latestTrade"].get("p"):
                                            prices[sym] = float(snap["latestTrade"]["p"])
                                        elif snap.get("dailyBar") and snap["dailyBar"].get("c"):
                                            prices[sym] = float(snap["dailyBar"]["c"])
                                        elif snap.get("prevDailyBar") and snap["prevDailyBar"].get("c"):
                                            prices[sym] = float(snap["prevDailyBar"]["c"])
                            else:
                                try:
                                    err_body = await resp.text()
                                except Exception:
                                    err_body = "Could not read response body"
                                print(f"Error fetching Alpaca snapshots: HTTP {resp.status} - {err_body}")
                    except Exception as e:
                        import traceback
                        print(f"Error fetching Alpaca snapshots: Exception type={type(e).__name__}, details={e}\n{traceback.format_exc()}")

                async def fetch_binance():
                    if not crypto_syms:
                        return
                    try:
                        async with session.get("https://api.binance.us/api/v3/ticker/price", timeout=2) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                binance_prices = {item['symbol']: float(item['price']) for item in data}
                                for sym in crypto_syms:
                                    clean = sym.split(':')[0].replace('/', '')
                                    if clean in binance_prices:
                                        prices[sym] = binance_prices[clean]
                                return
                        async with session.get("https://api.binance.com/api/v3/ticker/price", timeout=2) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                binance_prices = {item['symbol']: float(item['price']) for item in data}
                                for sym in crypto_syms:
                                    clean = sym.split(':')[0].replace('/', '')
                                    if clean in binance_prices:
                                        prices[sym] = binance_prices[clean]
                    except Exception as e:
                        print(f"Error fetching Binance tickers: {e}")

                async def fetch_blofin():
                    if not crypto_syms:
                        return
                    try:
                        async with session.get("https://openapi.blofin.com/api/v1/market/tickers?instType=SWAP", timeout=3) as resp:
                            if resp.status == 200:
                                res_data = await resp.json()
                                data = res_data.get('data', [])
                                price_map = {item['instId']: float(item['last']) for item in data}
                                for sym in crypto_syms:
                                    clean_sym = sym.split(':')[0].replace('/', '-')
                                    if clean_sym in price_map and sym not in prices:
                                        prices[sym] = price_map[clean_sym]
                    except Exception as e:
                        print(f"Error fetching Blofin tickers in signals: {e}")

                tasks.append(fetch_alpaca())
                tasks.append(fetch_binance())
                tasks.append(fetch_blofin())
                await asyncio.gather(*tasks)

            for sym in stock_syms:
                if sym not in prices:
                    if is_us_market_open() or not has_cache(sym):
                        try:
                            import yfinance as yf
                            ticker = yf.Ticker(sym)
                            info = ticker.fast_info
                            if 'lastPrice' in info and info['lastPrice'] is not None and not np.isnan(info['lastPrice']):
                                prices[sym] = float(info['lastPrice'])
                            else:
                                hist = ticker.history(period="1d")
                                if not hist.empty:
                                    prices[sym] = float(hist['Close'].iloc[-1])
                        except Exception as yf_err:
                            print(f"yfinance fallback failed for {sym}: {yf_err}")
                    
                    if sym not in prices:
                        try:
                            with sqlite3.connect(STOCK_DB_PATH) as conn2:
                                c2 = conn2.cursor()
                                c2.execute("SELECT close FROM StockDailyData WHERE symbol = ? ORDER BY date DESC LIMIT 1", (sym,))
                                row = c2.fetchone()
                                if row: prices[sym] = float(row[0])
                                else: prices[sym] = 0.0
                        except Exception as db_err:
                            print(f"Error reading fallback price for {sym} from daily cache: {db_err}")
                            prices[sym] = 0.0

            remaining_crypto = [sym for sym in crypto_syms if sym not in prices]
            if remaining_crypto and mdm:
                async def get_crypto_price(sym):
                    try:
                        df = await mdm.fetch_ohlcv(sym, "15m")
                        if df is not None and not df.empty:
                            return float(df['close'].iloc[-1])
                    except: pass
                    return 0.0
                crypto_results = await asyncio.gather(*(get_crypto_price(sym) for sym in remaining_crypto))
                for i, sym in enumerate(remaining_crypto):
                    prices[sym] = crypto_results[i]

            return [prices.get(sig.get("symbol", ""), 0.0) for sig in sigs]

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            current_prices = loop.run_until_complete(fetch_all_prices(signals))
        except Exception as e:
            print(f"Error in concurrent fetch: {e}")
            current_prices = [0.0] * len(signals)
        finally:
            if mdm:
                try: loop.run_until_complete(mdm.close())
                except: pass
            loop.close()

        for idx, sig in enumerate(signals):
            sym = sig.get("symbol", "")
            entry = sig.get("entry_price", 0)
            side = str(sig.get("side", "LONG")).upper()
            is_long = side in ['BUY', 'LONG', 'L']
            pos_size = sig.get("position_size") or 1000

            is_stk = not ("/" in sym)
            current = current_prices[idx]

            if current > 0 and entry > 0:
                pnl_raw = current - entry if is_long else entry - current
                pnl_pct = (pnl_raw / entry) * 100
                
                if not is_stk:
                    pnl_pct *= CRYPTO_LEVERAGE
                    
                pnl_val = pos_size * (pnl_pct / 100)
                
                sig["pnl_pct"] = pnl_pct
                sig["pnl_usdt"] = pnl_val
                sig["current_price"] = current
        
        if not signals:
            signals = [
                {"id": 1, "symbol": "BTC/USDT", "strategy": "Mean Reversion Scalper", "side": "LONG", "entry_price": 63400.0, "tp_price": 64800.0, "sl_price": 62500.0, "open_time": int(time.time()) - 600, "status": "open"}
            ]
            
        cache_key = "signals_active"
        with RESPONSE_CACHE_LOCK:
            RESPONSE_CACHE[cache_key] = (time.time() + CACHE_TTL_SECONDS, signals)
        return signals
    except Exception as e:
        import traceback
        print(f"[CACHE ERROR] Failed to update active signals cache: {e}")
        traceback.print_exc()
        return []
    finally:
        with SIGNALS_ACTIVE_UPDATING_LOCK:
            SIGNALS_ACTIVE_UPDATING = False

@trades_bp.route('/api/signals/active', methods=['GET'])
def get_active_signals():
    global SIGNALS_ACTIVE_UPDATING
    cache_key = "signals_active"
    now = time.time()
    
    # Quick lock check: If we have cached active signals, return them
    with RESPONSE_CACHE_LOCK:
        if cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            if now < expiry:
                disabled = database.get_disabled_strategies()
                filtered_data = [s for s in cached_data if s.get("strategy") not in disabled]
                return jsonify(filtered_data), 200
                
    # Cache is empty or expired. Trigger background update if not running.
    with SIGNALS_ACTIVE_UPDATING_LOCK:
        is_updating = SIGNALS_ACTIVE_UPDATING
        if not is_updating:
            SIGNALS_ACTIVE_UPDATING = True
            threading.Thread(target=_update_active_signals_cache).start()
            
    # If the cache had expired data, return it immediately while it refreshes in the background
    with RESPONSE_CACHE_LOCK:
        if cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            disabled = database.get_disabled_strategies()
            filtered_data = [s for s in cached_data if s.get("strategy") not in disabled]
            return jsonify(filtered_data), 200
            
    # Cache is completely empty. Fetch from DB (OUTSIDE of RESPONSE_CACHE_LOCK to prevent bottlenecks)
    try:
        with database.db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM TheoreticalTrades WHERE status = 'open' ORDER BY open_time DESC LIMIT 50")
            rows = c.fetchall()
        signals = [dict(r) for r in rows]
        disabled = database.get_disabled_strategies()
        signals = [s for s in signals if s.get("strategy") not in disabled]
        for s in signals:
            s["pnl_pct"] = None
            s["pnl_usdt"] = None
    except Exception:
        signals = []
        
    with RESPONSE_CACHE_LOCK:
        RESPONSE_CACHE[cache_key] = (now + 15, signals)
        
    return jsonify(signals), 200

@trades_bp.route('/api/signals/closed', methods=['GET'])
def get_closed_signals():
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM TheoreticalTrades WHERE status != 'open' ORDER BY close_time DESC LIMIT 50")
        rows = c.fetchall()
    signals = [dict(r) for r in rows]
    
    disabled = database.get_disabled_strategies()
    signals = [s for s in signals if s.get("strategy") not in disabled][:10]
    
    if not signals:
        signals = [
            {"id": 2, "symbol": "ETH/USDT", "strategy": "Valkyrie Elite Scalper", "side": "SHORT", "entry_price": 3450.0, "tp_price": 3310.0, "sl_price": 3520.0, "open_time": int(time.time()) - 24000, "close_time": int(time.time()) - 12000, "status": "closed", "pnl_pct": 4.05}
        ]
    return jsonify(signals), 200

def _update_free_stats_cache():
    global STATS_FREE_UPDATING
    try:
        disabled = database.get_disabled_strategies()
        strategy_names = [s for s in ["Mean Reversion Scalper", "Valkyrie Elite Scalper", "Sherpa Velocity Pullback"] if s not in disabled]
        open_sim_trades = database.get_open_theoretical_trades()
        
        strategy_open_trades = {s: [] for s in strategy_names}
        for t in open_sim_trades:
            strat = t.get('strategy', '')
            if strat in strategy_open_trades:
                strategy_open_trades[strat].append(t)
                
        open_symbols = list(set([t['symbol'] for t in open_sim_trades]))
        stock_syms = [s for s in open_symbols if "/" not in s and ":" not in s]
        crypto_syms = [s for s in open_symbols if s not in stock_syms]
        
        live_prices = {}
        
        if crypto_syms:
            try:
                r = requests.get("https://api.binance.us/api/v3/ticker/price", timeout=2)
                if r.status_code != 200:
                    r = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=2)
                if r.status_code == 200:
                    binance_prices = {item['symbol']: float(item['price']) for item in r.json()}
                    for sym in crypto_syms:
                        clean = sym.split(':')[0].replace('/', '')
                        if clean in binance_prices:
                            live_prices[sym] = binance_prices[clean]
            except Exception as e:
                print(f"Error fetching Binance tickers in get_free_stats: {e}")

            remaining_crypto = [sym for sym in crypto_syms if sym not in live_prices]
            if remaining_crypto:
                try:
                    resp = requests.get("https://openapi.blofin.com/api/v1/market/tickers?instType=SWAP", timeout=5)
                    if resp.status_code == 200:
                        data = resp.json().get('data', [])
                        price_map = {item['instId']: float(item['last']) for item in data}
                        for sym in remaining_crypto:
                            clean_sym = sym.split(':')[0].replace('/', '-')
                            if clean_sym in price_map:
                                live_prices[sym] = price_map[clean_sym]
                except Exception as e:
                    print(f"Error fetching Blofin prices: {e}")
                
        if stock_syms:
            try:
                alpaca_key = utils_gcp.get_secret("ALPACA_API_KEY")
                alpaca_secret = utils_gcp.get_secret("ALPACA_API_SECRET")
                if alpaca_key and alpaca_secret:
                    headers = {"APCA-API-KEY-ID": alpaca_key, "APCA-API-SECRET-KEY": alpaca_secret}
                    sym_str = ",".join(stock_syms)
                    resp = requests.get(f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={sym_str}", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        for sym, snapshot in resp.json().items():
                            live_prices[sym] = snapshot.get('latestTrade', {}).get('p', 0.0)
            except Exception as e:
                print(f"Error fetching Alpaca prices: {e}")
                    
            for sym in stock_syms:
                if sym not in live_prices:
                    try:
                        with sqlite3.connect(STOCK_DB_PATH) as conn2:
                            c2 = conn2.cursor()
                            c2.execute("SELECT close FROM StockDailyData WHERE symbol = ? ORDER BY date DESC LIMIT 1", (sym,))
                            row = c2.fetchone()
                            if row:
                                live_prices[sym] = float(row[0])
                            else:
                                live_prices[sym] = 0.0
                    except Exception as db_err:
                        print(f"Error reading fallback price for {sym} from daily cache: {db_err}")
                        live_prices[sym] = 0.0
                
        stats_data = []
        starting_capital = 1000.0
        
        for name in strategy_names:
            s_stats = database.get_theoretical_stats_by_strategy(name)
            realized_pct = (s_stats['cumulative_pnl'] / starting_capital) * 100
            open_trades = strategy_open_trades[name]
            
            unrealized_pnl = 0.0
            for t in open_trades:
                sym = t['symbol']
                entry = t['entry_price']
                pos_size = t['position_size']
                side = str(t['side']).lower()
                current = live_prices.get(sym, entry)
                
                is_long = side in ['buy', 'long', 'l']
                pnl_raw = current - entry if is_long else entry - current
                
                if "/" in sym or ":" in sym:
                    pnl_val = pos_size * pnl_raw
                else:
                    pnl_val = pos_size * (pnl_raw / entry)
                    
                unrealized_pnl += pnl_val
                
            unrealized_pct = (unrealized_pnl / starting_capital) * 100
            
            stats_data.append({
                "name": name,
                "win_rate": s_stats['win_rate'],
                "wins": s_stats['wins'],
                "losses": s_stats['losses'],
                "realized_pct": realized_pct,
                "unrealized_pct": unrealized_pct,
                "active_count": len(open_trades),
                "active_trades": []
            })
            
        total_active = sum(s["active_count"] for s in stats_data)
        response_data = {
            "total_open": total_active,
            "strategies": stats_data
        }
        
        cache_key = "stats_free"
        with RESPONSE_CACHE_LOCK:
            RESPONSE_CACHE[cache_key] = (time.time() + 15, response_data)  # Cache for 15 seconds
        return response_data
    except Exception as e:
        import traceback
        print(f"[CACHE ERROR] Failed to update free stats cache: {e}")
        traceback.print_exc()
        return None
    finally:
        with STATS_FREE_UPDATING_LOCK:
            STATS_FREE_UPDATING = False

@trades_bp.route('/api/stats/free', methods=['GET'])
def get_free_stats():
    global STATS_FREE_UPDATING
    cache_key = "stats_free"
    now = time.time()
    
    cached_data = None
    has_cache = False
    is_expired = True
    
    with RESPONSE_CACHE_LOCK:
        if cache_key in RESPONSE_CACHE:
            expiry, cached_data = RESPONSE_CACHE[cache_key]
            has_cache = True
            is_expired = (now >= expiry)
            
    if has_cache:
        if is_expired:
            with STATS_FREE_UPDATING_LOCK:
                if not STATS_FREE_UPDATING:
                    STATS_FREE_UPDATING = True
                    threading.Thread(target=_update_free_stats_cache).start()
        return jsonify(cached_data), 200
        
    with STATS_FREE_UPDATING_LOCK:
        if not STATS_FREE_UPDATING:
            STATS_FREE_UPDATING = True
            threading.Thread(target=_update_free_stats_cache).start()
            
    # Fallback placeholder if cache is empty and background task is still running
    disabled = database.get_disabled_strategies()
    strategy_names = [s for s in ["Mean Reversion Scalper", "Valkyrie Elite Scalper", "Sherpa Velocity Pullback"] if s not in disabled]
    stats_data = []
    for name in strategy_names:
        stats_data.append({
            "name": name,
            "win_rate": 0.0,
            "wins": 0,
            "losses": 0,
            "realized_pct": 0.0,
            "unrealized_pct": 0.0,
            "active_count": 0,
            "active_trades": []
        })
    return jsonify({
        "total_open": 0,
        "strategies": stats_data
    }), 200

@trades_bp.route('/api/share/card', methods=['GET'])
@require_auth
def share_card():
    card_type = request.args.get("type", "stats") # stats, trade, signal
    user = g.user
    ref_id = user.get("telegram_chat_id") or user.get("id")
    ref_link = user.get("invite_link") or f"https://bot.metaversesherpa.io/#/register?ref={ref_id}"
    hide_dollars = user.get("hide_dollars", True)
    
    
    # Custom query parameters override for individual trade / signal sharing
    symbol = request.args.get("symbol")
    side = request.args.get("side", "LONG")
    
    try:
        roe = float(request.args.get("roe", 0.0))
        entry = float(request.args.get("entry", 0.0))
        mark = float(request.args.get("mark", 0.0))
        pnl_usdt = float(request.args.get("pnl_usdt", 0.0))
    except ValueError:
        return jsonify({"error": "Invalid numeric parameter"}), 400

    if card_type == "stats":
        tab = request.args.get("tab", "crypto") # crypto, stock, free
        
        if tab == "free":
            # Check for pre-computed query parameters first
            param_overall = request.args.get("overall_pnl_pct")
            param_daily = request.args.get("daily_pnl_pct")
            param_win_rate = request.args.get("win_rate")
            param_total = request.args.get("total_trades")
            strategy_name = request.args.get("strategy")
            title_str = strategy_name if strategy_name else "TRADING PERFORMANCE"
            
            if all(v is not None for v in [param_overall, param_daily, param_win_rate, param_total]):
                try:
                    card_path = media_gen.generate_stats_card(
                        float(param_overall), float(param_daily), float(param_win_rate), int(param_total),
                        user_id=str(ref_id), ref_link=ref_link, title_text=title_str
                    )
                    if card_path and os.path.exists(card_path):
                        return send_file(card_path, mimetype="image/jpeg", as_attachment=False)
                except Exception as pe:
                    print(f"[SHARE] Error generating card with parameters: {pe}")
            
            # Bot theoretical/free signals stats
            strategy_name = request.args.get("strategy")
            if strategy_name:
                stats = database.get_theoretical_stats_by_strategy(strategy_name)
                overall_pnl = (stats.get("cumulative_pnl", 0.0) / 1000.0) * 100
                
                with database.db_session() as conn:
                    c = conn.cursor()
                    one_day_ago = int(time.time() - 86400)
                    c.execute("SELECT SUM(pnl_usdt) FROM TheoreticalTrades WHERE strategy = ? AND status != 'open' AND close_time >= ?", (strategy_name, one_day_ago))
                    daily_pnl_usdt = c.fetchone()[0] or 0.0
                    daily_pnl = (daily_pnl_usdt / 1000.0) * 100
                
                win_rate = stats.get("win_rate", 0.0)
                total_trades = stats.get("total_trades", 0)
                title_str = strategy_name
            else:
                stats = database.get_theoretical_stats()
                current_balance = stats.get("current_balance", 1000.0)
                overall_pnl = ((current_balance - 1000.0) / 1000.0) * 100
                
                with database.db_session() as conn:
                    c = conn.cursor()
                    one_day_ago = int(time.time() - 86400)
                    c.execute("SELECT SUM(pnl_usdt) FROM TheoreticalTrades WHERE status != 'open' AND close_time >= ?", (one_day_ago,))
                    daily_pnl_usdt = c.fetchone()[0] or 0.0
                    daily_pnl = (daily_pnl_usdt / 1000.0) * 100
                    
                win_rate = stats.get("win_rate", 0.0)
                total_trades = stats.get("total_trades", 0)
                title_str = "TRADING PERFORMANCE"
            
            # Free signals performance card is public/educational, show $ values
            card_path = media_gen.generate_stats_card(
                overall_pnl, daily_pnl, win_rate, total_trades,
                user_id=str(ref_id), ref_link=ref_link, title_text=title_str
            )
        else:
            # Stats for user's connected accounts
            tg_user = _get_telegram_user(user) or user
            
            if tab == "crypto":
                # Check for pre-computed query parameters first
                param_overall = request.args.get("overall_pnl_pct")
                param_daily = request.args.get("daily_pnl_pct")
                param_win_rate = request.args.get("win_rate")
                param_total = request.args.get("total_trades")
                
                
                if all(v is not None for v in [param_overall, param_daily, param_win_rate, param_total]):
                    try:
                        card_path = media_gen.generate_stats_card(
                            float(param_overall), float(param_daily), float(param_win_rate), int(param_total),
                            user_id=str(ref_id), ref_link=ref_link
                        )
                        if card_path and os.path.exists(card_path):
                            return send_file(card_path, mimetype="image/jpeg", as_attachment=False)
                    except Exception as pe:
                        print(f"[SHARE] Error generating card with parameters: {pe}", flush=True)
                
                # Fallback to live fetching
                crypto_wins = tg_user.get("wins", tg_user.get("total_wins", 0)) or 0
                crypto_losses = tg_user.get("losses", tg_user.get("total_losses", 0)) or 0
                crypto_total = crypto_wins + crypto_losses
                crypto_win_rate = (crypto_wins / crypto_total) * 100 if crypto_total > 0 else 0.0
                crypto_equity = tg_user.get("equity", 1000.0) or 1000.0
                crypto_cum_pnl = tg_user.get("cum_pnl", tg_user.get("cumulative_pnl", 0.0)) or 0.0
                
                # Fetch live crypto balance / unrealized if API key exists
                crypto_unrealized = 0.0
                crypto_api_key = tg_user.get("api_key")
                crypto_api_secret = tg_user.get("api_secret")
                crypto_api_password = tg_user.get("api_password")
                crypto_exchange_id = tg_user.get("exchange_id", "blofin")
                
                realized_daily_pnl = 0.0
                if crypto_api_key and crypto_api_secret:
                    try:
                        import ccxt
                        default_type = "swap"
                        config = {
                            "apiKey": crypto_api_key,
                            "secret": crypto_api_secret,
                            "password": crypto_api_password or "",
                            "options": {"defaultType": default_type},
                            "timeout": 3000
                        }
                        client = getattr(ccxt, crypto_exchange_id)(config)
                        try:
                            positions = client.fetch_positions()
                            for p in positions:
                                contracts = float(p.get("contracts", 0) or 0)
                                if contracts != 0:
                                    crypto_unrealized += float(p.get("unrealizedPnl", 0) or 0)
                        finally:
                            try: client.close()
                            except: pass
                    except Exception as ce:
                        futures_type = tg_user.get("bingx_futures_type", "standard")
                        type_desc = f" ({futures_type} Futures)" if crypto_exchange_id == 'bingx' else ""
                        print(f"[SHARE] Crypto live error for {crypto_exchange_id}{type_desc}: {ce}", flush=True)
                        
                overall_pnl = crypto_cum_pnl + crypto_unrealized
                overall_pnl_pct = (overall_pnl / crypto_equity) * 100 if crypto_equity > 0 else 0.0
                
                daily_pnl = realized_daily_pnl + crypto_unrealized
                daily_pnl_pct = (daily_pnl / crypto_equity) * 100 if crypto_equity > 0 else 0.0
                
                card_path = media_gen.generate_stats_card(
                    overall_pnl_pct, daily_pnl_pct, crypto_win_rate, crypto_total,
                    user_id=str(ref_id), ref_link=ref_link
                )
            else:
                # Check for pre-computed query parameters first
                param_overall = request.args.get("overall_pnl_pct")
                param_daily = request.args.get("daily_pnl_pct")
                param_win_rate = request.args.get("win_rate")
                param_total = request.args.get("total_trades")
                
                if all(v is not None for v in [param_overall, param_daily, param_win_rate, param_total]):
                    try:
                        card_path = media_gen.generate_stats_card(
                            float(param_overall), float(param_daily), float(param_win_rate), int(param_total),
                            user_id=str(ref_id), ref_link=ref_link
                        )
                        if card_path and os.path.exists(card_path):
                            return send_file(card_path, mimetype="image/jpeg", as_attachment=False)
                    except Exception as pe:
                        print(f"[SHARE] Error generating card with parameters: {pe}")

                # Stock Stats
                stock_equity = 10000.0
                stock_start_equity = 10000.0
                stock_last_equity = 10000.0
                
                stock_api_key = tg_user.get("alpaca_api_key")
                stock_api_secret = tg_user.get("alpaca_api_secret")
                
                if stock_api_key and stock_api_secret:
                    try:
                        acc = database.make_alpaca_request(tg_user, "GET", "/v2/account")
                        if acc:
                            stock_equity = float(acc.get("equity", 0) or acc.get("portfolio_value", 0))
                            stock_last_equity = float(acc.get("last_equity", 0) or stock_equity)
                            
                        transfers = database.make_alpaca_request(tg_user, "GET", "/v2/account/activities/TRANS", params={"direction": "asc"})
                        if isinstance(transfers, list) and len(transfers) > 0:
                            net_deposits = 0.0
                            for t in transfers:
                                if t.get("status") in ["COMPLETE", "complete", "EXECUTED", "executed"]:
                                    net_deposits += float(t.get("net_amount", 0) or 0)
                            if net_deposits > 0:
                                stock_start_equity = net_deposits
                            else:
                                stock_start_equity = tg_user.get("alpaca_start_equity", 10000.0) or 10000.0
                        else:
                            stock_start_equity = tg_user.get("alpaca_start_equity", 10000.0) or 10000.0
                    except Exception as se:
                        print(f"[SHARE] Stock live error: {se}")
                        
                overall_stock_pnl = stock_equity - stock_start_equity
                overall_stock_pnl_pct = (overall_stock_pnl / stock_start_equity) * 100 if stock_start_equity > 0 else 0.0
                
                stock_daily_pnl = stock_equity - stock_last_equity
                stock_daily_pnl_pct = (stock_daily_pnl / stock_last_equity) * 100 if stock_last_equity > 0 else 0.0
                
                if tg_user.get("telegram_chat_id"):
                    trade_chat_id = int(tg_user["telegram_chat_id"])
                else:
                    trade_chat_id = int(user["id"]) + 1000000000
                
                stock_wins = 0
                stock_losses = 0
                
                # Try to fetch actual closed orders from Alpaca API to compute wins/losses
                if stock_api_key and stock_api_secret:
                    try:
                        orders = database.make_alpaca_request(tg_user, "GET", "/v2/orders", params={"status": "closed", "limit": 100})
                        if isinstance(orders, list):
                            for o in orders:
                                qty = float(o.get("filled_qty", 0) or 0)
                                if qty > 0 and o.get("side") == "sell":
                                    price = float(o.get("filled_avg_price", 0))
                                    entry = price
                                    for prev in orders:
                                        if prev["symbol"] == o["symbol"] and prev["side"] == "buy":
                                            entry = float(prev.get("filled_avg_price", price))
                                            break
                                    pnl_raw = (price - entry) * qty
                                    if pnl_raw > 0:
                                        stock_wins += 1
                                    else:
                                        stock_losses += 1
                    except Exception as se:
                        print(f"[SHARE] Stock live error: {se}")
                
                # Fallback to database if still 0
                if stock_wins == 0 and stock_losses == 0:
                    try:
                        with database.db_session() as conn:
                            c = conn.cursor()
                            c.execute("SELECT COUNT(*) FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND status = 'closed' AND pnl_raw > 0", (trade_chat_id,))
                            stock_wins = c.fetchone()[0] or 0
                            c.execute("SELECT COUNT(*) FROM AlpacaActiveTrades WHERE telegram_chat_id = ? AND status = 'closed' AND pnl_raw <= 0", (trade_chat_id,))
                            stock_losses = c.fetchone()[0] or 0
                    except: pass
                
                stock_total = stock_wins + stock_losses
                stock_win_rate = (stock_wins / stock_total) * 100 if stock_total > 0 else 0.0
                
                card_path = media_gen.generate_stats_card(
                    overall_stock_pnl_pct, stock_daily_pnl_pct, stock_win_rate, stock_total,
                    user_id=str(ref_id), ref_link=ref_link
                )
    elif card_type in ["trade", "signal"]:
        if not symbol:
            return jsonify({"error": "Symbol is required"}), 400
            
        card_path = media_gen.generate_pnl_card(
            symbol, side, roe, entry, mark,
            hide_dollars=hide_dollars,
            pnl_usdt=pnl_usdt,
            user_id=str(ref_id),
            ref_link=ref_link
        )
    else:
        return jsonify({"error": "Invalid card type"}), 400

    if card_path and os.path.exists(card_path):
        return send_file(card_path, mimetype="image/jpeg", as_attachment=False)
    else:
        return jsonify({"error": "Failed to generate card image"}), 500

CHART_MEM_CACHE = {}
CHART_MEM_CACHE_LOCK = threading.Lock()
CHART_CACHE_TTL_SECONDS = 300  # 5 minutes
CHART_MAX_CACHE_SIZE = 200

@trades_bp.route('/api/trades/chart', methods=['GET'])
def get_trade_chart():
    symbol = request.args.get("symbol")
    try:
        entry = float(request.args.get("entry", 0.0))
        tp = float(request.args.get("tp", 0.0))
        sl = float(request.args.get("sl", 0.0))
        open_ts = int(request.args.get("open_ts", 0))
        current_price = float(request.args.get("current_price", 0.0))
    except ValueError:
        return "Invalid numeric parameters", 400
        
    side = request.args.get("side", "LONG").upper()
    trade_type = request.args.get("type", "crypto")

    if not symbol:
        return "Symbol required", 400

    # Bucket current price to 1% intervals of entry price to maximize cache hits
    price_pct_bucket = round(current_price / entry, 2) if entry > 0 else 1.0
    
    # Time-bucket to 5-minute intervals
    time_bucket = int(time.time() // 300)
    
    cache_key = f"{symbol}_{entry}_{tp}_{sl}_{side}_{price_pct_bucket}_{time_bucket}"
    
    with CHART_MEM_CACHE_LOCK:
        cached = CHART_MEM_CACHE.get(cache_key)
        if cached:
            cached_ts, png_bytes = cached
            if time.time() - cached_ts < CHART_CACHE_TTL_SECONDS:
                import io
                return send_file(
                    io.BytesIO(png_bytes),
                    mimetype='image/png',
                    as_attachment=False
                )

    t_start = time.time()
    try:
        import charting
        import live_bot_multi
        
        df_chart = None
        if trade_type == "stock":
            timeframe = "1D"
            try:
                conn = sqlite3.connect(STOCK_DB_PATH)
                df_chart = pd.read_sql_query("SELECT * FROM StockDailyData WHERE symbol = ? ORDER BY date ASC", conn, params=(symbol,))
                conn.close()
                if not df_chart.empty:
                    df_chart['timestamp'] = pd.to_datetime(df_chart['date']).astype('datetime64[ms]').astype('int64')
                    df_chart = df_chart.copy()
                else:
                    df_chart = None
            except Exception as e:
                print(f"Error fetching from stock daily cache: {e}", flush=True)
        else:
            timeframe = "15M"
            try:
                # Sourcing OHLCV from Binance public API is fast (less than 1s) and avoids CCXT overhead
                clean_sym = symbol.split(":")[0].replace("/", "")
                endpoints = [
                    f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval=15m&limit=100",
                    f"https://api.binance.us/api/v3/klines?symbol={clean_sym}&interval=15m&limit=100"
                ]
                klines_data = None
                for url in endpoints:
                    try:
                        resp = requests.get(url, timeout=3)
                        if resp.status_code == 200:
                            klines_data = resp.json()
                            break
                    except Exception:
                        continue
                
                if klines_data:
                    ohlcv = []
                    for item in klines_data:
                        ohlcv.append([
                            int(item[0]),
                            float(item[1]),
                            float(item[2]),
                            float(item[3]),
                            float(item[4]),
                            float(item[5])
                        ])
                    df_chart = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                else:
                    # Fallback to CCXT Blofin
                    mdm = live_bot_multi.MarketDataManager()
                    mdm.exchange.timeout = 3000
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        df_chart = loop.run_until_complete(mdm.fetch_ohlcv(symbol, "15m"))
                    finally:
                        loop.run_until_complete(mdm.close())
                    loop.close()
            except Exception as e:
                print(f"Error fetching OHLCV: {e}", flush=True)

        if df_chart is None or df_chart.empty:
            dates = pd.date_range(end=pd.Timestamp.now(), periods=30, freq='D' if trade_type == "stock" else '15T')
            df_chart = pd.DataFrame({
                'timestamp': dates.astype('datetime64[ms]').astype('int64'),
                'open': [entry] * 30,
                'high': [entry * 1.01] * 30,
                'low': [entry * 0.99] * 30,
                'close': [entry] * 30,
                'volume': [1000] * 30
            })

        chart_file = charting.generate_trade_chart(
            symbol=symbol,
            df=df_chart,
            entry=entry,
            tp=tp,
            sl=sl,
            side=side,
            open_ts=open_ts,
            timeframe=timeframe,
            current_price=current_price
        )
        
        # Read the generated chart image bytes
        with open(chart_file, 'rb') as f:
            png_bytes = f.read()
            
        # Save to memory cache and enforce cleanup/size-bounding
        with CHART_MEM_CACHE_LOCK:
            CHART_MEM_CACHE[cache_key] = (time.time(), png_bytes)
            
            # 1. Evict expired entries
            now = time.time()
            expired_keys = [k for k, v in CHART_MEM_CACHE.items() if now - v[0] > CHART_CACHE_TTL_SECONDS]
            for k in expired_keys:
                CHART_MEM_CACHE.pop(k, None)
                
            # 2. Bound the cache size (evict oldest inserted)
            if len(CHART_MEM_CACHE) > CHART_MAX_CACHE_SIZE:
                oldest_keys = list(CHART_MEM_CACHE.keys())[:len(CHART_MEM_CACHE) - CHART_MAX_CACHE_SIZE]
                for k in oldest_keys:
                    CHART_MEM_CACHE.pop(k, None)
                    
        import io
        return send_file(io.BytesIO(png_bytes), mimetype='image/png')
    except Exception as e:
        print(f"Error generating chart endpoint: {e}", flush=True)
        return f"Error: {str(e)}", 500

@trades_bp.route('/api/user/manual-trade', methods=['POST'])
@require_auth
def manual_trade():
    user = g.user
    data = request.json
    trade_id = data.get("signal_id")
    
    now = int(time.time())
    tg_user = _get_telegram_user(user)
    
    web_premium_expiry = user.get("premium_expiry") or 0
    bot_premium_expiry = (tg_user.get("premium_expiry") or 0) if tg_user else 0
    max_expiry = max(web_premium_expiry, bot_premium_expiry)
    
    is_super_admin = False
    super_admin_id = utils_gcp.get_secret("SUPER_ADMIN_ID")
    if super_admin_id:
        try:
            if user.get("telegram_chat_id") == int(super_admin_id) or (tg_user and tg_user.get("telegram_chat_id") == int(super_admin_id)):
                is_super_admin = True
        except ValueError:
            pass
            
    is_admin = user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin
    is_premium = max_expiry > now or is_admin
    
    if not is_premium:
        return jsonify({"success": False, "error": "Premium required"}), 403
        
    chat_id = user.get("telegram_chat_id")
    if not chat_id:
        return jsonify({"success": False, "error": "Please connect your Telegram account first."}), 400
        
    from bot.handlers.trading import execute_manual_trade
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success, msg = loop.run_until_complete(execute_manual_trade(chat_id, trade_id))
        return jsonify({"success": success, "message": msg}), 200 if success else 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        loop.close()
