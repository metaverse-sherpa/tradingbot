# 🧪 Research, Auditing & Optimization Scripts

This directory contains research, validation, testing, and optimization scripts used to build and verify the trading bot's strategies. They are not required for live execution of the production bot, but are essential for future strategy research, database management, exchange integration audits, and statistical optimization sweeps.

---

## 📈 Backtesting & Simulation Tools

*   **`backtest_optimized.py`**: The final multi-symbol portfolio simulator. It runs the full 20-symbol basket across a 3-year historical window using the exact execution logic of the live bot.
*   **`analyze_losses.py`**: A diagnostic tool. It breaks down trades by time of day, direction, and ADX level to isolate bad trading regimes.
*   **`stock_backtest.py` / `stock_backtest_blofin.py`**: Simulators for testing stock-based Bollinger Band and pullback strategies on custom intervals and data sources.
*   **`backtest.py` / `backtest_multi.py` / `backtest_h1_elite.py` / `backtest_portfolio.py` / `backtest_research.py` / `backtest_vwap.py`**: Modular backtesters evaluating different timeframe and indicator setups.

---

## 🦙 Stock & Equity Strategy Audits

These scripts run focused historical checks to test specific risk and performance characteristics of the *Sherpa Velocity Pullback (SVP)* daily stock strategy:
*   **`stock_durability_audit.py`**: Checks model performance during sustained down-markets and regimes.
*   **`stock_harvest_audit.py`**: Simulates trailing take-profits and aggressive capital harvesting.
*   **`stock_precision_audit.py`**: Measures trade-entry quality and win-rate ratios.
*   **`stock_safe_audit.py`**: Analyzes maximum drawdown risks and optimal leverage.

---

## 🛠️ Parameter Sweep & Optimization

*   **`optimize_symbols.py`**: The "Sweep" tool. It tests 216 different combinations of BB deviation, ATR multiplier, and ADX filters for every symbol to find the highest-quality settings.
*   **`optimize_new_symbols.py`**: A streamlined version of the sweep tool used specifically to onboard new high-volume candidates.
*   **`optimize_frequency.py`**: Evaluates different strategy candle granularities (e.g. 5m, 15m, 1h).
*   **`optimize_valkyrie.py`**: Sweeps thresholds specifically for the Valkyrie Elite Scalper strategy.
*   **`find_high_volume.py`**: Identifies the most liquid cryptocurrency trading pairs in the last 24 hours.

---

## 📦 Data Caching & Fetching

*   **`data_fetcher.py` / `fetch_all_data.py` / `blofin_deep_fetcher.py`**: Downloads and caches massive batches of 15m historical candles from exchange APIs for backtesting.
*   **`blofin_data_cacher.py`**: Caches real-time orderbook and ticket metadata from the Blofin API.
*   **`stock_data_cache.py`**: Downloads and caches intraday (15-minute) stock bar data from the Tiingo API.

---

## 🔒 Verification & Exchange Diagnostics

*   **`verify_exchange_logic.py`**: Verifies exact execution features (like order limits, size rules, and balance calls) across various CCXT-integrated exchanges.
*   **`blofin_live_test.py` / `blofin_variance_check.py` / `sherpa_blofin_audit.py`**: Tests live connectivity, orders, and historical calculations specifically for Blofin integrations.
*   **`win_rate_audit.py` / `mirror_audit.py`**: Verifies consistency between live-traded statistics and historical expected rates.
*   **`test_db_migration.py`**: Validates SQL schema upgrades and database table integrity checks.
*   **`diagnostic.py`**: Checks system dependencies, fonts, and local environment variables.

---

## 🎭 Simulation & Visual Helpers

*   **`trigger_simulated_alert.py` / `trigger_simulated_stock_alert.py`**: Generates and pushes mocked trades/alerts into the Telegram UI loop for design verification.
*   **`generate_stock_infographic.py` / `refresh_bot_visuals.py` / `sherpa_visual_audit.py`**: Pre-renders professional performance charts, comparison infographics, and theme palettes used directly by the UI.

---

## 🚦 Recommended Development Workflow

1.  **Regime Sweeping**: Run `optimize_symbols.py` every 3-6 months to verify if current Bollinger Band deviations are aligned with market volatility.
2.  **Asset Selection**: Before enabling a new coin on the VPS, run `optimize_new_symbols.py` to ensure it offers a statistical edge.
3.  **Exchange Onboarding**: Run `verify_exchange_logic.py` before deploying a new broker or exchange interface live.
