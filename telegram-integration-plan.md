# Telegram Integration Plan: Multi-Tenant Trading Bot

This document outlines the architecture, security, and implementation steps required to transform the single-user GitHub Actions trading bot into a multi-tenant Telegram Bot Service. Users will be able to securely connect their own Blofin accounts, and the bot will trade on their behalf while providing real-time stats and open trade updates via Telegram.

## 1. Architecture Shift: From Serverless to Stateful

Currently, the bot runs as a "serverless" script via GitHub Actions and stores state in a Markdown file. To support multiple users securely and interactively, the architecture must change:

*   **Hosting:** A dedicated Virtual Private Server (VPS) (e.g., DigitalOcean, AWS EC2, or Google Compute Engine).
*   **Database:** A relational database (e.g., PostgreSQL or SQLite for early stages) to store user profiles, encrypted API keys, and trade history.
*   **Telegram Interface:** A persistent Python process using `python-telegram-bot` or `aiogram` to handle user commands interactively.
*   **Execution Engine:** A background task scheduler (like `APScheduler`, `Celery`, or native `asyncio` loops) to run the trading logic every 5 minutes for *every* connected user.

## 2. Security: Protecting User API Keys (CRITICAL)

Storing other people's exchange API keys is a massive responsibility. If your database is compromised, their funds are at risk.

*   **Encryption at Rest:** You must NEVER store API keys in plain text in your database. Use a symmetric encryption library like `cryptography` (Fernet) in Python. 
    *   The bot application holds the master encryption key (in its `.env` file).
    *   When a user submits an API key via Telegram, the bot encrypts it before saving it to the database.
    *   When the 5-minute trading cycle runs, the bot pulls the encrypted key from the database, decrypts it in memory, executes the trade, and drops it from memory.
*   **API Key Restrictions:** During the `/setup` flow, explicitly instruct users to create API keys with **"Trade Only"** permissions and absolutely **NO Withdrawal permissions**.

## 3. Database Schema Design

You will need a minimum of two tables:

**Table: `Users`**
*   `telegram_chat_id` (Primary Key)
*   `blofin_api_key` (Encrypted)
*   `blofin_api_secret` (Encrypted)
*   `blofin_api_password` (Encrypted)
*   `starting_equity` (Float - Captured at go-live)
*   `is_active` (Boolean - True if they completed setup)
*   `total_wins` (Integer)
*   `total_losses` (Integer)
*   `total_trades_opened` (Integer)

**Table: `OpenTrades`** (Optional, but makes `/open_trades` faster)
*   `trade_id` (Primary Key)
*   `telegram_chat_id` (Foreign Key)
*   `symbol` (String)
*   `side` (String)
*   `entry_price` (Float)
*   `size` (Float)

## 4. Telegram Bot Commands & User Flow

The Telegram interface will be the user's dashboard. 

*   **`/start`**: Welcomes the user, explains the bot, and provides the disclaimer.
*   **`/setup`**: Initiates a secure, private conversation flow.
    *   Bot: "Please send me your Blofin API Key."
    *   Bot: "Now send your API Secret."
    *   Bot: "Finally, send your API Password."
    *   *Bot encrypts these, verifies a test connection to Blofin, records their current equity as `starting_equity`, and marks `is_active = True`.*
*   **`/open_trades`**: The bot decrypts the user's keys, queries `exchange.fetch_positions()`, and formats a nice Telegram message showing their currently open positions and live PnL.
*   **`/stats`**: Queries the database to show the user their All-Time Total Trades, Wins, Losses, Win Rate, and Total PnL % (Calculated via `(current_equity - starting_equity) / starting_equity`).
*   **`/stop`**: Pauses trading for their account (sets `is_active = False`).

## 5. Execution Engine (The 5-Minute Loop)

The `live_bot_multi.py` script will be heavily refactored. Instead of running once and exiting, it will run continuously in the background.

**The Loop Logic:**
1. Every 5 minutes, wake up.
2. Query the database for `SELECT * FROM Users WHERE is_active = True`.
3. Fetch the market data (OHLCV) *once* to save API calls (all users trade the same signals).
4. Compute the signals.
5. If a signal exists (e.g., BUY PEPE):
    * Loop through every active user.
    * Decrypt their API keys.
    * Connect to CCXT using their specific keys.
    * Check their specific equity to calculate their specific position size (1% of *their* account).
    * Place the order on their account.
    * Send them a direct Telegram message: *"🚀 I just opened a BUY position on PEPE for you!"*
6. Check for recently closed trades to update the database stats for each user.

## 6. Development Roadmap

**Phase 1: Telegram Shell**
*   Build the Telegram bot using `python-telegram-bot`.
*   Implement the `/setup` flow with dummy database storage to ensure the conversational UI feels smooth.

**Phase 2: Database & Security**
*   Implement PostgreSQL or SQLite.
*   Implement the `cryptography` Fernet encryption system.
*   Verify that `/setup` correctly encrypts data and can decrypt it to successfully connect to CCXT.

**Phase 3: The Engine Room**
*   Merge `live_bot_multi.py` logic into a background scheduler.
*   Test with 2 test accounts simultaneously to ensure the loop iterates correctly without cross-contaminating API keys.

**Phase 4: Notifications & Polishing**
*   Wire up the `/stats` and `/open_trades` commands.
*   Implement the live Telegram push notifications when a trade is executed on a user's behalf.
