# Trading Bot: Multi-Symbol BB Scalper 📈

A production-ready, multi-tenant Telegram trading bot for the Blofin exchange. This bot utilizes Bollinger Band scalping, trend filters, and volatility protection to trade for multiple users simultaneously from a dedicated VPS.

## 🚀 Features

*   **Multi-Tenant Telegram Interface**: Users securely connect their own accounts via `/setup` or `/reset`.
*   **Professional Dashboards**: Real-time stats, open position charts with Bollinger Clouds, and trade history.
*   **Precision Execution**: Async engine runs every 5 minutes with marketable limit orders to bypass size limits.
*   **Safety & Privacy**: 
    *   **Military-Grade Encryption**: API keys are encrypted with Fernet symmetric encryption at rest.
    *   **Privacy Mode**: Toggle between showing dollar PnL or protected percentages.
*   **Automated Tracking**: Real-time Win Rate, PnL %, and trade counts updated live.

## 🛠️ Initial VPS Setup (GCP/Ubuntu)

If setting up a new `e2-micro` instance, follow these essential steps:

1.  **Memory Safety (Swap File)**:
    ```bash
    sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
    sudo mkswap /swapfile && sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    ```
2.  **Install Dependencies**:
    ```bash
    sudo apt update && sudo apt install -y python3-pip python3-venv git libfontconfig1
    ```
3.  **Setup Service (Systemd)**:
    Create `/etc/systemd/system/tradingbot.service` to keep the bot running 24/7.

## 🔄 Updates & Maintenance

Follow these steps each time you push new code to Github:

1.  **Local**: `git add .` -> `git commit -m "Update"` -> `git push`
2.  **VPS**: Connect via SSH and run:
    ```bash
    cd ~/tradingbot
    git pull
    sudo systemctl restart tradingbot
    ```
3.  **Logs**: Monitor live activity with `journalctl -u tradingbot -f`

---

## 📈 Live Performance (All-Time)
<!-- PERFORMANCE_START -->
| Total Trades | Wins | Losses | Win Rate | Total PnL (%) |
| :--- | :--- | :--- | :--- | :--- |
| 12 | 11 | 4 | 73.3% | +4.24% |

**Last Updated:** 2026-05-12 07:35 UTC
<!-- PERFORMANCE_END -->

<!-- DATA_STORAGE_START
STARTING_EQUITY: 200.1733321
ALL_TIME_OPENED: 12
ALL_TIME_WINS: 11
ALL_TIME_LOSSES: 4
ALL_TIME_CUMULATIVE_PNL: 8.477543328
LAST_FETCH_TIMESTAMP: 1778571339977
DATA_STORAGE_END -->

## ⚠️ Disclaimer
Trading cryptocurrency involves significant risk. This bot is provided for educational purposes. Always start with **Dry Run** mode to verify behavior before committing real capital.
