# 🌍 Cyber-Sherpa: Multi-Exchange Expansion Strategy

This document outlines the architectural changes required to transform the bot from a Blofin-exclusive tool into a universal trading engine supporting Binance, MEXC, and more.

## 1. Core Architecture Changes

### 🏦 Database Update
*   **Column**: `exchange_id` (TEXT) added to `Users` table.
*   **Default**: `blofin`.
*   **Purpose**: Stores the CCXT exchange identifier (e.g., `binance`, `mexc`, `bingx`).

### 🛠️ Universal Exchange Factory
Instead of hardcoding Blofin, we will implement an internal "Factory" function:
```python
def create_exchange_client(user):
    ex_id = user.get('exchange_id', 'blofin')
    client = getattr(ccxt, ex_id)({
        'apiKey': user['api_key'],
        'secret': user['api_secret'],
        'password': user['api_password'],
        'options': {'defaultType': 'swap'} # Essential for Futures
    })
    return client
```

---

## 2. Technical "Gotchas" & Complications ⚠️

### A. Symbol Normalization
Different exchanges have different "Dialects" for the same token:
*   **Blofin**: `BTC/USDT:USDT`
*   **Binance**: `BTC/USDT:USDT` (usually compatible)
*   **MEXC**: Sometimes uses `BTC/USDT` without the `:USDT` suffix for some endpoints.
*   **Solution**: We will implement a `normalize_symbol(symbol, exchange_id)` helper to ensure the engine always speaks the correct dialect.

### C. Divergent Order Logic (CRITICAL)
The way SL/TP is handled varies wildly across the CCXT ecosystem:
*   **Integrated (Blofin)**: Single call with `params={'stopLoss': ...}`.
*   **Fragmented (Binance/MEXC)**: Requires **Entry + SL Order + TP Order**. 
*   **Solution**: We must implement an `AtomicOrder` class that handles the sequence:
    1. Place Market/Limit Entry.
    2. Await fill confirmation.
    3. Place `STOP_MARKET` for SL.
    4. Place `TAKE_PROFIT_MARKET` for TP.

### D. Manual PnL Reconstruction
*   **The Problem**: Binance and MEXC do not reliably provide a `realized_pnl` field in `fetch_my_trades`.
*   **Solution**: The `/list` and `/stats` logic must be updated to fetch the `Ledger` or manually match opening/closing execution IDs to calculate net profit.

### E. Market Symbol Dialects
*   **Normalization**: We will implement a `universal_sym(symbol, exchange)` mapper.
    *   `BTC/USDT:USDT` (Blofin/Binance)
    *   `BTC_USDT` (MEXC API v3 raw)
    *   `BTCUSDT` (Binance raw)
*   **CCXT Normalization**: We will rely on CCXT's unified symbols where possible but must handle the `:USDT` suffix specifically for futures.

### C. Rate Limiting
*   Binance is much stricter with rate limits than Blofin.
*   **Solution**: We must ensure `exchange.enableRateLimit = True` is active for all clients to prevent "IP Bans" during heavy signal periods.

### F. Precision & Minimums
*   **Lot Sizes**: `0.01` BTC on Blofin might be `0.001` on Binance. 
*   **Solution**: Always fetch `market['limits']` and `market['precision']` before calculating the final order size.

---

## 5. Core Functional Checklist (The "100% Goal")
To ensure 100% functionality, the following must work perfectly on all supported exchanges:

1.  **🚀 Signal Execution**: The bot must check signals for the 19 tokens and place orders with user-specific `risk_pct`.
2.  **🛡️ Atomic SL/TP**: Orders must include verified Stop-Loss and Take-Profit (either via single call or the 3-order combo).
3.  **📊 Visual Position Tracking**: `/opentrades` must generate 1H charts with accurate Entry/TP/SL zones for the specific exchange.
4.  **📜 Accurate History**: `/list` must show the correct side (Long/Short) and realized PnL calculated from the exchange's ledger.
5.  **💰 Account Stats**: `/stats` and `/balance` must reflect the live equity and cumulative PnL of the specific exchange wallet.
6.  **🔄 Personalized Audits**: `/backtest` and the automated simulations must account for exchange-specific fees and liquidity.
7.  **📸 Viral Shareability**: High-fidelity PnL card generation and "📸 Share" buttons must be available for both wins and losses across all exchanges.

---

## 6. Universal API Setup Guide
To ensure 100% functionality, users must follow these exchange-specific steps when generating their keys:

### 🏔️ Blofin
1.  Navigate to **API Management**.
2.  Create a new API Key (API Key, Secret, and Passphrase required).
3.  **Permissions**: Ensure "Read" and "Trade" are checked.
4.  **Security**: (Optional but Recommended) Whitelist the VPS IP address.

### 🔶 Binance
1.  Navigate to **API Management**.
2.  Create a "System Generated" Key.
3.  **Permissions**: Click "Edit Restrictions" and check **"Enable Futures"**.
4.  **Security**: **Mandatory** to whitelist the VPS IP for Futures trading.

### 💠 MEXC
1.  Navigate to **API Management**.
2.  Create a new API Key.
3.  **MEXC KYC**: Users MUST complete Primary KYC on MEXC to enable Futures trading via API.
4.  **Permissions**: Ensure **"Futures"** is checked (Spot is optional).
5.  **Security**: Whitelist the VPS IP to avoid key expiration.

---

## 3. Implementation Roadmap

### Phase 1: Database & Setup
1.  Add `exchange_id` to SQLite schema.
2.  Add a "Selection Step" in the Telegram `/setup` flow.

### Phase 2: Refactoring
1.  Replace all `ccxt.blofin` calls with the `Exchange Factory`.
2.  Add a "Dialect" mapper for symbol strings.

### Phase 3: Validation
1.  Perform "Dry Run" tests on a Binance Testnet account.
2.  Perform "Dry Run" tests on a MEXC account.

---

## 4. Proposed Exchange Support Order
1.  **Blofin** (Already Live)
2.  **Binance** (Most Requested)
3.  **MEXC** (Popular for Low Fees/Small Caps)
