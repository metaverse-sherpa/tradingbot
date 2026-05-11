# Trading Bot: Multi-Symbol BB Scalper 📈

A production-ready, multi-symbol mean-reversion trading bot for the Blofin exchange. This bot utilizes Bollinger Band scalping, trend filters (EMA 200), and volatility protection (ADX/RSI) to execute high-precision trades automatically via GitHub Actions and Google Cloud Scheduler.

## 🚀 Features

*   **Multi-Symbol Support**: Currently trading 20 high-liquidity assets (BTC, ETH, SOL, PEPE, etc.).
*   **Mean Reversion Strategy**: Buys the "dip" when price crosses the lower Bollinger Band during an uptrend.
*   **Precision Execution**: Triggered every 5 minutes with marketable limit orders to bypass exchange size limits.
*   **Safety First**:
    *   **Isolated Margin**: 20x leverage strictly isolated to each trade.
    *   **Slippage Protection**: Cancels trades if the price moves more than 1% from the signal entry.
    *   **Dynamic Risk/Reward**: Automatically calculates a 1.25:1 TP/SL ratio based on live price action.
*   **Automated Tracking**: Real-time Win Rate, PnL %, and trade counts updated automatically in this README.
*   **Instant Alerts**: Sends trade execution summaries and error reports via GitHub Issues (email notifications).

## 🛠️ Strategy Mechanics

1.  **Trend Filter**: Only opens LONG positions if the price is above the 200-period EMA.
2.  **Volatility Filter**: Uses ADX to skip "choppy" or hyper-trending markets.
3.  **Momentum Filter**: RSI oversold/overbought checks.
4.  **Session Filter**: Skips low-liquidity UTC hours (04:00 and 12:00) to reduce "fakeouts."

## 📂 Project Structure

*   `live_bot_multi.py`: **The Brain.** Refactored for efficient one-shot execution.
*   `.github/workflows/trade.yml`: **The Scheduler.** Tells GitHub to run the brain every 15 minutes.
*   `results/live_log.txt`: **The History.** Automatically updated by the bot every run.
*   `scripts/`: Research and optimization tools for advanced users.

---

## 📈 Live Performance (All-Time)
<!-- PERFORMANCE_START -->
| Total Trades | Wins | Losses | Win Rate | Total PnL (%) |
| :--- | :--- | :--- | :--- | :--- |
| 12 | 11 | 4 | 73.3% | +4.24% |

**Last Updated:** 2026-05-11 17:25 UTC
<!-- PERFORMANCE_END -->

<!-- DATA_STORAGE_START
STARTING_EQUITY: 200.1733321
ALL_TIME_OPENED: 12
ALL_TIME_WINS: 11
ALL_TIME_LOSSES: 4
ALL_TIME_CUMULATIVE_PNL: 8.477543328
LAST_FETCH_TIMESTAMP: 1778520342424
DATA_STORAGE_END -->

## ⚠️ Disclaimer
Trading cryptocurrency involves significant risk. This bot is provided for educational purposes. Always start with **Dry Run** mode to verify behavior before committing real capital.
