# Telegram Integration Plan: Multi-Tenant Trading Bot (Forever Free Architecture)

This document outlines the architecture, security, and implementation steps required to transform the single-user GitHub Actions trading bot into a multi-tenant Telegram Bot Service. Users will be able to securely connect their own Blofin accounts, and the bot will trade on their behalf.

This architecture is specifically designed to cost **$0.00/month** by utilizing generous "Always Free" cloud tiers.

## 1. Architecture Shift: The Free Stack

Currently, the bot runs as a "serverless" script via GitHub Actions. To support multiple users securely and interactively without incurring costs, we will use the following free infrastructure:

*   **Hosting:** A dedicated Virtual Private Server (VPS). Services like Render or Heroku "sleep" on free tiers (which kills the 5-minute loop), so we must use a real Virtual Machine.
    *   *Option A (Best):* **Oracle Cloud "Always Free"** provides an ARM server with up to 24GB RAM and 4 CPUs forever.
    *   *Option B:* **Google Cloud Platform (GCP)** provides 1 `e2-micro` instance free per month.
*   **Database:** 
    *   *Option A (Local):* **SQLite**. Stores everything in a local `.sqlite3` file on the VPS. Requires no setup and zero memory overhead. Perfect for hundreds of users.
    *   *Option B (Cloud):* **Supabase**. Offers a generous free-tier PostgreSQL database with a beautiful web UI for managing user data.
*   **Execution Engine:** Python's built-in **`asyncio`**. Instead of heavy task queues like Celery/Redis, a lightweight async loop will run the Telegram bot and the 5-minute trading cycle simultaneously.

## 2. Security: Protecting User API Keys (CRITICAL)

Storing other people's exchange API keys is a massive responsibility.

*   **Encryption at Rest:** You must NEVER store API keys in plain text. Use Python's `cryptography` library (Fernet symmetric encryption). 
    *   Your free server holds the master `.env` encryption key.
    *   When a user submits an API key via Telegram, the bot encrypts it before writing it to SQLite/Supabase.
    *   When the 5-minute loop runs, it decrypts the key in memory, executes the trade, and destroys the decrypted key instantly.
*   **API Key Restrictions:** During the `/setup` flow, explicitly warn users to create API keys with **"Trade Only"** permissions and absolutely **NO Withdrawal permissions**.

## 3. Database Schema Design

You will need a minimum of two tables:

**Table: `Users`**
*   `telegram_chat_id` (Primary Key)
*   `blofin_api_key` (Encrypted String)
*   `blofin_api_secret` (Encrypted String)
*   `blofin_api_password` (Encrypted String)
*   `starting_equity` (Float - Captured when they first connect)
*   `is_active` (Boolean - True if they completed setup and haven't paused)
*   `total_wins` (Integer)
*   `total_losses` (Integer)
*   `total_trades_opened` (Integer)

**Table: `OpenTrades`** (Optional, but makes the `/open_trades` command faster)
*   `trade_id` (Primary Key)
*   `telegram_chat_id` (Foreign Key)
*   `symbol` (String)
*   `side` (String)
*   `entry_price` (Float)
*   `size` (Float)

## 4. Telegram Bot Commands & User Flow

The Telegram interface (`python-telegram-bot`) will be the user's dashboard. 

*   **`/start`**: Welcomes the user and provides the risk disclaimer.
*   **`/setup`**: Initiates a secure, private conversation flow.
    *   Bot: "Please send me your Blofin API Key."
    *   Bot: "Now send your API Secret."
    *   Bot: "Finally, send your API Password."
    *   *Bot encrypts these, verifies a test connection to Blofin, records their current equity as `starting_equity`, and sets `is_active = True`.*
*   **`/open_trades`**: The bot decrypts the user's keys, checks their live positions, and sends a formatted message showing open trades.
*   **`/stats`**: Queries the database to show their All-Time Total Trades, Wins, Losses, Win Rate, and Total PnL %.
*   **`/stop`**: Pauses trading for their account (`is_active = False`).

## 5. Execution Engine (The Asynchronous Loop)

The `live_bot_multi.py` script will be converted into an async daemon running on your free VPS.

**The Loop Logic:**
1. Every 5 minutes, the async timer triggers.
2. Query the database for `SELECT * FROM Users WHERE is_active = True`.
3. Fetch the market data (OHLCV) *once* to save API rate limits (all users trade the same signals).
4. Compute the signals.
5. If a signal exists (e.g., BUY PEPE):
    * Loop through every active user.
    * Decrypt their API keys.
    * Connect to CCXT using their specific keys.
    * Check their specific equity to calculate their specific position size (1% of *their* account).
    * Place the order on their account via a marketable limit order.
    * Send them a direct Telegram message: *"🚀 I just opened a BUY position on PEPE for you!"*
6. Check for recently closed trades to update the database stats for each user.

## 6. Development Roadmap

**Phase 1: Telegram Shell**
*   Build the Telegram bot using `python-telegram-bot` (`async` version).
*   Implement the `/setup` flow with dummy storage to ensure the UI feels smooth.

**Phase 2: Database & Security**
*   Implement a local SQLite database.
*   Implement the `cryptography` Fernet encryption system.
*   Verify that `/setup` securely encrypts data and can decrypt it to connect to CCXT.

**Phase 3: The Engine Room**
*   Merge the `live_bot_multi.py` logic into an `asyncio.sleep(300)` background task.
*   Test with 2 test accounts simultaneously to ensure the loop iterates correctly without cross-contaminating API keys.

**Phase 4: VPS Deployment**
*   Spin up the free Google Cloud `e2-micro` or Oracle Cloud ARM instance.
*   Upload the code, set up the master encryption key in `.env`, and run it in the background using `tmux` or `systemd`.
