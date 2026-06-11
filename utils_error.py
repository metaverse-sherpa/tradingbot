import os
import html
import traceback
import requests
import logging

import utils_gcp

logger = logging.getLogger("ErrorNotifier")

def send_telegram_alert(service_name, error, tb_string=None):
    """
    Sends a formatted error notification to the Telegram bot admin.
    """
    token = utils_gcp.get_secret("TELEGRAM_BOT_TOKEN")
    admin_id = os.getenv("SUPER_ADMIN_ID", "1567788633")

    if not token or not admin_id:
        logger.warning("Telegram Bot Token or Admin ID not found. Cannot send alert.")
        return False

    try:
        if tb_string is None:
            tb_string = traceback.format_exc()

        safe_service = html.escape(str(service_name))
        safe_error = html.escape(str(error))
        
        # Truncate to avoid Telegram 4096 character limit
        tb_truncated = html.escape(tb_string[:3000])
        if len(tb_string) > 3000:
            tb_truncated += "\n... [TRUNCATED]"

        alert_msg = (
            f"🚨 <b>SERVICE CRASH: {safe_service}</b>\n\n"
            f"<b>Error:</b> <code>{safe_error}</code>\n\n"
            f"<b>Traceback:</b>\n<pre>{tb_truncated}</pre>"
        )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": int(admin_id),
            "text": alert_msg,
            "parse_mode": "HTML"
        }, timeout=5)
        
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Error sending Telegram alert: {e}")
        return False
