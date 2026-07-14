import os
import json
import time
import requests
import concurrent.futures
import yfinance as yf
import ccxt
from flask import Blueprint, request, jsonify, g
from datetime import datetime
import collections
import threading

import database
from database import db_session, get_config, update_config
from web_api.auth import require_auth, require_premium
import utils_gcp
from web_api.routes_trades import get_active_signals_internal
from bot.config import is_stock

portfolio_bp = Blueprint('portfolio', __name__)

def is_user_admin(user):
    if not user: return False
    import database
    tg_id = user.get("telegram_chat_id")
    tg_user = None
    if tg_id:
        try:
            tg_user = database.get_user(int(tg_id))
        except:
            pass
    is_super_admin = (tg_id == 1567788633 or user.get("email") == "gilesasp@gmail.com")
    return user.get("is_admin", False) or (tg_user and tg_user.get("is_admin", False)) or is_super_admin

# --- 🚀 Price Caching system ---
_PRICE_CACHE = {}  # {symbol: (price, change_pct, timestamp)}
_CACHE_DURATION = 3600  # 1 hour in seconds
_NEWS_CACHE = {}  # {user_id: (news_json, timestamp)}
_NEWS_CACHE_DURATION = 3600  # 1 hour in seconds

# --- 📊 Global Market Data Cache (shared across all users) ---
STOCK_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B",
    "JPM", "V", "MA", "UNH", "LLY", "AVGO", "COST", "HD",
    "PG", "JNJ", "ABBV", "CRM", "AMD", "NFLX", "XOM", "CVX",
    "PEP", "KO", "WMT", "MRK", "ORCL", "ADBE"
]

CRYPTO_WATCHLIST = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX",
    "DOT", "LINK", "XLM", "SHIB", "AAVE", "LTC", "ATOM",
    "NEAR", "LDO", "ARB", "OP", "RENDER"
]

_MARKET_DATA_CACHE = {
    "stocks": {},
    "crypto": {},
    "last_refresh": 0
}
_MARKET_DATA_LOCK = threading.Lock()
_MARKET_DATA_TTL = 43200  # 12 hours in seconds

_GOOD_BUYS_LOCKS = collections.defaultdict(threading.Lock)

_SPECULATIVE_STOCK_CACHE = {
    "stocks": {},
    "last_refresh": 0
}
_SPECULATIVE_MARKET_DATA_LOCK = threading.Lock()
FALLBACK_SPECULATIVE_WATCHLIST = ['TSLA', 'PLTR', 'AMD', 'COIN', 'MARA', 'RIOT', 'SOXL', 'UPST', 'CLSK', 'SOFI']

def _refresh_market_data_cache():
    """Fetch 30d price history for all watchlist assets and compute screening metrics."""
    try:
        now = time.time()
        new_stocks = {}
        new_crypto = {}

        # --- STOCKS ---
        try:
            stock_df = yf.download(
                STOCK_WATCHLIST,
                period="1mo",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False
            )
            for sym in STOCK_WATCHLIST:
                try:
                    if len(STOCK_WATCHLIST) == 1:
                        df = stock_df
                    else:
                        df = stock_df[sym]

                    closes = df["Close"].dropna()
                    if len(closes) < 2:
                        continue

                    current_price = float(closes.iloc[-1])
                    price_7d_ago = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
                    price_30d_ago = float(closes.iloc[0])

                    ret_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100
                    ret_30d = ((current_price - price_30d_ago) / price_30d_ago) * 100
                    avg_vol = int(df["Volume"].dropna().mean()) if "Volume" in df.columns else 0

                    ticker_obj = yf.Ticker(sym)
                    fi = ticker_obj.fast_info
                    high_52w = float(fi.get("year_high", current_price))
                    low_52w = float(fi.get("year_low", current_price))
                    market_cap = int(fi.get("market_cap", 0))

                    new_stocks[sym] = {
                        "price": round(current_price, 2),
                        "7d_return": round(ret_7d, 2),
                        "30d_return": round(ret_30d, 2),
                        "avg_volume": avg_vol,
                        "52w_high": round(high_52w, 2),
                        "52w_low": round(low_52w, 2),
                        "market_cap": market_cap,
                        "pct_from_52w_high": round(((current_price - high_52w) / high_52w) * 100, 2)
                    }
                except Exception:
                    continue
        except Exception as e:
            print(f"[MarketCache] Stock fetch error: {e}")

        # --- CRYPTO ---
        try:
            crypto_yf_symbols = [f"{sym}-USD" for sym in CRYPTO_WATCHLIST]
            crypto_df = yf.download(
                crypto_yf_symbols,
                period="1mo",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False
            )
            for sym in CRYPTO_WATCHLIST:
                yf_sym = f"{sym}-USD"
                try:
                    if len(CRYPTO_WATCHLIST) == 1:
                        df = crypto_df
                    else:
                        df = crypto_df[yf_sym]

                    closes = df["Close"].dropna()
                    if len(closes) < 2:
                        continue

                    current_price = float(closes.iloc[-1])
                    price_7d_ago = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
                    price_30d_ago = float(closes.iloc[0])

                    ret_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100
                    ret_30d = ((current_price - price_30d_ago) / price_30d_ago) * 100
                    avg_vol = int(df["Volume"].dropna().mean()) if "Volume" in df.columns else 0

                    ticker_obj = yf.Ticker(yf_sym)
                    fi = ticker_obj.fast_info
                    high_52w = float(fi.get("year_high", current_price))
                    low_52w = float(fi.get("year_low", current_price))
                    market_cap = int(fi.get("market_cap", 0))

                    new_crypto[sym] = {
                        "price": round(current_price, 6) if current_price < 1 else round(current_price, 2),
                        "7d_return": round(ret_7d, 2),
                        "30d_return": round(ret_30d, 2),
                        "avg_volume": avg_vol,
                        "52w_high": round(high_52w, 2),
                        "52w_low": round(low_52w, 2),
                        "market_cap": market_cap,
                        "pct_from_52w_high": round(((current_price - high_52w) / high_52w) * 100, 2)
                    }
                except Exception:
                    continue
        except Exception as e:
            print(f"[MarketCache] Crypto fetch error: {e}")

        with _MARKET_DATA_LOCK:
            if new_stocks:
                _MARKET_DATA_CACHE["stocks"] = new_stocks
            if new_crypto:
                _MARKET_DATA_CACHE["crypto"] = new_crypto
            _MARKET_DATA_CACHE["last_refresh"] = now

        print(f"[MarketCache] Refreshed: {len(new_stocks)} stocks, {len(new_crypto)} crypto")
    except Exception as e:
        print(f"[MarketCache] Fatal refresh error: {e}")

def _schedule_market_data_refresh():
    """Run market data refresh every 4 hours in a background thread."""
    _refresh_market_data_cache()
    # Schedule next run in 4 hours (14400 seconds)
    t = threading.Timer(14400, _schedule_market_data_refresh)
    t.daemon = True  # Dies when main process dies
    t.start()

# Start the first refresh in a background thread on module load
_initial_refresh = threading.Thread(target=_schedule_market_data_refresh, daemon=True)
_initial_refresh.start()

def _fetch_speculative_stock_symbols():
    symbols = set()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for scr_id in ["most_actives", "day_gainers"]:
        url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&scrIds={scr_id}&count=25"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            data = response.json()
            results = data.get("finance", {}).get("result", [])
            if results:
                for q in results[0].get("quotes", []):
                    sym = q.get('symbol', '')
                    if sym and "^" not in sym and "=" not in sym and "-" not in sym:
                        symbols.add(sym)
        except Exception as e:
            print(f"[MarketCache] Speculative fetch error for {scr_id}: {e}")
    if not symbols:
        return FALLBACK_SPECULATIVE_WATCHLIST
    return list(symbols)

