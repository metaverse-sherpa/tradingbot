# Trading Bot: Multi-Symbol BB Scalper & Premium Web Dashboard 📈

A production-ready, multi-tenant Telegram trading bot and companion web dashboard. This system supports futures trading on Blofin, Binance, MEXC, and Bitget, as well as equities swing trading via Alpaca. It is designed to run efficiently on a Google Cloud hosted free VM instance (`e2-micro`) using an asynchronous python execution loop, a Flask API backend, a Tailwind CSS + Vanilla JS SPA, and SQLite in WAL mode with Fernet symmetric encryption for credentials.

---

## 🚀 Key Features

*   **Multi-Tenant Telegram Interface**: Secure `/setup` or `/reset` flows. Each tenant runs autonomously using their own credentials.
*   **Multi-Exchange Engine**: Real-time integration with Blofin, Binance, MEXC, and Bitget futures via CCXT.
*   **Equities Integration**: Automated stock trading using the Alpaca API driven by the **Sherpa Velocity Pullback** strategy.
*   **Lightweight Web SPA**: A highly responsive premium web dashboard featuring glassmorphic designs, real-time position status, and inline technical charting.
*   **Military-Grade Encryption**: Fernet symmetric encryption key encrypts exchange API keys/passwords at rest in the SQLite database.
*   **Performance Tracking**: Live win rate, total trade counts, and theoretical/forward testing simulations.
*   **Administrative Control Overrides**: Admin-only commands to manage tiers, referrals, generate gift codes, and execute emergency panic closes.

---

## 📁 Codebase Architecture & File Reference

The codebase is modularized to separate the Telegram user interface, background trading engines, Flask API routes, and front-end SPA resources.

```
tradingbot/
├── bot/                         # Telegram Bot Source Directory
│   ├── engines/                 # Execution Loops & Market Sync Processes
│   │   ├── base.py              # Base class defining executor loop interface
│   │   ├── crypto.py            # Multi-exchange futures trading execution loops
│   │   ├── stocks.py            # Alpaca equities trading execution engine
│   │   ├── sync.py              # Balance/position synchronization engine
│   │   └── system.py            # Background scheduler, system audits & database backup
│   ├── handlers/                # Telegram Event Command & Callback Logic
│   │   ├── settings/            # Sizing, isolation, strategy whitelists
│   │   │   ├── commands.py      # Entry point for settings commands
│   │   │   ├── free_trades.py   # Settings for standard tier/free signals
│   │   │   └── helpers.py       # Layout formatting utility helpers
│   │   ├── admin.py             # Administrator commands (gift codes, vacuum, audit)
│   │   ├── auth.py              # Setup flow, reset API keys, user linking
│   │   ├── strategy.py          # Command handlers for switching trading strategies
│   │   ├── system.py            # System checks, uptime diagnostics, general help
│   │   └── trading.py           # Position details, one-click close, manual overrides
│   └── ui/                      # UI Rendering Layout Templates
│       ├── dashboards.py        # Text-based dashboards (crypto/stock/stats)
│       └── keyboards.py         # Dynamic markup inline keyboards and buttons
│
├── web_api/                     # Flask Backend API Blueprints
│   ├── auth.py                  # Argon2 password hashing and JWT token middleware
│   ├── cache.py                 # Thread-safe in-memory caching engine
│   ├── db_web.py                # Database controller wrapping web user operations
│   ├── email_service.py         # Alert templates, OTP, and registration triggers
│   ├── routes_auth.py           # Route blueprint: registration, login, OAuth
│   ├── routes_premium.py        # Route blueprint: Tron USDT payments, gift codes
│   ├── routes_settings.py       # Route blueprint: user API key storage, risk settings
│   └── routes_trades.py         # Route blueprint: positions, balance history, charts
│
├── webapp/                      # Single-Page Frontend Application (SPA)
│   ├── app.js                   # Main application controller (view logic & API routing)
│   ├── index.html               # Main index containing the UI structure
│   ├── input.css / output.css   # Tailwind CSS source styling sheets
│   └── tailwind.config.js       # Tailwind setup and custom color configurations
│
├── data/                        # Local SQLite Database Files (WAL Mode)
│   ├── bot_users.db             # Active database for user settings & API keys
│   └── stock_daily_cache.db     # Daily stock data cache for equity algorithms
│
├── docs/                        # Project Documentation
│   ├── db_schema.md             # In-depth SQLite schema mapping for all tables
│   ├── SSL_SETUP_GUIDE.md       # SSL/Nginx reverse proxy setup walkthrough
│   └── multiexchange-strategy.md# Multi-exchange futures scaling details
│
└── [Root Level Scripts]         # High-level entrypoints and helper utilities
    ├── server.py                # Entrypoint for the Flask backend web API
    ├── telegram_bot.py          # Entrypoint daemon for the Telegram Bot
    ├── live_bot_multi.py        # Production multi-exchange crypto futures engine
    ├── live_bot_multi_alpaca.py # Production Alpaca stock trading engine
    ├── database.py              # Core SQLite data layer and Fernet encryption wrapper
    ├── charting.py              # Technical candle/Bollinger Cloud rendering utility
    ├── media_gen.py             # PIL-based graphical performance card generator
    ├── strategies.py            # Math formulas for indicators and trigger conditions
    └── bot_ui.py                # Formatting layout blocks for Telegram markdown
```

