#!/usr/bin/env python3
"""
BTC/USDT 15m Bollinger Band Scalper — Live Execution Bot
Connects to Blofin via CCXT. Supports demo and production modes.
"""

import os
import time
import logging
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

SYMBOL = "BTC/USDT:USDT"           # Blofin perp symbol
TIMEFRAME = "15m"
LEVERAGE = 20

# Strategy parameters — optimised via 288-combo sweep (BB=2.5, ATR=6.0, RR=1.25, ADX>20, Risk=3%)
EMA_TREND_PERIOD = 200
BB_PERIOD = 20
BB_DEVFACTOR = 2.5
RSI_PERIOD = 14
RSI_LOWER = 30
RSI_UPPER = 70
ATR_PERIOD = 14
ATR_MULTIPLIER = 6.0   # wider stops = fewer premature SL hits
RR_RATIO = 1.25        # 1.25:1 reward-to-risk consistently outperforms 1:1
ADX_PERIOD = 14
ADX_THRESHOLD = 20     # only trade in trending markets (ADX > 20)
RISK_PER_TRADE = 0.03  # 3% of equity risked per trade

POLL_SECONDS = 60  # check every 60 s (plenty fast for 15 m candles)
DRY_RUN = os.getenv("BLOFIN_DRY_RUN", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("live_bot")

# ---------------------------------------------------------------------------
# Exchange initialisation
# ---------------------------------------------------------------------------

def create_exchange() -> ccxt.blofin:
    """Create and configure the Blofin exchange instance."""
    api_key = os.getenv("BLOFIN_API_KEY")
    api_secret = os.getenv("BLOFIN_API_SECRET")
    api_password = os.getenv("BLOFIN_API_PASSWORD")
    demo_mode = os.getenv("BLOFIN_DEMO_MODE", "false").lower() == "true"

    if not api_key or not api_secret:
        raise RuntimeError("BLOFIN_API_KEY and BLOFIN_API_SECRET must be set in .env")

    exchange = ccxt.blofin({
        "apiKey": api_key,
        "secret": api_secret,
        "password": api_password,
        "enableRateLimit": True,
    })

    if demo_mode:
        exchange.set_sandbox_mode(True)
        log.info("🧪 DEMO MODE — using %s", exchange.urls["api"]["rest"])
    else:
        log.info("🔴 PRODUCTION MODE — using %s", exchange.urls["api"]["rest"])

    if DRY_RUN:
        log.info("🛡️  DRY RUN enabled — signals will be logged but NO orders placed")

    return exchange

# ---------------------------------------------------------------------------
# Indicator calculations (pure pandas / numpy)
# ---------------------------------------------------------------------------

def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength, not direction."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr = calc_atr(df, period)
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.ewm(span=period, adjust=False).mean()


def calc_bollinger(series: pd.Series, period: int, dev: float):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    return mid, mid + dev * std, mid - dev * std  # mid, top, bot

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_candles(exchange: ccxt.blofin, limit: int = 300) -> pd.DataFrame:
    """Fetch the most recent OHLCV candles and return a DataFrame."""
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("datetime", inplace=True)
    return df

# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

def compute_signals(df: pd.DataFrame) -> dict | None:
    """
    Return a signal dict {'side': 'buy'|'sell', 'sl': float, 'tp': float}
    or None if no setup.
    """
    df = df.copy()
    df["ema_trend"] = calc_ema(df["close"], EMA_TREND_PERIOD)
    df["rsi"] = calc_rsi(df["close"], RSI_PERIOD)
    df["atr"] = calc_atr(df, ATR_PERIOD)
    df["adx"] = calc_adx(df, ADX_PERIOD)
    df["bb_mid"], df["bb_top"], df["bb_bot"] = calc_bollinger(df["close"], BB_PERIOD, BB_DEVFACTOR)

    # Use the last *closed* bar (index -2) to avoid acting on an incomplete candle
    last = df.iloc[-2]

    if pd.isna(last["ema_trend"]) or pd.isna(last["rsi"]) or pd.isna(last["atr"]) or pd.isna(last["adx"]):
        return None

    # ADX filter: skip choppy, directionless markets
    if last["adx"] < ADX_THRESHOLD:
        log.debug("ADX %.1f < %d — no trade (choppy market)", last["adx"], ADX_THRESHOLD)
        return None

    sl_dist = last["atr"] * ATR_MULTIPLIER

    # LONG
    if (last["close"] > last["ema_trend"]
            and last["close"] < last["bb_bot"]
            and last["rsi"] < RSI_LOWER):
        return {
            "side": "buy",
            "entry": last["close"],
            "sl": last["close"] - sl_dist,
            "tp": last["close"] + sl_dist * RR_RATIO,
            "sl_dist": sl_dist,
        }

    # SHORT
    if (last["close"] < last["ema_trend"]
            and last["close"] > last["bb_top"]
            and last["rsi"] > RSI_UPPER):
        return {
            "side": "sell",
            "entry": last["close"],
            "sl": last["close"] + sl_dist,
            "tp": last["close"] - sl_dist * RR_RATIO,
            "sl_dist": sl_dist,
        }

    return None

# ---------------------------------------------------------------------------
# Order execution helpers
# ---------------------------------------------------------------------------

def get_equity(exchange: ccxt.blofin) -> float:
    """Return total USDT equity from the futures account."""
    balance = exchange.fetch_balance(params={"type": "futures"})
    usdt = balance.get("USDT", {})
    return float(usdt.get("total", 0))


def get_open_position(exchange: ccxt.blofin) -> dict | None:
    """Return the current BTC-USDT position or None."""
    positions = exchange.fetch_positions([SYMBOL])
    for pos in positions:
        size = float(pos.get("contracts", 0) or 0)
        if size != 0:
            return pos
    return None


def set_leverage(exchange: ccxt.blofin):
    """Set leverage for BTC-USDT to the configured value."""
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL, params={"marginMode": "cross"})
        log.info("Leverage set to %sx for %s", LEVERAGE, SYMBOL)
    except Exception as e:
        log.warning("Could not set leverage (may already be set): %s", e)