def _get_speculative_market_data():
    with _SPECULATIVE_MARKET_DATA_LOCK:
        last_refresh = _SPECULATIVE_STOCK_CACHE.get("last_refresh", 0)
        if time.time() - last_refresh < 3600 and _SPECULATIVE_STOCK_CACHE.get("stocks"):
            return dict(_SPECULATIVE_STOCK_CACHE["stocks"])

    symbols = _fetch_speculative_stock_symbols()
    new_stocks = {}
    try:
        stock_df = yf.download(symbols, period="1mo", interval="1d", group_by="ticker", auto_adjust=True, threads=True, progress=False)
        for sym in symbols:
            try:
                df = stock_df if len(symbols) == 1 else stock_df[sym]
                closes = df["Close"].dropna()
                if len(closes) < 2: continue
                current_price = float(closes.iloc[-1])
                price_7d_ago = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
                price_30d_ago = float(closes.iloc[0])
                ret_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100
                ret_30d = ((current_price - price_30d_ago) / price_30d_ago) * 100
                avg_vol = int(df["Volume"].dropna().mean()) if "Volume" in df.columns else 0
                
                ticker_obj = yf.Ticker(sym)
                fi = ticker_obj.fast_info
                high_52w = float(fi.get("year_high", current_price))
                low_52w = float(fi.get("year_low", current_price))
                market_cap = int(fi.get("market_cap", 0))

                new_stocks[sym] = {
                    "price": round(current_price, 2),
                    "7d_return": round(ret_7d, 2),
                    "30d_return": round(ret_30d, 2),
                    "avg_volume": avg_vol,
                    "52w_high": round(high_52w, 2),
                    "52w_low": round(low_52w, 2),
                    "market_cap": market_cap,
                    "pct_from_52w_high": round(((current_price - high_52w) / high_52w) * 100, 2)
                }
            except Exception:
                continue
        with _SPECULATIVE_MARKET_DATA_LOCK:
            _SPECULATIVE_STOCK_CACHE["stocks"] = new_stocks
            _SPECULATIVE_STOCK_CACHE["last_refresh"] = time.time()
    except Exception as e:
        print(f"[MarketCache] Failed to download speculative data: {e}")
    
    return new_stocks

def _build_market_research_brief(user_id, risk_profile="Moderate", investment_goal="Growth"):
    """Build a structured research brief from cached market data + active signals."""
    # 1. Get cached market data
    with _MARKET_DATA_LOCK:
        stock_data = dict(_MARKET_DATA_CACHE.get("stocks", {}))
        crypto_data = dict(_MARKET_DATA_CACHE.get("crypto", {}))
        last_refresh = _MARKET_DATA_CACHE.get("last_refresh", 0)

    # If cache is empty or stale (>12h), do an on-demand refresh
    if not stock_data and not crypto_data:
        _refresh_market_data_cache()
        with _MARKET_DATA_LOCK:
            stock_data = dict(_MARKET_DATA_CACHE.get("stocks", {}))
            crypto_data = dict(_MARKET_DATA_CACHE.get("crypto", {}))

    # If aggressive and speculation, swap the stock_data with dynamic speculative candidates
    if risk_profile.lower() == "aggressive" and investment_goal.lower() == "speculation":
        speculative_data = _get_speculative_market_data()
        if speculative_data:
            stock_data = speculative_data

    # 2. Get active bot signals
    active_signals = get_active_signals_internal(bypass_cache=False)
    open_longs = [s for s in active_signals if s.get("status") == "open" and s.get("side", "").lower() == "long"]

    # Build lookup: symbol -> signal data
    signal_lookup = {}
    for s in open_longs:
        sym = s.get("symbol", "").replace("/USDT", "").replace("/USD", "").upper()
        signal_lookup[sym] = {
            "strategy": s.get("strategy", ""),
            "entry_price": s.get("entry_price", 0),
            "tp_price": s.get("tp_price", 0),
            "sl_price": s.get("sl_price", 0),
        }

    # 3. Get user's existing holdings to exclude
    held_symbols = set()
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT symbol FROM PortfolioPositions WHERE user_id = ?', (user_id,))
        for row in c.fetchall():
            held_symbols.add(database.decrypt(row[0]).upper())

    # 4. Build the text brief
    brief_lines = []
    brief_lines.append("=== STOCK CANDIDATES ===")
    brief_lines.append("(Sorted by 30-day return. Assets the user already holds are excluded.)")
    brief_lines.append("")

    for sym in sorted(stock_data.keys(), key=lambda s: stock_data[s].get("30d_return", 0), reverse=True):
        if sym in held_symbols:
            continue
        d = stock_data[sym]
        sig = signal_lookup.get(sym)
        line = (
            f"  {sym}: Price=${d['price']} | 7d={d['7d_return']:+.1f}% | 30d={d['30d_return']:+.1f}% | "
            f"Vol={d['avg_volume']:,} | 52wHigh=${d['52w_high']} ({d['pct_from_52w_high']:+.1f}% from high) | "
            f"MktCap=${d['market_cap']:,}"
        )
        if sig:
            tp_upside = ((sig['tp_price'] - sig['entry_price']) / sig['entry_price'] * 100) if sig['entry_price'] > 0 else 0
            line += f" | ⚡ ACTIVE SIGNAL (Strategy: {sig['strategy']}, TP Upside: {tp_upside:+.1f}%)"
        brief_lines.append(line)

    brief_lines.append("")
    brief_lines.append("=== CRYPTO CANDIDATES ===")
    brief_lines.append("(Sorted by 30-day return. Assets the user already holds are excluded.)")
    brief_lines.append("(Note: Our crypto bot signals are 15-minute scalps, NOT buy-and-hold. Weigh them less.)")
    brief_lines.append("")

    for sym in sorted(crypto_data.keys(), key=lambda s: crypto_data[s].get("30d_return", 0), reverse=True):
        if sym in held_symbols:
            continue
        d = crypto_data[sym]
        sig = signal_lookup.get(sym)
        line = (
            f"  {sym}: Price=${d['price']} | 7d={d['7d_return']:+.1f}% | 30d={d['30d_return']:+.1f}% | "
            f"Vol={d['avg_volume']:,} | 52wHigh=${d['52w_high']} ({d['pct_from_52w_high']:+.1f}% from high) | "
            f"MktCap=${d['market_cap']:,}"
        )
        if sig:
            line += f" | ⚡ ACTIVE SIGNAL (Strategy: {sig['strategy']}, short-term scalp)"
        brief_lines.append(line)

    return "\\n".join(brief_lines)

def get_stock_prices(symbols):
    """Fetch batch stock prices from Alpaca snapshots API using system credentials."""
    prices = {}
    if not symbols:
        return prices

    api_key = utils_gcp.get_secret("ALPACA_API_KEY")
    api_secret = utils_gcp.get_secret("ALPACA_API_SECRET")

    if not api_key or not api_secret:
        return {sym: (None, 0.0) for sym in symbols}

    url = "https://data.alpaca.markets/v2/stocks/snapshots"
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    params = {
        "symbols": ",".join(symbols),
        "feed": "iex"
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            # Alpaca v2 snapshots returns symbols directly at the root
            snapshots = data.get("snapshots") if "snapshots" in data else data
            for sym in symbols:
                snap = snapshots.get(sym)
                if snap:
                    last_price = snap.get("latestTrade", {}).get("p") or snap.get("dailyBar", {}).get("c")
                    prev_close = snap.get("prevDailyBar", {}).get("c")
                    if last_price and prev_close:
                        change_pct = ((last_price - prev_close) / prev_close) * 100
                    elif last_price and snap.get("dailyBar", {}).get("o"):
                        o_val = snap.get("dailyBar", {}).get("o")
                        change_pct = ((last_price - o_val) / o_val) * 100
                    else:
                        change_pct = 0.0
                    prices[sym] = (float(last_price) if last_price else None, float(change_pct))
                else:
                    prices[sym] = (None, 0.0)
        else:
            for sym in symbols:
                prices[sym] = (None, 0.0)
    except Exception:
        for sym in symbols:
            prices[sym] = (None, 0.0)
    return prices

def get_crypto_prices(symbols):
    """Fetch batch crypto prices from CCXT Binance (with Coinbase fallback)."""
    prices = {}
    if not symbols:
        return prices

    try:
        exchange = ccxt.binance({
            "options": {"defaultType": "spot"},
            "enableRateLimit": True,
            "timeout": 3000
        })
        ccxt_symbols = [f"{sym}/USDT" for sym in symbols]
        tickers = exchange.fetch_tickers(ccxt_symbols)
        for sym in symbols:
            t = tickers.get(f"{sym}/USDT")
            if t:
                prices[sym] = (float(t.get('last') or t.get('close')), float(t.get('percentage') or 0.0))
    except Exception:
        pass

    missing_symbols = [s for s in symbols if s not in prices]
    if missing_symbols:
        binance_exch = ccxt.binance({'timeout': 3000})
        coinbase_exch = ccxt.coinbase({'timeout': 3000})
        
        def fetch_single(sym):
            try:
                t = binance_exch.fetch_ticker(f"{sym}/USDT")
                return sym, float(t.get('last') or t.get('close')), float(t.get('percentage') or 0.0)
            except Exception:
                try:
                    t = coinbase_exch.fetch_ticker(f"{sym}/USD")
                    return sym, float(t.get('last') or t.get('close')), float(t.get('percentage') or 0.0)
                except Exception:
                    return sym, None, 0.0

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(fetch_single, missing_symbols)
            for sym, price, pct in results:
                prices[sym] = (price, pct)

    return prices

def get_cached_prices(symbols, categories):
    """Get stock and crypto prices using in-memory caching."""
    now = time.time()
    to_fetch_stock = []
    to_fetch_crypto = []
    result = {}

    for sym, cat in zip(symbols, categories):
        sym = sym.upper()
        cat = cat.lower()
        cache_key = f"{sym}_{cat}"
        if cache_key in _PRICE_CACHE:
            price, pct, ts = _PRICE_CACHE[cache_key]
            if now - ts < _CACHE_DURATION:
                result[cache_key] = (price, pct)
                continue
        if cat == 'stock':
            if sym not in to_fetch_stock:
                to_fetch_stock.append(sym)
        else:
            if sym not in to_fetch_crypto:
                to_fetch_crypto.append(sym)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_stock = executor.submit(get_stock_prices, to_fetch_stock) if to_fetch_stock else None
        f_crypto = executor.submit(get_crypto_prices, to_fetch_crypto) if to_fetch_crypto else None

        if f_stock:
            stock_prices = f_stock.result()
            for sym, val in stock_prices.items():
                cache_key = f"{sym}_stock"
                if val[0] is not None:
                    _PRICE_CACHE[cache_key] = (val[0], val[1], now)
                result[cache_key] = val

        if f_crypto:
            crypto_prices = f_crypto.result()
            for sym, val in crypto_prices.items():
                cache_key = f"{sym}_crypto"
                if val[0] is not None:
                    _PRICE_CACHE[cache_key] = (val[0], val[1], now)
                result[cache_key] = val

    # Ensure all requested keys are in the result
    for sym, cat in zip(symbols, categories):
        cache_key = f"{sym.upper()}_{cat.lower()}"
        if cache_key not in result:
            result[cache_key] = (None, 0.0)

    return result


# --- 🤖 Gemini Helper Function ---
def call_gemini(prompt, system_instruction=None, json_mode=False, image_base64=None, mime_type="image/jpeg"):
    """Call Google Gemini API using configured env variables/secrets."""
    url = os.getenv("PORTFOLIO_AI_URL") or "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    api_key = utils_gcp.get_secret("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    if "generativelanguage.googleapis.com" in url:
        url_with_key = f"{url}?key={api_key}"
    else:
        url_with_key = url

    headers = {
        "Content-Type": "application/json"
    }
    if "generativelanguage.googleapis.com" not in url:
        headers["x-goog-api-key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"

    parts = []
    if image_base64:
        parts.append({
            "inlineData": {
                "mimeType": mime_type,
                "data": image_base64
            }
        })
    parts.append({"text": prompt})
    contents = [{"parts": parts}]
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2
        }
    }

    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    try:
        res = requests.post(url_with_key, headers=headers, json=payload, timeout=120)
        if res.status_code == 200:
            res_data = res.json()
            candidates = res_data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return ""
        else:
            raise RuntimeError(f"Gemini API returned status {res.status_code}: {res.text}")
    except Exception as e:
        raise e


