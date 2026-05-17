# 🏔️ Metaverse Sherpa: Institutional Feature Roadmap & Strategy Plan

This document serves as our collaborative whiteboard to trace, design, and track the high-impact enhancements we are integrating into the **Metaverse Sherpa Trading Bot**. 

By checking off items below, we can maintain perfect alignment as we elevate the platform to an elite, institutional-grade product.

---

## 📌 Active Development Tracker
- `[ ]` **Feature 1**: ⚡ Real-Time Push Notifications (WebSocket Listener)
- `[ ]` **Feature 2**: 🛡️ Automated API Health Auditor & Key Expiry Alerts
- `[ ]` **Feature 3**: 🗺️ Strategy Expansion: "Crypto Chart Patterns" (The Incomplete Strategy)
- `[ ]` **Feature 4**: 🎛️ Custom Capital Allocation & Wallet Isolation
- `[ ]` **Feature 5**: 🔬 Individual Token Backtesting & Basket Tuning
- `[ ]` **Feature 6**: 🔗 Full Multi-Exchange Production Hardening (Binance & MEXC)

---

## 💎 Detailed Feature Architecture & Specifications

### 1. ⚡ Real-Time Push Notifications (WebSocket Listener)
*   **Aesthetic & Impact**: High. Gives users instant dopamine and clarity with immediate feedback on fills, entries, and target completions.
*   **Implementation Plan**:
    *   Initialize an asynchronous CCXT Pro (or exchange WebSocket native) loop alongside our existing sync/signal tasks.
    *   Subscribe to account execution streams (private orders channel) using the user's encrypted API keys.
    *   Format filled order executions into beautifully styled rich-text card templates.
    *   **Proposed Telegram Template**:
        ```text
        🎯 TARGET HIT: SOL Long Closed!
        
        • Entry Price: $138.20
        • Exit Price: $142.50
        • Realized PnL: +$84.20 USDT
        • Return on Equity (ROE): +42.1% 🚀
        
        🏔️ The Sherpa continues the climb.
        ```

### 2. 🛡️ Automated API Health Auditor & Key Expiry Alerts
*   **Aesthetic & Impact**: Medium (High Utility). Reduces support overhead significantly by warning users *before* a trade fail happens due to invalid keys/whitelists.
*   **Implementation Plan**:
    *   Add a lightweight async task inside `telegram_bot.py` that wakes up once every 24 hours.
    *   For each active user, run a secure permission audit (e.g. CCXT `fetch_balance` or check active API key restrictions).
    *   If a connection failure is intercepted, flag the user as `inactive` in the database and proactively broadcast a diagnostic alert:
        ```text
        ⚠️ API KEY CONNECTION ALERT
        
        The Sherpa lost connection to your Blofin exchange account. 
        
        Potential Causes:
        1. The VPS IP has changed or is not whitelisted on your API Key settings.
        2. API Key permissions have expired.
        
        Please check your exchange configurations and run /setup to verify.
        ```

### 3. 🗺️ Strategy Expansion: "Crypto Chart Patterns"
*   **Aesthetic & Impact**: High. Delivers on the placeholder in our main strategy menu.
*   **Implementation Plan**:
    *   Define the logic in `live_bot_multi.py` and `scripts/backtest_multi.py` for standard chart patterns:
        *   **Bull Flags / Pennants**: Pull historical 15m candle highs/lows to detect consolidation and break-outs.
        *   **Double Bottoms**: Identify price retests of key supports accompanied by ADX strength.
    *   Provide users a toggle under Strategy Options: `[1] Mean Reversion Scalper` or `[2] Crypto Chart Patterns`.

### 4. 🎛️ Custom Capital Allocation & Wallet Isolation
*   **Aesthetic & Impact**: High. Instills trust in users who do not want the bot compounding on their entire exchange account wallet balance.
*   **Implementation Plan**:
    *   Add a new column `allocated_equity` to the `Users` database table.
    *   Provide a `/settings` button: `💰 Set Trading Capital`.
    *   If a user allocates e.g., $1,000, all compounding calculations (`equity * Risk %`) will be calculated off the allocated limit rather than the total exchange equity.

### 5. 🔬 Individual Token Backtesting & Basket Tuning
*   **Aesthetic & Impact**: High. Gives users the power to customize and optimize their own institutional trading basket.
*   **Implementation Plan**:
    *   Extend `/backtest` command to parse arguments (e.g. `/backtest SOL` or `/backtest BTC`).
    *   If a coin argument is passed, instruct the `sherpa_visual_audit.py` engine to run the backtest exclusively on that token's historical CSV.
    *   Return a token-specific equity chart overlay with the standard final statistics.

### 6. 🔗 Full Multi-Exchange Hardening (Binance & MEXC)
*   **Aesthetic & Impact**: Medium. Expands the addressable user base.
*   **Implementation Plan**:
    *   Audit all order and history fetching calls in `database.py` and `telegram_bot.py`.
    *   Ensure proper parameter translation (e.g., matching Blofin's `instType='SWAP'` to Binance's futures equivalent `marginType` and MEXC's futures query formats).
    *   Ensure exact error handling and IP Whitelisting guidelines are updated for all three platforms.

---

## 📈 Strategic Discussion: Where Do We Start?
Let's decide on which feature to tackle first. My recommendation is to begin with **Feature 2: Automated API Health Auditor** because it is a low-risk, high-resilience operation that will immediately protect the bot's runtime, followed closely by **Feature 1: WebSocket Instant Fills** to elevate the user experience.

*What are your thoughts on this roadmap? Let's fine-tune the descriptions, order, and priorities!*
