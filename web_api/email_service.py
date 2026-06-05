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

import queue
import time
import requests

# Create a thread-safe task queue
_email_queue = queue.Queue()

def _send_email_direct(to_email, subject, html_content):
    """
    Directly sends email using SMTP or Resend API (with 429 retry support).
    """
    if not to_email:
        logger.warning("No recipient email provided. Skipping dispatch.")
        return False

    # Replace unsubscribe placeholder dynamically
    unsub_url = f"https://bot.metaversesherpa.io/unsubscribe?email={to_email}"
    html_content = html_content.replace("{UNSUBSCRIBE_LINK}", unsub_url)

    # Try Resend API first if key exists
    if RESEND_API_KEY:
        for attempt in range(3):
            try:
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
                    return True
                elif resp.status_code == 429:
                    # Rate limit hit, backoff and retry
                    retry_after = 2.0 ** (attempt + 1)
                    logger.warning(f"⚠️ Resend 429 Rate Limit hit. Retrying in {retry_after}s...")
                    time.sleep(retry_after)
                else:
                    logger.error(f"❌ Resend API failed: {resp.status_code} - {resp.text}")
                    break
            except Exception as res_err:
                logger.error(f"❌ Failed sending email via Resend API: {res_err}")
                break

    # Fallback to SMTP
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not fully configured. Email was not sent.")
        return False

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
        return True
    except Exception as e:
        logger.error(f"❌ Background SMTP delivery failed: {e}")
        return False

def _email_worker():
    """
    Background worker that processes the email queue sequentially.
    Enforces a rate limit for Resend API to stay under 5 req/sec.
    """
    while True:
        try:
            task = _email_queue.get()
            to_email, subject, html_content = task
            
            start_time = time.time()
            _send_email_direct(to_email, subject, html_content)
            elapsed = time.time() - start_time
            
            # Sleep if needed to ensure at least 0.22 seconds spacing between Resend calls (approx 4.5 req/sec max)
            if RESEND_API_KEY:
                delay = max(0.0, 0.22 - elapsed)
                if delay > 0:
                    time.sleep(delay)
                    
            _email_queue.task_done()
        except Exception as err:
            logger.error(f"Email worker error: {err}")
            time.sleep(1)

# Start background daemon worker thread
_worker_thread = threading.Thread(target=_email_worker, daemon=True)
_worker_thread.start()

def send_alert_email(to_email, subject, html_content):
    """
    Public asynchronous entry point to dispatch emails without VPS blockage.
    Enqueues the email to the rate-limited background worker.
    """
    _email_queue.put((to_email, subject, html_content))

