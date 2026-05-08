# 📈 Multi-Symbol BB Scalper

A robust, multi-symbol Bollinger Band mean-reversion trading bot designed for Blofin perpetual futures. This bot is optimized to run **24/7 for free** using GitHub Actions.

## 🚀 GitHub Actions Deployment

This bot is configured to run every **15 minutes** automatically.

### 1. Setup GitHub Secrets
To allow the bot to trade securely, you must add your Blofin API credentials as **GitHub Secrets** (do NOT put them in the code):
1.  Go to your GitHub Repository > **Settings**.
2.  In the left sidebar, click **Secrets and variables** > **Actions**.
3.  Click **New repository secret** for each of the following:
    *   `BLOFIN_API_KEY`: Your Blofin API Key.
    *   `BLOFIN_API_SECRET`: Your Blofin API Secret.
    *   `BLOFIN_API_PASSWORD`: Your Blofin API Passphrase.

### 2. Verify the Workflow
1.  Click the **Actions** tab in your GitHub repository.
2.  Select **📈 Trade Bot Execution**.
3.  Click **Run workflow** to trigger a manual test.
4.  Once finished, check the **`results/live_log.txt`** file in your repo to see the activity.

### 3. Going Live
By default, the bot runs in **Dry Run** mode (no real orders). To go live:
1.  Open `.github/workflows/trade.yml`.
2.  Change `BLOFIN_DRY_RUN: 'true'` to `BLOFIN_DRY_RUN: 'false'`.
3.  Commit and push the change.

---

## 🛠️ Local Development (Optional)

If you want to run the bot or backtests locally:

1.  **Install Dependencies**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

2.  **Configure Environment**:
    Create a `.env` file in the root directory or copy/rename the .env.copy file:
    ```env
    BLOFIN_API_KEY=your_api_key
    BLOFIN_API_SECRET=your_api_secret
    BLOFIN_API_PASSWORD=your_passphrase
    BLOFIN_DRY_RUN=true
    ```

3.  **Run the Bot**:
    ```bash
    python live_bot_multi.py
    ```

## 🛠️ Configuration

*   **Production vs. Dry Run**: Set `BLOFIN_DRY_RUN=false` in `.env` to place real orders.
*   **Leverage**: Default is **20x** (configurable in `live_bot_multi.py`).
*   **Risk Management**: Default is **1% equity risk per symbol**.
*   **Symbols**: Monitors 20 high-volume assets including BTC, ETH, SOL, DOGE, PEPE, and more.

## 📊 Strategy & Optimization

The strategy uses Bollinger Band mean-reversion filtered by:
1.  **EMA-200**: Trend filter (Longs only when price > EMA).
2.  **ADX**: Volatility filter (ADX > Symbol Threshold AND ADX < 35).
3.  **RSI**: Exhaustion filter (Symbol Specific).
4.  **Session Filter**: Skips entries at 04:00 and 12:00 UTC (low-quality hours).

### Research & Backtesting
All optimization and research scripts are located in the `scripts/` directory.
*   `scripts/backtest_optimized.py`: Runs the final 20-symbol 3rd-year portfolio simulation.
*   `scripts/analyze_losses.py`: Analyzes losing trades to identify filters (how we found the ADX cap and Session block).
*   `scripts/optimize_new_symbols.py`: Tool to find optimal parameters for new assets.

**To run a backtest**:
```bash
python scripts/backtest_optimized.py
```

## 📂 Directory Structure

*   `live_bot_multi.py`: **Main Production Bot.**
*   `csv/`: Cached historical data for backtesting.
*   `results/`:
    *   `live_log.txt`: Real-time bot activity and signal logs.
    *   `optimized_results.txt`: Results from the latest portfolio backtest.
*   `scripts/`: Research, optimization, and legacy backtesting tools.

## ⚠️ Disclaimer
Trading cryptocurrency involves significant risk. This bot is provided for educational purposes. Always use `BLOFIN_DRY_RUN=true` to verify behavior before committing capital.