# --- 📂 DB / Positions API Handlers ---

@portfolio_bp.route('/api/portfolio', methods=['GET'])
@require_auth
@require_premium
def get_portfolio():
    user_id = g.user["id"]
    positions = []
    cash_balance = 0.0
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT cash_balance FROM WebUsers WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row and row[0] is not None:
            cash_balance = float(row[0])

        c.execute('''
            SELECT id, symbol, name, category, quantity, avg_entry_price, purchase_date, dividend_yield
            FROM PortfolioPositions
            WHERE user_id = ?
            ORDER BY symbol ASC
        ''', (user_id,))
        rows = c.fetchall()
        for r in rows:
            positions.append({
                "id": r[0],
                "symbol": database.decrypt(r[1]),
                "name": database.decrypt(r[2]) or database.decrypt(r[1]),
                "category": r[3],
                "quantity": float(database.decrypt(r[4])),
                "avg_entry_price": float(database.decrypt(r[5])),
                "purchase_date": database.decrypt(r[6]),
                "dividend_yield": float(database.decrypt(r[7]) or 0.0)
            })

    if not positions:
        return jsonify({
            "positions": [],
            "stats": {
                "cash_balance": cash_balance,
                "total_portfolio_value": cash_balance,
                "market_value": 0.0,
                "cost_basis": 0.0,
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "daily_pnl": 0.0,
                "daily_pnl_pct": 0.0,
                "annual_dividends": 0.0,
                "dividend_yield_pct": 0.0,
                "win_rate": 0.0,
                "positions_count": 0,
                "avg_hold_time_days": 0,
                "portfolio_age_days": 0,
                "best_performer": "-",
                "best_performer_pct": 0.0,
                "worst_performer": "-",
                "worst_performer_pct": 0.0,
                "top_mover": "-",
                "top_mover_pct": 0.0,
                "avg_daily_pnl": 0.0
            },
            "allocation": []
        }), 200

    symbols = [p["symbol"] for p in positions]
    categories = [p["category"] for p in positions]
    prices_map = get_cached_prices(symbols, categories)

    total_market_value = 0.0
    total_cost_basis = 0.0
    total_daily_pnl = 0.0
    total_annual_dividends = 0.0
    profitable_count = 0
    earliest_purchase = None
    total_hold_time_days = 0

    best_perf_sym = "-"
    best_perf_pct = -999999.0
    worst_perf_sym = "-"
    worst_perf_pct = 999999.0

    top_mover_sym = "-"
    top_mover_pct = 0.0

    # Populate position metrics
    for p in positions:
        sym = p["symbol"].upper()
        cat = p["category"].lower()
        cache_key = f"{sym}_{cat}"
        curr_price, daily_change_pct = prices_map.get(cache_key, (None, 0.0))
        if curr_price is None:
            curr_price = p["avg_entry_price"]

        p["current_price"] = curr_price
        p["daily_change_pct"] = daily_change_pct
        
        cost_basis = p["quantity"] * p["avg_entry_price"]
        market_value = p["quantity"] * curr_price
        overall_pnl = market_value - cost_basis
        overall_pnl_pct = ((curr_price - p["avg_entry_price"]) / p["avg_entry_price"] * 100) if p["avg_entry_price"] > 0 else 0.0
        
        daily_pnl = market_value * (daily_change_pct / 100)
        annual_div = cost_basis * p["dividend_yield"]

        p["cost_basis"] = cost_basis
        p["market_value"] = market_value
        p["overall_pnl"] = overall_pnl
        p["overall_pnl_pct"] = overall_pnl_pct
        p["daily_pnl"] = daily_pnl
        p["annual_dividend"] = annual_div

        total_market_value += market_value
        total_cost_basis += cost_basis
        total_daily_pnl += daily_pnl
        total_annual_dividends += annual_div

        if overall_pnl > 0:
            profitable_count += 1

        # Dates & hold times
        try:
            p_date = datetime.strptime(p["purchase_date"], "%Y-%m-%d")
            if earliest_purchase is None or p_date < earliest_purchase:
                earliest_purchase = p_date
            
            hold_days = (datetime.now() - p_date).days
            p["hold_time_days"] = max(0, hold_days)
            total_hold_time_days += p["hold_time_days"]
        except Exception:
            p["hold_time_days"] = 0

        # Performance checkers
        if overall_pnl_pct > best_perf_pct:
            best_perf_pct = overall_pnl_pct
            best_perf_sym = p["symbol"]
        if overall_pnl_pct < worst_perf_pct:
            worst_perf_pct = overall_pnl_pct
            worst_perf_sym = p["symbol"]

        # Today's top mover
        if abs(daily_change_pct) > abs(top_mover_pct):
            top_mover_pct = daily_change_pct
            top_mover_sym = p["symbol"]

    # Compute percentage allocations
    total_denominator = total_market_value + cash_balance
    allocation_list = []
    for p in positions:
        pct = (p["market_value"] / total_denominator * 100) if total_denominator > 0 else 0.0
        p["allocation_pct"] = pct
        allocation_list.append({
            "name": p["symbol"],
            "value": p["market_value"],
            "percentage": pct
        })

    if cash_balance > 0:
        cash_pct = (cash_balance / total_denominator * 100) if total_denominator > 0 else 0.0
        allocation_list.append({
            "name": "CASH",
            "value": cash_balance,
            "percentage": cash_pct
        })

    allocation_list = sorted(allocation_list, key=lambda x: x["value"], reverse=True)

    # General Stats calculations
    total_pnl = total_market_value - total_cost_basis
    total_pnl_pct = (total_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0.0
    daily_pnl_pct = (total_daily_pnl / total_market_value * 100) if total_market_value > 0 else 0.0
    div_yield_pct = (total_annual_dividends / total_cost_basis * 100) if total_cost_basis > 0 else 0.0
    win_rate = (profitable_count / len(positions) * 100) if positions else 0.0
    avg_hold_time = int(total_hold_time_days / len(positions)) if positions else 0
    portfolio_age = (datetime.now() - earliest_purchase).days if earliest_purchase else 0

    stats = {
        "cash_balance": cash_balance,
        "total_portfolio_value": total_market_value + cash_balance,
        "market_value": total_market_value,
        "cost_basis": total_cost_basis,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "daily_pnl": total_daily_pnl,
        "daily_pnl_pct": daily_pnl_pct,
        "annual_dividends": total_annual_dividends,
        "dividend_yield_pct": div_yield_pct,
        "win_rate": win_rate,
        "positions_count": len(positions),
        "avg_hold_time_days": avg_hold_time,
        "portfolio_age_days": portfolio_age,
        "best_performer": best_perf_sym if best_perf_sym != "-" else None,
        "best_performer_pct": best_perf_pct if best_perf_pct != -999999.0 else 0.0,
        "worst_performer": worst_perf_sym if worst_perf_sym != "-" else None,
        "worst_performer_pct": worst_perf_pct if worst_perf_pct != 999999.0 else 0.0,
        "top_mover": top_mover_sym if top_mover_sym != "-" else None,
        "top_mover_pct": top_mover_pct,
        "avg_daily_pnl": total_daily_pnl / len(positions) if positions else 0.0
    }

    return jsonify({
        "positions": positions,
        "stats": stats,
        "allocation": allocation_list
    }), 200

@portfolio_bp.route('/api/portfolio/cash', methods=['POST'])
@require_auth
@require_premium
def update_cash():
    data = request.json or {}
    if "cash_balance" not in data:
        return jsonify({"error": "Missing cash_balance."}), 400
    try:
        cash_balance = float(data["cash_balance"])
    except ValueError:
        return jsonify({"error": "Invalid cash_balance value."}), 400
        
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET cash_balance = ?, last_portfolio_update = ? WHERE id = ?', 
                  (cash_balance, int(time.time()), g.user["id"]))
        conn.commit()
        
    return jsonify({"message": "Cash balance updated successfully.", "cash_balance": cash_balance}), 200

