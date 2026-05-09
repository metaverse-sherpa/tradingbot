# 📈 Multi-Symbol BB Scalper

A robust, multi-symbol Bollinger Band mean-reversion trading bot designed for **Blofin Perpetual Futures**. This bot is optimized to run **24/7 for free** using GitHub Actions.

---

## 🚀 How to set up your own bot

If you've found this repository and want to run this bot for yourself, follow these steps to get your own automated version running in less than 5 minutes.

### 1. Fork this Repository
Click the **"Fork"** button at the top right of this page. This creates your own personal copy of the code that you can control.

### 2. Enable GitHub Actions
By default, GitHub disables automation on forked projects for safety.
1.  In **your** new repository, click the **Actions** tab at the top.
2.  Click the large green button that says **"I understand my workflows, go ahead and enable them"**.

### 3. Add your Blofin Secrets
To allow the bot to trade securely, you must add your Blofin API credentials as **GitHub Secrets**:
1.  Go to **Settings** > **Secrets and variables** > **Actions**.
2.  Click **New repository secret** and add these three:
    *   `BLOFIN_API_KEY`: Your Blofin API Key.
    *   `BLOFIN_API_SECRET`: Your Blofin API Secret.
    *   `BLOFIN_API_PASSWORD`: Your Blofin API Passphrase.

### 5. Precision Scheduling (Optional - Recommended)
GitHub's built-in scheduler can be delayed by 10-60 minutes. For professional-grade 5-minute precision, use **Google Cloud Scheduler** to "ping" the bot:

1.  **Create a GitHub PAT**: Go to **Developer Settings** > **Tokens (classic)** and create a token with `repo` and `workflow` scopes.
2.  **Google Cloud Scheduler**: Create a new job:
    *   **Frequency**: `*/5 * * * *`
    *   **Target**: `HTTP`
    *   **URL**: `https://api.github.com/repos/YOUR_USERNAME/YOUR_REPO/dispatches`
    *   **Method**: `POST`
    *   **Headers**:
        *   `Accept`: `application/vnd.github+json`
        *   `Authorization`: `Bearer YOUR_GITHUB_PAT`
        *   `User-Agent`: `Google-Cloud-Scheduler`
    *   **Body**: `{ "event_type": "trigger-bot" }`

### 6. Verify & Monitor
1.  Once the bot runs (automatically or via Google Cloud), any trades found will appear in the **Issues** tab.
2.  Detailed logs are stored in your local `results/live_log.txt` (if running locally).

### 5. Going Live
The bot starts in **Dry Run** mode (no real orders) by default. To start trading real money:
1.  Open `.github/workflows/trade.yml` in your browser.
2.  Click the **Pencil icon** to edit.
3.  Change `BLOFIN_DRY_RUN: 'true'` to `BLOFIN_DRY_RUN: 'false'`.
4.  Click **Commit changes**.

---

## 🏦 Exchange Compatibility

### Designed for Blofin
This bot is specifically configured for **Blofin** because of its high leverage limits and clean API for perpetual futures. 

### Using other exchanges (Binance, Bybit, OKX, etc.)
Because this bot uses the **CCXT** library, it can be adapted for other exchanges, but you will need to make minor code adjustments in `live_bot_multi.py`:
1.  **Change the Exchange ID**: Update `ccxt.blofin()` to your exchange (e.g., `ccxt.binance()`).
2.  **Order Parameters**: Different exchanges use different names for Take Profit and Stop Loss. Check the [CCXT Documentation](https://docs.ccxt.com/) for your specific exchange's `create_order` syntax.
3.  **Symbols**: Ensure the symbol format (e.g., `BTC/USDT:USDT`) matches your exchange's requirements.

---

## 📊 Strategy Overview

The bot monitors a **20-symbol basket** of highly liquid assets:
`BTC`, `ETH`, `SOL`, `DOGE`, `ADA`, `LINK`, `DOT`, `TON`, `ZEC`, `PEPE`, `BNB`, `NEAR`, `SUI`, `NOT`, `TAO`, `ONDO`, `ENA`, `FET`, `WIF`, `SHIB`.

It uses a 4-layer filter to ensure high-quality entries:
1.  **Trend Filter**: Only longs above the 200 EMA.
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
| 3 | 0 | 0 | 0.0% | -3.04% |

**Last Updated:** 2026-05-09 15:02 UTC
<!-- PERFORMANCE_END -->

<!-- DATA_STORAGE_START
STARTING_EQUITY: 200.1733321
ALL_TIME_OPENED: 3
ALL_TIME_WINS: 0
ALL_TIME_LOSSES: 0
DATA_STORAGE_END -->

## ⚠️ Disclaimer
Trading cryptocurrency involves significant risk. This bot is provided for educational purposes. Always start with **Dry Run** mode to verify behavior before committing real capital.
