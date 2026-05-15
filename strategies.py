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
    description = "Bollinger Band dips + EMA 200 trend filter."
    
    def check_signal(self, df):
        # 1. EMA 200 Trend Filter (Manual calculation)
        ema_200 = df['close'].ewm(span=200, adjust=False).mean()
        current_price = df['close'].iloc[-1]
        
        is_uptrend = current_price > ema_200.iloc[-1]
        
        # 2. Bollinger Bands (Manual calculation)
        sma_20 = df['close'].rolling(window=20).mean()
        std_20 = df['close'].rolling(window=20).std()
        
        lower_band = sma_20.iloc[-1] - (2 * std_20.iloc[-1])
        upper_band = sma_20.iloc[-1] + (2 * std_20.iloc[-1])
        
        # 3. RSI Filter (Manual calculation)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        # Signal: Price crosses lower band in uptrend + RSI oversold (< 30)
        if is_uptrend and current_price < lower_band and current_rsi < 30:
            return "LONG"
        
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