---

## 🛠️ GCP Free VM Setup Guide (Ubuntu `e2-micro`)

Follow this step-by-step guide to set up the system on Google Cloud Platform's Free Tier instance (`e2-micro` virtual machine running Ubuntu 22.04 LTS).

### 1. Provision the VM Instance
*   Go to **Google Compute Engine** > **VM Instances** > **Create Instance**.
*   **Name**: `tradingbot-free-tier`
*   **Region**: Pick a free tier region (e.g., `us-central1` (Iowa), `us-east1` (South Carolina), `us-west1` (Oregon)).
*   **Machine configuration**: Machine family: **General-purpose** > Series: **E2** > Machine type: **e2-micro** (2 vCPUs, 1 GB memory).
*   **Boot Disk**: Ubuntu 22.04 LTS (Standard persistent disk up to 30 GB is free).
*   **Firewall**: Check both **Allow HTTP traffic** and **Allow HTTPS traffic**.
*   **Access Scopes**: Under *Identity and API access*, choose **Allow full access to all Cloud APIs** (required if using GCP Secret Manager).

### 2. Configure Virtual Memory (Swap File)
The `e2-micro` instance only has 1 GB of RAM. Setting up a 2 GB swap file is **mandatory** to prevent the web app or background engines from being killed by the Linux Out-Of-Memory (OOM) killer.
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 3. Install System Packages & Node.js
Update the system package repository and install Git, Python 3 development libraries, Nginx (for SSL reverse proxying), and Cairo graphics dependencies (needed by PIL for P&L card generation).
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev git libfontconfig1 fonts-dejavu-core Nginx pkg-config libcairo2-dev
```

### 4. Clone Repository & Setup Python Virtual Environment
Clone the bot code to your user home directory, configure the virtual environment, and install dependencies.
```bash
cd ~
git clone https://github.com/YOUR_GITHUB_USERNAME/tradingbot.git
cd tradingbot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Setup Local Database File Structure
Initialize the data directory (the SQLite databases will be automatically created by the system upon the first start of the server or telegram bot).
```bash
mkdir -p data results pnl_cards
```

### 6. Environment Configurations (`.env`)
Copy `.env.copy` to `.env` and fill in the configuration values:
```bash
cp .env.copy .env
nano .env
```
Ensure the following key variables are defined in your local `.env`:
*   `TELEGRAM_BOT_TOKEN`: The API token from `@BotFather`.
*   `ENCRYPTION_KEY`: A 32-byte URL-safe base64-encoded key generated via cryptography (e.g. `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). This is critical for encrypting API credentials at rest.
*   `FLASK_SECRET_KEY` and `JWT_SECRET`: Random secure string tokens for web authentication.
*   `TIINGO_API_KEY`: API Key for pulling daily stock pricing.

---

## 🔐 Google Cloud Secret Manager Integration

If running on GCP, the bot can securely load credentials from Google Secret Manager instead of saving them as plaintext in `.env`:
1.  **Create Secrets**: In the GCP Console under **Security > Secret Manager**, create secrets for sensitive keys (e.g., `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `TELEGRAM_BOT_TOKEN`).
2.  **IAM Role**: Assign the **Secret Manager Secret Accessor** role to your VM's default service account.
3.  **Local Fallback**: Outside of GCP (during local testing), the system automatically falls back to values defined inside your local `.env` file.

---

## 🔄 VPS Deployment & Maintenance Commands

Use the following commands to manage the production services on your VPS.

### Restart Services

*   **Telegram Bot Daemon**: Running as a background systemd service:
    ```bash
    sudo systemctl restart tradingbot
    ```
*   **Web API (Flask backend)**: Managed in a persistent `screen` session:
    ```bash
    screen -S webapp -X quit 2>/dev/null
    screen -dmS webapp bash -c "source venv/bin/activate && python3 server.py"
    ```

### Monitor Console Logs
*   **Bot Output**: `journalctl -u tradingbot -f`
*   **Web Server Output**: `screen -r webapp` (Press `Ctrl+A` then `D` to detach without stopping it)

### Maintenance Operations
*   **Vacuum System Logs**: Run periodically to clean system journal files and prevent disk exhaustion:
    ```bash
    sudo journalctl --vacuum-size=500M
    ```
*   **SQLite DB Backups**: Automatically handled in the background by `bot/engines/system.py`, saving timestamped SQL dumps to the workspace directory.

### Pull Code Updates from GitHub
```bash
cd ~/tradingbot
git pull
# Run service restart commands after pulling changes
sudo systemctl restart tradingbot
screen -S webapp -X quit 2>/dev/null
screen -dmS webapp bash -c "source venv/bin/activate && python3 server.py"
```

---

## ⚠️ Disclaimer

Trading cryptocurrency futures and equities carries high risk and may not be suitable for all investors. This software is provided for educational and research purposes. Always verify strategy executions in **Dry Run** mode (`BLOFIN_DRY_RUN=true`) before committing live funds.
