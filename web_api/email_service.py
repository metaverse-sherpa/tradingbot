import smtplib
import os
import threading
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import utils_gcp to fetch secrets from Google Secret Manager
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils_gcp import get_secret

logger = logging.getLogger("email_service")

# Default configurations loaded from environment
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Generous fallback to Resend API endpoint if Resend API Key is provided
RESEND_API_KEY = get_secret("RESEND_API_KEY") or os.getenv("RESEND_API_KEY", "")

SMTP_SENDER_EMAIL = get_secret("SMTP_SENDER_EMAIL") or os.getenv("SMTP_SENDER_EMAIL", "")

# Only attempt to fetch SMTP credentials if we are NOT using Resend
if not RESEND_API_KEY:
    SMTP_USERNAME = get_secret("SMTP_USERNAME") or os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = get_secret("SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD", "")
else:
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

def _send_email_thread(to_email, subject, html_content):
    """
    Sends email in a background thread using SMTP or Resend API.
    Does not block main execution loop.
    """
    if not to_email:
        logger.warning("No recipient email provided. Skipping dispatch.")
        return

    # Try Resend API first if key exists
    if RESEND_API_KEY:
        try:
            import requests
            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "from": "Metaverse Sherpa Bot Alerts <" + (SMTP_SENDER_EMAIL or "alerts@metaversesherpa.io") + ">",
                "to": [to_email],
                "subject": subject,
                "html": html_content
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code in [200, 201]:
                logger.info(f"✅ Email successfully sent via Resend API to {to_email}")
                return
            else:
                logger.error(f"❌ Resend API failed: {resp.status_code} - {resp.text}")
        except Exception as res_err:
            logger.error(f"❌ Failed sending email via Resend API: {res_err}")

    # Fallback to SMTP
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not fully configured. Email was not sent.")
        return

    try:
        sender = SMTP_SENDER_EMAIL or SMTP_USERNAME
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Metaverse Sherpa <{sender}>"
        msg["To"] = to_email

        # Attach HTML
        part_html = MIMEText(html_content, "html")
        msg.attach(part_html)

        # Establish secure TLS connection
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(sender, to_email, msg.as_string())
        server.quit()
        logger.info(f"✅ Email successfully sent via SMTP to {to_email}")
    except Exception as e:
        logger.error(f"❌ Background SMTP delivery failed: {e}")

def send_alert_email(to_email, subject, html_content):
    """
    Public asynchronous entry point to dispatch emails without VPS blockage.
    """
    thread = threading.Thread(target=_send_email_thread, args=(to_email, subject, html_content))
    thread.daemon = True
    thread.start()

def get_signal_alert_html(symbol, side, strategy, entry, tp, sl, resolution=None, pnl_pct=None):
    """
    Generates premium responsive HTML email template for trading signals.
    """
    is_win = (pnl_pct and pnl_pct > 0)
    pnl_str = f"{pnl_pct:+.2f}%" if pnl_pct is not None else ""
    
    color_primary = "#3cd7ff"  # Cyan
    color_highlight = "#D500F9"  # Neon purple
    color_bg = "#0B0E14"
    color_card = "#141A24"
    
    status_header = "NEW ALPHA SIGNAL DETECTED"
    status_sub = "Sherpa is leading a path to market victory"
    status_color = "#3cd7ff"
    
    if resolution == "tp":
        status_header = f"🏆 TARGET PROFIT ACHIEVED: {pnl_str}"
        status_sub = "Strategy reached target profit limit seamlessly!"
        status_color = "#00C853"
    elif resolution == "sl":
        status_header = f"❌ STOP LOSS TRIGGERED: {pnl_str}"
        status_sub = "Risk parameters guarded capital successfully."
        status_color = "#FF1744"
    elif resolution == "closed":
        status_header = f"🔒 POSITION EXITED: {pnl_str}"
        status_sub = "Position was manually exited successfully."
        status_color = "#ffdb3c"
        
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Metaverse Sherpa Alerts</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background-color: {color_bg};
                color: #FFFFFF;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 600px;
                margin: 20px auto;
                background-color: {color_card};
                border: 1px solid rgba(60, 215, 255, 0.15);
                border-radius: 12px;
                overflow: hidden;
            }}
            .header {{
                padding: 30px;
                text-align: center;
                background: linear-gradient(135deg, rgba(60, 215, 255, 0.1) 0%, rgba(12, 31, 48, 0.5) 100%);
                border-bottom: 1px solid rgba(60, 215, 255, 0.1);
            }}
            .header h1 {{
                font-size: 20px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 2px;
                margin: 0;
                color: {status_color};
            }}
            .header p {{
                font-size: 13px;
                color: rgba(255, 255, 255, 0.6);
                margin: 5px 0 0 0;
            }}
            .content {{
                padding: 30px;
            }}
            .metric-box {{
                background-color: rgba(0, 0, 0, 0.2);
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }}
            .metric-row {{
                display: flex;
                justify-content: space-between;
                padding: 10px 0;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }}
            .metric-row:last-child {{
                border-bottom: none;
            }}
            .label {{
                color: rgba(255, 255, 255, 0.5);
                font-size: 13px;
                text-transform: uppercase;
                font-weight: 600;
            }}
            .value {{
                font-weight: bold;
                font-size: 14px;
            }}
            .btn-cta {{
                display: block;
                width: 200px;
                margin: 30px auto 10px auto;
                text-align: center;
                background: linear-gradient(90deg, #3cd7ff 0%, #00C853 100%);
                color: #000000 !important;
                text-decoration: none;
                font-weight: bold;
                padding: 12px 24px;
                border-radius: 8px;
                text-transform: uppercase;
                font-size: 12px;
                letter-spacing: 1px;
            }}
            .footer {{
                padding: 20px;
                text-align: center;
                border-t: 1px solid rgba(255, 255, 255, 0.05);
                font-size: 11px;
                color: rgba(255, 255, 255, 0.3);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{status_header}</h1>
                <p>{status_sub}</p>
            </div>
            <div class="content">
                <div class="metric-box">
                    <div class="metric-row">
                        <span class="label">Symbol</span>
                        <span class="value" style="color: #3cd7ff;">{symbol}</span>
                    </div>
                    <div class="metric-row">
                        <span class="label">Direction</span>
                        <span class="value" style="color: {('#00C853' if side == 'LONG' else '#FF1744')};">{side}</span>
                    </div>
                    <div class="metric-row">
                        <span class="label">Strategy</span>
                        <span class="value">{strategy}</span>
                    </div>
                    <div class="metric-row">
                        <span class="label">Entry Price</span>
                        <span class="value">${entry:.4f}</span>
                    </div>
                    <div class="metric-row">
                        <span class="label">Take Profit</span>
                        <span class="value" style="color: #00C853;">${tp:.4f}</span>
                    </div>
                    <div class="metric-row">
                        <span class="label">Stop Loss</span>
                        <span class="value" style="color: #FF1744;">${sl:.4f}</span>
                    </div>
                </div>
                
                <a href="https://bot.metaversesherpa.io" class="btn-cta">Go To Dashboard</a>
            </div>
            <div class="footer">
                🏔️ Metaverse Sherpa Institutional Trading Platform • Secure Military-Grade Encryption Active
            </div>
        </div>
    </body>
    </html>
    """