def place_entry_with_tpsl(exchange: ccxt.blofin, signal: dict, equity: float):
    """Place a market entry order with TP/SL attached."""
    side = signal["side"]
    sl_dist = signal["sl_dist"]

    # Position sizing: risk amount / SL distance = notional size in BTC
    risk_amount = equity * RISK_PER_TRADE
    size_btc = risk_amount / sl_dist

    # Clamp to max leverage
    max_size = (equity * LEVERAGE) / signal["entry"]
    size_btc = min(size_btc, max_size)

    # Round to Blofin's contract precision (0.01 for BTC-USDT perp)
    size_btc = round(size_btc, 2)
    if size_btc <= 0:
        log.warning("Calculated size is 0 — skipping trade.")
        return

    log.info(
        "📈 %s %s signal | Size: %.4f BTC | Entry ~%.2f | SL: %.2f | TP: %.2f",
        "[DRY RUN]" if DRY_RUN else "Placing",
        side.upper(), size_btc, signal["entry"], signal["sl"], signal["tp"],
    )

    if DRY_RUN:
        log.info("🛡️  DRY RUN — order NOT sent to exchange.")
        return

    try:
        # Place market order with TP/SL params
        params = {
            "marginMode": "cross",
            "positionSide": "net",
            "takeProfitPrice": signal["tp"],
            "stopLossPrice": signal["sl"],
        }

        order = exchange.create_order(
            symbol=SYMBOL,
            type="market",
            side=side,
            amount=size_btc,
            params=params,
        )
        log.info("✅ Order placed: %s", order.get("id", order))

    except Exception as e:
        log.error("❌ Order failed: %s", e)

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run():
    exchange = create_exchange()
    set_leverage(exchange)

    log.info("Bot started. Polling every %ds for %s on %s timeframe.", POLL_SECONDS, SYMBOL, TIMEFRAME)

    while True:
        try:
            # 1. Check for existing position
            position = get_open_position(exchange)
            if position:
                side = position.get("side", "unknown")
                size = position.get("contracts", "?")
                pnl = position.get("unrealizedPnl", "?")
                log.info("🔒 Open position: %s %.4s contracts | uPnL: %s", side, size, pnl)
                time.sleep(POLL_SECONDS)
                continue

            # 2. Fetch candles & compute signals
            df = fetch_candles(exchange)
            signal = compute_signals(df)

            if signal is None:
                log.info("— No setup detected. Waiting…")
                time.sleep(POLL_SECONDS)
                continue

            # 3. Get equity and execute
            equity = get_equity(exchange)
            if equity <= 0:
                log.warning("Equity is %.2f — cannot trade.", equity)
                time.sleep(POLL_SECONDS)
                continue

            log.info("💰 Account equity: $%.2f", equity)
            place_entry_with_tpsl(exchange, signal, equity)

        except ccxt.NetworkError as e:
            log.warning("Network error: %s — retrying in %ds", e, POLL_SECONDS)
        except ccxt.ExchangeError as e:
            log.error("Exchange error: %s", e)
        except KeyboardInterrupt:
            log.info("Bot stopped by user.")
            break
        except Exception as e:
            log.exception("Unexpected error: %s", e)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run()