@portfolio_bp.route('/api/portfolio/position', methods=['POST'])
@require_auth
@require_premium
def add_position():
    data = request.json or {}
    symbol = data.get("symbol", "").strip().upper()
    category = data.get("category", "stock").strip().lower()
    quantity = float(data.get("quantity", 0))
    avg_entry_price = float(data.get("avg_entry_price", 0))
    purchase_date = data.get("purchase_date", "").strip()
    dividend_yield = float(data.get("dividend_yield") or 0.0) / 100.0
    deduct_from_cash = data.get("deduct_from_cash", False)
    auto_top_up = data.get("auto_top_up", False)

    if not symbol or not purchase_date or quantity <= 0 or avg_entry_price <= 0:
        return jsonify({"error": "Missing or invalid position details."}), 400

    name = symbol
    if category == 'stock':
        api_key = utils_gcp.get_secret("ALPACA_API_KEY")
        api_secret = utils_gcp.get_secret("ALPACA_API_SECRET")
        if api_key and api_secret:
            try:
                url = f"https://paper-api.alpaca.markets/v2/assets/{symbol}"
                headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}
                res = requests.get(url, headers=headers, timeout=5)
                if res.status_code == 200:
                    name = res.json().get("name", symbol)
            except Exception:
                pass

    with db_session() as conn:
        c = conn.cursor()
        
        if deduct_from_cash:
            cost_basis = quantity * avg_entry_price
            c.execute('SELECT cash_balance FROM WebUsers WHERE id = ?', (g.user["id"],))
            row = c.fetchone()
            current_cash = float(row[0]) if row and row[0] is not None else 0.0
            if cost_basis > current_cash and auto_top_up:
                current_cash = cost_basis  # Auto top-up
            new_cash = current_cash - cost_basis
            c.execute('UPDATE WebUsers SET cash_balance = ? WHERE id = ?', (new_cash, g.user["id"]))
            
        c.execute('''
            INSERT INTO PortfolioPositions (user_id, symbol, name, category, quantity, avg_entry_price, purchase_date, dividend_yield, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (g.user["id"], database.encrypt(symbol), database.encrypt(name), category, database.encrypt(str(quantity)), database.encrypt(str(avg_entry_price)), database.encrypt(purchase_date), database.encrypt(str(dividend_yield)), int(time.time())))
        
        c.execute('UPDATE WebUsers SET last_portfolio_update = ? WHERE id = ?', (int(time.time()), g.user["id"]))
        conn.commit()

    return jsonify({"message": "Position added successfully."}), 200

@portfolio_bp.route('/api/portfolio/position/<int:position_id>', methods=['PUT'])
@require_auth
@require_premium
def edit_position(position_id):
    data = request.json or {}
    quantity = float(data.get("quantity", 0))
    avg_entry_price = float(data.get("avg_entry_price", 0))
    purchase_date = data.get("purchase_date", "").strip()
    dividend_yield = float(data.get("dividend_yield") or 0.0) / 100.0

    category = data.get("category", "").strip()
    symbol = data.get("symbol", "").strip()

    if quantity <= 0 or avg_entry_price <= 0 or not purchase_date:
        return jsonify({"error": "Invalid input values."}), 400

    # Retrieve name for symbol update if needed
    name = symbol
    if symbol:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={symbol}&quotesCount=1&newsCount=0"
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200 and res.json().get('quotes'):
                name = res.json()['quotes'][0].get('longname') or res.json()['quotes'][0].get('shortname') or symbol
        except Exception:
            pass

    with db_session() as conn:
        c = conn.cursor()
        if category and symbol:
            c.execute('''
                UPDATE PortfolioPositions
                SET quantity = ?, avg_entry_price = ?, purchase_date = ?, dividend_yield = ?, category = ?, symbol = ?, name = ?
                WHERE id = ? AND user_id = ?
            ''', (database.encrypt(str(quantity)), database.encrypt(str(avg_entry_price)), database.encrypt(purchase_date), database.encrypt(str(dividend_yield)), category, database.encrypt(symbol), database.encrypt(name), position_id, g.user["id"]))
        else:
            c.execute('''
                UPDATE PortfolioPositions
                SET quantity = ?, avg_entry_price = ?, purchase_date = ?, dividend_yield = ?
                WHERE id = ? AND user_id = ?
            ''', (database.encrypt(str(quantity)), database.encrypt(str(avg_entry_price)), database.encrypt(purchase_date), database.encrypt(str(dividend_yield)), position_id, g.user["id"]))
        
        c.execute('UPDATE WebUsers SET last_portfolio_update = ? WHERE id = ?', (int(time.time()), g.user["id"]))
        conn.commit()
        success = c.rowcount > 0

    if success:
        return jsonify({"message": "Position updated successfully."}), 200
    else:
        return jsonify({"error": "Position not found."}), 404

@portfolio_bp.route('/api/portfolio/position/<int:position_id>', methods=['DELETE'])
@require_auth
@require_premium
def delete_position(position_id):
    add_to_cash = request.args.get('add_to_cash', 'false').lower() == 'true'
    proceeds = float(request.args.get('proceeds', 0.0))

    with db_session() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM PortfolioPositions WHERE id = ? AND user_id = ?', (position_id, g.user["id"]))
        success = c.rowcount > 0
        if success:
            if add_to_cash and proceeds > 0.0:
                c.execute('UPDATE WebUsers SET cash_balance = COALESCE(cash_balance, 0.0) + ? WHERE id = ?', (proceeds, g.user["id"]))
            c.execute('UPDATE WebUsers SET last_portfolio_update = ? WHERE id = ?', (int(time.time()), g.user["id"]))
        conn.commit()

    if success:
        return jsonify({"message": "Position deleted successfully."}), 200
    else:
        return jsonify({"error": "Position not found."}), 404


# --- 📄 AI CSV & Image Importer Handlers ---

@portfolio_bp.route('/api/portfolio/parse-image', methods=['POST'])
@require_auth
@require_premium
def parse_image():
    data = request.json or {}
    image_base64 = data.get("image_base64")
    mime_type = data.get("mime_type", "image/jpeg")

    if not image_base64:
        return jsonify({"error": "No image data provided."}), 400

    system_instruction = (
        "You are an expert financial assistant. Analyze the uploaded screenshot of the user's portfolio holdings and extract the positions into a structured JSON list.\n"
        "Required fields for each position:\n"
        "- symbol: Uppercase ticker/token name (e.g. QQQ, AAPL, BTC, ETH)\n"
        "- category: Either 'stock' or 'crypto' (infer from the symbol or context)\n"
        "- quantity: Numerical quantity of shares or coins (float)\n"
        "- avg_entry_price: Numerical cost basis entry price (float)\n"
        "- purchase_date: Date formatted as YYYY-MM-DD. If missing/invalid, assume '2026-01-01'\n"
        "- dividend_yield: Percentage (e.g. 2.85 or 0.0285). Return it as a percentage number (e.g., 2.85 for 2.85%). Default to 0.0.\n"
        "\n"
        "Return ONLY a valid JSON list of objects matching this schema. Do not wrap in markdown ```json or include text."
    )

    try:
        raw_json_str = call_gemini("Extract portfolio positions from this image.", system_instruction=system_instruction, json_mode=True, image_base64=image_base64, mime_type=mime_type)
        clean_json_str = raw_json_str.strip().replace("```json", "").replace("```", "")
        parsed_positions = json.loads(clean_json_str)
        return jsonify({"positions": parsed_positions}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to parse image: {str(e)}"}), 500

@portfolio_bp.route('/api/portfolio/parse-csv', methods=['POST'])
@require_auth
@require_premium
def parse_csv():
    data = request.json or {}
    csv_content = data.get("csv_content", "").strip()
    if not csv_content:
        return jsonify({"error": "No CSV content provided."}), 400

    system_instruction = (
        "You are an expert financial assistant. Parse the uploaded CSV text and map the columns to standard portfolio positions.\n"
        "Required fields:\n"
        "- symbol: Uppercase ticker/token name (e.g. QQQ, AAPL, BTC, ETH)\n"
        "- category: Either 'stock' or 'crypto'\n"
        "- quantity: Numerical quantity of shares or coins (float)\n"
        "- avg_entry_price: Numerical cost basis entry price (float)\n"
        "- purchase_date: Date formatted as YYYY-MM-DD. If missing/invalid, assume '2026-01-01'\n"
        "- dividend_yield: Percentage (e.g. 2.85 or 0.0285). Return it as a percentage number (e.g., 2.85 for 2.85%). Default to 0.0.\n"
        "\n"
        "Return ONLY a valid JSON list of objects matching this schema. Do not wrap in markdown ```json or include text."
    )

    try:
        raw_json_str = call_gemini(csv_content, system_instruction=system_instruction, json_mode=True)
        clean_json_str = raw_json_str.strip().replace("```json", "").replace("```", "")
        parsed_positions = json.loads(clean_json_str)
        return jsonify({"positions": parsed_positions}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to parse CSV: {str(e)}"}), 500

@portfolio_bp.route('/api/portfolio/import', methods=['POST'])
@require_auth
@require_premium
def import_positions():
    data = request.json or {}
    positions = data.get("positions", [])
    if not positions:
        return jsonify({"error": "No positions to import."}), 400

    user_id = g.user["id"]
    created_time = int(time.time())

    with db_session() as conn:
        c = conn.cursor()
        for p in positions:
            symbol = p.get("symbol", "").strip().upper()
            category = p.get("category", "stock").strip().lower()
            quantity = float(p.get("quantity", 0))
            avg_entry = float(p.get("avg_entry_price", 0))
            p_date = p.get("purchase_date", "2026-01-01")
            div_yield = float(p.get("dividend_yield") or 0.0) / 100.0

            if not symbol or quantity <= 0 or avg_entry <= 0:
                continue

            c.execute('''
                INSERT INTO PortfolioPositions (user_id, symbol, name, category, quantity, avg_entry_price, purchase_date, dividend_yield, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, database.encrypt(symbol), database.encrypt(symbol), category, database.encrypt(str(quantity)), database.encrypt(str(avg_entry)), database.encrypt(p_date), database.encrypt(str(div_yield)), created_time))
        
        c.execute('UPDATE WebUsers SET last_portfolio_update = ? WHERE id = ?', (created_time, user_id))
        conn.commit()

    return jsonify({"message": "Positions imported successfully."}), 200


