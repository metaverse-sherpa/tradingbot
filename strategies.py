import pandas as pd
import numpy as np

class BaseStrategy:
    name = "Base"
    description = "Base strategy class"
    
    def check_signal(self, df):
        """Returns 'LONG', 'SHORT', or None"""
        return None

class MeanReversionScalper(BaseStrategy):
    name = "Mean Reversion Scalper"
    description = "Bollinger Band dips + EMA 200 + Volume Momentum Confirmation."
    
    def check_signal(self, df, config=None):
        """
        config: dict containing 'bb', 'rsi', 'adx', etc.
        """
        # Default config if none provided (Institutional Standard)
        cfg = config if config else {"bb": 2.7, "rsi": 30, "adx": 25, "rvol": 1.5}
        
        # 1. EMA 200 Trend Filter
        ema_200 = df['close'].ewm(span=200, adjust=False).mean()
        current_price = df['close'].iloc[-1]
        is_uptrend = current_price > ema_200.iloc[-1]
        is_downtrend = current_price < ema_200.iloc[-1]
        
        # 2. Bollinger Bands (Dynamic Dev)
        sma_20 = df['close'].rolling(window=20).mean()
        std_20 = df['close'].rolling(window=20).std()
        dev = cfg.get('bb', 2.7)
        lower_band = sma_20.iloc[-1] - (dev * std_20.iloc[-1])
        upper_band = sma_20.iloc[-1] + (dev * std_20.iloc[-1])
        
        # 3. RSI Filter
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        # 4. 🚀 VOLUME MOMENTUM (RVOL) - The Anti-Wick Filter
        avg_vol = df['volume'].rolling(window=20).mean().iloc[-1]
        current_vol = df['volume'].iloc[-1]
        rvol_threshold = cfg.get('rvol', 1.5)
        has_real_volume = current_vol > (avg_vol * rvol_threshold)
        
        # 5. ADX Filter (Trend Strength)
        hi, lo, cl = df['high'], df['low'], df['close']
        pdm = hi.diff().clip(lower=0); ndm = (-lo.diff()).clip(lower=0)
        pdm = pdm.where(pdm > ndm, 0.0); ndm = ndm.where(ndm > pdm, 0.0)
        # ATR for ADX
        tr = pd.concat([hi-lo, (hi-cl.shift()).abs(), (lo-cl.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()
        pdi = 100 * pdm.rolling(14).mean() / atr
        ndi = 100 * ndm.rolling(14).mean() / atr
        dx = (abs(pdi - ndi) / (pdi + ndi).replace(0, np.nan)) * 100
        adx = dx.rolling(14).mean().iloc[-1]
        is_strong_trend = adx > cfg.get('adx', 25)

        # Signal Logic
        # LONG: Uptrend + BB Dip + Oversold + Volume Spike + Strong Trend
        if is_uptrend and current_price < lower_band and current_rsi < cfg.get('rsi', 30) and has_real_volume and is_strong_trend:
            return "LONG"
            
        # SHORT: Downtrend + BB Peak + Overbought + Volume Spike + Strong Trend
        if is_downtrend and current_price > upper_band and current_rsi > (100 - cfg.get('rsi', 30)) and has_real_volume and is_strong_trend:
            return "SHORT"
        
        return None

class CryptoChartPatterns(BaseStrategy):
    name = "Crypto Chart Patterns"
    description = "Queries an external API for technical pattern breakouts. (Coming Soon)"
    
    def check_signal(self, df):
        return None

# Strategy Registry
STRATEGIES = {
    "Mean Reversion Scalper": MeanReversionScalper(),
    "Crypto Chart Patterns": CryptoChartPatterns()
}

def get_strategy(name):
    return STRATEGIES.get(name, STRATEGIES["Mean Reversion Scalper"])
