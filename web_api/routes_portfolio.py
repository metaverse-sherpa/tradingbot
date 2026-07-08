import os
import json
import time
import requests
import concurrent.futures
import yfinance as yf
import ccxt
from flask import Blueprint, request, jsonify, g
from datetime import datetime

import database
from database import db_session
from web_api.auth import require_auth, require_premium
import utils_gcp

portfolio_bp = Blueprint('portfolio', __name__)

# --- 🚀 Price Caching system ---
_PRICE_CACHE = {}  # {symbol: (price, change_pct, timestamp)}
_CACHE_DURATION = 300  # 5 minutes in seconds

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
            "enableRateLimit": True
        })
        ccxt_symbols = [f"{sym}/USDT" for sym in symbols]
        tickers = exchange.fetch_tickers(ccxt_symbols)
        for sym in symbols:
            t = tickers.get(f"{sym}/USDT")
            if t:
                prices[sym] = (float(t.get('last') or t.get('close')), float(t.get('percentage') or 0.0))
    except Exception:
        # Fallback to fetching individually
        for sym in symbols:
            try:
                exchange = ccxt.binance()
                t = exchange.fetch_ticker(f"{sym}/USDT")
                prices[sym] = (float(t.get('last') or t.get('close')), float(t.get('percentage') or 0.0))
            except Exception:
                try:
                    exchange = ccxt.coinbase()
                    t = exchange.fetch_ticker(f"{sym}/USD")
                    prices[sym] = (float(t.get('last') or t.get('close')), float(t.get('percentage') or 0.0))
                except Exception:
                    prices[sym] = (None, 0.0)
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

    if to_fetch_stock:
        stock_prices = get_stock_prices(to_fetch_stock)
        for sym, val in stock_prices.items():
            cache_key = f"{sym}_stock"
            if val[0] is not None:
                _PRICE_CACHE[cache_key] = (val[0], val[1], now)
            result[cache_key] = val

    if to_fetch_crypto:
        crypto_prices = get_crypto_prices(to_fetch_crypto)
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
        res = requests.post(url_with_key, headers=headers, json=payload, timeout=30)
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
    
    with db_session() as conn:
        c = conn.cursor()
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
    allocation_list = []
    for p in positions:
        pct = (p["market_value"] / total_market_value * 100) if total_market_value > 0 else 0.0
        p["allocation_pct"] = pct
        allocation_list.append({
            "name": p["symbol"],
            "value": p["market_value"],
            "percentage": pct
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
        c.execute('''
            INSERT INTO PortfolioPositions (user_id, symbol, name, category, quantity, avg_entry_price, purchase_date, dividend_yield, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (g.user["id"], database.encrypt(symbol), database.encrypt(name), category, database.encrypt(str(quantity)), database.encrypt(str(avg_entry_price)), database.encrypt(purchase_date), database.encrypt(str(dividend_yield)), int(time.time())))
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
    with db_session() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM PortfolioPositions WHERE id = ? AND user_id = ?', (position_id, g.user["id"]))
        conn.commit()
        success = c.rowcount > 0

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
        conn.commit()

    return jsonify({"message": "Positions imported successfully."}), 200


# --- 🤖 AI Analysis Score Handlers ---

@portfolio_bp.route('/api/portfolio/analyze', methods=['POST'])
@require_auth
@require_premium
def analyze_portfolio():
    user_id = g.user["id"]
    
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
        "Return a JSON object containing the following keys:\n"
        "- score: An integer score (1-100) representing how well the portfolio aligns with their specific risk profile and goals.\n"
        "- action_plan: A JSON list of 3-5 clean recommendation strings (e.g. ['Diversify out of high-growth tech stocks', 'Trim CRWD due to high volatility']).\n"
        "- detailed_recommendations: A detailed markdown summary of your findings (under 300 words, no HTML).\n"
        "- show_me_how: Step-by-step instructions in markdown showing exactly how the user can execute the action plan (e.g., sell orders, re-allocating to crypto/stocks).\n"
        "Ensure the response is valid JSON and nothing else."
    )

    prompt = f"Analyze this portfolio: {compiled_positions_str}. General stats: Market Value: ${stats['market_value']:.2f}, Cost Basis: ${stats['cost_basis']:.2f}, Dividends: ${stats['annual_dividends']:.2f}."

    try:
        raw_json_str = call_gemini(prompt, system_instruction=system_instruction, json_mode=True)
        clean_json_str = raw_json_str.strip().replace("```json", "").replace("```", "")
        analysis = json.loads(clean_json_str)

        score = int(analysis.get("score", 75))
        action_plan = analysis.get("action_plan", [])
        detailed_recs = analysis.get("detailed_recommendations", "")
        show_me_how = analysis.get("show_me_how", "")

        with db_session() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO PortfolioAnalysisHistory (user_id, score, analysis_text, action_plan, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, score, json.dumps({
                "detailed_recommendations": detailed_recs,
                "show_me_how": show_me_how
            }), json.dumps(action_plan), int(time.time())))
            conn.commit()

        return jsonify({
            "score": score,
            "action_plan": action_plan,
            "detailed_recommendations": detailed_recs,
            "show_me_how": show_me_how
        }), 200
    except Exception as e:
        return jsonify({"error": f"AI Analysis failed: {str(e)}"}), 500

@portfolio_bp.route('/api/portfolio/analysis/latest', methods=['GET'])
@require_auth
@require_premium
def get_latest_analysis():
    user_id = g.user["id"]
    latest = None
    previous = None

    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT score, analysis_text, action_plan, timestamp
            FROM PortfolioAnalysisHistory
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT 2
        ''', (user_id,))
        rows = c.fetchall()
        if len(rows) >= 1:
            latest = rows[0]
        if len(rows) >= 2:
            previous = rows[1]

    if not latest:
        return jsonify({"analysis": None}), 200

    text_data = json.loads(latest[1])
    latest_obj = {
        "score": latest[0],
        "detailed_recommendations": text_data.get("detailed_recommendations", ""),
        "show_me_how": text_data.get("show_me_how", ""),
        "action_plan": json.loads(latest[2]),
        "timestamp": latest[3]
    }

    response_data = {
        "latest": latest_obj,
        "previous_score": previous[0] if previous else None
    }
    return jsonify(response_data), 200


# --- 📰 Yahoo Finance News Sentiment ---

@portfolio_bp.route('/api/portfolio/news', methods=['GET'])
@require_auth
@require_premium
def get_portfolio_news():
    user_id = g.user["id"]
    positions = []

    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT symbol, category FROM PortfolioPositions WHERE user_id = ? LIMIT 5', (user_id,))
        rows = c.fetchall()
        positions = [{"symbol": database.decrypt(r[0]), "category": r[1]} for r in rows]

    if not positions:
        positions = [{"symbol": "BTC", "category": "crypto"}, {"symbol": "AAPL", "category": "stock"}]

    news_items = []
    for p in positions:
        sym = p["symbol"]
        cat = p["category"]
        yf_symbol = f"{sym}-USD" if cat.lower() == 'crypto' else sym
        
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
                pub_date = content.get("pubDate")
                provider = content.get("provider", {}).get("displayName", "Yahoo Finance")
                link = content.get("clickThroughUrl", {}).get("url") or content.get("canonicalUrl", {}).get("url")
                
                if title:
                    news_items.append({
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

    if not news_items:
        return jsonify({"news": [], "counts": {"bullish": 0, "bearish": 0, "neutral": 0}}), 200

    news_items = news_items[:6]

    prompt_list = [f"{i+1}. Title: {n['title']} (Summary: {n['summary']})" for i, n in enumerate(news_items)]
    prompt_str = "\n".join(prompt_list)

    system_instruction = (
        "You are a financial sentiment analyst. Classify the sentiment of each provided news article headline/summary as exactly 'Bullish', 'Bearish', or 'Neutral'.\n"
        "Return ONLY a JSON array of strings containing these classifications, matching the order of the input articles. E.g. ['Bullish', 'Neutral', 'Bearish']."
    )

    try:
        raw_json = call_gemini(prompt_str, system_instruction=system_instruction, json_mode=True)
        clean_json = raw_json.strip().replace("```json", "").replace("```", "")
        sentiments = json.loads(clean_json)
    except Exception:
        sentiments = ["Neutral"] * len(news_items)

    bullish_count = 0
    bearish_count = 0
    neutral_count = 0

    for i, n in enumerate(news_items):
        sentiment = sentiments[i] if i < len(sentiments) else "Neutral"
        if sentiment not in ("Bullish", "Bearish", "Neutral"):
            sentiment = "Neutral"
            
        n["sentiment"] = sentiment
        
        if sentiment == "Bullish":
            bullish_count += 1
        elif sentiment == "Bearish":
            bearish_count += 1
        else:
            neutral_count += 1

    counts = {
        "bullish": bullish_count,
        "bearish": bearish_count,
        "neutral": neutral_count
    }

    return jsonify({
        "news": news_items,
        "counts": counts
    }), 200