def get_signal_alert_html(symbol, side, strategy, entry, tp, sl, resolution=None, pnl_pct=None, is_premium_user=True):
    """
    Generates premium responsive HTML email template for trading signals.
    """
    from bot.config import is_stock
    if is_stock(symbol):
        symbol_link = f'<a href="https://marketmasters.ai/stocks/{symbol}" style="color: #3cd7ff; text-decoration: underline;">{symbol}</a>'
    else:
        clean_sym = symbol.replace("/", "").split(":")[0]
        symbol_link = f'<a href="https://marketmasters.ai/currency/{clean_sym}" style="color: #3cd7ff; text-decoration: underline;">{symbol}</a>'

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
        status_sub = "Boom! That's one more step up the mountain!"
        status_color = "#00C853"
    elif resolution == "sl":
        status_header = f"❌ STOP LOSS TRIGGERED: {pnl_str}"
        status_sub = "Sometimes on a hike, you get off course.. Let's get back on course and continue up the mountain!"
        status_color = "#FF1744"
    elif resolution == "closed":
        status_header = f"🔒 POSITION EXITED: {pnl_str}"
        status_sub = "Position was manually exited successfully."
        status_color = "#ffdb3c"
        
    if not is_premium_user and resolution is None:
        teaser_link = f'<a href="https://bot.metaversesherpa.io/#/premium" style="color: #D500F9; text-decoration: none; font-size: 12px; font-weight: bold; background: rgba(213, 0, 249, 0.1); padding: 4px 8px; border-radius: 4px; border: 1px solid rgba(213, 0, 249, 0.3);">Upgrade to Premium</a>'
        entry_val = teaser_link
        tp_val = teaser_link
        sl_val = teaser_link
    else:
        entry_val = f"${entry:.4f}"
        tp_val = f'<span style="color: #00C853;">${tp:.4f}</span>'
        sl_val = f'<span style="color: #FF1744;">${sl:.4f}</span>'
        
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="color-scheme" content="light dark">
        <meta name="supported-color-schemes" content="light dark">
        <title>Metaverse Sherpa Alerts</title>
        <style>
            :root {{
                color-scheme: light dark;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background-color: {color_bg};
                background-image: linear-gradient({color_bg}, {color_bg});
                color: #FFFFFF;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 600px;
                margin: 20px auto;
                background-color: {color_card};
                background-image: linear-gradient({color_card}, {color_card});
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
                border-top: 1px solid rgba(255, 255, 255, 0.05);
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
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #1a222e; border-radius: 8px; margin-bottom: 20px; border: 1px solid #2a3546; border-collapse: separate; overflow: hidden;">
                    <tr>
                        <td style="padding: 15px 20px; border-bottom: 1px solid #2a3546;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td align="left" style="color: #8892b0; font-size: 12px; text-transform: uppercase; font-weight: 600; width: 40%;">Symbol</td>
                                    <td align="right" style="color: #3cd7ff; font-weight: bold; font-size: 14px; width: 60%;">{symbol_link}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 15px 20px; border-bottom: 1px solid #2a3546;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td align="left" style="color: #8892b0; font-size: 12px; text-transform: uppercase; font-weight: 600; width: 40%;">Direction</td>
                                    <td align="right" style="color: {('#00C853' if side == 'LONG' else '#FF1744')}; font-weight: bold; font-size: 14px; width: 60%;">{side}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 15px 20px; border-bottom: 1px solid #2a3546;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td align="left" style="color: #8892b0; font-size: 12px; text-transform: uppercase; font-weight: 600; width: 40%;">Strategy</td>
                                    <td align="right" style="color: #FFFFFF; font-weight: bold; font-size: 14px; width: 60%;">{strategy}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 15px 20px; border-bottom: 1px solid #2a3546;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td align="left" style="color: #8892b0; font-size: 12px; text-transform: uppercase; font-weight: 600; width: 40%;">Entry Price</td>
                                    <td align="right" style="color: #FFFFFF; font-weight: bold; font-size: 14px; width: 60%;">{entry_val}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 15px 20px; border-bottom: 1px solid #2a3546;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td align="left" style="color: #8892b0; font-size: 12px; text-transform: uppercase; font-weight: 600; width: 40%;">Take Profit</td>
                                    <td align="right" style="font-weight: bold; font-size: 14px; width: 60%;">{tp_val}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 15px 20px;">
                            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td align="left" style="color: #8892b0; font-size: 12px; text-transform: uppercase; font-weight: 600; width: 40%;">Stop Loss</td>
                                    <td align="right" style="font-weight: bold; font-size: 14px; width: 60%;">{sl_val}</td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
                
                <a href="https://bot.metaversesherpa.io" class="btn-cta">Go To Dashboard</a>
            </div>
            <div class="footer">
                🏔️ Metaverse Sherpa Institutional Trading Platform • Secure Military-Grade Encryption Active
                <br><br>
                Do you prefer silent hikes in the Metaverse? <br>
                <a href="{{UNSUBSCRIBE_LINK}}" style="color: #3cd7ff; text-decoration: underline;">Click here to silence the noise (unsubscribe)</a>.
            </div>

        </div>
    </body>
    </html>
    """

def get_daily_summary_html(signals_opened, signals_closed):
    """
    Generates premium responsive HTML email template for daily trading summaries.
    """
    from bot.config import is_stock
    color_bg = "#0B0E14"
    color_card = "#141A24"
    
    opened_rows = ""
    if not signals_opened:
        opened_rows = '<tr><td colspan="4" style="padding: 15px; text-align: center; color: rgba(255,255,255,0.4); font-size: 13px;">No new signals opened today.</td></tr>'
    else:
        for s in signals_opened:
            sym = s['symbol']
            if is_stock(sym):
                symbol_link = f'<a href="https://marketmasters.ai/stocks/{sym}" style="color: #3cd7ff; text-decoration: underline;">{sym}</a>'
            else:
                clean_sym = sym.replace("/", "").split(":")[0]
                symbol_link = f'<a href="https://marketmasters.ai/currency/{clean_sym}" style="color: #3cd7ff; text-decoration: underline;">{sym}</a>'
            direction_color = "#00C853" if s['side'] in ['buy', 'long', 'LONG'] else "#FF1744"
            direction_label = "LONG" if s['side'] in ['buy', 'long', 'LONG'] else "SHORT"
            opened_rows += f"""
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                <td style="padding: 12px 10px; font-weight: bold; color: #3cd7ff; font-size: 14px;">{symbol_link}</td>
                <td style="padding: 12px 10px; font-weight: bold; color: {direction_color}; font-size: 12px;">{direction_label}</td>
                <td style="padding: 12px 10px; color: #FFF; font-size: 13px;">${s['entry_price']:.4f}</td>
                <td style="padding: 12px 10px; color: rgba(255,255,255,0.6); font-size: 12px;">{s['strategy']}</td>
            </tr>
            """
            
    closed_rows = ""
    if not signals_closed:
        closed_rows = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: rgba(255,255,255,0.4); font-size: 13px;">No positions resolved today.</td></tr>'
    else:
        for s in signals_closed:
            sym = s['symbol']
            if is_stock(sym):
                symbol_link = f'<a href="https://marketmasters.ai/stocks/{sym}" style="color: #3cd7ff; text-decoration: underline;">{sym}</a>'
            else:
                clean_sym = sym.replace("/", "").split(":")[0]
                symbol_link = f'<a href="https://marketmasters.ai/currency/{clean_sym}" style="color: #3cd7ff; text-decoration: underline;">{sym}</a>'
            direction_color = "#00C853" if s['side'] in ['buy', 'long', 'LONG'] else "#FF1744"
            direction_label = "LONG" if s['side'] in ['buy', 'long', 'LONG'] else "SHORT"
            
            pnl_pct = s.get('pnl_pct', 0.0)
            from bot.config import CRYPTO_LEVERAGE
            # Apply crypto leverage display multiplier
            if not is_stock(sym):
                pnl_pct *= CRYPTO_LEVERAGE
                
            pnl_color = "#00C853" if pnl_pct >= 0 else "#FF1744"
            pnl_str = f"{pnl_pct:+.2f}%"
            
            closed_rows += f"""
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                <td style="padding: 12px 10px; font-weight: bold; color: #3cd7ff; font-size: 14px;">{symbol_link}</td>
                <td style="padding: 12px 10px; font-weight: bold; color: {direction_color}; font-size: 12px;">{direction_label}</td>
                <td style="padding: 12px 10px; font-weight: bold; color: {pnl_color}; font-size: 13px;">{pnl_str}</td>
                <td style="padding: 12px 10px; color: rgba(255,255,255,0.6); font-size: 12px;">{s['status'].upper()}</td>
                <td style="padding: 12px 10px; color: rgba(255,255,255,0.5); font-size: 12px;">{s['strategy']}</td>
            </tr>
            """
            
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="color-scheme" content="light dark">
        <meta name="supported-color-schemes" content="light dark">
        <title>Metaverse Sherpa Daily Digest</title>
        <style>
            :root {{
                color-scheme: light dark;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background-color: {color_bg};
                background-image: linear-gradient({color_bg}, {color_bg});
                color: #FFFFFF;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 600px;
                margin: 20px auto;
                background-color: {color_card};
                background-image: linear-gradient({color_card}, {color_card});
                border: 1px solid rgba(60, 215, 255, 0.15);
                border-radius: 12px;
                overflow: hidden;
            }}
            .header {{
                padding: 35px 30px;
                text-align: center;
                background: linear-gradient(135deg, rgba(60, 215, 255, 0.1) 0%, rgba(12, 31, 48, 0.5) 100%);
                border-bottom: 1px solid rgba(60, 215, 255, 0.1);
            }}
            .header h1 {{
                font-size: 22px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 2px;
                margin: 0;
                color: #3cd7ff;
            }}
            .header p {{
                font-size: 13px;
                color: rgba(255, 255, 255, 0.6);
                margin: 8px 0 0 0;
            }}
            .content {{
                padding: 30px;
            }}
            .section-title {{
                font-size: 15px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 1px;
                color: #D500F9;
                margin: 0 0 15px 0;
                border-left: 3px solid #D500F9;
                padding-left: 10px;
            }}
            .table-container {{
                background-color: rgba(0, 0, 0, 0.2);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                margin-bottom: 30px;
                overflow: hidden;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                text-align: left;
            }}
            th {{
                background-color: rgba(255, 255, 255, 0.02);
                padding: 12px 10px;
                font-size: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
                color: rgba(255,255,255,0.4);
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }}
            .btn-cta {{
                display: block;
                width: 220px;
                margin: 20px auto 10px auto;
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
                border-top: 1px solid rgba(255, 255, 255, 0.05);
                font-size: 11px;
                color: rgba(255, 255, 255, 0.3);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🏔️ Daily Signals Digest</h1>
                <p>Metaverse Sherpa Institutional Algorithmic Performance Summary</p>
            </div>
            <div class="content">
                
                <h3 class="section-title">🛰️ New Signals Opened</h3>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Entry</th>
                                <th>Strategy</th>
                            </tr>
                        </thead>
                        <tbody>
                            {opened_rows}
                        </tbody>
                    </table>
                </div>

                <h3 class="section-title">🏆 Signals Resolved</h3>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>PnL</th>
                                <th>Status</th>
                                <th>Strategy</th>
                            </tr>
                        </thead>
                        <tbody>
                            {closed_rows}
                        </tbody>
                    </table>
                </div>
                
                <a href="https://bot.metaversesherpa.io" class="btn-cta">Access Trading Console</a>
            </div>
            <div class="footer">
                🏔️ Metaverse Sherpa Institutional Trading Platform • Secure Military-Grade Encryption Active
                <br><br>
                Do you prefer silent hikes in the Metaverse? <br>
                <a href="{{UNSUBSCRIBE_LINK}}" style="color: #3cd7ff; text-decoration: underline;">Click here to silence the noise (unsubscribe)</a>.
            </div>
        </div>
    </body>
    </html>
    """


