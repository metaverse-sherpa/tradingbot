# 🗄️ Database Schemas (`data/bot_users.db`)

All tables are maintained in WAL mode via the abstraction layer in [database.py](file:///Users/johngiles/projects/tradingbot/database.py).

---

## 1. `Users` Table (Telegram Auto-Pilot Configurations)
Stores active strategy settings and encrypted api keys for Telegram tenants.

| Column Name | Data Type | Default / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `telegram_chat_id` | INTEGER | PRIMARY KEY | Unique Telegram identifier |
| `blofin_api_key` | TEXT | | Cryptographically encrypted API Key |
| `blofin_api_secret` | TEXT | | Cryptographically encrypted API Secret |
| `blofin_api_password` | TEXT | | Cryptographically encrypted API Passphrase |
| `exchange_id` | TEXT | `'blofin'` | Active exchange identifier |
| `starting_equity` | REAL | | Starting balance value |
| `is_active` | BOOLEAN | | Active bot flag |
| `total_wins` | INTEGER | `0` | Successful trade count |
| `total_losses` | INTEGER | `0` | Unsuccessful trade count |
| `total_trades_opened` | INTEGER | `0` | Cumulative trades triggered |
| `cumulative_pnl` | REAL | `0.0` | Sum of trade performance |
| `last_fetch_timestamp` | INTEGER | `0` | Timestamp of last balance refresh |
| `strategy` | TEXT | `'Valkyrie Elite Scalper'` | Legacy active strategy name |
| `active_crypto_strategy` | TEXT | `'Valkyrie Elite Scalper'` | Current active crypto strategy |
| `active_stock_strategy` | TEXT | `'None'` | Current active stock strategy |
| `risk_pct` | REAL | `1.0` | Sizing percentage |
| `stock_risk_pct` | REAL | `2.0` | Stock sizing percentage |
| `enabled_symbols` | TEXT | | Comma-separated symbol whitelist |
| `referred_by` | INTEGER | | Referral user ID |
| `premium_expiry` | INTEGER | `0` | Premium expiry unix timestamp |
| `referral_count` | INTEGER | `0` | Number of successful referrals |
| `has_open_positions` | BOOLEAN | `0` | If user has active positions |
| `undercover_mode` | BOOLEAN | `0` | Privacy mode toggle |
| `source_wallet` | TEXT | | TRON wallet address for payments |
| `last_audit_stats` | TEXT | | JSON string of last stats audit |
| `referral_credits` | REAL | `0.0` | Balance of referral earnings |
| `full_name` | TEXT | | User full name |
| `username` | TEXT | | Telegram username |
| `is_admin` | BOOLEAN | `0` | Admin access flag |
| `custom_equity_type` | TEXT | `'all'` | Portfolio allocation calculation mode |
| `custom_equity_value` | REAL | | Target sizing allocation value |
| `alpaca_api_key` | TEXT | | Encrypted Alpaca API key |
| `alpaca_api_secret` | TEXT | | Encrypted Alpaca API secret |
| `alpaca_endpoint` | TEXT | | Target Alpaca API endpoint URL |
| `alpaca_start_equity` | REAL | | Starting equity for stocks |
| `premium_referrals` | INTEGER | `0` | Count of referrals upgraded to premium |
| `premium_expired_notified` | BOOLEAN | `0` | Expiration notification flag |
| `had_premium_before` | BOOLEAN | `0` | History flag |
| `referral_reward_triggered` | BOOLEAN | `0` | Reward redemption tracker |
| `bingx_futures_type` | TEXT | `'standard'` | Futures category for BingX |

---

## 2. `WebUsers` Table (Dashboard Portal Profiles)
Tracks web-only users, sessions, and linked settings.

| Column Name | Data Type | Default / Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique user identifier |
| `email` | TEXT | UNIQUE NOT NULL | Account email address |
| `password_hash` | TEXT | | Argon2/PBKDF2 hash of user password |
| `google_id` | TEXT | UNIQUE | Google OAuth token unique sub id |
| `full_name` | TEXT | | User display name |
| `avatar_url` | TEXT | | Profile avatar link |
| `telegram_chat_id` | INTEGER | | Linked Telegram ID |
| `exchange_id` | TEXT | `'blofin'` | Active exchange identifier |
| `api_key` / `api_secret` / `api_password` | TEXT | | Encrypted crypto keys |
| `alpaca_api_key` / `alpaca_api_secret` / `alpaca_endpoint` | TEXT | | Encrypted Alpaca keys |
| `is_active` | BOOLEAN | `0` | Account status flag |
| `risk_pct` | REAL | `1.0` | Crypto risk allocation |
| `stock_risk_pct` | REAL | `2.0` | Stock risk allocation |
| `enabled_symbols` | TEXT | | Whitelisted comma-separated symbols |
| `hide_dollars` | BOOLEAN | `0` | Privacy mode toggle |
| `custom_equity_type` | TEXT | `'all'` | Equity calculation method |
| `custom_equity_value` | REAL | | Set capital size overrides |
| `active_crypto_strategy` | TEXT | `'Valkyrie Elite Scalper'` | Selected crypto algorithm |
| `active_stock_strategy` | TEXT | `'None'` | Selected stock algorithm |
| `source_wallet` | TEXT | | Linked TRON wallet address |
| `premium_expiry` | INTEGER | `0` | Unix timestamp of subscription end |
| `referral_credits` | REAL | `0.0` | Credits accumulated |
| `referred_by` | INTEGER | | Referrer ID |
| `referral_count` | INTEGER | `0` | Count of registered referrals |
| `total_wins` | INTEGER | `0` | Cumulative wins |
| `total_losses` | INTEGER | `0` | Cumulative losses |
| `cumulative_pnl` | REAL | `0.0` | Overall realized performance |
| `has_open_positions` | BOOLEAN | `0` | True if user has active swaps |
| `history_cache` | TEXT | | Cached JSON block of past transactions |
| `last_audit_stats` | TEXT | | JSON metadata cache of stats |
| `created_at` | INTEGER | | Account creation Unix timestamp |
| `reset_token` | TEXT | | Recovery token |
| `reset_token_expiry` | INTEGER | | Recovery expiry Unix timestamp |
| `email_notifications` | INTEGER | `1` | Alert preference |
| `email_frequency` | TEXT | `'realtime'` | Digest frequency configuration |
| `browser_notifications` | INTEGER | `1` | Push notification toggle |
| `public_key` | TEXT | | Public encryption key |
| `encrypted_private_key` | TEXT | | Encrypted private key block |
| `bingx_futures_type` | TEXT | `'standard'` | BingX futures mode |

---

## 3. `TheoreticalTrades` Table
Performance statistics for forward-test/paper trade automation.

- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `symbol` (TEXT) - Traded asset pair
- `strategy` (TEXT) - Executing brain name
- `side` (TEXT) - `'long'` or `'short'`
- `entry_price` (REAL) - Price filled
- `tp_price` / `sl_price` (REAL) - Target triggers
- `open_time` / `close_time` (INTEGER) - Unix timestamps
- `status` (TEXT) - `'open'` or `'closed'`
- `position_size` (REAL) - Traded size quantity
- `pnl_raw` (REAL) - PnL in points
- `pnl_pct` (REAL) - PnL percentage change
- `pnl_usdt` (REAL) - PnL in dollar equivalent

---

## 4. `AlpacaActiveTrades` Table
Tracks live fractional stock executions.

- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `telegram_chat_id` (INTEGER) - Linked Telegram recipient
- `symbol` (TEXT) - Ticker symbol
- `qty` (REAL) - Share size
- `entry_price` / `tp_price` / `sl_price` (REAL) - Order configurations
- `close_time` / `close_price` (INTEGER / REAL) - Realized details
- `pnl_raw` / `pnl_pct` (REAL) - Performance metrics
- `status` (TEXT) - `'open'`, `'closed'`
- `web_user_id` (INTEGER) - Linked Web User ID

---

## 5. `PortfolioBalanceHistory` Table
Captures periodic balance reports for user portfolio charts.

- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `user_id` (INTEGER) - Foreign key referencing `WebUsers(id)`
- `timestamp` (INTEGER) - Capture Unix timestamp
- `encrypted_crypto_balance` (TEXT) - Fernet encrypted balance
- `encrypted_stock_balance` (TEXT) - Fernet encrypted balance

---

## 6. `Config` Table
Stores system-wide parameters.

- `key` (TEXT PRIMARY KEY)
- `value` (TEXT)

---

## 7. `GiftCodes` Table
Tracks generated promotional codes for subscription access.

- `code` (TEXT PRIMARY KEY)
- `target_chat_id` (INTEGER)
- `target_username` (TEXT)
- `expiry_days` (INTEGER)
- `is_used` (BOOLEAN)
- `created_at` (INTEGER)

---

## 8. `FAQs` Table
Stores dynamic frequently asked questions to be displayed on the Help page.

- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `question` (TEXT) - The FAQ question
- `answer` (TEXT) - The FAQ answer
- `order_index` (INTEGER) - Used for custom sorting
- `created_at` (INTEGER) - Unix timestamp
