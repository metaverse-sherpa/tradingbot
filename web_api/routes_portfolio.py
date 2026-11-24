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
_ASSET_META_CACHE = {}  # {symbol: {"target_price": ..., "recommendation": ..., "sector": ..., "beta": ..., "ts": ...}}
_ASSET_META_TTL = 43200  # 12 hours in seconds
_SPY_BENCHMARK_CACHE = {"closes": [], "ts": 0}  # Cached daily closes for SPY benchmark comparison
_SPY_BENCHMARK_TTL = 43200  # 12 hours in seconds

def _get_spy_benchmark_return(hold_days):
    """Compute SPY percentage return over roughly `hold_days` calendar days using cached daily closes."""
    now_ts = time.time()
    closes = _SPY_BENCHMARK_CACHE.get("closes") or []
    if not closes or (now_ts - _SPY_BENCHMARK_CACHE.get("ts", 0) >= _SPY_BENCHMARK_TTL):
        try:
            hist = yf.Ticker("SPY").history(period="2y", interval="1d")
            if hist is not None and not hist.empty and "Close" in hist.columns:
                closes = [float(x) for x in hist["Close"].dropna().tolist()]
                _SPY_BENCHMARK_CACHE["closes"] = closes
                _SPY_BENCHMARK_CACHE["ts"] = now_ts
        except Exception as e:
            print(f"[Portfolio] SPY benchmark fetch error: {e}")

    if len(closes) < 5:
        return None, None

    effective_days = max(7, min(int(hold_days or 30), 700))
    # Convert calendar days to approximate trading days (~252/365)
    trading_days = max(5, min(int(effective_days * 0.69), len(closes) - 1))
    past_close = closes[-1 - trading_days]
    latest_close = closes[-1]
    if past_close <= 0:
        return None, None
    ret_pct = round(((latest_close - past_close) / past_close) * 100.0, 2)
    return ret_pct, effective_days

# --- 📊 Global Market Data Cache (shared across all users) ---
BENCHMARK_SYMBOLS = {"SPY", "QQQ"}

STOCK_WATCHLIST = [
    # Benchmarks (used for macro regime, excluded from picks)
    "SPY", "QQQ",
    # Tech & AI / Semiconductors
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "AMD", "ORCL", "CRM", "ADBE", "PANW", "PLTR", "NFLX",
    # Financials
    "BRK-B", "JPM", "V", "MA", "GS", "BLK", "SCHW",
    # Healthcare
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "ISRG", "TMO",
    # Consumer & Retail
    "COST", "WMT", "HD", "PG", "KO", "PEP", "MCD", "TSLA",
    # Industrials, Energy & Utilities / REITs
    "CAT", "GE", "ETN", "LMT", "XOM", "CVX", "NEE", "DUK", "O",
    # Core Income / Defensive ETFs
    "SCHD", "VYM"
]

INCOME_DEFENSIVE_SYMBOLS = {
    "SCHD", "VYM", "JNJ", "PG", "KO", "PEP", "ABBV", "MRK",
    "XOM", "CVX", "NEE", "DUK", "O", "MCD", "JPM", "BRK-B", "WMT", "COST", "HD"
}

CRYPTO_WATCHLIST = []

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
FALLBACK_SPECULATIVE_WATCHLIST = ['TSLA', 'PLTR', 'AMD', 'COIN', 'MARA', 'RIOT', 'SOXL', 'UPST', 'CLSK', 'SOFI', 'HOOD', 'APP', 'SMCI', 'RKLB', 'IONQ']

def _compute_stock_quant_metrics(sym, df):
    """Compute technical & screening metrics directly from a 1y daily OHLCV DataFrame."""
    closes = df["Close"].dropna()
    if len(closes) < 15:
        return None

    current_price = float(closes.iloc[-1])
    if current_price <= 0:
        return None

    price_7d_ago = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
    price_30d_ago = float(closes.iloc[-22]) if len(closes) >= 22 else float(closes.iloc[0])

    ret_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100.0
    ret_30d = ((current_price - price_30d_ago) / price_30d_ago) * 100.0
    avg_vol = int(df["Volume"].dropna().tail(20).mean()) if "Volume" in df.columns and len(df["Volume"].dropna()) > 0 else 0

    high_series = df["High"].dropna() if "High" in df.columns else closes
    low_series = df["Low"].dropna() if "Low" in df.columns else closes
    high_52w = float(high_series.max()) if len(high_series) > 0 else current_price
    low_52w = float(low_series.min()) if len(low_series) > 0 else current_price
    swing_low_20d = float(low_series.tail(20).min()) if len(low_series) >= 5 else round(current_price * 0.92, 2)

    # RSI(14)
    delta = closes.diff().dropna()
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)
    avg_gain = float(gains.tail(14).mean()) if len(gains) >= 14 else float(gains.mean())
    avg_loss = float(losses.tail(14).mean()) if len(losses) >= 14 else float(losses.mean())
    if avg_loss == 0:
        rsi_14 = 100.0 if avg_gain > 0 else 50.0
    else:
        rs = avg_gain / avg_loss
        rsi_14 = 100.0 - (100.0 / (1.0 + rs))

    # Moving Averages (50d & 200d)
    sma_50 = float(closes.tail(50).mean()) if len(closes) >= 50 else float(closes.mean())
    sma_200 = float(closes.tail(200).mean()) if len(closes) >= 120 else None
    pct_vs_sma50 = ((current_price - sma_50) / sma_50) * 100.0 if sma_50 > 0 else 0.0
    pct_vs_sma200 = ((current_price - sma_200) / sma_200) * 100.0 if sma_200 and sma_200 > 0 else None

    if sma_200 is not None:
        if current_price > sma_50 and sma_50 > sma_200:
            trend = "Strong Uptrend"
        elif current_price > sma_200 and current_price <= sma_50:
            trend = "Pullback in Uptrend"
        elif current_price > sma_50:
            trend = "Reversal / Recovering"
        else:
            trend = "Downtrend"
    else:
        trend = "Uptrend" if current_price > sma_50 else "Downtrend"

    # ATR(14)
    try:
        prev_close = closes.shift(1)
        tr_df = df[["High", "Low", "Close"]].dropna()
        if len(tr_df) >= 15:
            tr = (tr_df["High"] - tr_df["Low"]).combine(
                (tr_df["High"] - prev_close.reindex(tr_df.index)).abs(), max
            ).combine(
                (tr_df["Low"] - prev_close.reindex(tr_df.index)).abs(), max
            )
            atr_14 = float(tr.tail(14).mean())
        else:
            atr_14 = current_price * 0.025
    except Exception:
        atr_14 = current_price * 0.025
    atr_pct = (atr_14 / current_price) * 100.0 if current_price > 0 else 2.5

    return {
        "price": round(current_price, 2),
        "7d_return": round(ret_7d, 2),
        "30d_return": round(ret_30d, 2),
        "avg_volume": avg_vol,
        "52w_high": round(high_52w, 2),
        "52w_low": round(low_52w, 2),
        "pct_from_52w_high": round(((current_price - high_52w) / high_52w) * 100.0, 2) if high_52w > 0 else 0.0,
        "rsi_14": round(rsi_14, 1),
        "sma_50": round(sma_50, 2),
        "pct_vs_sma50": round(pct_vs_sma50, 1),
        "sma_200": round(sma_200, 2) if sma_200 is not None else None,
        "pct_vs_sma200": round(pct_vs_sma200, 1) if pct_vs_sma200 is not None else None,
        "trend": trend,
        "atr_14": round(atr_14, 2),
        "atr_pct": round(atr_pct, 2),
        "swing_low_20d": round(swing_low_20d, 2),
    }

def _enrich_candidate_fundamentals(symbols):
    """Fetch & cache fundamentals (sector, forward_pe, dividend_yield, analyst target, market_cap) for candidate stocks."""
    now_ts = time.time()
    to_fetch = []
    out = {}
    for sym in symbols:
        cached = _ASSET_META_CACHE.get(sym)
        if cached and (now_ts - cached.get("ts", 0) < _ASSET_META_TTL) and "dividend_yield" in cached:
            out[sym] = cached
        else:
            to_fetch.append(sym)

    if to_fetch:
        def fetch_one(sym):
            try:
                info = yf.Ticker(sym).info or {}
                raw_div = info.get("dividendYield")
                # yfinance dividendYield can be percentage (e.g. 3.45) or decimal (0.0345) depending on version
                div_yield_pct = None
                if raw_div is not None:
                    try:
                        val = float(raw_div)
                        div_yield_pct = round(val * 100.0, 2) if val < 0.25 else round(val, 2)
                    except (ValueError, TypeError):
                        div_yield_pct = None
                raw_pe = info.get("forwardPE") or info.get("trailingPE")
                fwd_pe = round(float(raw_pe), 1) if raw_pe and float(raw_pe) > 0 else None
                raw_beta = info.get("beta") or info.get("beta3Year")
                beta = round(float(raw_beta), 2) if raw_beta is not None else None
                meta = {
                    "target_price": info.get("targetMeanPrice"),
                    "recommendation": info.get("recommendationKey"),
                    "sector": info.get("sector") or info.get("category") or ("ETF / Index" if info.get("quoteType") == "ETF" else "Other"),
                    "beta": beta,
                    "forward_pe": fwd_pe,
                    "dividend_yield": div_yield_pct,
                    "market_cap": int(info.get("marketCap") or 0),
                    "ts": now_ts,
                }
                _ASSET_META_CACHE[sym] = meta
                return sym, meta
            except Exception:
                return sym, _ASSET_META_CACHE.get(sym) or {}

        ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(to_fetch)))
        try:
            futs = [ex.submit(fetch_one, s) for s in to_fetch]
            done, _ = concurrent.futures.wait(futs, timeout=12)
            for f in done:
                try:
                    sym, meta = f.result(timeout=0)
                    out[sym] = meta
                except Exception:
                    pass
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    return out