# --- 🤖 AI Analysis Score Handlers ---

@portfolio_bp.route('/api/portfolio/analyze', methods=['POST'])
@require_auth
@require_premium
def analyze_portfolio():
    user_id = g.user["id"]
    
    # 24-hour Rate Limit Check
    now = int(time.time())
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT timestamp, score, action_plan, completed_actions FROM PortfolioAnalysisHistory WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (user_id,))
        last_analysis = c.fetchone()
        
    if not is_user_admin(g.user) and last_analysis and (now - last_analysis[0] < 86400):
        last_update = g.user.get('last_portfolio_update') or 0
        if last_update <= last_analysis[0]:
            return jsonify({"error": "You can only run a new analysis once every 24 hours unless you update your holdings."}), 429
            
    data = request.get_json(silent=True) or {}
    risk_profile = data.get("risk_profile") or g.user.get("risk_profile") or "Moderate"
    investment_goal = data.get("investment_goal") or g.user.get("investment_goal") or "Growth"
    
    p_response, code = get_portfolio()
    if code != 200:
        return jsonify({"error": "Failed to compile portfolio data for analysis."}), 500

    p_data = p_response.get_json()
    positions = p_data.get("positions", [])
    stats = p_data.get("stats", {})

    if not positions:
        return jsonify({"error": "Cannot analyze an empty portfolio."}), 400

    # Fetch analyst target prices and recommendations concurrently for stock positions
    def fetch_info(p):
        if p.get('category') == 'stock':
            try:
                info = yf.Ticker(p['symbol']).info
                return {
                    'target_price': info.get('targetMeanPrice'),
                    'recommendation': info.get('recommendationKey')
                }
            except Exception:
                return {}
        return {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_info, positions))
        
    for p, res in zip(positions, results):
        p['target_price'] = res.get('target_price')
        p['analyst_recommendation'] = res.get('recommendation')

    compiled_positions_str = json.dumps([{
        "symbol": p["symbol"],
        "category": p["category"],
        "quantity": p["quantity"],
        "avg_entry_price": p["avg_entry_price"],
        "current_price": p["current_price"],
        "target_price": p.get("target_price"),
        "analyst_recommendation": p.get("analyst_recommendation"),
        "market_value": p["market_value"],
        "overall_pnl_pct": p["overall_pnl_pct"],
        "allocation_pct": p["allocation_pct"],
        "purchase_date": p["purchase_date"]
    } for p in positions])

    system_instruction = (
        f"You are an expert investment advisor tailoring advice for a client with a **{risk_profile}** risk profile and an investment goal of **{investment_goal}**.\n"
        "Analyze the user's holdings and provide a detailed portfolio health report. Pay close attention to target prices.\n"
        "CRITICAL RULE: Do NOT recommend selling a stock or crypto asset if its current price is still 5-10% (or more) below its target price, as it still has room for growth.\n"
    )

    if last_analysis and len(last_analysis) >= 4 and last_analysis[1] is not None:
        last_score = last_analysis[1]
        last_plan_str = last_analysis[2]
        
        checked_items_str = "None"
        if last_analysis[3]:
            try:
                last_plan = json.loads(last_plan_str)
                completed_bools = json.loads(last_analysis[3])
                checked_items = [item for i, item in enumerate(last_plan) if i < len(completed_bools) and completed_bools[i]]
                if checked_items:
                    checked_items_str = json.dumps(checked_items)
            except Exception:
                pass

        system_instruction += (
            f"\nPREVIOUS CONTEXT:\nYou previously analyzed this portfolio and gave it a score of {last_score}/100. "
            f"Your previous action plan was: {last_plan_str}\n"
            f"The user has explicitly completed the following items from that plan: {checked_items_str}\n"
            "Evaluate if the user has implemented these recommendations. If they have followed your advice, "
            "you MUST reward them by increasing their score above their previous score. It is very frustrating for a user to follow advice and see their score drop.\n"
        )

    system_instruction += (
        "\nReturn a JSON object containing the following keys:\n"
        "- score: An integer score (1-100) representing how well the portfolio aligns with their specific risk profile and goals.\n"
        "- action_plan: A JSON list of 3-5 clean recommendation strings (e.g. ['Diversify out of high-growth tech stocks', 'Trim CRWD due to high volatility']).\n"
        "- detailed_recommendations: A detailed markdown summary of your findings (under 300 words, no HTML).\n"
        "- show_me_how: Step-by-step instructions in markdown showing exactly how the user can execute the action plan (e.g., sell orders, re-allocating to crypto/stocks).\n"
        "Ensure the response is valid JSON and nothing else."
    )

    # Load active Good Buys and inject them into the system instruction
    cache_key = f"good_buys_{risk_profile}_{investment_goal}"
    cached_data_str = get_config(cache_key)
    good_buys_dict = None
    buys_md = ""
    if cached_data_str:
        try:
            cached_data = json.loads(cached_data_str)
            cached_timestamp = cached_data.get("timestamp", 0)
            if time.time() - cached_timestamp < 86400:
                recommendations = cached_data.get("recommendations", {})
                good_buys_dict = recommendations
                stock_recs = recommendations.get("stocks", [])
                crypto_recs = recommendations.get("crypto", [])
                
                if stock_recs or crypto_recs:
                    buys_md = "\n\n### 💡 Fresh Investment Ideas\n\n"
                    prompt_buys_ctx = "\n\nRECOMMENDED BUYS (Consider recommending selling poor performing assets or assets that reached their targets, and re-allocating funds into these recommended assets):\n"
                    if stock_recs:
                        buys_md += "#### 📈 Top Stock Ideas\n\n"
                        prompt_buys_ctx += "- STOCKS:\n"
                        for rec in stock_recs:
                            active_badge = " ⚡ (Active Signal)" if rec.get('is_active_signal') else ""
                            conviction_badge = " 🟢 HIGH" if rec.get('conviction') == 'high' else " 🟡 MEDIUM"
                            buys_md += f"* **{rec.get('symbol')} ({rec.get('name')})**{active_badge}{conviction_badge}\n"
                            buys_md += f"  * {rec.get('metrics_summary', '')}\n"
                            if rec.get('target_price'):
                                buys_md += f"  * Target: {rec.get('target_price')} (+{rec.get('expected_growth_pct')}%) | Timeframe: {rec.get('estimated_timeframe')}\n"
                            buys_md += f"  * {rec.get('rationale', '')}\n"
                            prompt_buys_ctx += f"  * {rec.get('symbol')}: {rec.get('rationale', '')}\n"

                    if crypto_recs:
                        buys_md += "\n#### 🪙 Top Crypto Ideas\n\n"
                        prompt_buys_ctx += "- CRYPTO:\n"
                        for rec in crypto_recs:
                            active_badge = " ⚡ (Active Signal)" if rec.get('is_active_signal') else ""
                            conviction_badge = " 🟢 HIGH" if rec.get('conviction') == 'high' else " 🟡 MEDIUM"
                            buys_md += f"* **{rec.get('symbol')} ({rec.get('name')})**{active_badge}{conviction_badge}\n"
                            buys_md += f"  * {rec.get('metrics_summary', '')}\n"
                            if rec.get('target_price'):
                                buys_md += f"  * Target: {rec.get('target_price')} (+{rec.get('expected_growth_pct')}%) | Timeframe: {rec.get('estimated_timeframe')}\n"
                            buys_md += f"  * {rec.get('rationale', '')}\n"
                            prompt_buys_ctx += f"  * {rec.get('symbol')}: {rec.get('rationale', '')}\n"
                    
                    system_instruction += prompt_buys_ctx
        except Exception:
            pass

    prompt = f"Analyze this portfolio: {compiled_positions_str}. General stats: Market Value: ${stats['market_value']:.2f}, Cost Basis: ${stats['cost_basis']:.2f}, Dividends: ${stats['annual_dividends']:.2f}."

    try:
        raw_json_str = call_gemini(prompt, system_instruction=system_instruction, json_mode=True)
        clean_json_str = raw_json_str.strip().replace("```json", "").replace("```", "")
        analysis = json.loads(clean_json_str)

        score = int(analysis.get("score", 75))
        action_plan = analysis.get("action_plan", [])
        detailed_recs = analysis.get("detailed_recommendations", "")
        show_me_how = analysis.get("show_me_how", "")
        
        if buys_md:
            show_me_how += buys_md

        analysis_data = {
            "detailed_recommendations": detailed_recs,
            "show_me_how": show_me_how
        }
        if good_buys_dict:
            analysis_data["good_buys"] = good_buys_dict

        with db_session() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO PortfolioAnalysisHistory (user_id, score, analysis_text, action_plan, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, score, json.dumps(analysis_data), json.dumps(action_plan), int(time.time())))
            conn.commit()

        return jsonify({
            "score": score,
            "action_plan": action_plan,
            "detailed_recommendations": detailed_recs,
            "show_me_how": show_me_how
        }), 200
    except Exception as e:
        return jsonify({"error": f"AI Analysis failed: {str(e)}"}), 500

