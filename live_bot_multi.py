#!/usr/bin/env python3
"""
Multi-Symbol BB Scalper — Precision Analytics Edition (Blofin Global Fix)
------------------------------------------------------
- Feature: Fetches entire account position history in one call.
- Feature: Improved symbol matching and PnL parsing.
"""

import os
import time
import logging
import requests
import re
import asyncio
import ccxt.async_support as ccxt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timezone
import database
from utils_error import send_telegram_alert

class DynamicSymbolsList(list):
    def __init__(self, configs):
        self.configs = configs
        super().__init__()

    def _get_list(self):
        try:
            excluded = database.get_config("excluded_symbols", "")
            excluded_list = [s.strip().upper() for s in excluded.split(",") if s.strip()]
        except Exception:
            excluded_list = []
        return [f"{s}/USDT:USDT" for s in self.configs.keys() if s not in excluded_list]

    def __iter__(self):
        return iter(self._get_list())

    def __len__(self):
        return len(self._get_list())

    def __getitem__(self, index):
        return self._get_list()[index]

    def __repr__(self):
        return repr(self._get_list())

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

SYMBOL_CONFIGS = {
    "BTC":  {"bb": 2.5, "atr": 6.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "ETH":  {"bb": 2.5, "atr": 5.0, "rr": 1.25, "adx": 25, "rsi": 30},
    "SOL":  {"bb": 2.0, "atr": 4.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "DOGE": {"bb": 2.0, "atr": 5.0, "rr": 1.25, "adx": 0,  "rsi": 30, "long_only": True},
    "ADA":  {"bb": 2.5, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 40},
    "LINK": {"bb": 2.0, "atr": 6.0, "rr": 1.0,  "adx": 20, "rsi": 30},
    "DOT":  {"bb": 2.5, "atr": 4.0, "rr": 1.25, "adx": 20, "rsi": 30},
    "ZEC":  {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 20, "rsi": 30},
    "PEPE": {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "BNB":  {"bb": 2.5, "atr": 4.0, "rr": 1.25, "adx": 25, "rsi": 30},
    "NEAR": {"bb": 3.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "SUI":  {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "NOT":  {"bb": 2.0, "atr": 6.0, "rr": 1.25, "adx": 0,  "rsi": 30},
    "TAO":  {"bb": 2.0, "atr": 5.0, "rr": 1.25, "adx": 0,  "rsi": 30},
    "ONDO": {"bb": 2.5, "atr": 5.0, "rr": 1.25, "adx": 0,  "rsi": 30},
    "ENA":  {"bb": 2.0, "atr": 4.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "FET":  {"bb": 2.0, "atr": 6.0, "rr": 1.0,  "adx": 25, "rsi": 30},
    "WIF":  {"bb": 3.0, "atr": 5.0, "rr": 1.25, "adx": 25, "rsi": 30},
    "SHIB": {"bb": 2.5, "atr": 6.0, "rr": 1.25, "adx": 15, "rsi": 30},
}

# Optimized Valkyrie Elite Scalper individual symbol configurations
VALKYRIE_SYMBOL_CONFIGS = {
    "SOL":  {"bb": 2.0, "atr": 4.0, "rr": 1.2, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "LINK": {"bb": 2.6, "atr": 3.5, "rr": 0.8, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "BTC":  {"bb": 2.4, "atr": 3.0, "rr": 1.5, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "ADA":  {"bb": 2.4, "atr": 3.0, "rr": 1.0, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "DOT":  {"bb": 2.8, "atr": 4.5, "rr": 1.5, "adx": 25, "rsi_low": 25, "rsi_high": 75},
    "ETH":  {"bb": 2.2, "atr": 3.5, "rr": 1.0, "adx": 30, "rsi_low": 25, "rsi_high": 75},
    "SUI":  {"bb": 2.2, "atr": 4.0, "rr": 0.8, "adx": 25, "rsi_low": 25, "rsi_high": 75}
}

SYMBOLS = DynamicSymbolsList(SYMBOL_CONFIGS)
BAD_HOURS_UTC = {4, 12}
TIMEFRAME     = "15m"
LEVERAGE      = 20
RISK_PER_TRADE = 0.015         # Default 1.5% compounding risk (Valkyrie Sweet Spot)
CANDLE_LIMIT   = 1000
DRY_RUN        = os.getenv("BLOFIN_DRY_RUN", "true").lower() == "true"

os.makedirs("results", exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler("results/live_log.txt"), logging.StreamHandler()])
log = logging.getLogger("Bot")

# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

import database
from database import get_exchange_client, normalize_symbol

class MarketDataManager:
    """
    Centralized Market Data Manager (MDM)
    
    Architecture:
    - Fetches OHLCV data once per symbol and caches it in memory.
    - Prevents rate-limiting (HTTP 429) that would occur if each user individually fetched the data.
    - Used by both the background `signal_engine` and forward-testing routines.
    """
    def __init__(self, exchange_id='blofin'):
        self.exchange_id = exchange_id
        self.exchange = getattr(ccxt, exchange_id)({"options": {"defaultType": "swap"}})
        self.ohlcv_cache = {}

    async def fetch_ohlcv(self, symbol, timeframe, limit=250):
        if symbol not in self.ohlcv_cache:
            try:
                ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                self.ohlcv_cache[symbol] = df
            except Exception as e:
                log.error(f"MarketData fetch failed for {symbol}: {e}")
                try:
                    from utils_error import send_telegram_alert
                    send_telegram_alert("Crypto Trading Engine (Market Data Fetch)", e)
                except Exception:
                    pass
                return None
        return self.ohlcv_cache[symbol]

    async def close(self):
        await self.exchange.close()

def create_github_issue(subject, body):
    token, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not token or not repo: return
    owner = repo.split("/")[0]
    try:
        requests.post(f"https://api.github.com/repos/{repo}/issues", json={"title": subject, "body": body, "assignees": [owner]}, headers={"Authorization": f"token {token}"})
    except: pass

import strategies

def compute_signal(df, symbol_name, strategy_name="Mean Reversion Scalper", web_user_id=None):
    """
    Modular Signal Generator
    
    Flow:
    1. Routes the DataFrame through the requested strategy algorithm (e.g., Mean Reversion or Valkyrie).
    2. If a signal triggers (LONG/SHORT), pulls the risk constraints (ATR multipliers, TP/SL Ratios) 
       for that specific asset from the global CONFIG dictionaries.
    3. Calculates dynamic Stop Loss distance using rolling Average True Range (ATR).
    4. Evaluates `BAD_HOURS_UTC` to suppress trading during low-liquidity institutional rollover windows.
    """
    is_custom = strategy_name not in ["Mean Reversion Scalper", "Valkyrie Elite Scalper"]
    custom_cfg = None
    if is_custom:
        import database
        custom_cfg = database.get_custom_strategy_config(user_id=web_user_id, name=strategy_name)
        if not custom_cfg:
            return None
        from custom_strategy_interpreter import CustomStrategyInterpreter
        interpreter = CustomStrategyInterpreter(custom_cfg)
        processed_df = interpreter.build_indicators(df.copy())
        side = interpreter.check_signal(processed_df, len(processed_df)-1)
    else:
        strat = strategies.get_strategy(strategy_name)
        side = strat.check_signal(df, symbol_name)
    
    if not side or side not in ["LONG", "SHORT"]:
        return None
        
    # Standardize output using strategy-specific configurations
    if is_custom and custom_cfg:
        rr = custom_cfg.get("risk", {}).get("rr_ratio", 1.5)
        atr_mult = custom_cfg.get("risk", {}).get("sl_atr_mult", 3.0)
        cfg = {"atr": atr_mult, "rr": rr}
    elif strategy_name == "Valkyrie Elite Scalper":
        cfg = VALKYRIE_SYMBOL_CONFIGS.get(symbol_name)
        if not cfg:
            return None
    else:
        cfg = SYMBOL_CONFIGS.get(symbol_name)
        if not cfg:
            return None
    
    # ATR for SL calculation (common across strategies)
    tr = pd.concat([df["high"] - df["low"], abs(df["high"] - df["close"].shift()), abs(df["low"] - df["close"].shift())], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    last = df.iloc[-2]
    
    if datetime.now(timezone.utc).hour in BAD_HOURS_UTC: 
        return None
        
    return {
        "side": "buy" if side == "LONG" else "sell", 
        "entry": last["close"], 
        "sl_dist": atr.iloc[-2] * cfg["atr"], 
        "rr": cfg["rr"]
    }


async def place_order(exchange, symbol, signal, equity, risk_pct=None, is_manual=False):
    """
    Core Order Execution Engine
    """
    try:
        # Use user-specific risk or fallback to global default
        risk_val = (risk_pct / 100.0) if risk_pct is not None else RISK_PER_TRADE
        
        if not getattr(exchange, 'markets', None):
            await exchange.load_markets()

        symbol = database.normalize_symbol(symbol, exchange.id, client=exchange)
        market = exchange.market(symbol)
        ticker = await exchange.fetch_ticker(symbol)
        lp = ticker["last"]
        
        # Determine symbol multiplier (e.g., 1000 for 1000PEPE)
        base = market.get('base', '')
        import re
        m = re.match(r'^(\d+)', base)
        multiplier = float(m.group(1)) if m else 1.0
        
        scaled_entry = signal["entry"] * multiplier
        scaled_sl_dist = signal["sl_dist"] * multiplier
        rr = signal.get("rr", 2.0)
        
        if not is_manual and abs(lp - scaled_entry) / scaled_entry > 0.01: return None

        # Keep SL and TP fixed to the theoretical targets based on the signal entry price
        if signal["side"] == "buy":
            sl = scaled_entry - scaled_sl_dist
            tp = scaled_entry + (scaled_sl_dist * rr)
        else: # sell (SHORT)
            sl = scaled_entry + scaled_sl_dist
            tp = scaled_entry - (scaled_sl_dist * rr)

        # Reject the trade if the live price has already crossed the fixed SL or TP
        if signal["side"] == "buy":
            if lp <= sl:
                log.warning("⚠️ Skipping %s: current price %.8g is already at or below fixed SL %.8g", symbol, lp, sl)
                return None
            if lp >= tp:
                log.warning("⚠️ Skipping %s: current price %.8g is already at or above fixed TP %.8g", symbol, lp, tp)
                return None
        else:
            if lp >= sl:
                log.warning("⚠️ Skipping %s: current price %.8g is already at or above fixed SL %.8g", symbol, lp, sl)
                return None
            if lp <= tp:
                log.warning("⚠️ Skipping %s: current price %.8g is already at or below fixed TP %.8g", symbol, lp, tp)
                return None
            
        max_possible_leverage = 10 if exchange.id == 'coinbase' else LEVERAGE
        trade_leverage = max_possible_leverage
        if signal["side"] == "buy":
            # For Long: sl > lp * (1 - 1/Lev + 0.025)  =>  Lev < 1 / (1.025 - sl/lp)
            denom = 1.025 - (sl / lp)
            if denom > 0:
                trade_leverage = min(max_possible_leverage, int(1.0 / denom))
        else:
            # For Short: sl < lp * (1 + 1/Lev - 0.025)  =>  Lev < 1 / (sl/lp - 0.975)
            denom = (sl / lp) - 0.975
            if denom > 0:
                trade_leverage = min(max_possible_leverage, int(1.0 / denom))
        
        # Ensure leverage is at least 1x
        trade_leverage = max(1, trade_leverage)
        
        if trade_leverage < (10 if exchange.id == 'coinbase' else LEVERAGE):
            log.info("ℹ️ Dynamic Leverage adjustment for %s: reduced from %dx to %dx to protect SL (%.8g)", symbol, (10 if exchange.id == 'coinbase' else LEVERAGE), trade_leverage, sl)

        contract_size = float(market.get('contractSize') or 1)
        if contract_size <= 0: contract_size = 1
        
        # Calculate actual Stop Loss distance from our live entry (lp) to the fixed SL
        actual_sl_dist = abs(lp - sl)
        raw_size = (equity * risk_val) / (actual_sl_dist * contract_size)
        
        limits = market.get('limits', {})
        max_market = limits.get('market', {}).get('amount', {}).get('max')
        if max_market is None: 
            max_market = limits.get('amount', {}).get('max')
        if max_market is None:
            max_market = 999999999.0 # Safe fallback
            
        max_leverage_size = (equity * trade_leverage) / (lp * contract_size)
        size = min(float(raw_size), float(max_market), float(max_leverage_size))
        
        # Format the size using the exchange's unified precision format
        try:
            size_str = exchange.amount_to_precision(symbol, size)
            size = float(size_str)
        except Exception:
            size = round(size, 3)
            
        if size <= 0: return None

        # 🛡️ DYNAMIC LEVERAGE SYNC
        if exchange.has.get('setLeverage', False):
            try:
                params = {}
                if exchange.id == 'bingx':
                    params['side'] = 'LONG' if signal["side"] == 'buy' else 'SHORT'
                await exchange.set_leverage(trade_leverage, symbol, params=params)
            except Exception as le:
                log.warning("⚠️ Leverage set failed for %s: %s. Continuing with caution.", symbol, le)

        # Risk Check: Liquidation vs Stop Loss
        # Institutional Buffer: Entry * (1 - 1/Lev + 2.5% Safety Margin)
        liq_buffer = (1 / trade_leverage) - 0.025 
        if signal["side"] == "buy":
            est_liq = lp * (1 - liq_buffer)
            if sl <= est_liq:
                log.warning("⚠️ RISK ALERT: %s Long SL (%.8g) is beyond safety Liq (%.8g) even at %dx leverage. Skipping.", symbol, sl, est_liq, trade_leverage)
                return None
        else: # Short
            est_liq = lp * (1 + liq_buffer)
            if sl >= est_liq:
                log.warning("⚠️ RISK ALERT: %s Short SL (%.8g) is beyond safety Liq (%.8g) even at %dx leverage. Skipping.", symbol, sl, est_liq, trade_leverage)
                return None

        log.info("🔔 SIGNAL on %s: %s | Entry: %.8g | SL: %.8g | TP: %.8g", symbol, signal["side"].upper(), lp, sl, tp)
        if DRY_RUN: return None

        # Integrated exchanges like Blofin
        limit_price = lp * 1.01 if signal["side"] == "buy" else lp * 0.99
        order_side = "buy" if signal["side"] == "buy" else "sell"
        if exchange.id == 'coinbase':
            if signal["side"] == "buy":
                limit_price = min(limit_price, tp * 0.999)
            else:
                limit_price = max(limit_price, tp * 1.001)
            params = {
                "attached_order_configuration": {
                    "trigger_bracket_gtc": {
                        "limit_price": exchange.price_to_precision(symbol, tp),
                        "stop_trigger_price": exchange.price_to_precision(symbol, sl)
                    }
                }
            }
        else:
            params = {
                "marginMode": "isolated", 
                "positionSide": "net", 
                "stopLoss": {"triggerPrice": sl}, 
                "takeProfit": {"triggerPrice": tp}
            }
            if exchange.id == 'bitget':
                params['tdMode'] = 'isolated' # Bitget specific override
            elif exchange.id == 'bingx':
                params['positionSide'] = 'LONG' if signal["side"] == "buy" else 'SHORT'
            
        try:
            await exchange.create_order(symbol, "limit", order_side, size, limit_price, params=params)
        except Exception as e:
            raise e
            
        log.info("✅ Order placed for %s on %s", symbol, exchange.id)
        return {"symbol": symbol.split("/")[0], "side": "BUY", "size": size, "entry": lp, "tp": tp, "sl": sl}
    except Exception as e:
        log.error("❌ Order failed for %s: %s", symbol, e)
        return None


async def process_user_on_symbol(user, symbol, signal):
    """
    User Trade Router
    
    This function processes an individual user for a generated signal.
    
    Logic:
    1. Institutional Gating: Checks premium tier. Standard users do not execute live trades.
    2. Symbol Check: Verifies the user has manually enabled the symbol in their settings.
    3. Equity Override: Applies the user's custom capital allocation limits (e.g., only trade with 50% of equity).
    4. Position Check: Queries CCXT to prevent double-entry if the user is already in a trade for this symbol.
    5. Dispatches to `place_order`.
    """
    try:
        # 💎 Institutional Gating
        is_prem = database.is_premium(user)
        if not is_prem:
            return  # Standard users do not execute live trades
            
        sym_name = symbol.split("/")[0]
        risk_val = user.get('risk_pct', 1.5)

        if sym_name not in user.get('enabled_symbols', []):
            return
        
        # Capital Allocation Override
        eq_type = user.get('custom_equity_type', 'all')
        eq_val = user.get('custom_equity_value')
        
        effective_equity = user.get('equity', 10000.0)
        if eq_type == 'amount' and eq_val is not None:
            effective_equity = min(float(eq_val), user.get('equity', 10000.0))
        elif eq_type == 'pct' and eq_val is not None:
            effective_equity = user.get('equity', 10000.0) * (float(eq_val) / 100.0)
        
        ex = get_exchange_client(user)
        try:
            norm_sym = normalize_symbol(symbol, ex.id)
            # Check existing positions
            pos = await ex.fetch_positions()
            if not any(p.get('symbol') == norm_sym and float(p.get("contracts", 0) or 0) != 0 for p in pos):
                await place_order(ex, norm_sym, signal, effective_equity, risk_pct=risk_val)
        finally:
            await ex.close()
    except Exception as ue:
        futures_type = user.get('bingx_futures_type', 'standard') or 'standard'
        log.error("User %s error on %s using exchange %s (%s futures): %s",
                  user.get('telegram_chat_id') or f"web_{user.get('web_user_id')}",
                  symbol,
                  user.get('exchange_id', 'blofin'),
                  futures_type,
                  ue)


async def run():
    log.info("═"*60 + "\n  Multi-Exchange Metaverse Sherpa Engine (ASYNC) \n" + "═"*60)
    import database
    active_users = database.get_all_active_users()
    if not active_users:
        log.info("No active users found. Skipping pass.")
        return

    mdm = MarketDataManager()
    sem = asyncio.Semaphore(3)
    try:
        # 🕵️ Sync Position Status for all users first (Parallelized)
        async def sync_user_pos(user):
            async with sem:
                try:
                    ex = get_exchange_client(user)
                    try:
                        pos = await ex.fetch_positions()
                        has_active = any(float(p.get("contracts", 0) or 0) != 0 for p in pos)
                        database.update_position_status(user.get('telegram_chat_id'), has_active, web_user_id=user.get('web_user_id'))
                    finally:
                        await ex.close()
                except Exception as e:
                    futures_type = user.get('bingx_futures_type', 'standard') or 'standard'
                    e_str = str(e)
                    log.error("Position sync failed for %s on exchange %s (%s futures): %s",
                              user.get('telegram_chat_id') or f"web_{user.get('web_user_id')}",
                              user.get('exchange_id', 'blofin'),
                              futures_type,
                              e_str)
                              
                    auth_keywords = [
                        "AuthenticationError", "PermissionDenied", "403 Forbidden", "401 Unauthorized",
                        "10024", "Unmatched IP", "regulatory restrictions", "Invalid API-key", "Invalid API Key"
                    ]
                    if any(k.lower() in e_str.lower() for k in auth_keywords):
                        chat_id = user.get('telegram_chat_id')
                        web_user_id = user.get('web_user_id')
                        # database.invalidate_exchange_credentials(chat_id=chat_id, web_user_id=web_user_id)
                        ex_id = user.get('exchange_id', 'exchange').capitalize()
                        
                        email = user.get('email')
                        username = user.get('username')
                        id_parts = []
                        if chat_id:
                            tg_str = f"Telegram ID: {chat_id}"
                            if username:
                                tg_str += f" (@{username})"
                            id_parts.append(tg_str)
                        if web_user_id:
                            id_parts.append(f"Web User ID: {web_user_id}")
                        if email:
                            id_parts.append(f"Email: {email}")
                        
                        user_id_str = " | ".join(id_parts) if id_parts else "Unknown User"
                        
                        try:
                            from utils_error import send_telegram_alert
                            error_msg = f"User {user_id_str} API Key authentication failure.\\nExchange: {ex_id}\\nReason: {e_str}"
                            send_telegram_alert("API Key Auth Error (Trading Engine)", error_msg, tb_string="")
                        except Exception:
                            pass
                    else:
                        try:
                            from utils_error import send_telegram_alert
                            send_telegram_alert("Crypto Trading Engine (Position Sync)", e)
                        except Exception:
                            pass

        await asyncio.gather(*(sync_user_pos(u) for u in active_users))

        # Parallelize Market Data Fetching
        market_data_tasks = [mdm.fetch_ohlcv(sym, TIMEFRAME, limit=CANDLE_LIMIT) for sym in SYMBOLS]
        await asyncio.gather(*market_data_tasks)

        # Parallelize Signal Computation and User Processing by grouping users by strategy
        disabled_strats = database.get_disabled_strategies()
        strategy_groups = {}
        for user in active_users:
            strat = user.get("strategy", "Mean Reversion Scalper")
            if strat in disabled_strats:
                if not user.get('has_open_positions', False):
                    database.migrate_user_if_no_open_positions(user.get('telegram_chat_id'), web_user_id=user.get('web_user_id'))
                    # Load the migrated strategy preference
                    if user.get('telegram_chat_id'):
                        migrated_user = database.get_user(user['telegram_chat_id'])
                    else:
                        from web_api.db_web import get_web_user_by_id
                        web_raw = get_web_user_by_id(user['web_user_id'])
                        migrated_user = database.get_user_from_web_row(web_raw) if web_raw else None
                    strat = migrated_user.get("strategy", "Valkyrie Elite Scalper") if migrated_user else "Valkyrie Elite Scalper"

            if strat not in strategy_groups:
                strategy_groups[strat] = []
            strategy_groups[strat].append(user)
            
        processing_tasks = []
        for strat_name, users in strategy_groups.items():
            if strat_name in disabled_strats:
                log.info(f"Strategy '{strat_name}' is disabled. Skipping new signal entries.")
                continue
                
            is_custom = strat_name not in ["Mean Reversion Scalper", "Valkyrie Elite Scalper"]
            custom_cfg = None
            tf = TIMEFRAME
            if is_custom:
                custom_cfg = database.get_custom_strategy_config(users[0].get('web_user_id'), strat_name)
                if custom_cfg:
                    tf = custom_cfg.get('timeframe', TIMEFRAME)
                    
            for symbol in SYMBOLS:
                df = await mdm.fetch_ohlcv(symbol, tf)
                if df is not None:
                    signal = compute_signal(df, symbol.split("/")[0], strategy_name=strat_name, web_user_id=users[0].get('web_user_id') if is_custom else None)
                    if signal:
                        for user in users:
                            async def wrapped_process(u=user, s=symbol, sig=signal):
                                async with sem:
                                    await process_user_on_symbol(u, s, sig)
                            processing_tasks.append(wrapped_process())

        if processing_tasks:
            await asyncio.gather(*processing_tasks)
    finally:
        await mdm.close()
    log.info("═"*60 + "\n  Multi-Exchange Pass Complete \n" + "═"*60)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as e:
        log.error("Fatal exception in crypto trading engine: %s", e, exc_info=True)
        try:
            from utils_error import send_telegram_alert
            send_telegram_alert("Crypto Trading Engine (live_bot_multi.py)", e)
        except Exception as alert_err:
            log.error("Failed to send Telegram alert for crypto engine crash: %s", alert_err)