def _refresh_market_data_cache():
    """Fetch 1y daily history for all watchlist US equities and compute technical screening metrics."""
    try:
        now = time.time()
        new_stocks = {}

        try:
            stock_df = yf.download(
                STOCK_WATCHLIST,
                period="1y",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False
            )
            for sym in STOCK_WATCHLIST:
                try:
                    df = stock_df if len(STOCK_WATCHLIST) == 1 else stock_df[sym]
                    metrics = _compute_stock_quant_metrics(sym, df)
                    if metrics:
                        new_stocks[sym] = metrics
                except Exception:
                    continue
        except Exception as e:
            print(f"[MarketCache] Stock fetch error: {e}")

        with _MARKET_DATA_LOCK:
            if new_stocks:
                _MARKET_DATA_CACHE["stocks"] = new_stocks
            _MARKET_DATA_CACHE["crypto"] = {}
            _MARKET_DATA_CACHE["last_refresh"] = now

        print(f"[MarketCache] Refreshed: {len(new_stocks)} US equities with quant indicators")
    except Exception as e:
        print(f"[MarketCache] Fatal refresh error: {e}")

def _schedule_market_data_refresh():
    """Run market data refresh every 4 hours in a background thread."""
    _refresh_market_data_cache()
    t = threading.Timer(14400, _schedule_market_data_refresh)
    t.daemon = True
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
    return list(symbols)[:30]

def _get_speculative_market_data():
    with _SPECULATIVE_MARKET_DATA_LOCK:
        last_refresh = _SPECULATIVE_STOCK_CACHE.get("last_refresh", 0)
        if time.time() - last_refresh < 3600 and _SPECULATIVE_STOCK_CACHE.get("stocks"):
            return dict(_SPECULATIVE_STOCK_CACHE["stocks"])

    symbols = _fetch_speculative_stock_symbols()
    new_stocks = {}
    try:
        stock_df = yf.download(symbols, period="1y", interval="1d", group_by="ticker", auto_adjust=True, threads=True, progress=False)
        for sym in symbols:
            try:
                df = stock_df if len(symbols) == 1 else stock_df[sym]
                metrics = _compute_stock_quant_metrics(sym, df)
                if metrics and metrics["price"] >= 5.0 and metrics["avg_volume"] >= 500000:
                    new_stocks[sym] = metrics
            except Exception:
                continue
        with _SPECULATIVE_MARKET_DATA_LOCK:
            _SPECULATIVE_STOCK_CACHE["stocks"] = new_stocks
            _SPECULATIVE_STOCK_CACHE["last_refresh"] = time.time()
    except Exception as e:
        print(f"[MarketCache] Failed to download speculative data: {e}")

    return new_stocks

def _build_market_research_brief(user_id, risk_profile="Moderate", investment_goal="Growth"):
    """Build a global, profile-tailored US equities quant research brief (does NOT leak a single user's personal holdings)."""
    # 1. Get cached market data
    with _MARKET_DATA_LOCK:
        core_stock_data = dict(_MARKET_DATA_CACHE.get("stocks", {}))

    if not core_stock_data:
        _refresh_market_data_cache()
        with _MARKET_DATA_LOCK:
            core_stock_data = dict(_MARKET_DATA_CACHE.get("stocks", {}))

    stock_data = dict(core_stock_data)

    # If aggressive and speculation, swap candidates with dynamic speculative screen (keeping SPY/QQQ for macro)
    if risk_profile.lower() == "aggressive" and investment_goal.lower() == "speculation":
        speculative_data = _get_speculative_market_data()
        if speculative_data:
            stock_data = dict(speculative_data)
            for bm in BENCHMARK_SYMBOLS:
                if bm in core_stock_data:
                    stock_data[bm] = core_stock_data[bm]

    # 2. Get active bot signals
    active_signals = get_active_signals_internal(bypass_cache=False)
    open_longs = [s for s in active_signals if s.get("status") == "open" and s.get("side", "").lower() == "long"]

    signal_lookup = {}
    for s in open_longs:
        sym = s.get("symbol", "").replace("/USDT", "").replace("/USD", "").upper()
        signal_lookup[sym] = {
            "strategy": s.get("strategy", ""),
            "entry_price": s.get("entry_price", 0),
            "tp_price": s.get("tp_price", 0),
            "sl_price": s.get("sl_price", 0),
        }

    # 3. Check existing active recommendations & 14-day stop-loss cooldown in AIRecommendations
    active_rec_symbols = set()
    cooldown_symbols = set()
    active_rec_lines = []
    cooldown_cutoff = int(time.time()) - 14 * 86400
    try:
        with db_session() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT symbol, entry_price, target_price, stop_loss FROM AIRecommendations WHERE status = 'active' AND risk_profile = ? AND investment_goal = ?",
                (risk_profile, investment_goal)
            )
            for row in c.fetchall():
                s_u = str(row[0]).upper()
                active_rec_symbols.add(s_u)
                active_rec_lines.append(f"{s_u} (Entry ${row[1]}, Target ${row[2]}, SL ${row[3]})")

            c.execute(
                "SELECT symbol FROM AIRecommendations WHERE LOWER(status) IN ('hit_stop_loss', 'stopped_out', 'loss') AND created_at >= ?",
                (cooldown_cutoff,)
            )
            for row in c.fetchall():
                cooldown_symbols.add(str(row[0]).upper())
    except Exception as e:
        print(f"[MarketCache] Error reading AIRecommendations state: {e}")

    excluded_symbols = BENCHMARK_SYMBOLS | active_rec_symbols | cooldown_symbols

    # 4. Macro Market Regime via real SPY & QQQ technicals
    spy = core_stock_data.get("SPY") or stock_data.get("SPY")
    qqq = core_stock_data.get("QQQ") or stock_data.get("QQQ")
    if spy:
        spy_7d = spy.get("7d_return", 0.0)
        spy_30d = spy.get("30d_return", 0.0)
        spy_trend = spy.get("trend", "Unknown")
        spy_rsi = spy.get("rsi_14", 50.0)
        qqq_str = f" | QQQ 30d: {qqq['30d_return']:+.1f}% ({qqq['trend']})" if qqq else ""
        if spy_7d >= 1.5 and spy_trend in ("Strong Uptrend", "Reversal / Recovering"):
            market_regime = f"BULLISH MOMENTUM (SPY 7d: {spy_7d:+.1f}%, 30d: {spy_30d:+.1f}%, RSI: {spy_rsi}, {spy_trend}{qqq_str}) - Favor trend-following breakouts & quality leaders"
        elif spy_7d <= -1.5 or spy_trend == "Downtrend":
            market_regime = f"PULLBACK / RISK-OFF (SPY 7d: {spy_7d:+.1f}%, 30d: {spy_30d:+.1f}%, RSI: {spy_rsi}, {spy_trend}{qqq_str}) - Prioritize Pullback/Dip value, defensive quality, & ATR-buffered support stops"
        else:
            market_regime = f"NEUTRAL / CONSOLIDATION (SPY 7d: {spy_7d:+.1f}%, 30d: {spy_30d:+.1f}%, RSI: {spy_rsi}, {spy_trend}{qqq_str}) - Favor selective high-conviction setups near support with strong R:R"
    else:
        avg_7d = sum(d.get("7d_return", 0.0) for d in stock_data.values()) / max(1, len(stock_data))
        market_regime = f"BROAD MARKET (Avg 7d: {avg_7d:+.1f}%)"

    # 5. Select candidate buckets & enrich with cached fundamentals
    eligible_syms = [s for s in stock_data.keys() if s not in excluded_symbols]

    # Category A: Momentum Leaders (above 50d SMA, not wildly overbought RSI < 78)
    mom_pool = [s for s in eligible_syms if stock_data[s].get("pct_vs_sma50", -99) > 0 and stock_data[s].get("rsi_14", 50) < 78]
    if len(mom_pool) < 8:
        mom_pool = eligible_syms
    momentum_stocks = sorted(mom_pool, key=lambda s: stock_data[s].get("30d_return", 0), reverse=True)[:10]

    # Category B: Quality Pullback / Dip Opportunities (5%-25% off 52w high, RSI 30-60)
    dip_pool = [
        s for s in eligible_syms
        if -28.0 <= stock_data[s].get("pct_from_52w_high", 0) <= -5.0
        and 25.0 <= stock_data[s].get("rsi_14", 50) <= 62.0
        and s not in momentum_stocks
    ]
    dip_stocks = sorted(dip_pool, key=lambda s: stock_data[s].get("pct_vs_sma200") or -99, reverse=True)[:10]

    # Category C: Income & Defensive Leaders (for Conservative or Income goals)
    is_defensive_goal = (risk_profile.lower() == "conservative" or investment_goal.lower() == "income")
    income_stocks = [s for s in eligible_syms if s in INCOME_DEFENSIVE_SYMBOLS][:12] if is_defensive_goal else []

    all_selected = list(dict.fromkeys(momentum_stocks + dip_stocks + income_stocks))
    fundamentals = _enrich_candidate_fundamentals(all_selected)

    def format_candidate(sym):
        d = stock_data[sym]
        f = fundamentals.get(sym, {})
        sig = signal_lookup.get(sym)
        sector = f.get("sector") or "N/A"
        pe_str = f"FwdP/E={f['forward_pe']}" if f.get("forward_pe") else "FwdP/E=N/A"
        div_str = f"Div={f['dividend_yield']}%" if f.get("dividend_yield") else "Div=0%"
        analyst_str = ""
        if f.get("target_price") and d["price"] > 0:
            upside = ((float(f["target_price"]) - d["price"]) / d["price"]) * 100.0
            analyst_str = f" | AnalystTarget=${float(f['target_price']):.2f} ({upside:+.1f}%)"
        sma200_str = f"vs200d={d['pct_vs_sma200']:+.1f}%" if d.get("pct_vs_sma200") is not None else "vs200d=N/A"
        line = (
            f"  {sym} [{sector}]: Price=${d['price']} | 7d={d['7d_return']:+.1f}% | 30d={d['30d_return']:+.1f}% | "
            f"Trend={d['trend']} (vs50d={d['pct_vs_sma50']:+.1f}%, {sma200_str}) | RSI14={d['rsi_14']} | "
            f"ATR14={d['atr_pct']}% (${d['atr_14']}) | 20dLow=${d['swing_low_20d']} | "
            f"52wHigh=${d['52w_high']} ({d['pct_from_52w_high']:+.1f}%) | {pe_str} | {div_str}{analyst_str}"
        )
        if sig:
            tp_upside = ((sig['tp_price'] - sig['entry_price']) / sig['entry_price'] * 100) if sig['entry_price'] > 0 else 0
            line += f" | ⚡ ACTIVE BOT SIGNAL (Strategy: {sig['strategy']}, TP Upside: {tp_upside:+.1f}%)"
        return line

    # 6. Build the structured text brief
    brief_lines = [
        "=== MACRO MARKET REGIME ===",
        f"Current Environment: {market_regime}",
        "",
    ]
    if active_rec_lines:
        brief_lines.append("=== ALREADY ACTIVE RECOMMENDATIONS FOR THIS PROFILE (DO NOT DUPLICATE; DIVERSIFY SECTORS) ===")
        brief_lines.append("  " + ", ".join(active_rec_lines[:10]))
        brief_lines.append("")
    if cooldown_symbols:
        brief_lines.append(f"=== 14-DAY STOP-LOSS COOLDOWN (EXCLUDED) ===\n  {', '.join(sorted(cooldown_symbols))}")
        brief_lines.append("")

    brief_lines.append("=== US EQUITIES CANDIDATES ===")
    brief_lines.append("--- CATEGORY A: MOMENTUM & TREND LEADERS (Above 50d SMA, RSI < 78) ---")
    for sym in momentum_stocks:
        brief_lines.append(format_candidate(sym))

    brief_lines.append("")
    brief_lines.append("--- CATEGORY B: QUALITY PULLBACK & DIP OPPORTUNITIES (5%-28% off 52w High, RSI 25-62) ---")
    for sym in dip_stocks:
        brief_lines.append(format_candidate(sym))

    if income_stocks:
        brief_lines.append("")
        brief_lines.append("--- CATEGORY C: INCOME & DEFENSIVE LEADERS (Prioritize Dividend Yield & Low Volatility) ---")
        for sym in income_stocks:
            brief_lines.append(format_candidate(sym))

    return "\n".join(brief_lines), stock_data, set(all_selected)

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
        res = requests.get(url, headers=headers, params=params, timeout=8)
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
            print(f"[Portfolio] Alpaca stock snapshots returned HTTP {res.status_code}")
            for sym in symbols:
                prices[sym] = (None, 0.0)
    except Exception as e:
        print(f"[Portfolio] Alpaca stock snapshots error: {e}")
        for sym in symbols:
            prices[sym] = (None, 0.0)
    return prices

