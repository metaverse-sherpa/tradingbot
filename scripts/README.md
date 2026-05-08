# 🧪 Research & Optimization Scripts

These scripts were used to build and verify the trading strategy. They are not required for live trading but are essential for future development.

## 📈 Main Simulation Tools

*   **`backtest_optimized.py`**: The final portfolio simulator. It runs the full 20-symbol basket across a 3-year historical window using the exact logic found in the live bot. Use this to verify PnL and Drawdown before making strategy changes.
*   **`analyze_losses.py`**: A diagnostic tool. It breaks down trades by time of day, direction, and ADX level. This script is how we identified the "bad" trading hours (04:00/12:00 UTC) and the ADX cap (35).

## 🛠️ Parameter Optimization

*   **`optimize_symbols.py`**: The "Sweep" tool. It tests 216 different combinations of BB deviation, ATR multiplier, and ADX filters for every symbol to find the highest-quality settings.
*   **`optimize_new_symbols.py`**: A streamlined version of the sweep tool used specifically to onboard the 10 high-volume candidates (SUI, TAO, etc.).
*   **`find_high_volume.py`**: Uses the Binance API to identify the most liquid trading pairs in the last 24 hours.

## 📦 Utilities & Legacy

*   **`data_fetcher.py`**: Handles the heavy lifting of downloading and caching 3 years of 15m candles.
*   **`backtest.py` / `backtest_multi.py`**: Early-stage basic simulators used before the portfolio model was built.
*   **`strategy.py` / `strategy_ema.py`**: Modular logic files for different indicator combinations.

## 🚦 When to use these?

1.  **Every 3-6 months**: Run `optimize_symbols.py` to see if the market regime has changed and if you need to adjust your BB or ADX levels.
2.  **Before adding a new coin**: Run `optimize_new_symbols.py` on that coin to ensure it actually has a statistical edge with this strategy.
3.  **If performance dips**: Run `analyze_losses.py` on your live trade history to see if a new "bad session" or pattern has emerged.
