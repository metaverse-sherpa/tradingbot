import pandas as pd
import numpy as np

class BaseStrategy:
    name = "Base"
    description = "Base strategy class"
    
    def check_signal(self, df, symbol_name="BTC"):
        """Returns 'LONG', 'SHORT', or None"""
        return None

class MeanReversionScalper(BaseStrategy):
    name = "Mean Reversion Scalper"
    description = "Institutional BB + EMA + ADX + Wilder Smoothing."
    
    def check_signal(self, df, symbol_name="BTC"):
        # Import configs here to avoid circular imports if needed, 
        # but better to pass the specific config we need.
        # For now, we'll assume the caller passes the symbol_name 
        # and we use the global SYMBOL_CONFIGS (or we can pass the config dict)
        from live_bot_multi import SYMBOL_CONFIGS
        cfg = SYMBOL_CONFIGS.get(symbol_name, {"bb": 2.0, "atr": 4.0, "rr": 1.0, "adx": 20, "rsi": 30})
        
        close = df['close']
        
        # 1. EMA 200 (Institutional Trend Filter)
        ema_200 = close.ewm(span=200, adjust=False).mean()
        
        # 2. Bollinger Bands (Surgical Multipliers)
        sma_20 = close.rolling(window=20).mean()
        std_20 = close.rolling(window=20).std()
        lower_band = sma_20 - (cfg["bb"] * std_20)
        upper_band = sma_20 + (cfg["bb"] * std_20)
        
        # 3. RSI (Wilder Smoothing)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / (loss.replace(0, np.nan))
        rsi = 100 - (100 / (1 + rs))
        
        # 4. ADX (Trend Strength Filter)
        def calc_adx(df, p=14):
            hl = df["high"] - df["low"]
            hc = (df["high"] - df["close"].shift()).abs()
            lc = (df["low"] - df["close"].shift()).abs()
            tr = pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(alpha=1/p, adjust=False).mean()
            pdm = df["high"].diff().clip(lower=0)
            ndm = (-df["low"].diff()).clip(lower=0)
            pdm = pdm.where(pdm > ndm, 0.0)
            ndm = ndm.where(ndm > pdm, 0.0)
            pdi = 100 * pdm.ewm(alpha=1/p, adjust=False).mean() / tr
            ndi = 100 * ndm.ewm(alpha=1/p, adjust=False).mean() / tr
            dx = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
            return dx.ewm(alpha=1/p, adjust=False).mean()
        
        adx = calc_adx(df)
        
        # Current values (using iloc[-2] as per the 45-min candle confirmation protocol)
        c_p = close.iloc[-2]
        c_ema = ema_200.iloc[-2]
        c_low = lower_band.iloc[-2]
        c_high = upper_band.iloc[-2]
        c_rsi = rsi.iloc[-2]
        c_adx = adx.iloc[-2]
        
        # ADX Threshold Check
        if cfg["adx"] > 0 and c_adx < cfg["adx"]:
            return None

        # Long Signal: Uptrend + BB Dip + RSI Oversold
        if c_p > c_ema and c_p < c_low and c_rsi < cfg["rsi"]:
            return "LONG"
            
        # Short Signal: Downtrend + BB Peak + RSI Overbought
        if not cfg.get("long_only") and c_p < c_ema and c_p > c_high and c_rsi > (100 - cfg["rsi"]):
            return "SHORT"
        
        return None

# Strategy Registry
STRATEGIES = {
    "Mean Reversion Scalper": MeanReversionScalper()
}

def get_strategy(name):
    return STRATEGIES.get(name, STRATEGIES["Mean Reversion Scalper"])