def get_crypto_prices(symbols):
    """Fetch batch crypto prices via Alpaca Crypto Snapshots with Coinbase public REST fallback."""
    prices = {}
    if not symbols:
        return prices

    # 1. Batch fetch via Alpaca Crypto Snapshots (fast, US-friendly, no heavy market-loading)
    try:
        alpaca_pairs = [f"{sym}/USD" for sym in symbols]
        res = requests.get(
            "https://data.alpaca.markets/v1beta3/crypto/us/snapshots",
            params={"symbols": ",".join(alpaca_pairs)},
            timeout=6
        )
        if res.status_code == 200:
            snapshots = res.json().get("snapshots", {})
            for sym in symbols:
                snap = snapshots.get(f"{sym}/USD")
                if snap:
                    last_price = snap.get("latestTrade", {}).get("p") or snap.get("dailyBar", {}).get("c")
                    prev_close = snap.get("prevDailyBar", {}).get("c") or snap.get("dailyBar", {}).get("o")
                    if last_price:
                        change_pct = ((last_price - prev_close) / prev_close) * 100 if prev_close else 0.0
                        prices[sym] = (float(last_price), float(change_pct))
    except Exception as e:
        print(f"[Portfolio] Alpaca crypto snapshots error: {e}")

    # 2. Lightweight Coinbase public REST fallback for any missing symbols (strict timeouts)
    missing_symbols = [s for s in symbols if s not in prices]
    if missing_symbols:
        def fetch_single_coinbase(sym):
            try:
                r = requests.get(
                    f"https://api.exchange.coinbase.com/products/{sym}-USD/stats",
                    timeout=4
                )
                if r.status_code == 200:
                    d = r.json()
                    last_p = float(d.get("last") or 0)
                    open_p = float(d.get("open") or 0)
                    if last_p > 0:
                        pct = ((last_p - open_p) / open_p) * 100 if open_p > 0 else 0.0
                        return sym, last_p, pct
            except Exception:
                pass
            return sym, None, 0.0

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(missing_symbols)))
        try:
            futures = {executor.submit(fetch_single_coinbase, sym): sym for sym in missing_symbols}
            done, _ = concurrent.futures.wait(futures, timeout=6)
            for fut in done:
                try:
                    sym, price, pct = fut.result(timeout=0)
                    prices[sym] = (price, pct)
                except Exception:
                    pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        for sym in missing_symbols:
            if sym not in prices:
                prices[sym] = (None, 0.0)

    return prices