@portfolio_bp.route('/api/portfolio/analysis/history', methods=['GET'])
@require_auth
@require_premium
def get_analysis_history():
    user_id = g.user["id"]
    history = []

    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, score, analysis_text, action_plan, timestamp, completed_actions
            FROM PortfolioAnalysisHistory
            WHERE user_id = ?
            ORDER BY timestamp DESC
        ''', (user_id,))
        rows = c.fetchall()
        for r in rows:
            text_data = json.loads(r[2])
            completed_actions = []
            if r[5]:
                try:
                    completed_actions = json.loads(r[5])
                except Exception:
                    pass
            
            history.append({
                "id": r[0],
                "score": r[1],
                "detailed_recommendations": text_data.get("detailed_recommendations", ""),
                "show_me_how": text_data.get("show_me_how", ""),
                "good_buys": text_data.get("good_buys", None),
                "action_plan": json.loads(r[3]),
                "timestamp": r[4],
                "completed_actions": completed_actions
            })

    return jsonify({"history": history}), 200

@portfolio_bp.route('/api/portfolio/analysis/<int:analysis_id>/check', methods=['POST'])
@require_auth
@require_premium
def check_action_plan_item(analysis_id):
    user_id = g.user["id"]
    data = request.json or {}
    completed_actions = data.get("completed_actions", [])

    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE PortfolioAnalysisHistory
            SET completed_actions = ?
            WHERE id = ? AND user_id = ?
        ''', (json.dumps(completed_actions), analysis_id, user_id))
        conn.commit()

    return jsonify({"success": True}), 200


