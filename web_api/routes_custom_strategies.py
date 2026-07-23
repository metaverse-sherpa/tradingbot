import uuid
import threading
import time
import json
from flask import Blueprint, request, jsonify, g
from web_api.auth import require_auth, require_premium
from database import db_session
import utils_gcp
from web_api.routes_portfolio import call_gemini

custom_strategies_bp = Blueprint('custom_strategies', __name__)

# --- Worker Thread Queue ---
def load_historical_data(asset_type="crypto", timeframe="1h", symbol=None):
    """Fetch real OHLCV market data for backtesting.
    Crypto uses Binance via CCXT.
    Stocks use Alpaca Data API.
    """
    import pandas as pd
    import logging
    logger = logging.getLogger(__name__)

    tf = timeframe or "1h"

    if asset_type == "crypto":
        target_symbol = symbol or "BTC/USDT"
        if "/" not in target_symbol:
            target_symbol = f"{target_symbol}/USDT" if not target_symbol.endswith("USDT") else f"{target_symbol[:-4]}/USDT"
        
        try:
            import ccxt
            import os
            
            cache_file = f"data/crypto_{target_symbol.replace('/', '_')}_{tf}_cache.csv"
            if os.path.exists(cache_file):
                df = pd.read_csv(cache_file, index_col="timestamp", parse_dates=True)
            else:
                ex = ccxt.binance({"enableRateLimit": True})
                limit = 1000
                since = ex.parse8601((pd.Timestamp.now() - pd.DateOffset(years=3)).strftime('%Y-%m-%dT%H:%M:%SZ'))
                all_ohlcv = []
                while True:
                    ohlcv = ex.fetch_ohlcv(target_symbol, timeframe=tf, since=since, limit=limit)
                    if not ohlcv:
                        break
                    all_ohlcv.extend(ohlcv)
                    since = ohlcv[-1][0] + 1
                    if len(ohlcv) < limit:
                        break
                    # Cap at roughly 3 years of hourly data (26280 bars + buffer)
                    if len(all_ohlcv) >= 27000:
                        break
                
                if all_ohlcv:
                    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                    df.set_index("timestamp", inplace=True)
                    df = df[~df.index.duplicated(keep='last')]
                    df.to_csv(cache_file)
                else:
                    return {}
                    
            symbol_key = target_symbol.split("/")[0]
            return {symbol_key: df[["open", "high", "low", "close", "volume"]]}
        except Exception as e:
            logger.warning(f"Failed to fetch Binance crypto data for {target_symbol}: {e}")

    else: # stock
        target_symbol = symbol or "AAPL"
        try:
            import requests, utils_gcp, os
            cache_file = f"data/stock_{target_symbol}_{tf}_cache.csv"
            if os.path.exists(cache_file):
                df = pd.read_csv(cache_file, index_col="timestamp", parse_dates=True)
                return {target_symbol: df}
                
            key = utils_gcp.get_secret("ALPACA_API_KEY") or ""
            secret = utils_gcp.get_secret("ALPACA_API_SECRET") or ""
            tf_map = {"15m": "15Min", "1h": "1Hour", "4h": "1Hour", "1d": "1Day"}
            alpaca_tf = tf_map.get(tf, "1Hour")
            headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
            
            from datetime import datetime, timedelta
            end_dt = datetime.utcnow()
            start_dt = end_dt - timedelta(days=3*365)
            
            page_token = None
            all_bars = []
            
            while True:
                url = f"https://data.alpaca.markets/v2/stocks/bars?symbols={target_symbol}&timeframe={alpaca_tf}&start={start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}&end={end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=10000&feed=iex"
                if page_token:
                    url += f"&page_token={page_token}"
                
                res = requests.get(url, headers=headers, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    bars = data.get("bars", {}).get(target_symbol, [])
                    if bars:
                        all_bars.extend(bars)
                    page_token = data.get("next_page_token")
                    if not page_token:
                        break
                else:
                    break
                    
            if all_bars:
                df = pd.DataFrame(all_bars).rename(columns={"o":"open", "h":"high", "l":"low", "c":"close", "v":"volume", "t":"timestamp"})
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.set_index("timestamp", inplace=True)
                df = df[~df.index.duplicated(keep='last')]
                df.to_csv(cache_file)
                return {target_symbol: df[["open", "high", "low", "close", "volume"]]}
        except Exception as e:
            logger.warning(f"Failed to fetch Alpaca stock data for {target_symbol}: {e}")

    # Synthetic fallback if API network calls fail
    logger.info("Using fallback synthetic data")
    import numpy as np
    dates = pd.date_range("2023-01-01", periods=1000, freq="1h")
    steps = np.random.normal(0, 0.5, size=1000)
    base_price = 100 + np.cumsum(steps)
    base_price = np.where(base_price < 10, 10, base_price)
    df = pd.DataFrame({
        "open": base_price + np.random.uniform(-0.2, 0.2, size=1000),
        "high": base_price + np.random.uniform(0.2, 0.5, size=1000),
        "low": base_price - np.random.uniform(0.2, 0.5, size=1000),
        "close": base_price + np.random.uniform(-0.2, 0.2, size=1000),
        "volume": np.random.uniform(1000, 5000, size=1000),
    }, index=dates)
    return {"BTC" if asset_type == "crypto" else "AAPL": df}

def async_backtest_runner(task_id, strategy_config, user_id):
    """Background worker that runs the combined portfolio backtester."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE BacktestTasks SET status = 'running' WHERE id = ?", (task_id,))
        
    try:
        asset_type = strategy_config.get("asset_type", "crypto")
        timeframe = strategy_config.get("timeframe", "1h")
        symbol = strategy_config.get("symbol")
        data_dict = load_historical_data(asset_type=asset_type, timeframe=timeframe, symbol=symbol)
        
        from custom_strategy_interpreter import CustomStrategyInterpreter, run_combined_backtest
        interpreter = CustomStrategyInterpreter(strategy_config)
        
        initial_cash = float(strategy_config.get("initial_cash", 10000.0))
        risk_pct = float(strategy_config.get("risk_pct", 0.02))
        default_leverage = 20.0 if asset_type == "crypto" else 1.6
        leverage = float(strategy_config.get("leverage", default_leverage))

        result = run_combined_backtest(
            data_dict,
            interpreter,
            risk_pct=risk_pct,
            initial_cash=initial_cash,
            leverage=leverage
        )
        
        with db_session() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE BacktestTasks SET status = 'completed', result = ?, completed_at = ? WHERE id = ?",
                (json.dumps(result), int(time.time()), task_id)
            )
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        with db_session() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE BacktestTasks SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
                (err_msg, int(time.time()), task_id)
            )

@custom_strategies_bp.route('/api/custom-strategies/backtest/trigger', methods=['POST'])
@require_auth
@require_premium
def trigger_backtest():
    """Queues a new backtesting job."""
    data = request.json or {}
    config = data.get("strategy_config")
    if not config:
        return jsonify({"error": "Config missing."}), 400
    
    # 1. Validate user has no other currently running tasks
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM BacktestTasks WHERE user_id = ? AND status = 'running'", (g.user["id"],))
        if c.fetchone():
            return jsonify({"error": "You already have a backtesting task in progress."}), 429
            
    task_id = str(uuid.uuid4())
    with db_session() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO BacktestTasks (id, user_id, strategy_config, created_at) VALUES (?, ?, ?, ?)",
            (task_id, g.user["id"], json.dumps(config), int(time.time()))
        )
        
    # Spawn background worker thread
    t = threading.Thread(target=async_backtest_runner, args=(task_id, config, g.user["id"]))
    t.start()
    
    return jsonify({"task_id": task_id, "status": "pending"}), 202

@custom_strategies_bp.route('/api/custom-strategies/chat', methods=['POST'])
@require_auth
@require_premium
def chat():
    # Support both JSON and multipart/form-data
    if request.is_json:
        data = request.json or {}
        prompt = data.get("prompt")
        history = data.get("history", [])
        file_content = None
    else:
        prompt = request.form.get("prompt")
        history_str = request.form.get("history")
        history = json.loads(history_str) if history_str else []
        file = request.files.get("file")
        file_content = ""
        if file:
            file_content = file.read().decode('utf-8', errors='replace')

    if not prompt:
        return jsonify({"error": "Prompt missing."}), 400
        
    sys_instruction = (
        "You are a senior quantitative trading strategist with 15+ years of experience building systematic, rule-based strategies for crypto and equities. "
        "You think like a professional quant: you understand that indicators are probabilistic tools, not crystal balls, and your edge comes from exploiting statistical patterns and risk management.\n\n"

        "## YOUR TRADING PHILOSOPHY\n"
        "- Standard portfolio parameters: Assume an initial capital balance of $10,000 ('initial_cash': 10000.0) and risk 2% of capital per trade ('risk_pct': 0.02), unless the user explicitly specifies a different starting balance or risk per trade.\n"
        "- A strategy's profitability is determined by win_rate * avg_win - (1 - win_rate) * avg_loss. With a 1:1.5 risk/reward (SL=1%, TP=1.5%), you need ~40% win rate to break even. With 1:2 (SL=1%, TP=2%), you only need ~33%.\n"
        "- WIDER stop losses (2-3%) produce HIGHER win rates because they give trades more room to breathe, but smaller position sizes. TIGHTER stops (0.5-1%) produce MORE trades but LOWER win rates.\n"
        "- For scalping on 1h crypto, use SL=1-2% and TP=1.5-3%. For swing trading on 4h/1d, use SL=3-5% and TP=5-10%.\n"
        "- Fewer, higher-quality conditions are ALWAYS better than many conditions. 2-3 conditions is ideal. More than 3 conditions will dramatically reduce trade frequency.\n"
        "- NEVER use more than ONE crossover operator (crosses_above/crosses_below) per entry block. Use ONE crossover as the primary trigger, and simple state comparisons (>, <) for confirmation filters.\n\n"

        "## PROVEN STRATEGY TEMPLATES YOU SHOULD USE\n"
        "1. **EMA Crossover + RSI Filter**: Fast EMA crosses above Slow EMA (trend), RSI < 70 (not overbought). This is the most reliable simple strategy. Use EMA_9 crossing EMA_21 for scalping, EMA_20 crossing EMA_50 for swing.\n"
        "2. **MACD Momentum + Bollinger Mean Reversion**: MACD crosses above signal (momentum confirmed), close > Bollinger lower band (not oversold). Good for range-bound markets.\n"
        "3. **RSI Oversold Bounce**: RSI < 30 (oversold), close > SMA_50 (still in uptrend). Catches pullback reversals in trending markets.\n"
        "4. **Bollinger Squeeze Breakout**: Close crosses above Bollinger upper band (breakout), RSI > 50 (momentum confirmation).\n\n"

        "## WHEN AUTO-OPTIMIZING (System Notes with backtest results)\n"
        "When you receive backtest results that don't meet the target:\n"
        "- If win rate is low (<45%) and PnL is negative: WIDEN the stop-loss (increase sl_pct by 0.5-1%) to give trades more room.\n"
        "- If win rate is decent (>45%) but PnL is still negative: INCREASE the take-profit (increase tp_pct) to improve risk/reward ratio.\n"
        "- If total trades are too few (<5): REMOVE a condition to relax entry requirements, or switch from crosses_above to a simple > comparison.\n"
        "- If max drawdown is too high (>30%): TIGHTEN the stop-loss or reduce the number of indicators to avoid whipsaw.\n"
        "- ALWAYS change at least 2 things between iterations. Never submit the exact same strategy twice.\n"
        "- Try different strategy archetypes between iterations (e.g., switch from EMA crossover to RSI mean-reversion).\n\n"

        "## SAVING STRATEGIES & FINALIZATION\n"
        "- When the user asks to save the strategy (e.g., 'save strategy', 'allow me to save', 'add to my profile'), confirm warmly in your reply that the strategy is saved and ALWAYS populate the complete 'strategy_config' object in your JSON response so the client engine can store it.\n"
        "- When a strategy reaches strong backtest performance (e.g. win rate > 60%), explicitly invite the user to save it to their profile in your reply text.\n\n"

        "## JSON OUTPUT FORMAT\n"
        "Reply with a JSON object containing these keys:\n"
        "- 'reply': A friendly text response explaining the strategy, reasoning, and next steps.\n"
        "- 'requires_backtest': Boolean. CRITICAL: Set to true if running or optimizing a backtest. Set to false if just answering questions or confirming a save.\n"
        "- 'strategy_config': The complete strategy configuration object (MUST be included whenever a strategy is proposed or saved).\n"
        "  - 'name', 'asset_type' ('crypto'/'stock'), 'timeframe' (e.g. '1h')\n"
        "  - 'initial_cash': Optional starting portfolio balance float (default 10000.0).\n"
        "  - 'risk_pct': Optional risk per trade float as a fraction (default 0.02 for 2% risk).\n"
        "  - 'leverage': Optional leverage float (default 20.0 for crypto, 1.6 for stock).\n"
        "  - 'indicators': list of dicts with 'name', 'type', and 'params'.\n"
        "    - EVERY indicator referenced in conditions MUST appear in this list.\n"
        "    - Supported types: EMA, SMA, RSI, ATR, MACD, BOLLINGER. No others.\n"
        "    - For EMA/SMA: params must include 'period' (e.g. {\"period\": 9}).\n"
        "    - For RSI: params must include 'period' (e.g. {\"period\": 14}).\n"
        "    - For MACD: params can include 'fast', 'slow', 'signal' (defaults: 12, 26, 9).\n"
        "    - For BOLLINGER: params can include 'period', 'std_dev' (defaults: 20, 2.0).\n"
        "  - 'long_entry_conditions' and 'short_entry_conditions': list of dicts with 'left', 'operator', 'right'.\n"
        "    - 'left' and 'right' MUST exactly match an indicator 'name' from the list above, or be a numeric value, or 'close'/'open'/'high'/'low'.\n"
        "    - For MACD: generated columns are [name], [name]_signal, [name]_hist.\n"
        "    - For BOLLINGER: generated columns are [name]_upper, [name]_lower, [name]_mid.\n"
        "    - Operators: '>', '<', '>=', '<=', '==', 'crosses_above', 'crosses_below'.\n"
        "    - MAXIMUM ONE crossover operator per entry condition list.\n"
        "  - 'exit_conditions': dict with 'sl_pct' (stop loss %) and 'tp_pct' (take profit %).\n"
        "- 'asset_type': 'crypto' or 'stock'.\n"
    )
    # Build complete prompt including history - trim to last 10 messages to prevent token overflow
    trimmed_history = history[-10:] if len(history) > 10 else history
    full_prompt = json.dumps(trimmed_history) + "\nUser: " + (prompt or "")
    if file_content:
        full_prompt += f"\n\nAttached File Content:\n{file_content}"
    
    try:
        pro_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-latest:generateContent"
        response_str = call_gemini(full_prompt, system_instruction=sys_instruction, json_mode=True, custom_url=pro_url)
        
        import json_repair
        response_data = None
        
        # Stage 1: Try json-repair (handles unescaped quotes, missing commas, newlines, extra braces)
        try:
            parsed = json_repair.loads(response_str)
            if isinstance(parsed, dict) and ("reply" in parsed or "strategy_config" in parsed):
                response_data = parsed
        except Exception:
            pass

        # Stage 2: Fallback to raw_decode streaming parser
        if not response_data:
            try:
                import re
                text_to_parse = response_str.strip() if response_str else ""
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text_to_parse, re.DOTALL)
                if json_match:
                    text_to_parse = json_match.group(1).strip()
                first_brace = text_to_parse.find('{')
                if first_brace != -1:
                    text_to_parse = text_to_parse[first_brace:]
                decoder = json.JSONDecoder()
                response_data, _ = decoder.raw_decode(text_to_parse)
            except Exception:
                pass

        # Stage 3: Final fallback to extract reply text via regex so the chat never errors out
        if not isinstance(response_data, dict):
            import re
            reply_match = re.search(r'"reply"\s*:\s*"([^"]+)"', response_str)
            reply_text = reply_match.group(1) if reply_match else response_str
            return jsonify({
                "reply": reply_text if reply_text else "Strategy generation completed.",
                "requires_backtest": False,
                "strategy_config": {},
                "asset_type": "crypto"
            }), 200

        return jsonify({
            "reply": response_data.get("reply", "Here is your strategy config."),
            "requires_backtest": bool(response_data.get("requires_backtest", False)),
            "strategy_config": response_data.get("strategy_config", {}) if isinstance(response_data.get("strategy_config"), dict) else {},
            "asset_type": response_data.get("asset_type", "crypto")
        }), 200
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({
            "reply": "I generated the strategy update, but experienced a temporary parsing issue. Please try sending your prompt again.",
            "requires_backtest": False,
            "strategy_config": {},
            "asset_type": "crypto"
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@custom_strategies_bp.route('/api/custom-strategies/parse-pinescript', methods=['POST'])
@require_auth
@require_premium
def parse_pinescript():
    data = request.json or {}
    code = data.get("code")
    if not code:
        return jsonify({"error": "PineScript code missing."}), 400
        
    sys_instruction = "You are an AI that translates PineScript v5 into JSON configuration for a Python backtester."
    try:
        response = call_gemini(code, system_instruction=sys_instruction, json_mode=True)
        return jsonify({"config": json.loads(response)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@custom_strategies_bp.route('/api/custom-strategies/parse-screenshot', methods=['POST'])
@require_auth
@require_premium
def parse_screenshot():
    data = request.json or {}
    image_base64 = data.get("image_base64")
    prompt = data.get("prompt", "Analyze this chart and extract the strategy into JSON.")
    if not image_base64:
        return jsonify({"error": "Base64 image missing."}), 400
        
    sys_instruction = "You are a trading strategy builder AI. Analyze charts and reply with JSON config."
    try:
        response = call_gemini(prompt, system_instruction=sys_instruction, json_mode=True, image_base64=image_base64)
        return jsonify({"config": json.loads(response)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@custom_strategies_bp.route('/api/custom-strategies/backtest/status/<task_id>', methods=['GET'])
@require_auth
@require_premium
def backtest_status(task_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT status, result, error FROM BacktestTasks WHERE id = ? AND user_id = ?", (task_id, g.user["id"]))
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Task not found."}), 404
            
        status, result, error = row
        return jsonify({
            "status": status,
            "result": json.loads(result) if result else None,
            "error": error
        }), 200

@custom_strategies_bp.route('/api/custom-strategies/save', methods=['POST'])
@require_auth
@require_premium
def save_strategy():
    data = request.json or {}
    name = data.get("name")
    asset_type = data.get("asset_type")
    timeframe = data.get("timeframe")
    config = data.get("config")
    metrics = data.get("metrics")
    
    if not all([name, asset_type, timeframe, config]):
        return jsonify({"error": "Missing required fields."}), 400
        
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO UserStrategies (user_id, name, asset_type, timeframe, strategy_config, performance_metrics, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (g.user["id"], name, asset_type, timeframe, json.dumps(config), json.dumps(metrics) if metrics else None, int(time.time()), int(time.time())))
        
    return jsonify({"success": True}), 200

@custom_strategies_bp.route('/api/custom-strategies/list', methods=['GET'])
@require_auth
def list_strategies():
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, name, description, asset_type, timeframe, strategy_config, performance_metrics, sharing_status, is_active
            FROM UserStrategies 
            WHERE user_id = ? OR sharing_status = 'approved'
        ''', (g.user["id"],))
        rows = c.fetchall()
        
        strategies = []
        for r in rows:
            strategies.append({
                "id": r[0],
                "name": r[1],
                "description": r[2],
                "asset_type": r[3],
                "timeframe": r[4],
                "strategy_config": json.loads(r[5]) if r[5] else None,
                "performance_metrics": json.loads(r[6]) if r[6] else None,
                "sharing_status": r[7],
                "is_active": bool(r[8])
            })
            
    return jsonify({"strategies": strategies}), 200

@custom_strategies_bp.route('/api/custom-strategies/delete/<int:strat_id>', methods=['DELETE'])
@require_auth
def delete_strategy(strat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM UserStrategies WHERE id = ? AND user_id = ?', (strat_id, g.user["id"]))
        if c.rowcount == 0:
            return jsonify({"error": "Strategy not found or not authorized to delete"}), 404
        conn.commit()
    return jsonify({"message": "Strategy deleted successfully"}), 200

@custom_strategies_bp.route('/api/custom-strategies/publish/<int:strat_id>', methods=['POST'])
@require_auth
@require_premium
def publish_strategy(strat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE UserStrategies SET sharing_status = 'pending' WHERE id = ? AND user_id = ?", (strat_id, g.user["id"]))
        
        # Trigger admin notification via telegram bot (would need to communicate with the bot daemon)
        
    return jsonify({"success": True}), 200

@custom_strategies_bp.route('/api/custom-strategies/activate', methods=['POST'])
@require_auth
@require_premium
def activate_strategy():
    data = request.json or {}
    strat_id = data.get("strategy_id")
    asset_type = data.get("asset_type")
    if not strat_id or not asset_type:
        return jsonify({"error": "strategy_id and asset_type required."}), 400
        
    with db_session() as conn:
        c = conn.cursor()
        # Fetch the strategy name
        c.execute("SELECT name FROM UserStrategies WHERE id = ? AND (user_id = ? OR sharing_status = 'approved')", (strat_id, g.user["id"]))
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Strategy not found or not approved."}), 404
            
        strat_name = row[0]
        
        # Deactivate previous
        c.execute("UPDATE UserStrategies SET is_active = 0 WHERE user_id = ? AND asset_type = ?", (g.user["id"], asset_type))
        # Activate new
        c.execute("UPDATE UserStrategies SET is_active = 1 WHERE id = ?", (strat_id,))
        
        # Update WebUsers table
        if asset_type == "crypto":
            c.execute("UPDATE WebUsers SET active_crypto_strategy = ? WHERE id = ?", (strat_name, g.user["id"]))
            c.execute("UPDATE Users SET active_crypto_strategy = ? WHERE telegram_chat_id = (SELECT telegram_chat_id FROM WebUsers WHERE id = ?)", (strat_name, g.user["id"]))
        elif asset_type == "stocks":
            c.execute("UPDATE WebUsers SET active_stock_strategy = ? WHERE id = ?", (strat_name, g.user["id"]))
            c.execute("UPDATE Users SET active_stock_strategy = ? WHERE telegram_chat_id = (SELECT telegram_chat_id FROM WebUsers WHERE id = ?)", (strat_name, g.user["id"]))
            
    return jsonify({"success": True, "active_strategy": strat_name}), 200