def get_cached_prices(symbols, categories):
    """Get stock and crypto prices using in-memory caching with strict timeouts."""
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

    if to_fetch_stock or to_fetch_crypto:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        try:
            f_stock = executor.submit(get_stock_prices, to_fetch_stock) if to_fetch_stock else None
            f_crypto = executor.submit(get_crypto_prices, to_fetch_crypto) if to_fetch_crypto else None

            if f_stock:
                try:
                    stock_prices = f_stock.result(timeout=12)
                    for sym, val in stock_prices.items():
                        cache_key = f"{sym}_stock"
                        if val[0] is not None:
                            _PRICE_CACHE[cache_key] = (val[0], val[1], now)
                        result[cache_key] = val
                except Exception as e:
                    print(f"[Portfolio] Stock price fetch timed out or failed: {e}")

            if f_crypto:
                try:
                    crypto_prices = f_crypto.result(timeout=12)
                    for sym, val in crypto_prices.items():
                        cache_key = f"{sym}_crypto"
                        if val[0] is not None:
                            _PRICE_CACHE[cache_key] = (val[0], val[1], now)
                        result[cache_key] = val
                except Exception as e:
                    print(f"[Portfolio] Crypto price fetch timed out or failed: {e}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    # Ensure all requested keys are in the result
    for sym, cat in zip(symbols, categories):
        cache_key = f"{sym.upper()}_{cat.lower()}"
        if cache_key not in result:
            result[cache_key] = (None, 0.0)

    return result


# --- 🤖 Gemini Helper Function ---
GEMINI_PRO_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-latest:generateContent"
GEMINI_FLASH_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
GEMINI_FALLBACK_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

def call_gemini(prompt, system_instruction=None, json_mode=False, image_base64=None, mime_type="image/jpeg", custom_url=None):
    """Call Google Gemini API using configured env variables/secrets with modern model fallback."""
    api_key = utils_gcp.get_secret("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    preferred_url = custom_url or os.getenv("PORTFOLIO_AI_URL") or GEMINI_FLASH_URL
    fallback_urls = [
        preferred_url,
        GEMINI_FLASH_URL,
        GEMINI_FALLBACK_URL,
    ]
    # Remove duplicates preserving order
    urls_to_try = list(dict.fromkeys(fallback_urls))

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
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    last_error = None
    for url in urls_to_try:
        if "generativelanguage.googleapis.com" in url:
            url_with_key = f"{url}?key={api_key}"
        else:
            url_with_key = url

        headers = {"Content-Type": "application/json"}
        if "generativelanguage.googleapis.com" not in url:
            headers["x-goog-api-key"] = api_key
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            resp = requests.post(url_with_key, json=payload, headers=headers, timeout=90)
            if resp.status_code == 200:
                res_data = resp.json()
                try:
                    return res_data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError):
                    raise ValueError(f"Unexpected response structure from Gemini API: {res_data}")
            else:
                last_error = f"Status {resp.status_code}: {resp.text}"
                print(f"[Gemini API] Call to {url} failed with {last_error}. Trying fallback...")
        except Exception as e:
            last_error = str(e)
            print(f"[Gemini API] Exception calling {url}: {e}. Trying fallback...")

    raise ValueError(f"All Gemini API endpoints failed. Last error: {last_error}")


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

    # Persist inline profile/goal updates if provided
    if data.get("risk_profile") or data.get("investment_goal"):
        try:
            with db_session() as conn:
                c = conn.cursor()
                c.execute(
                    "UPDATE WebUsers SET risk_profile = ?, investment_goal = ? WHERE id = ?",
                    (risk_profile, investment_goal, user_id)
                )
                conn.commit()
        except Exception as e:
            print(f"[Analysis] Could not persist risk_profile/investment_goal: {e}")
    
    p_response, code = get_portfolio()
    if code != 200:
        return jsonify({"error": "Failed to compile portfolio data for analysis."}), 500

    p_data = p_response.get_json()
    positions = p_data.get("positions", [])
    stats = p_data.get("stats", {})

    if not positions:
        return jsonify({"error": "Cannot analyze an empty portfolio."}), 400

    # Fetch analyst target prices, sector, beta, and active signal setups concurrently
    def fetch_info(p):
        signal_target = None
        signal_stop_loss = None
        analyst_target = None
        recommendation = None
        sector = None
        beta = None
        sym = p.get('symbol', '').strip().upper()
        cat = p.get('category', 'stock').lower()
        curr_p = float(p.get('current_price') or p.get('avg_entry_price') or 0)
        clean_sym = sym.replace('/', '').replace('USDT', '').replace('USD', '').strip()

        # 1. Check AIRecommendations DB using EXACT normalized symbol match (prevents LIKE '%PAY%' matching PAYC/PAYX)
        try:
            with db_session() as conn:
                c = conn.cursor()
                c.execute("""
                    SELECT target_price, stop_loss FROM AIRecommendations
                    WHERE (
                        UPPER(symbol) = ?
                        OR UPPER(REPLACE(REPLACE(REPLACE(symbol, '/', ''), 'USDT', ''), 'USD', '')) = ?
                    )
                    AND LOWER(category) = ? AND status = 'active'
                    ORDER BY id DESC LIMIT 1
                """, (sym, clean_sym, cat))
                rec_row = c.fetchone()
                if rec_row and rec_row[0]:
                    cand_tp = float(rec_row[0])
                    cand_sl = float(rec_row[1]) if rec_row[1] else None
                    # Sanity check against current price so stale/mismatched prices don't poison the audit
                    if curr_p <= 0 or (0.1 * curr_p <= cand_tp <= 5.0 * curr_p):
                        signal_target = cand_tp
                        if cand_sl and (curr_p <= 0 or (0.1 * curr_p <= cand_sl <= 3.0 * curr_p)):
                            signal_stop_loss = cand_sl

                # 2. Check TheoreticalTrades DB for active signal target price if not found (exact match)
                if not signal_target:
                    c.execute("""
                        SELECT tp_price, sl_price FROM TheoreticalTrades
                        WHERE (
                            UPPER(symbol) = ?
                            OR UPPER(REPLACE(REPLACE(REPLACE(symbol, '/', ''), 'USDT', ''), 'USD', '')) = ?
                        )
                        AND status = 'open'
                        ORDER BY id DESC LIMIT 1
                    """, (sym, clean_sym))
                    tt_row = c.fetchone()
                    if tt_row and tt_row[0] and cat == 'crypto':
                        cand_tp = float(tt_row[0])
                        if curr_p <= 0 or (0.1 * curr_p <= cand_tp <= 5.0 * curr_p):
                            signal_target = cand_tp
                            signal_stop_loss = float(tt_row[1]) if tt_row[1] else None
        except Exception as e:
            print(f"[Analysis] Error fetching DB target price for {sym}: {e}")

        # 3. Cached Yahoo Finance metadata (sector, beta, analyst targetMeanPrice) for stocks/ETFs
        if cat == 'stock':
            now_ts = time.time()
            cached = _ASSET_META_CACHE.get(sym)
            if cached and (now_ts - cached.get("ts", 0) < _ASSET_META_TTL):
                analyst_target = cached.get("target_price")
                recommendation = cached.get("recommendation")
                sector = cached.get("sector")
                beta = cached.get("beta")
            else:
                try:
                    info = yf.Ticker(sym).info or {}
                    analyst_target = info.get('targetMeanPrice')
                    recommendation = info.get('recommendationKey')
                    sector = info.get('sector') or info.get('category') or (
                        'ETF / Index' if info.get('quoteType') == 'ETF' else None
                    )
                    raw_beta = info.get('beta') or info.get('beta3Year')
                    if raw_beta is not None:
                        try:
                            beta = round(float(raw_beta), 2)
                        except (ValueError, TypeError):
                            beta = None
                    _ASSET_META_CACHE[sym] = {
                        "target_price": analyst_target,
                        "recommendation": recommendation,
                        "sector": sector,
                        "beta": beta,
                        "ts": now_ts
                    }
                except Exception:
                    pass
        else:
            sector = "Digital Assets"

        return {
            'signal_target': signal_target,
            'signal_stop_loss': signal_stop_loss,
            'analyst_target': analyst_target,
            'recommendation': recommendation,
            'sector': sector or ('ETF / Other' if cat == 'stock' else 'Digital Assets'),
            'beta': beta
        }

    meta_results = [{} for _ in positions]
    meta_executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(8, max(1, len(positions))))
    try:
        future_to_idx = {meta_executor.submit(fetch_info, p): idx for idx, p in enumerate(positions)}
        done, _ = concurrent.futures.wait(future_to_idx, timeout=15)
        for fut in done:
            idx = future_to_idx[fut]
            try:
                meta_results[idx] = fut.result(timeout=0)
            except Exception:
                meta_results[idx] = {}
    finally:
        meta_executor.shutdown(wait=False, cancel_futures=True)

    for p, res in zip(positions, meta_results):
        p['signal_target'] = res.get('signal_target')
        p['signal_stop_loss'] = res.get('signal_stop_loss')
        p['analyst_target'] = res.get('analyst_target')
        p['analyst_recommendation'] = res.get('recommendation')
        p['sector'] = res.get('sector') or ('Other' if p.get('category', 'stock').lower() == 'stock' else 'Digital Assets')
        p['beta'] = res.get('beta')

    # --- Compute Quantitative Portfolio Concentration, Sector & Risk Metrics ---
    total_port_val = float(stats.get("total_portfolio_value") or stats.get("market_value") or 0.0)
    cash_bal = float(stats.get("cash_balance") or 0.0)
    cash_pct = round((cash_bal / total_port_val * 100.0), 2) if total_port_val > 0 else 0.0

    sorted_by_alloc = sorted(positions, key=lambda x: x.get("allocation_pct", 0.0), reverse=True)
    top_1_pos = sorted_by_alloc[0] if sorted_by_alloc else None
    top_3_pct = round(sum(x.get("allocation_pct", 0.0) for x in sorted_by_alloc[:3]), 1)
    top_5_pct = round(sum(x.get("allocation_pct", 0.0) for x in sorted_by_alloc[:5]), 1)

    sector_totals = collections.defaultdict(float)
    weighted_beta_num = 0.0
    weighted_beta_den = 0.0
    deep_losers = []
    for p in positions:
        sec = p.get("sector") or "Other"
        alloc = float(p.get("allocation_pct") or 0.0)
        sector_totals[sec] += alloc
        if p.get("beta") is not None and alloc > 0:
            weighted_beta_num += float(p["beta"]) * alloc
            weighted_beta_den += alloc
        if float(p.get("overall_pnl_pct") or 0.0) <= -15.0:
            deep_losers.append(f"{p['symbol']} ({p['overall_pnl_pct']:.1f}%)")

    sector_breakdown = sorted(
        [{"sector": k, "pct": round(v, 1)} for k, v in sector_totals.items()],
        key=lambda x: x["pct"],
        reverse=True
    )
    top_sector = sector_breakdown[0] if sector_breakdown else {"sector": "N/A", "pct": 0.0}
    portfolio_beta = round(weighted_beta_num / weighted_beta_den, 2) if weighted_beta_den > 0 else None

    # SPY Benchmark Comparison over average holding period
    spy_benchmark_pct, spy_benchmark_days = _get_spy_benchmark_return(stats.get("avg_hold_time_days") or 30)
    alpha_vs_spy_pct = (
        round(float(stats.get("total_pnl_pct") or 0.0) - spy_benchmark_pct, 2)
        if spy_benchmark_pct is not None else None
    )

    # Fetch / reuse cached holdings news sentiment for top holdings
    top_news_symbols = [
        {"symbol": x["symbol"], "category": x["category"]}
        for x in sorted_by_alloc[:6]
    ]
    news_payload = _get_portfolio_news_data(user_id, override_positions=top_news_symbols)
    news_items_for_prompt = news_payload.get("news", [])
    news_counts_for_prompt = news_payload.get("counts", {"bullish": 0, "bearish": 0, "neutral": 0})

    portfolio_metrics = {
        "cash_balance": round(cash_bal, 2),
        "cash_pct": cash_pct,
        "top_1_symbol": top_1_pos["symbol"] if top_1_pos else None,
        "top_1_pct": round(top_1_pos.get("allocation_pct", 0.0), 1) if top_1_pos else 0.0,
        "top_3_pct": top_3_pct,
        "top_5_pct": top_5_pct,
        "top_sector": top_sector["sector"],
        "top_sector_pct": top_sector["pct"],
        "sector_breakdown": sector_breakdown[:6],
        "portfolio_beta": portfolio_beta,
        "deep_losers_count": len(deep_losers),
        "positions_count": len(positions),
        "spy_benchmark_pct": spy_benchmark_pct,
        "spy_benchmark_days": spy_benchmark_days,
        "alpha_vs_spy_pct": alpha_vs_spy_pct,
        "news_sentiment": news_counts_for_prompt,
    }

    # Build clean position payload (omit null target/stop-loss keys so LLM doesn't nag about missing UI fields)
    compiled_positions = []
    for p in positions:
        item = {
            "symbol": p["symbol"],
            "category": p["category"],
            "sector": p.get("sector"),
            "quantity": round(float(p["quantity"]), 4),
            "avg_entry_price": round(float(p["avg_entry_price"]), 4),
            "current_price": round(float(p["current_price"]), 4),
            "market_value": round(float(p["market_value"]), 2),
            "overall_pnl_pct": round(float(p["overall_pnl_pct"]), 2),
            "allocation_pct": round(float(p["allocation_pct"]), 2),
            "purchase_date": p["purchase_date"],
        }
        if p.get("beta") is not None:
            item["beta"] = p["beta"]
        if p.get("signal_target") is not None:
            item["system_signal_target"] = p["signal_target"]
        if p.get("signal_stop_loss") is not None:
            item["system_signal_stop_loss"] = p["signal_stop_loss"]
        if p.get("analyst_target") is not None:
            item["analyst_consensus_target"] = p["analyst_target"]
        if p.get("analyst_recommendation"):
            item["analyst_recommendation"] = p["analyst_recommendation"]
        compiled_positions.append(item)

    compiled_positions_str = json.dumps(compiled_positions)

    system_instruction = (
        f"You are an institutional-grade investment advisor tailoring advice for a client with a **{risk_profile}** risk profile and an investment goal of **{investment_goal}**.\n"
        "Analyze the user's holdings, sector/concentration exposure, cash buffer, and performance to produce a high-signal portfolio health report.\n"
        "CRITICAL RULE 1 (HOLDINGS OWNERSHIP): The user's ONLY current portfolio positions are the assets explicitly listed in `compiled_positions_str`. Do NOT recommend selling, trimming, or taking profit on ANY asset unless it is explicitly present in `compiled_positions_str`!\n"
        "CRITICAL RULE 2 (TARGET PRICES): For owned positions that have `system_signal_target` or `analyst_consensus_target`, do NOT recommend taking profit solely for hitting target if `current_price` is well below target (unless trimming for concentration/risk management).\n"
        "CRITICAL RULE 3 (RECOMMENDATIONS ARE NOT HOLDINGS): The `ACTIVE RECOMMENDATIONS` list below contains external trade setups available to buy. These are NOT owned by the user unless listed in `compiled_positions_str`. NEVER tell the user to sell or take profit on an unowned recommendation.\n"
        "CRITICAL RULE 4 (STOCK ETFs VS CRYPTO COINS): If a position's category is `stock` (e.g. BTC ETF, ETH ETF, IBIT, BITO, ETHA, or tickers BTC/ETH categorized as `stock`), treat it strictly as an ETF stock equity position priced per share. Do NOT confuse ETF share prices with underlying crypto coin prices, and NEVER tell the user to change its category.\n"
        "CRITICAL RULE 5 (NO MISSING-METADATA NAGGING): This portfolio tracks static holdings, NOT live brokerage orders. NEVER waste action items telling the user to 'define target prices', 'set stop-loss fields in the tracker', or 'fix missing stop-losses'. Focus exclusively on real investment decisions: position sizing, concentration/sector risk, trimming overweight winners or deep underperformers, rotating capital, and building a cash buffer.\n"
        "CRITICAL RULE 6 (CASH-AWARE ALLOCATION): Always respect `cash_balance`. If `cash_balance` is $0 (or < 2% of total portfolio value), NEVER recommend initiating a new buy without explicitly specifying which existing holding(s) to trim or exit (and approximate dollar/% amount) to fund it.\n"
    )

    last_score = None
    num_completed = 0
    num_total_plan = 0

    if last_analysis and len(last_analysis) >= 4 and last_analysis[1] is not None:
        last_score = int(last_analysis[1])
        last_plan_str = last_analysis[2]
        
        checked_items_str = "None"
        if last_analysis[3]:
            try:
                last_plan = json.loads(last_plan_str)
                num_total_plan = len(last_plan)
                completed_bools = json.loads(last_analysis[3])
                checked_items = [
                    (item.get("title", str(item)) if isinstance(item, dict) else item)
                    for i, item in enumerate(last_plan)
                    if i < len(completed_bools) and completed_bools[i]
                ]
                num_completed = len(checked_items)
                if checked_items:
                    checked_items_str = json.dumps(checked_items)
            except Exception:
                pass

        system_instruction += (
            f"\nPREVIOUS CONTEXT:\nYou previously analyzed this portfolio and gave it a score of {last_score}/100. "
            f"Your previous action plan was: {last_plan_str}\n"
            f"The user has explicitly completed {num_completed} of {num_total_plan} items from that plan: {checked_items_str}\n"
            "Evaluate if the user has implemented these recommendations. If they have followed your advice, "
            "you MUST reward them by increasing their score above their previous score. It is very frustrating for a user to follow advice and see their score drop.\n"
        )

    system_instruction += (
        "\nReturn a valid JSON object containing EXACTLY these keys:\n"
        "- score: An integer score (1-100) representing overall portfolio health aligned with their risk profile and goal.\n"
        "- score_breakdown: An object with 5 integer sub-scores (0-100) explaining the overall score:\n"
        "    {\n"
        "      \"diversification\": <int 0-100, based on sector spread and single-stock/top-3 concentration>,\n"
        "      \"risk_management\": <int 0-100, based on beta, drawdown exposure, and deep losers>,\n"
        "      \"momentum_upside\": <int 0-100, based on win rate, P&L health, and analyst/signal upside>,\n"
        "      \"goal_alignment\": <int 0-100, how well holdings match the client's risk_profile and investment_goal>,\n"
        "      \"liquidity\": <int 0-100, based on cash_pct dry powder for dip-buying/rebalancing>\n"
        "    }\n"
        "- action_plan: A JSON list of 3-5 structured action objects ordered by priority:\n"
        "    [\n"
        "      {\n"
        "        \"title\": \"Concise, specific action (e.g. 'Trim NVDA from 18% to 12% to lock in gains and fund cash buffer')\",\n"
        "        \"action_type\": \"TRIM\" | \"EXIT\" | \"ADD\" | \"REBALANCE\" | \"RISK\" | \"HOLD\",\n"
        "        \"symbol\": \"Ticker symbol if specific to one holding (e.g. 'NVDA'), or null if portfolio-wide\",\n"
        "        \"priority\": \"HIGH\" | \"MEDIUM\" | \"LOW\",\n"
        "        \"rationale\": \"One crisp sentence citing exact numbers (allocation %, P&L %, sector %, or cash $).\"\n"
        "      }\n"
        "    ]\n"
        "- detailed_recommendations: A concise executive audit summary in markdown (150-240 words, no HTML) covering key strengths, biggest risks (citing exact concentration/sector/drawdown numbers), and strategic priorities.\n"
        "- show_me_how: Step-by-step execution guide in markdown showing exact trades/percentages/dollar amounts to execute the action plan.\n"
        "Ensure the response is valid JSON and nothing else."
    )

    # Load active recommendations from DB and inject them into the system instruction
    active_recs = []
    try:
        with db_session() as conn:
            c = conn.cursor()
            c.execute("SELECT symbol, category, entry_price, target_price, stop_loss FROM AIRecommendations WHERE status = 'active' AND risk_profile = ? AND investment_goal = ?", (risk_profile, investment_goal))
            active_recs = [dict(row) for row in c.fetchall()]
    except Exception as e:
        print(f"[Analysis] Error fetching active recommendations: {e}")

    buys_md = ""
    if active_recs:
        rec_symbols = [r['symbol'] for r in active_recs]
        rec_cats = [r['category'] for r in active_recs]
        rec_prices = get_cached_prices(rec_symbols, rec_cats)

        valid_recs = []
        for rec in active_recs:
            sym_key = f"{rec['symbol'].upper()}_{rec['category'].lower()}"
            curr_price, _ = rec_prices.get(sym_key, (None, None))
            rec['current_price'] = curr_price if curr_price is not None else rec.get('entry_price', 0.0)

            entry = float(rec.get('entry_price') or 0)
            target = float(rec.get('target_price') or 0)
            curr = float(rec.get('current_price') or entry)

            if target > entry and entry > 0:
                progress_pct = max(0.0, (curr - entry) / (target - entry) * 100.0)
            else:
                progress_pct = 0.0
            rec['progress_pct'] = progress_pct

            # Exclude recommendations that have already hit or nearly hit target (>90% progress)
            if progress_pct < 90.0:
                valid_recs.append(rec)

        active_recs = valid_recs

        # Sort recommendations so those closest to entry price (lowest progress towards target) come FIRST
        active_recs.sort(key=lambda r: r['progress_pct'])

        prompt_recs_ctx = (
            "\n\nACTIVE RECOMMENDATIONS (Ranked by proximity to Entry Price - closest to entry price first):\n"
            "CRITICAL RECOMMENDATION SELECTION RULES:\n"
            "- You MUST prioritize recommending new positions or re-allocating funds into active recommendations that are CLOSEST to their Entry Price (lowest Progress % towards target).\n"
            "- Do NOT recommend initiating new positions in recommendations that have ALREADY moved significantly towards their Target Price (e.g., >=30% progress towards target), as the risk/reward is less favorable.\n"
            "- When listing buy orders or re-allocations in your step-by-step instructions (`show_me_how`), you MUST include the Target Growth % "
            "(e.g., `(Target Price: $X, Target Growth: +Y%, Stop Loss: $Z)`). You MUST include a markdown link to "
            "[AI Recommendations](/recommendations) in your markdown response so the user can easily click to track these setups):\n"
        )
        buys_md = "\n\n👉 [Click here to view all active recommendations](/recommendations)\n"
        for rec in active_recs:
            entry = float(rec.get('entry_price') or 0)
            target = float(rec.get('target_price') or 0)
            curr = float(rec.get('current_price') or entry)
            sl = float(rec.get('stop_loss') or 0)
            growth_pct = ((target - entry) / entry * 100) if entry > 0 and target > 0 else 0.0
            growth_str = f"+{growth_pct:.1f}%" if growth_pct > 0 else f"{growth_pct:.1f}%"
            prog = rec['progress_pct']

            prompt_recs_ctx += f"- {rec['symbol']} ({rec['category']}): Entry: ${entry}, Current: ${curr:.4f}, Target: ${target}, Target Growth: {growth_str}, Stop Loss: ${sl}, Progress Towards Target: {prog:.1f}%\n"
        
        system_instruction += prompt_recs_ctx

    sector_summary_str = ", ".join(f"{s['sector']} {s['pct']}%" for s in sector_breakdown[:6]) or "N/A"
    spy_line = (
        f"- Benchmark vs SPY ({spy_benchmark_days}d avg hold): SPY {spy_benchmark_pct:+.2f}% vs Portfolio {stats['total_pnl_pct']:+.2f}% (Alpha: {alpha_vs_spy_pct:+.2f}%)\n"
        if spy_benchmark_pct is not None else ""
    )
    news_headlines_str = "; ".join(
        f"[{n.get('sentiment', 'Neutral')}] {n.get('symbol')}: {n.get('title')}"
        for n in news_items_for_prompt[:3]
    )
    news_line = (
        f"- Recent Holdings News Sentiment: {news_counts_for_prompt['bullish']} Bullish, {news_counts_for_prompt['bearish']} Bearish, {news_counts_for_prompt['neutral']} Neutral"
        + (f" | Top headlines: {news_headlines_str}\n" if news_headlines_str else "\n")
    )

    prompt = (
        f"Analyze this portfolio ({len(positions)} positions): {compiled_positions_str}\n\n"
        f"PORTFOLIO SUMMARY & RISK METRICS:\n"
        f"- Total Portfolio Value: ${total_port_val:,.2f} (Holdings: ${stats['market_value']:,.2f}, Cash Available: ${cash_bal:,.2f} [{cash_pct:.1f}%])\n"
        f"- Cost Basis: ${stats['cost_basis']:,.2f} | Total P/L: ${stats['total_pnl']:+,.2f} ({stats['total_pnl_pct']:+.2f}%) | Win Rate: {stats['win_rate']:.0f}%\n"
        f"{spy_line}"
        f"- Annual Dividends: ${stats['annual_dividends']:,.2f}\n"
        f"- Concentration: Largest position = {portfolio_metrics['top_1_symbol']} ({portfolio_metrics['top_1_pct']}%), Top 3 = {top_3_pct}%, Top 5 = {top_5_pct}%\n"
        f"- Sector Exposure: {sector_summary_str}\n"
        f"- Estimated Portfolio Beta: {portfolio_beta if portfolio_beta is not None else 'N/A'}\n"
        f"- Positions Down >=15%: {', '.join(deep_losers) if deep_losers else 'None'}\n"
        f"{news_line}"
    )

    try:
        raw_json_str = call_gemini(
            prompt,
            system_instruction=system_instruction,
            json_mode=True,
            custom_url=os.getenv("PORTFOLIO_AI_URL") or GEMINI_PRO_URL
        )
        clean_json_str = raw_json_str.strip().replace("```json", "").replace("```", "")
        analysis = json.loads(clean_json_str)

        raw_score = int(analysis.get("score", 75))
        score = raw_score
        
        # Enforce guaranteed score reward if user completed action plan items from previous analysis
        if last_score is not None and num_completed > 0:
            ratio = num_completed / max(1, num_total_plan)
            bonus_pts = max(3 * num_completed, int(ratio * 15))
            score = min(100, max(raw_score, last_score + bonus_pts))

        raw_breakdown = analysis.get("score_breakdown") or {}
        score_breakdown = None
        if isinstance(raw_breakdown, dict) and raw_breakdown:
            score_breakdown = {
                "diversification": max(0, min(100, int(raw_breakdown.get("diversification", score)))),
                "risk_management": max(0, min(100, int(raw_breakdown.get("risk_management", score)))),
                "momentum_upside": max(0, min(100, int(raw_breakdown.get("momentum_upside", score)))),
                "goal_alignment": max(0, min(100, int(raw_breakdown.get("goal_alignment", score)))),
                "liquidity": max(0, min(100, int(raw_breakdown.get("liquidity", score)))),
            }

        action_plan = analysis.get("action_plan", [])
        detailed_recs = analysis.get("detailed_recommendations", "")
        show_me_how = analysis.get("show_me_how", "")
        
        if buys_md:
            show_me_how += buys_md

        analysis_data = {
            "detailed_recommendations": detailed_recs,
            "show_me_how": show_me_how,
            "score_breakdown": score_breakdown,
            "portfolio_metrics": portfolio_metrics,
        }

        with db_session() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO PortfolioAnalysisHistory (user_id, score, analysis_text, action_plan, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, score, json.dumps(analysis_data), json.dumps(action_plan), int(time.time())))
            conn.commit()

        return jsonify({
            "score": score,
            "score_breakdown": score_breakdown,
            "portfolio_metrics": portfolio_metrics,
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
                "score_breakdown": text_data.get("score_breakdown", None),
                "portfolio_metrics": text_data.get("portfolio_metrics", None),
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


def generate_and_cache_recommendations(user_id, risk_profile, investment_goal, force_regenerate=False, is_admin=False):
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
    if force_regenerate and not is_admin:
        if time.time() - cached_timestamp < 86400:
            return {"error": f"This list was recently generated in the last 24 hours for {risk_profile} & {investment_goal}.", "status_code": 429}

    # 1. First Pass: Check Cache (No Lock)
    if not force_regenerate and cached_recommendations:
        if time.time() - cached_timestamp < 86400:
            return {"recommendations": cached_recommendations, "status_code": 200}

    # 2. Acquire Lock for this specific combination
    lock = _GOOD_BUYS_LOCKS[cache_key]
    acquired = lock.acquire(blocking=False)
    if not acquired:
        return {"error": f"An analysis is currently in progress for {risk_profile} & {investment_goal}. Please wait a moment.", "status_code": 429}

    try:
        # 3. Double-Check Cache
        if not force_regenerate:
            cached_data_str = get_config(cache_key)
            if cached_data_str:
                try:
                    cached_data = json.loads(cached_data_str)
                    timestamp = cached_data.get("timestamp", 0)
                    if time.time() - timestamp < 86400:
                        return {"recommendations": cached_data["recommendations"], "status_code": 200}
                except Exception:
                    pass

        # 4. Generate New Recommendations
        analysis_id = None
        analysis_data = {}
        if user_id:
            with db_session() as conn:
                c = conn.cursor()
                c.execute('SELECT id, analysis_text, timestamp FROM PortfolioAnalysisHistory WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (user_id,))
                last_analysis = c.fetchone()

            if last_analysis:
                analysis_id = last_analysis[0]
                try:
                    analysis_data = json.loads(last_analysis[1])
                except Exception:
                    pass

        if "good_buys" in analysis_data and not is_admin and not force_regenerate:
             pass 

        # Build the quant US equities market research brief (global, not biased by one user's personal holdings)
        research_brief, stock_lookup, valid_candidate_syms = _build_market_research_brief(user_id, risk_profile, investment_goal)

        is_speculative = (risk_profile.lower() == "aggressive" and investment_goal.lower() == "speculation")
        is_income = (risk_profile.lower() == "conservative" or investment_goal.lower() == "income")

        # Construct the AI Prompt (100% US Equities, quant-grounded)
        system_instruction = (
            "You are a senior quantitative US equities portfolio analyst AI for Metaverse Sherpa. "
            "You are selecting the top 5 institutional-grade US equity / ETF buy-and-hold ideas.\n\n"
            f"Target Risk Profile: '{risk_profile}'\n"
            f"Target Investment Goal: '{investment_goal}'\n\n"
            "IMPORTANT STRATEGY & RISK MANAGEMENT RULES:\n"
            "1. Base your analysis ONLY on the US equities listed in the brief below. NEVER invent tickers or fabricate numbers.\n"
            "2. ADAPT TO MACRO REGIME: Read the MACRO MARKET REGIME section (SPY/QQQ trend & RSI). In Pullback/Risk-Off regimes, favor Category B dips and defensive quality. In Bullish regimes, favor Category A trend leaders.\n"
            "3. BALANCED & SECTOR-DIVERSIFIED SELECTION: Pick 5 stocks across at least 3-4 distinct sectors (shown in [Sector] brackets). Avoid picking overbought names (RSI14 > 75) or falling knives unless justified by strong valuation/support.\n"
            "4. TECHNICAL STOP-LOSS PLACEMENT: Place `stop_loss` below the `20dLow` or ~1.8-2.5x `ATR14` below current price — never arbitrary round numbers or tighter than 1.5x ATR14.\n"
            "5. STRICT RISK-TO-REWARD (MINIMUM 2:1 R:R): Upside from current price to `target_price` MUST be at least 2.0x the downside to `stop_loss`. Ground `target_price` in `52wHigh`, `AnalystTarget`, and trend momentum.\n"
            "6. Assets marked with ⚡ ACTIVE BOT SIGNAL have confirmed algorithmic momentum — prioritize them when their technicals & R:R align.\n"
            "7. Calculate `expected_growth_pct` (number) accurately from current price to `target_price`, and provide a realistic `estimated_timeframe` (e.g., '3-6 Months').\n"
        )
        if is_speculative:
            system_instruction += (
                "8. **AGGRESSIVE/SPECULATION OVERRIDE**: Favor high-beta momentum/breakout equities with larger projected upside (25-60%+) and shorter timeframes ('1-3 Months'), while still honoring >= 2:1 R:R.\n"
            )
        elif is_income:
            system_instruction += (
                "8. **INCOME/CONSERVATIVE OVERRIDE**: Prioritize Category C defensive & dividend-paying leaders (strong Div %, lower ATR14 %, reasonable FwdP/E) with steady 3-12 Month total-return targets.\n"
            )

        system_instruction += (
            "\nReturn a JSON object with exactly this structure (no markdown, no extra text):\n"
            "{\n"
            '  "stocks": [\n'
            "    {\n"
            '      "symbol": "AAPL",\n'
            '      "name": "Apple Inc.",\n'
            '      "type": "stock",\n'
            '      "rationale": "1-2 sentence quant rationale citing actual Trend, RSI14, Sector, valuation/dividend, or AnalystTarget numbers.",\n'
            '      "is_active_signal": true,\n'
            '      "conviction": "high",\n'
            '      "metrics_summary": "Price: $198 | RSI: 54 | Strong Uptrend | ATR: 1.8% | 8% off 52w high",\n'
            '      "target_price": "$224.00",\n'
            '      "stop_loss": "$185.00",\n'
            '      "expected_growth_pct": 13.1,\n'
            '      "estimated_timeframe": "3-6 Months"\n'
            "    }\n"
            "  ],\n"
            '  "crypto": []\n'
            "}\n\n"
            "Select exactly 5 US equities in `stocks` and keep `crypto` as an empty list `[]`. "
            "Set conviction to 'high' if the asset has an active signal OR strong trend + favorable R:R + analyst support, otherwise 'medium'.\n\n"
            "--- MARKET DATA RESEARCH BRIEF ---\n\n"
            f"{research_brief}"
        )

        try:
            raw_json_str = call_gemini(
                "Analyze the US equities quantitative brief and select the top 5 sector-diversified US stocks/ETFs.",
                system_instruction=system_instruction,
                json_mode=True,
                custom_url=os.getenv("PORTFOLIO_AI_URL") or GEMINI_PRO_URL
            )
            clean_json_str = raw_json_str.strip().replace("```json", "").replace("```", "")
            recommendations = json.loads(clean_json_str)

            raw_stock_recs = recommendations.get("stocks", [])
            validated_stock_recs = []

            # Hard Python post-validation: verify real symbols, ATR-aware stop-loss, >= 2:1 R:R, and exact math
            max_sl_pct = 0.25 if is_speculative else 0.18
            max_tp_pct = 1.00 if is_speculative else 0.60

            for rec in raw_stock_recs:
                sym = str(rec.get("symbol", "")).strip().upper()
                if not sym or sym in BENCHMARK_SYMBOLS:
                    continue
                # Reject hallucinated tickers not present in our market brief
                if valid_candidate_syms and sym not in valid_candidate_syms:
                    continue

                cand_metrics = stock_lookup.get(sym, {})
                entry_price = float(cand_metrics.get("price") or 0.0)
                if entry_price <= 0.0:
                    try:
                        entry_price = float(yf.Ticker(sym).fast_info.get("lastPrice", 0.0))
                    except Exception:
                        entry_price = 0.0
                if entry_price <= 0.0:
                    continue

                atr_14 = float(cand_metrics.get("atr_14") or (entry_price * 0.025))
                swing_low_20d = float(cand_metrics.get("swing_low_20d") or (entry_price * 0.92))

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

                # 1. Validate / clamp stop_loss (must be below entry, at least 1.5x ATR or 4% away, at most max_sl_pct away)
                min_sl_dist = max(entry_price * 0.04, atr_14 * 1.5)
                max_sl_dist = entry_price * max_sl_pct
                if stop_loss <= 0 or stop_loss >= entry_price:
                    stop_loss = min(swing_low_20d * 0.99, entry_price - (2.0 * atr_14))
                sl_dist = entry_price - stop_loss
                if sl_dist < min_sl_dist:
                    stop_loss = entry_price - min_sl_dist
                elif sl_dist > max_sl_dist:
                    stop_loss = entry_price - max_sl_dist
                stop_loss = round(max(0.01, stop_loss), 2)

                # 2. Validate / enforce minimum 2.0:1 Reward-to-Risk ratio & realistic ceiling
                risk_per_share = entry_price - stop_loss
                min_target = entry_price + (2.0 * risk_per_share)
                max_target = entry_price * (1.0 + max_tp_pct)
                if target_price <= entry_price or target_price < min_target:
                    target_price = min(min_target, max_target)
                elif target_price > max_target:
                    target_price = max_target
                target_price = round(target_price, 2)

                # 3. Recompute exact expected_growth_pct mathematically
                expected_growth_pct = round(((target_price - entry_price) / entry_price) * 100.0, 1)

                rec["symbol"] = sym
                rec["type"] = "stock"
                rec["entry_price"] = round(entry_price, 2)
                rec["target_price"] = f"${target_price:.2f}"
                rec["stop_loss"] = f"${stop_loss:.2f}"
                rec["expected_growth_pct"] = expected_growth_pct
                rec["_validated_entry"] = round(entry_price, 2)
                rec["_validated_target"] = target_price
                rec["_validated_sl"] = stop_loss
                validated_stock_recs.append(rec)

            recommendations = {
                "stocks": [
                    {k: v for k, v in r.items() if not k.startswith("_")}
                    for r in validated_stock_recs
                ],
                "crypto": []
            }

            # Store validated recommendations in cache
            cache_payload = {
                "timestamp": time.time(),
                "recommendations": recommendations
            }
            update_config(cache_key, json.dumps(cache_payload))

            # Record validated recommendations to AIRecommendations table
            with db_session() as conn:
                c = conn.cursor()
                now_ts = int(time.time())

                for rec in validated_stock_recs:
                    sym = rec["symbol"]
                    cat = "stock"
                    entry_price = rec["_validated_entry"]
                    target_price = rec["_validated_target"]
                    stop_loss = rec["_validated_sl"]

                    # Check if there is an active recommendation for this combination already
                    c.execute('''
                        SELECT id FROM AIRecommendations
                        WHERE symbol = ? AND risk_profile = ? AND investment_goal = ? AND status = 'active'
                    ''', (sym, risk_profile, investment_goal))
                    existing = c.fetchone()

                    if not existing:
                        rec_name = rec.get('name', sym)
                        expected_growth_pct = rec.get('expected_growth_pct', 0)
                        estimated_timeframe = rec.get('estimated_timeframe', '')
                        rationale = rec.get('rationale', '')
                        metrics_summary = rec.get('metrics_summary', '')

                        c.execute('''
                            INSERT INTO AIRecommendations
                            (symbol, name, category, risk_profile, investment_goal, entry_price, current_price, target_price, stop_loss, expected_growth_pct, estimated_timeframe, rationale, metrics_summary, status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                        ''', (sym, rec_name, cat, risk_profile, investment_goal, entry_price, entry_price, target_price, stop_loss, expected_growth_pct, estimated_timeframe, rationale, metrics_summary, now_ts))
                conn.commit()

            # Build markdown for the Detailed Implementation Plan
            buys_md = "\n\n### 💡 Fresh US Equities Investment Ideas\n\n"
            for rec in recommendations["stocks"]:
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

            return {"recommendations": recommendations, "status_code": 200}
        except Exception as e:
            return {"error": f"Failed to generate recommendations: {str(e)}", "status_code": 500}
    finally:
        lock.release()

@portfolio_bp.route('/api/portfolio/good-buys', methods=['POST'])
@require_auth
@require_premium
def good_buys():
    user_id = g.user["id"]
    data = request.json or {}
    risk_profile = data.get("risk_profile") or g.user.get("risk_profile") or "Moderate"
    investment_goal = data.get("investment_goal") or g.user.get("investment_goal") or "Growth"
    force_regenerate = data.get("force_regenerate", False)

    result = generate_and_cache_recommendations(
        user_id=user_id,
        risk_profile=risk_profile,
        investment_goal=investment_goal,
        force_regenerate=force_regenerate,
        is_admin=is_user_admin(g.user)
    )
    
    status_code = result.pop("status_code", 200)
    return jsonify(result), status_code


# --- 📰 Holdings News & Sentiment (Alpaca News primary + Yahoo Finance fallback) ---

def _get_portfolio_news_data(user_id, override_positions=None):
    """Fetch and cache news + sentiment for a user's holdings."""
    now = time.time()

    if user_id in _NEWS_CACHE:
        cached_news, ts = _NEWS_CACHE[user_id]
        if (now - ts < _NEWS_CACHE_DURATION) and cached_news.get("news"):
            return cached_news

    positions = override_positions
    if not positions:
        with db_session() as conn:
            c = conn.cursor()
            c.execute('SELECT symbol, category FROM PortfolioPositions WHERE user_id = ? LIMIT 8', (user_id,))
            rows = c.fetchall()
            positions = [{"symbol": database.decrypt(r[0]), "category": r[1]} for r in rows]

    if not positions:
        positions = [{"symbol": "SPY", "category": "stock"}, {"symbol": "AAPL", "category": "stock"}]

    news_items = []
    seen_titles = set()

    # 1. Primary: Alpaca News API (single fast batch request for stock holdings)
    stock_syms = list(dict.fromkeys(
        p["symbol"].strip().upper()
        for p in positions
        if (p.get("category") or "stock").lower() == "stock" and p.get("symbol")
    ))[:8]

    if stock_syms:
        try:
            api_key = utils_gcp.get_secret("ALPACA_API_KEY")
            api_secret = utils_gcp.get_secret("ALPACA_API_SECRET")
            if api_key and api_secret:
                res = requests.get(
                    "https://data.alpaca.markets/v1beta1/news",
                    headers={
                        "APCA-API-KEY-ID": api_key,
                        "APCA-API-SECRET-KEY": api_secret,
                    },
                    params={
                        "symbols": ",".join(stock_syms),
                        "limit": 8,
                        "sort": "desc",
                    },
                    timeout=6,
                )
                if res.status_code == 200:
                    for art in res.json().get("news", []):
                        title = (art.get("headline") or "").strip()
                        link = art.get("url")
                        if not title or not link or title in seen_titles:
                            continue
                        seen_titles.add(title)
                        art_syms = [s for s in (art.get("symbols") or []) if s in stock_syms]
                        matched_sym = art_syms[0] if art_syms else stock_syms[0]
                        summary = (art.get("summary") or "").strip()
                        news_items.append({
                            "symbol": matched_sym,
                            "title": title,
                            "summary": summary[:200] + "..." if len(summary) > 200 else summary,
                            "pubDate": art.get("created_at") or art.get("updated_at"),
                            "provider": art.get("source") or "Alpaca News",
                            "link": link,
                        })
        except Exception as e:
            print(f"[Portfolio News] Alpaca news fetch error: {e}")

    # 2. Fallback: Yahoo Finance news (safe nested dict access + timeout cap)
    if len(news_items) < 4:
        def fetch_news_for_position(p):
            sym = p["symbol"]
            cat = (p.get("category") or "stock").lower()
            yf_symbol = f"{sym}-USD" if cat == 'crypto' else sym
            items = []
            try:
                ticker = yf.Ticker(yf_symbol)
                ticker_news = ticker.news or []
                count = 0
                for item in ticker_news:
                    if count >= 2:
                        break
                    content = item.get("content") or {}
                    title = content.get("title") or item.get("title")
                    summary = content.get("summary") or content.get("description") or ""
                    click_url = (content.get("clickThroughUrl") or {}).get("url")
                    canon_url = (content.get("canonicalUrl") or {}).get("url")
                    link = click_url or canon_url or item.get("link")
                    pub_date = content.get("pubDate") or item.get("providerPublishTime")
                    provider = (content.get("provider") or {}).get("displayName") or item.get("publisher") or "Yahoo Finance"

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

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
        try:
            futures = [executor.submit(fetch_news_for_position, p) for p in positions[:5]]
            done, _ = concurrent.futures.wait(futures, timeout=6)
            for fut in done:
                try:
                    for item in fut.result(timeout=0):
                        if item["title"] not in seen_titles:
                            seen_titles.add(item["title"])
                            news_items.append(item)
                except Exception:
                    pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    news_items = news_items[:6]

    bullish_keywords = ['soar', 'surge', 'jump', 'gain', 'buy', 'up', 'high', 'growth', 'positive', 'bull', 'rally', 'beat', 'outperform', 'strong', 'upgrade', 'record']
    bearish_keywords = ['plunge', 'drop', 'fall', 'lose', 'sell', 'down', 'low', 'decline', 'negative', 'bear', 'crash', 'miss', 'underperform', 'weak', 'downgrade', 'cut']

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

    payload = {
        "news": news_items,
        "counts": {
            "bullish": bullish_count,
            "bearish": bearish_count,
            "neutral": neutral_count
        }
    }

    if news_items:
        _NEWS_CACHE[user_id] = (payload, now)

    return payload


@portfolio_bp.route('/api/portfolio/news', methods=['GET'])
@require_auth
@require_premium
def get_portfolio_news():
    user_id = g.user["id"]
    payload = _get_portfolio_news_data(user_id)
    return jsonify(payload), 200


LAST_RECOMMENDATIONS_UPDATE_TIME = 0

def is_us_market_open():
    try:
        import pytz
        tz_et = pytz.timezone('US/Eastern')
        now = datetime.now(tz_et)
        if now.weekday() >= 5:
            return False
        market_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_end = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return market_start <= now <= market_end
    except Exception:
        return True

@portfolio_bp.route('/api/portfolio/recommendations', methods=['GET'])
@require_auth
@require_premium
def get_tracked_recommendations():

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


@portfolio_bp.route('/api/portfolio/recommendations/<int:rec_id>', methods=['DELETE'])
@require_auth
@require_premium
def delete_recommendation(rec_id):
    if not is_user_admin(g.user):
        return jsonify({"error": "Admin permission required"}), 403

    with db_session() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM AIRecommendations WHERE id = ?", (rec_id,))
        conn.commit()

    return jsonify({"success": True, "message": "Recommendation deleted successfully"}), 200