@portfolio_bp.route('/api/portfolio/good-buys', methods=['POST'])
@require_auth
@require_premium
def good_buys():
    user_id = g.user["id"]
    data = request.json or {}
    risk_profile = data.get("risk_profile") or g.user.get("risk_profile") or "Moderate"
    investment_goal = data.get("investment_goal") or g.user.get("investment_goal") or "Growth"
    force_regenerate = data.get("force_regenerate", False)

    cache_key = f"good_buys_{risk_profile}_{investment_goal}"
    
    cached_data_str = get_config(cache_key)
    cached_timestamp = 0
    cached_recommendations = None
    if cached_data_str:
        try:
            cached_data = json.loads(cached_data_str)
            cached_timestamp = cached_data.get("timestamp", 0)
            cached_recommendations = cached_data.get("recommendations")
        except Exception:
            pass

    # If force_regenerate is requested but it was already generated in the last 24 hours
    if force_regenerate and not is_user_admin(g.user):
        if time.time() - cached_timestamp < 86400:
            return jsonify({"error": f"This list was recently generated in the last 24 hours for {risk_profile} & {investment_goal}."}), 429

    # 1. First Pass: Check Cache (No Lock)
    if not force_regenerate and cached_recommendations:
        if time.time() - cached_timestamp < 86400:
            return jsonify(cached_recommendations), 200

    # 2. Acquire Lock for this specific combination
    lock = _GOOD_BUYS_LOCKS[cache_key]
    acquired = lock.acquire(blocking=False)
    if not acquired:
        return jsonify({"error": f"An analysis is currently in progress for {risk_profile} & {investment_goal}. Please wait a moment."}), 429

    try:
        # 3. Double-Check Cache
        if not force_regenerate:
            cached_data_str = get_config(cache_key)
            if cached_data_str:
                try:
                    cached_data = json.loads(cached_data_str)
                    timestamp = cached_data.get("timestamp", 0)
                    if time.time() - timestamp < 86400:
                        return jsonify(cached_data["recommendations"]), 200
                except Exception:
                    pass

        # 4. Generate New Recommendations
        # Fetch latest analysis to append if applicable
        with db_session() as conn:
            c = conn.cursor()
            c.execute('SELECT id, analysis_text, timestamp FROM PortfolioAnalysisHistory WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (user_id,))
            last_analysis = c.fetchone()

        analysis_id = None
        analysis_data = {}
        if last_analysis:
            analysis_id = last_analysis[0]
            try:
                analysis_data = json.loads(last_analysis[1])
            except Exception:
                pass

        if "good_buys" in analysis_data and not is_user_admin(g.user) and not force_regenerate:
             # This prevents abuse of forcing generation by just clicking the button.
             # Wait, if force_regenerate is True, they can bypass.
             # But let's restrict force_regenerate to admins or something?
             # The user asked to show "Recommended Buys" even without an analysis.
             pass 

        # Build the market research brief from cached data
        research_brief = _build_market_research_brief(user_id, risk_profile, investment_goal)

        # Construct the AI Prompt
        system_instruction = (
            "You are a senior portfolio analyst AI for Metaverse Sherpa. "
            "You are selecting the best buy-and-hold investment ideas for a user.\\n\\n"
            f"User's risk profile: '{risk_profile}'\\n"
            f"User's investment goal: '{investment_goal}'\\n\\n"
            "IMPORTANT RULES:\\n"
            "1. Base your analysis ONLY on the market data provided below.\\n"
            "2. Do NOT fabricate earnings data, revenue figures, P/E ratios, or any information not present in the research brief.\\n"
            "3. Your rationale must reference the actual numbers from the data (e.g., '30d momentum of +12.3%').\\n"
            "4. Assets marked with ⚡ ACTIVE SIGNAL have been identified by our trading algorithm. Stock signals are high-conviction momentum plays. Crypto signals are short-term scalps (weigh less for buy-and-hold).\\n"
            "5. Prefer assets with: strong 30d momentum, reasonable distance from 52-week highs (room to run), high liquidity.\\n"
            "6. Diversify across sectors/categories. Do not recommend 5 tech stocks.\\n"
            "7. Generate realistic technical target prices (`target_price`) and stop loss prices (`stop_loss`) based on 52-week highs, momentum, and technical supports/resistances. Calculate the `expected_growth_pct` (number) mathematically from the current price, and provide an `estimated_timeframe` (e.g., '3-6 Months').\\n"
        )
        if risk_profile.lower() == "aggressive" and investment_goal.lower() == "speculation":
            system_instruction += (
                "8. **AGGRESSIVE/SPECULATION OVERRIDE**: The user wants high risk, high reward. Select highly volatile, high-volume assets. Target substantial gains (e.g., 20-50%+) and project shorter timeframes (e.g., '1-3 Months'). Focus heavily on short-term momentum and liquidity turnover rather than market cap.\\n"
            )
        system_instruction += (
            "\\nReturn a JSON object with exactly this structure (no markdown, no extra text):\\n"
            "{\\n"
            '  "stocks": [\\n'
            "    {\\n"
            '      "symbol": "AAPL",\\n'
            '      "name": "Apple Inc.",\\n'
            '      "type": "stock",\\n'
            '      "rationale": "1-2 sentence rationale referencing actual data numbers.",\\n'
            '      "is_active_signal": true,\\n'
            '      "conviction": "high",\\n'
            '      "metrics_summary": "Price: $198 | 30d: +5.2% | 8% below 52w high",\\n'
            '      "target_price": "$220.00",\\n'
            '      "stop_loss": "$180.00",\\n'
            '      "expected_growth_pct": 11.1,\\n'
            '      "estimated_timeframe": "3-6 Months"\\n'
            "    }\\n"
            "  ],\\n"
            '  "crypto": [\\n'
            "    {\\n"
            '      "symbol": "SOL",\\n'
            '      "name": "Solana",\\n'
            '      "type": "crypto",\\n'
            '      "rationale": "1-2 sentence rationale referencing actual data numbers.",\\n'
            '      "is_active_signal": false,\\n'
            '      "conviction": "medium",\\n'
            '      "metrics_summary": "Price: $142 | 30d: +18.4% | 22% below 52w high",\\n'
            '      "target_price": "$175.00",\\n'
            '      "stop_loss": "$120.00",\\n'
            '      "expected_growth_pct": 23.2,\\n'
            '      "estimated_timeframe": "2-4 Months"\\n'
            "    }\\n"
            "  ]\\n"
            "}\\n\\n"
            "Select exactly 5 stocks and exactly 5 crypto assets. "
            "Set conviction to 'high' if the asset has an active signal AND strong momentum, otherwise 'medium'.\\n\\n"
            "--- MARKET DATA RESEARCH BRIEF ---\\n\\n"
            f"{research_brief}"
        )

        try:
            raw_json_str = call_gemini(
                "Analyze the market data and select the top 5 stocks and top 5 crypto for buy-and-hold investment.",
                system_instruction=system_instruction,
                json_mode=True
            )
            clean_json_str = raw_json_str.strip().replace("```json", "").replace("```", "")
            recommendations = json.loads(clean_json_str)

            # Store in cache
            cache_payload = {
                "timestamp": time.time(),
                "recommendations": recommendations
            }
            update_config(cache_key, json.dumps(cache_payload))

            # Ensure we have both keys
            stock_recs = recommendations.get("stocks", [])
            crypto_recs = recommendations.get("crypto", [])

            # Record recommendations to AIRecommendations table
            with db_session() as conn:
                c = conn.cursor()
                now_ts = int(time.time())
                
                with _MARKET_DATA_LOCK:
                    stock_cache = dict(_MARKET_DATA_CACHE.get("stocks", {}))
                    crypto_cache = dict(_MARKET_DATA_CACHE.get("crypto", {}))
                
                speculative_cache = _get_speculative_market_data() or {}

                for rec in stock_recs + crypto_recs:
                    sym = rec.get("symbol", "").upper()
                    cat = rec.get("type", "stock").lower()
                    
                    t_price_str = str(rec.get("target_price", "0")).replace("$", "").replace(",", "").strip()
                    try:
                        target_price = float(t_price_str)
                    except ValueError:
                        target_price = 0.0
                        
                    sl_price_str = str(rec.get("stop_loss", "0")).replace("$", "").replace(",", "").strip()
                    try:
                        stop_loss = float(sl_price_str)
                    except ValueError:
                        stop_loss = 0.0

                    entry_price = 0.0
                    if cat == "stock":
                        if sym in speculative_cache:
                            entry_price = speculative_cache[sym].get("price", 0.0)
                        elif sym in stock_cache:
                            entry_price = stock_cache[sym].get("price", 0.0)
                    else:
                        if sym in crypto_cache:
                            entry_price = crypto_cache[sym].get("price", 0.0)

                    if entry_price <= 0.0:
                        try:
                            yf_sym = sym if cat == "stock" else f"{sym}-USD"
                            ticker = yf.Ticker(yf_sym)
                            entry_price = float(ticker.fast_info.get("lastPrice", 0.0))
                        except Exception:
                            import re
                            price_match = re.search(r"Price:\s*\$?([\d\.]+)", rec.get("metrics_summary", ""))
                            if price_match:
                                try:
                                    entry_price = float(price_match.group(1))
                                except ValueError:
                                    pass

                    if entry_price <= 0.0:
                        continue

                    if stop_loss <= 0.0:
                        stop_loss = round(entry_price * 0.85, 2)

                    # Check if there is an active recommendation for this combination already
                    c.execute('''
                        SELECT id FROM AIRecommendations 
                        WHERE symbol = ? AND risk_profile = ? AND investment_goal = ? AND status = 'active'
                    ''', (sym, risk_profile, investment_goal))
                    existing = c.fetchone()
                    
                    if not existing:
                        c.execute('''
                            INSERT INTO AIRecommendations 
                            (symbol, category, risk_profile, investment_goal, entry_price, current_price, target_price, stop_loss, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                        ''', (sym, cat, risk_profile, investment_goal, entry_price, entry_price, target_price, stop_loss, now_ts))
                conn.commit()

            # Build markdown for the Detailed Implementation Plan
            buys_md = "\n\n### 💡 Fresh Investment Ideas\n\n"
            buys_md += "#### 📈 Top Stock Ideas\n\n"
            for rec in stock_recs:
                active_badge = " ⚡ (Active Signal)" if rec.get('is_active_signal') else ""
                conviction_badge = " 🟢 HIGH" if rec.get('conviction') == 'high' else " 🟡 MEDIUM"
                buys_md += f"* **{rec.get('symbol')} ({rec.get('name')})**{active_badge}{conviction_badge}\n"
                buys_md += f"  * {rec.get('metrics_summary', '')}\n"
                if rec.get('target_price'):
                    sl_str = f" | Stop Loss: {rec.get('stop_loss')}" if rec.get('stop_loss') else ""
                    buys_md += f"  * Target: {rec.get('target_price')}{sl_str} (+{rec.get('expected_growth_pct')}%) | Timeframe: {rec.get('estimated_timeframe')}\n"
                buys_md += f"  * {rec.get('rationale', '')}\n"

            buys_md += "\n#### 🪙 Top Crypto Ideas\n\n"
            for rec in crypto_recs:
                active_badge = " ⚡ (Active Signal)" if rec.get('is_active_signal') else ""
                conviction_badge = " 🟢 HIGH" if rec.get('conviction') == 'high' else " 🟡 MEDIUM"
                buys_md += f"* **{rec.get('symbol')} ({rec.get('name')})**{active_badge}{conviction_badge}\n"
                buys_md += f"  * {rec.get('metrics_summary', '')}\n"
                if rec.get('target_price'):
                    sl_str = f" | Stop Loss: {rec.get('stop_loss')}" if rec.get('stop_loss') else ""
                    buys_md += f"  * Target: {rec.get('target_price')}{sl_str} (+{rec.get('expected_growth_pct')}%) | Timeframe: {rec.get('estimated_timeframe')}\n"
                buys_md += f"  * {rec.get('rationale', '')}\n"

            # Append to the Detailed Implementation Plan
            if analysis_id:
                analysis_data["show_me_how"] = analysis_data.get("show_me_how", "") + buys_md
                analysis_data["good_buys"] = recommendations
                with db_session() as conn:
                    c = conn.cursor()
                    c.execute('''
                        UPDATE PortfolioAnalysisHistory 
                        SET analysis_text = ? 
                        WHERE id = ?
                    ''', (json.dumps(analysis_data), analysis_id))
                    conn.commit()

            return jsonify(recommendations), 200
        except Exception as e:
            return jsonify({"error": f"Failed to generate recommendations: {str(e)}"}), 500
    finally:
        lock.release()


# --- 📰 Yahoo Finance News Sentiment ---

@portfolio_bp.route('/api/portfolio/news', methods=['GET'])
@require_auth
@require_premium
def get_portfolio_news():
    user_id = g.user["id"]
    now = time.time()
    
    if user_id in _NEWS_CACHE:
        cached_news, ts = _NEWS_CACHE[user_id]
        if now - ts < _NEWS_CACHE_DURATION:
            return jsonify(cached_news), 200

    positions = []

    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT symbol, category FROM PortfolioPositions WHERE user_id = ? LIMIT 5', (user_id,))
        rows = c.fetchall()
        positions = [{"symbol": database.decrypt(r[0]), "category": r[1]} for r in rows]

    if not positions:
        positions = [{"symbol": "BTC", "category": "crypto"}, {"symbol": "AAPL", "category": "stock"}]

    news_items = []
    
    def fetch_news_for_position(p):
        sym = p["symbol"]
        cat = p["category"]
        yf_symbol = f"{sym}-USD" if cat.lower() == 'crypto' else sym
        
        items = []
        try:
            ticker = yf.Ticker(yf_symbol)
            ticker_news = ticker.news
            count = 0
            for item in ticker_news:
                if count >= 2:
                    break
                content = item.get("content", {})
                title = content.get("title")
                summary = content.get("summary") or content.get("description") or ""
                link = content.get("clickThroughUrl", {}).get("url") or item.get("link")
                pub_date = content.get("pubDate") or item.get("providerPublishTime")
                provider = content.get("provider", {}).get("displayName", "Yahoo Finance")
                
                if title and link:
                    items.append({
                        "symbol": sym,
                        "title": title,
                        "summary": summary[:200] + "..." if len(summary) > 200 else summary,
                        "pubDate": pub_date,
                        "provider": provider,
                        "link": link
                    })
                    count += 1
        except Exception:
            pass
        return items

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(fetch_news_for_position, positions)
        for items in results:
            news_items.extend(items)

    news_items = news_items[:6]
    
    bullish_keywords = ['soar', 'surge', 'jump', 'gain', 'buy', 'up', 'high', 'growth', 'positive', 'bull', 'rally', 'beat', 'outperform', 'strong']
    bearish_keywords = ['plunge', 'drop', 'fall', 'lose', 'sell', 'down', 'low', 'decline', 'negative', 'bear', 'crash', 'miss', 'underperform', 'weak']

    bullish_count = 0
    bearish_count = 0
    neutral_count = 0

    for n in news_items:
        text = (n['title'] + " " + n['summary']).lower()
        bull_score = sum(1 for word in bullish_keywords if word in text)
        bear_score = sum(1 for word in bearish_keywords if word in text)
        
        if bull_score > bear_score:
            sentiment = "Bullish"
            bullish_count += 1
        elif bear_score > bull_score:
            sentiment = "Bearish"
            bearish_count += 1
        else:
            sentiment = "Neutral"
            neutral_count += 1
            
        n["sentiment"] = sentiment

    counts = {
        "bullish": bullish_count,
        "bearish": bearish_count,
        "neutral": neutral_count
    }

    return jsonify({
        "news": news_items,
        "counts": counts
    }), 200


@portfolio_bp.route('/api/portfolio/recommendations', methods=['GET'])
@require_auth
@require_premium
def get_tracked_recommendations():
    # 1. Fetch active recommendations from AIRecommendations
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM AIRecommendations WHERE status = 'active'")
        active_recs = [dict(row) for row in c.fetchall()]

    # 2. Update active prices on-demand
    if active_recs:
        updated_recs = []
        now_ts = int(time.time())
        symbols_to_fetch = []
        for rec in active_recs:
            sym = rec["symbol"]
            cat = rec["category"]
            yf_sym = sym if cat == "stock" else f"{sym}-USD"
            symbols_to_fetch.append((rec["id"], sym, cat, yf_sym, rec["target_price"], rec["stop_loss"]))

        if symbols_to_fetch:
            yf_symbols = [item[3] for item in symbols_to_fetch]
            try:
                data = yf.download(yf_symbols, period="1d", group_by="ticker", progress=False)
                
                with db_session() as conn:
                    c = conn.cursor()
                    for rec_id, sym, cat, yf_sym, target, sl in symbols_to_fetch:
                        price = 0.0
                        try:
                            if len(yf_symbols) == 1:
                                df = data
                            else:
                                df = data[yf_sym]
                            
                            closes = df["Close"].dropna()
                            if not closes.empty:
                                price = float(closes.iloc[-1])
                        except Exception:
                            try:
                                ticker = yf.Ticker(yf_sym)
                                price = float(ticker.fast_info.get("lastPrice", 0.0))
                            except Exception:
                                pass
                        
                        if price > 0.0:
                            status = 'active'
                            closed_at = None
                            if price >= target:
                                status = 'hit_target'
                                closed_at = now_ts
                            elif price <= sl:
                                status = 'hit_stop_loss'
                                closed_at = now_ts
                                
                            c.execute('''
                                UPDATE AIRecommendations 
                                SET current_price = ?, status = ?, closed_at = ?
                                WHERE id = ?
                            ''', (price, status, closed_at, rec_id))
                    conn.commit()
            except Exception as e:
                print(f"[Recommendations] Error updating prices: {e}")

    # 3. Retrieve all recommendations
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM AIRecommendations ORDER BY created_at DESC")
        all_recs = [dict(row) for row in c.fetchall()]

    # 4. Calculate Stats
    stock_stats = {"total": 0, "hits": 0, "stops": 0, "win_rate": 0.0, "avg_days": 0.0}
    crypto_stats = {"total": 0, "hits": 0, "stops": 0, "win_rate": 0.0, "avg_days": 0.0}
    
    closed_stocks = [r for r in all_recs if r["category"] == "stock" and r["status"] != "active"]
    closed_cryptos = [r for r in all_recs if r["category"] == "crypto" and r["status"] != "active"]

    stock_stats["total"] = len([r for r in all_recs if r["category"] == "stock"])
    crypto_stats["total"] = len([r for r in all_recs if r["category"] == "crypto"])

    # Stock win rate
    closed_stock_count = len(closed_stocks)
    if closed_stock_count > 0:
        hits = len([r for r in closed_stocks if r["status"] == "hit_target"])
        stops = len([r for r in closed_stocks if r["status"] == "hit_stop_loss"])
        stock_stats["hits"] = hits
        stock_stats["stops"] = stops
        stock_stats["win_rate"] = round((hits / closed_stock_count) * 100, 1)
        
        total_dur = sum((r["closed_at"] - r["created_at"]) for r in closed_stocks)
        stock_stats["avg_days"] = round((total_dur / closed_stock_count) / 86400, 1)

    # Crypto win rate
    closed_crypto_count = len(closed_cryptos)
    if closed_crypto_count > 0:
        hits = len([r for r in closed_cryptos if r["status"] == "hit_target"])
        stops = len([r for r in closed_cryptos if r["status"] == "hit_stop_loss"])
        crypto_stats["hits"] = hits
        crypto_stats["stops"] = stops
        crypto_stats["win_rate"] = round((hits / closed_crypto_count) * 100, 1)
        
        total_dur = sum((r["closed_at"] - r["created_at"]) for r in closed_cryptos)
        crypto_stats["avg_days"] = round((total_dur / closed_crypto_count) / 86400, 1)

    return jsonify({
        "recommendations": all_recs,
        "stats": {
            "stock": stock_stats,
            "crypto": crypto_stats
        }
    }), 200

