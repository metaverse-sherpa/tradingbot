# Trading Bot: Multi-Symbol BB Scalper 📈

A production-ready, multi-tenant Telegram trading bot for Blofin, Binance, MEXC, and Bitget. This bot utilizes advanced algorithmic strategies (including Bollinger Band scalping, trend filters, and volatility protection) to trade for multiple users simultaneously from a dedicated VPS.

## 🚀 Features

*   **Multi-Tenant Telegram Interface**: Users securely connect their own accounts via `/setup` or `/reset`.
*   **Multi-Exchange Support**: Fully integrated with Blofin, Binance, MEXC, and Bitget futures.
*   **Professional Dashboards**: Real-time stats, open position charts with Bollinger Clouds, and trade history.
*   **Precision Execution**: Async engine runs every 15 minutes (30s after the candle close) with marketable limit orders to bypass size limits.
*   **Safety & Privacy**: 
    *   **Military-Grade Encryption**: API keys are encrypted with Fernet symmetric encryption at rest.
    *   **Privacy Mode**: Toggle between showing dollar PnL or protected percentages (`/privacy`).
*   **Advanced Algorithmic Strategies**: Switch between multiple brains, including the *Mean Reversion Scalper* and the *Valkyrie Elite Scalper* (`/strategy`).
*   **Tactical Controls**: Manual overrides including One-Click Close and Panic Close functionality directly from Telegram.
*   **Capital Allocation**: Granular control over position sizing (trade with full balance, fixed $ amount, or % isolation) via `/settings`.
*   **Tiered Access & Referrals**: Standard (Free trade signals) and Institutional (Premium exchange autopilot) tiers. Built-in referral system to earn Premium.
*   **Automated & Forward Testing**: Real-time Win Rate, PnL %, and trade counts updated live (`/stats`), plus simulated forward test tracking (`/forwardtest`).

## 📁 Codebase Architecture & File Reference

This repository is organized into distinct components separating production operations, background engines, database state, and historical research scripts.

### 🐍 Production Root Scripts

The project root contains only active production-critical scripts that drive the Telegram interface and real-time execution engines:

*   **`telegram_bot.py`**: The main application entrypoint. Boots up the Telegram bot daemon using `python-telegram-bot`, maps command callbacks (e.g., `/setup`, `/settings`, `/stats`), manages user interactions, and schedules the async background trading loop.
*   **`live_bot_multi.py`**: The core multi-exchange execution engine for crypto futures. It acts asynchronously to fetch market feeds, calculate Bollinger Band scalp levels, trigger order submissions (marketable limits) for user tenants, and manage active position lifecycles.
*   **`live_bot_multi_alpaca.py`**: The production execution engine for equities trading via the Alpaca API. Automates the **Sherpa Velocity Pullback** strategy at the market open, manages orders, and tallies theoretical trade outcomes.
*   **`database.py`**: The data abstraction layer. Manages SQLite database operations, handles cryptographic symmetric encryption/decryption (Fernet) of exchange API keys at rest, maintains user preferences, and records theoretical backtest logs.
*   **`charting.py`**: Renders real-time technical analysis charts of active positions (overlaying candles, Bollinger Clouds, entries, and current prices) which are sent directly to users via Telegram.
*   **`media_gen.py`**: Generates premium visual asset cards (such as P&L performance, portfolio allocation, and dynamic UI panels) using drawing libraries (`PIL/Pillow`) to enhance user reporting.
*   **`strategies.py`**: Implements technical indicator math and signal triggers (such as BB Scalping, Valkyrie Elite signals, and trend filters) for execution engines.
*   **`bot_ui.py`**: Houses layout utilities, keyboard formatting helpers, inline button builders, and markdown parsing for the Telegram user interface.
*   **`stock_backtester_daily.py`** & **`stock_data_cache_daily.py`**: Backtester and caching tools that update historical stock price data feeds for live swing trading evaluation.

---

### 🗄️ Database Architecture (`data/` Directory)

All database engines and SQLite state files are isolated inside the `data/` subdirectory to keep the workspace root tidy, secure, and separated from version control:

*   **`data/bot_users.db`**: **The active user database.** Securely stores Telegram chat profiles, encrypted API keys/secrets, active strategies, tier access states, referral analytics, and open simulated forward-testing trades. *Must never be committed to Git.*
*   **`data/stock_daily_cache.db`**: Stores cached daily price histories for equities used by the Alpaca live bot.
*   **`data/stock_cache.db`**: A comprehensive historical stock price cache populated via the Tiingo API for local daily backtesting.
*   **`data/blofin_stock_cache.db`**: Local caching database storing historical futures data for backtest validations.

---

### 🧪 Supplementary Directories

*   **`scripts/`**: Retained exclusively for historical developer research, ad-hoc audits, and variance-checking scripts (e.g., `sherpa_visual_audit.py`, `blofin_variance_check.py`).
*   **`results/`**: Stores generated technical analysis equity curves, strategy audit infographics, and premium performance report images.
*   **`pnl_cards/`**: Serves as a temporary directory for generated user P&L social sharing cards.

## 🛠️ Initial VPS Setup (GCP/Ubuntu)

If setting up a new `e2-micro` instance, follow these essential steps:

1.  **Memory Safety (Swap File)**:
    ```bash
    sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
    sudo mkswap /swapfile && sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    ```
2.  **Install Dependencies & Setup Venv**:
    ```bash
    sudo apt update && sudo apt install -y python3-pip python3-venv git libfontconfig1 fonts-dejavu-core
    cd ~/tradingbot
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
3.  **Setup Service (Systemd)**:
    Create the service file: `sudo nano /etc/systemd/system/tradingbot.service`
    ```ini
    [Unit]
    Description=Cyber-Sherpa Trading Bot
    After=network.target

    [Service]
    User=gilesasp
    WorkingDirectory=/home/gilesasp/tradingbot
    ExecStart=/home/gilesasp/tradingbot/venv/bin/python3 telegram_bot.py
    Restart=always
    RestartSec=10
    StandardOutput=journal
    StandardError=journal

    [Install]
    WantedBy=multi-user.target
    ```
    Then run:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable tradingbot
    sudo systemctl start tradingbot
    ```

## 🔐 Google Cloud Secret Manager Setup

To securely run the bot on GCP without hardcoding API keys in `.env` files, the bot uses Google Cloud Secret Manager.

1.  **Create Secrets**: Go to **Security > Secret Manager** in the Google Cloud Console and create your secrets (e.g., `ALPACA_API_KEY`, `ALPACA_API_SECRET`).
2.  **Grant Permissions**: Give your VM's Service Account the **Secret Manager Secret Accessor** role in IAM.
3.  **Enable VM Scopes**: 
    * Stop your VM instance.
    * Click **Edit**.
    * Under **Identity and API access**, change the **Access scopes** to **"Allow full access to all Cloud APIs"**.
    * Save and restart the VM.
4.  **Local Fallback**: When running locally on your own machine (outside of GCP), the bot will gracefully fall back to checking your local `.env` file for uppercase equivalents (e.g., `ALPACA_API_KEY` and `ALPACA_API_SECRET`).

## 🔄 Updates & Maintenance

Follow these steps each time you push new code to Github:

1.  **Local**: `git add .` -> `git commit -m "Update"` -> `git push`
2.  **VPS**: Connect via SSH and run:
    ```bash
    cd ~/tradingbot
    git pull
    sudo systemctl restart tradingbot

    or

    cd /home/gilesasp/tradingbot && git pull && sudo systemctl restart tradingbot && journalctl -u tradingbot -f
    ```
3.  **Logs**: Monitor live activity with `journalctl -u tradingbot -f`
4.  **Disk Safety**: Limit system logs to 500MB to prevent disk bloat:
    ```bash
    sudo journalctl --vacuum-size=500M
    ```

## 🛠️ Troubleshooting & Environment


### ⚠️ PATH Warnings
If you see a warning like `WARNING: The script ... is installed in ... which is not on PATH`, **don't worry.** This is normal and doesn't affect the bot. It just means the optional command-line tools aren't in your system's shortcut list. The bot code itself will work perfectly.

### 🐍 Virtual Environment (Venv)
To ensure all libraries are installed correctly, always activate your virtual environment before running `pip`:
```bash
source ~/tradingbot/venv/bin/activate
pip install -r requirements.txt
```

---

## ⚠️ Disclaimer
Trading cryptocurrency involves significant risk. This bot is provided for educational purposes. Always start with **Dry Run** mode to verify behavior before committing real capital.
