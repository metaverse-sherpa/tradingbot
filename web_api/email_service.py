import os
import threading
import logging

# Import utils_gcp to fetch secrets from Google Secret Manager
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils_gcp import get_secret

logger = logging.getLogger("email_service")

from web_api.disclaimer import NFA_MEDIUM_HTML, NFA_SHORT_TEXT

# Resend API Key
RESEND_API_KEY = get_secret("RESEND_API_KEY") or os.getenv("RESEND_API_KEY", "")

SENDER_EMAIL = get_secret("SMTP_SENDER_EMAIL") or os.getenv("SMTP_SENDER_EMAIL", "")

import queue
import time
import requests

# Create a thread-safe task queue
_email_queue = queue.Queue()

import datetime

_quota_exceeded_date = None

def _send_email_direct(to_email, subject, html_content):
    """
    Directly sends email using SMTP or Resend API (with 429 retry support).
    """
    global _quota_exceeded_date

    if not to_email:
        logger.warning("No recipient email provided. Skipping dispatch.")
        return False

    # Replace unsubscribe placeholder dynamically
    unsub_url = f"https://bot.metaversesherpa.io/unsubscribe?email={to_email}"
    html_content = html_content.replace("{UNSUBSCRIBE_LINK}", unsub_url)

    # Try Resend API first if key exists
    if RESEND_API_KEY:
        current_date = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        if _quota_exceeded_date == current_date:
            logger.warning(f"Skipping Resend API dispatch; daily/monthly quota limit has already been exceeded for today ({current_date}).")
            return False

        for attempt in range(3):
            try:
                url = "https://api.resend.com/emails"
                headers = {
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "from": "Metaverse Sherpa Bot Alerts <" + (SENDER_EMAIL or "alerts@metaversesherpa.io") + ">",
                    "to": [to_email],
                    "subject": subject,
                    "html": html_content
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                if resp.status_code in [200, 201]:
                    logger.info(f"✅ Email successfully sent via Resend API to {to_email}")
                    return True
                elif resp.status_code == 429:
                    is_quota_limit = False
                    err_name = ""
                    try:
                        err_json = resp.json()
                        err_name = err_json.get("name", "")
                        if "quota_exceeded" in err_name:
                            is_quota_limit = True
                    except Exception:
                        pass

                    if is_quota_limit:
                        logger.error(f"❌ Resend API Quota Exceeded ({err_name}): {resp.text}")
                        # Record the exceeded state for today
                        _quota_exceeded_date = current_date
                        
                        # Send alert to Telegram admin once
                        try:
                            from utils_error import send_telegram_alert
                            send_telegram_alert(
                                "Resend API Quota Exceeded",
                                Exception(f"Resend email quota limit hit ({err_name}). Message: {resp.text}\nEmail sending is disabled for today.")
                            )
                        except Exception as telegram_err:
                            logger.error(f"Failed to send Telegram alert for quota limit: {telegram_err}")
                        return False
                    else:
                        # Rate limit hit, backoff and retry
                        retry_after = 2.0 ** (attempt + 1)
                        logger.warning(f"⚠️ Resend 429 Rate Limit hit. Retrying in {retry_after}s...")
                        time.sleep(retry_after)
                else:
                    logger.error(f"❌ Resend API failed: {resp.status_code} - {resp.text}")
                    try:
                        from utils_error import send_telegram_alert
                        send_telegram_alert(f"Email Delivery Error (Resend API)", Exception(f"Status {resp.status_code}: {resp.text}"))
                    except: pass
                    break
            except Exception as res_err:
                logger.error(f"❌ Failed sending email via Resend API: {res_err}")
                try:
                    from utils_error import send_telegram_alert
                    send_telegram_alert(f"Email Delivery Error (Resend API)", res_err)
                except: pass
                return False
                
    else:
        logger.warning("RESEND_API_KEY not configured. Email was not sent.")

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
    import re
    if re.match(r"^user_\d+_\d+@metaversesherpa\.io$", to_email):
        logger.info(f"Skipping email to test account: {to_email}")
        return
        
    _email_queue.put((to_email, subject, html_content))

def get_signal_alert_html(symbol, side, strategy, entry, tp, sl, resolution=None, pnl_pct=None, is_premium_user=True):
    """
    Generates premium responsive HTML email template for trading signals.
    """
    from bot.config import is_stock
    if is_stock(symbol):
        symbol_link = f'<span style="color: #3cd7ff; text-decoration: underline;">{symbol}</span>'
    else:
        symbol_link = f'<span style="color: #3cd7ff; text-decoration: underline;">{symbol}</span>'

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
        teaser_link = f'<a href="https://bot.metaversesherpa.io/premium" style="color: #D500F9; text-decoration: none; font-size: 12px; font-weight: bold; background: rgba(213, 0, 249, 0.1); padding: 4px 8px; border-radius: 4px; border: 1px solid rgba(213, 0, 249, 0.3);">Upgrade to Premium</a>'
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
                🏔️ Metaverse Sherpa Trading Platform
                {NFA_MEDIUM_HTML}
                <br>
                Do you prefer silent hikes in the Metaverse? <br>
                <a href="{{UNSUBSCRIBE_LINK}}" style="color: #3cd7ff; text-decoration: underline;">Click here to silence the noise (unsubscribe)</a>.
            </div>

        </div>
    </body>
    </html>
    """



def get_combined_daily_summary_html(is_premium=False,
                                     has_stock_exchange=False, stock_portfolio_data=None, stock_open_trades=None, stock_hypothetical_data=None,
                                     has_crypto_exchange=False, crypto_portfolio_data=None, crypto_open_trades=None, crypto_hypothetical_data=None,
                                     stock_opened=None, stock_closed=None, crypto_opened=None, crypto_closed=None,
                                     recent_recommendations=None):
    """
    Generates premium/free tailored daily combined session summary HTML.
    """
    color_bg = "#0B0E14"
    color_card = "#141A24"
    
    header_section = """
        <div style="padding: 35px 30px; text-align: center; background: #0c1f30; background-image: linear-gradient(135deg, rgba(60, 215, 255, 0.1) 0%, rgba(213, 0, 249, 0.1) 100%); border-bottom: 1px solid rgba(60, 215, 255, 0.1);">
            <h1 style="font-size: 22px; font-weight: bold; text-transform: uppercase; letter-spacing: 2px; margin: 0; color: #FFFFFF;">🏔️ Daily Digest</h1>
            <p style="font-size: 13px; color: #8892b0; margin: 8px 0 0 0;">Metaverse Sherpa Daily Performance Summary</p>
        </div>
    """
    
    content = ""
    
    def render_section(title, icon, accent_color, has_exchange, portfolio_data, open_trades, hypothetical_data, global_opened, global_closed):
        section_content = f'<h2 style="font-size: 16px; font-weight: bold; text-transform: uppercase; letter-spacing: 1.5px; color: {accent_color}; margin: 20px 0 20px 0; border-bottom: 1px solid #2a3546; padding-bottom: 10px;">{icon} {title}</h2>'
        
        # Portfolio Summary / Hypothetical logic (same as weekly)
        if is_premium:
            if has_exchange:
                equity = portfolio_data.get("equity", 0.0)
                daily_pnl_pct = portfolio_data.get("daily_pnl_pct", 0.0)
                daily_pnl_usd = portfolio_data.get("daily_pnl_usd", 0.0)
                pnl_color = "#00C853" if daily_pnl_pct >= 0 else "#FF1744"
                sign = "+" if daily_pnl_pct >= 0 else ""
                usd_sign = "+" if daily_pnl_usd >= 0 else ""
                
                section_content += f"""
                <div style="background-color: #1a222e; border-radius: 8px; border: 1px solid #2a3546; padding: 20px; margin-bottom: 25px; text-align: center;">
                    <div style="font-size: 11px; text-transform: uppercase; color: #8892b0; font-weight: bold; margin-bottom: 5px; letter-spacing: 0.5px;">Portfolio Equity</div>
                    <div style="font-size: 28px; font-weight: bold; color: #FFFFFF; margin-bottom: 5px;">${equity:,.2f} USD</div>
                    <div style="font-size: 16px; color: {pnl_color}; font-weight: bold;">
                        Daily Performance: {sign}{daily_pnl_pct:.2f}% ({usd_sign}${daily_pnl_usd:,.2f})
                    </div>
                </div>
                """
            else:
                hypo_pnl = hypothetical_data.get("cumulative_pnl", 0.0)
                hypo_balance = 1000.0 + hypo_pnl
                hypo_growth = (hypo_pnl / 1000.0) * 100
                wins = hypothetical_data.get("wins", 0)
                losses = hypothetical_data.get("losses", 0)
                win_rate = hypothetical_data.get("win_rate", 0.0)
                pnl_color = "#00C853" if hypo_pnl >= 0 else "#FF1744"
                sign = "+" if hypo_pnl >= 0 else ""
                
                section_content += f"""
                <div style="background-color: #1a222e; border-radius: 8px; border: 1px dashed {accent_color}; padding: 20px; margin-bottom: 25px; text-align: center; position: relative; overflow: hidden;">
                    <div style="position: absolute; top: 0; right: 0; background-color: {accent_color}; color: #000; font-size: 9px; font-weight: bold; padding: 3px 10px; border-bottom-left-radius: 8px; text-transform: uppercase;">Hypothetical</div>
                    <div style="font-size: 11px; text-transform: uppercase; color: #8892b0; font-weight: bold; margin-bottom: 5px; letter-spacing: 0.5px;">Simulated Portfolio Equity</div>
                    <div style="font-size: 28px; font-weight: bold; color: #FFFFFF; margin-bottom: 5px;">${hypo_balance:,.2f} USD</div>
                    <div style="font-size: 16px; color: {pnl_color}; font-weight: bold;">
                        Cumulative Performance: {sign}{hypo_growth:.2f}% ({sign}${hypo_pnl:,.2f})
                    </div>
                    <div style="font-size: 13px; color: #8892b0; margin-top: 10px;">
                        <b>Win Rate:</b> {win_rate:.1f}% ({wins} W | {losses} L)
                    </div>
                    <p style="font-size: 11px; color: #8892b0; margin: 15px 0 0 0; font-style: italic;">
                        * This is a simulation of what your {title.lower()} portfolio would look like with our automated fractional execution (starting from a $1,000 base). Connect your exchange to see your real performance!
                    </p>
                </div>
                
                <div style="background-color: #1a1126; border: 1px solid rgba(213, 0, 249, 0.3); border-radius: 8px; padding: 20px; margin-bottom: 25px; text-align: center;">
                    <h3 style="color: #FF1744; margin: 0 0 10px 0; font-size: 16px; font-weight: bold; text-transform: uppercase;">⚠️ Exchange Connection Required</h3>
                    <p style="font-size: 13px; color: #b3a9c9; margin: 0 0 15px 0; line-height: 1.5;">
                        You have Premium Access, but your exchange API keys for {title.lower()} are missing or invalid. Please connect your exchange in the trading console to enable real-time tracking and autopilot execution.
                    </p>
                    <a href="https://bot.metaversesherpa.io/settings" style="display: inline-block; background: linear-gradient(90deg, #3cd7ff 0%, #D500F9 100%); color: #000000 !important; text-decoration: none; font-weight: bold; padding: 10px 20px; border-radius: 6px; text-transform: uppercase; font-size: 11px; letter-spacing: 1px;">Connect Exchange</a>
                </div>
                """

        active_headers = f"""
                            <tr style="background-color: #111822;">
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'25%' if (is_premium and has_exchange) else '40%'};">Symbol</th>
                                {'<th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: 30%;">Parameters</th>' if (is_premium and has_exchange) else ''}
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'15%' if (is_premium and has_exchange) else '20%'};">Daily PnL</th>
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'15%' if (is_premium and has_exchange) else '20%'};">Total PnL</th>
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'15%' if (is_premium and has_exchange) else '20%'};">Target PnL</th>
                            </tr>
        """

        open_rows = ""
        my_symbols = []
        if is_premium and has_exchange:
            if open_trades:
                open_trades_sorted = sorted(open_trades, key=lambda x: x.get('current_pnl_pct', 0.0), reverse=True)
                for t in open_trades_sorted:
                    pnl_pct = t.get("current_pnl_pct", 0.0)
                    daily_pnl_pct = t.get("daily_pnl_pct", 0.0)
                    target_pnl_pct = t.get("target_pnl_pct", 0.0)
                    
                    t_pnl_color = "#00C853" if pnl_pct >= 0 else "#FF1744"
                    daily_pnl_color = "#00C853" if daily_pnl_pct >= 0 else "#FF1744"
                    t_pnl_weight = "bold" if pnl_pct >= 0 else "normal"
                    daily_pnl_weight = "bold" if daily_pnl_pct >= 0 else "normal"
                    
                    sym = t['symbol']
                    my_symbols.append(sym)
                    clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                    is_long = t.get('side', '').upper() in ['BUY', 'LONG']
                    dir_emoji = "📈" if is_long else "📉"
                    sym_html = f'<span style="color: {accent_color}; text-decoration: none;">{dir_emoji} {sym}</span>'
                    
                    open_rows += f"""
                    <tr style="border-bottom: 1px solid #2a3546; background-color: #1a222e;">
                        <td style="padding: 12px 10px; font-weight: bold; font-size: 14px; width: 25%;">{sym_html}</td>
                        <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 30%;">Entry: ${t['entry_price']:.4f}<br>SL: ${t['sl_price']:.4f}<br>TP: ${t['tp_price']:.4f}</td>
                        <td style="padding: 12px 10px; font-weight: {daily_pnl_weight}; color: {daily_pnl_color}; font-size: 13px; width: 15%;">{daily_pnl_pct:+.2f}%</td>
                        <td style="padding: 12px 10px; font-weight: {t_pnl_weight}; color: {t_pnl_color}; font-size: 13px; width: 15%;">{pnl_pct:+.2f}%</td>
                        <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 15%;">+{target_pnl_pct:.1f}%</td>
                    </tr>
                    """
                    
            # Check global opened for missed signals
            if global_opened:
                for s in global_opened:
                    if s['symbol'] not in my_symbols:
                        pnl_pct = s.get('current_pnl_pct', 0.0)
                        daily_pnl_pct = s.get('daily_pnl_pct', 0.0)
                        target_tp_pct = s.get('target_tp_pct', 0.0)
                        t_pnl_color = "#00C853" if pnl_pct >= 0 else "#FF1744"
                        daily_pnl_color = "#00C853" if daily_pnl_pct >= 0 else "#FF1744"
                        
                        sym = s['symbol']
                        clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                        is_long = s.get('side', '').upper() in ['BUY', 'LONG']
                        dir_emoji = "📈" if is_long else "📉"
                        sym_html = f'<span style="color: {accent_color}; text-decoration: none;">{dir_emoji} {sym}</span>'
                        
                        open_rows += f"""
                        <tr style="border-bottom: 1px solid #2a3546; background-color: #1a222e; opacity: 0.7;">
                            <td style="padding: 12px 10px; font-weight: bold; font-size: 14px; width: 25%;">{sym_html}</td>
                            <td style="padding: 12px 10px; color: #FF9800; font-style: italic; font-size: 13px; width: 30%;">⚠️ Not Positioned</td>
                            <td style="padding: 12px 10px; color: {daily_pnl_color}; font-size: 13px; width: 15%;">{daily_pnl_pct:+.2f}%</td>
                            <td style="padding: 12px 10px; color: {t_pnl_color}; font-size: 13px; width: 15%;">{pnl_pct:+.2f}%</td>
                            <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 15%;">+{target_tp_pct:.1f}%</td>
                        </tr>
                        """
        else:
            # Free user (or premium w/o exchange), just show global opened
            if global_opened:
                global_opened_sorted = sorted(global_opened, key=lambda x: x.get('current_pnl_pct', 0.0), reverse=True)
                for s in global_opened_sorted:
                    sym = s['symbol']
                    clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                    pnl_pct = s.get('current_pnl_pct', 0.0)
                    daily_pnl_pct = s.get('daily_pnl_pct', 0.0)
                    target_tp_pct = s.get('target_tp_pct', 0.0)
                    
                    t_pnl_color = "#00C853" if pnl_pct >= 0 else "#FF1744"
                    daily_pnl_color = "#00C853" if daily_pnl_pct >= 0 else "#FF1744"
                    t_pnl_weight = "bold" if pnl_pct >= 0 else "normal"
                    daily_pnl_weight = "bold" if daily_pnl_pct >= 0 else "normal"
                    
                    is_long = s.get('side', '').upper() in ['BUY', 'LONG']
                    dir_emoji = "📈" if is_long else "📉"
                    sym_html = f'<span style="color: {accent_color}; text-decoration: none;">{dir_emoji} {sym}</span>'
                    
                    open_rows += f"""
                    <tr style="border-bottom: 1px solid #2a3546; background-color: #1a222e;">
                        <td style="padding: 12px 10px; font-weight: bold; font-size: 14px; width: 40%;">{sym_html}</td>
                        <td style="padding: 12px 10px; font-weight: {daily_pnl_weight}; color: {daily_pnl_color}; font-size: 13px; width: 20%;">{daily_pnl_pct:+.2f}%</td>
                        <td style="padding: 12px 10px; font-weight: {t_pnl_weight}; color: {t_pnl_color}; font-size: 13px; width: 20%;">{pnl_pct:+.2f}%</td>
                        <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 20%;">+{target_tp_pct:.1f}%</td>
                    </tr>
                    """

        if not open_rows:
            col_count = "5" if (is_premium and has_exchange) else "4"
            open_rows = f'<tr><td colspan="{col_count}" style="padding: 15px; text-align: center; color: #8892b0; font-size: 13px; background-color: #1a222e;">No active {title.lower()} positions today.</td></tr>'

        section_content += f"""
        <h3 style="font-size: 14px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; color: {accent_color}; margin: 25px 0 15px 0; border-left: 3px solid {accent_color}; padding-left: 10px;">🛰️ Active Positions</h3>
        <div style="background-color: #1a222e; border-radius: 8px; border: 1px solid #2a3546; overflow: hidden; margin-bottom: 30px;">
            <table style="width: 100%; border-collapse: collapse; text-align: left;">
                <thead>{active_headers}</thead>
                <tbody>{open_rows}</tbody>
            </table>
        </div>
        """

        # Closed Positions
        closed_headers = f"""
                            <tr style="background-color: #111822;">
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'25%' if is_premium else '40%'};">Symbol</th>
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'25%' if is_premium else '30%'};">Status</th>
                                {'<th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: 30%;">Parameters</th>' if is_premium else ''}
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'20%' if is_premium else '30%'};">Final PnL</th>
                            </tr>
        """

        closed_rows = ""
        if global_closed:
            for s in global_closed:
                sym = s['symbol']
                clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                pnl_pct = s.get('pnl_pct', 0.0)
                pnl_color = "#00C853" if pnl_pct >= 0 else "#FF1744"
                
                is_long = s.get('side', '').upper() in ['BUY', 'LONG']
                dir_emoji = "📈" if is_long else "📉"
                sym_html = f'<span style="color: {accent_color}; text-decoration: none;">{dir_emoji} {sym}</span>'
                
                if is_premium:
                    exit_price = s.get('close_price') or 0.0
                    closed_rows += f"""
                    <tr style="border-bottom: 1px solid #2a3546; background-color: #1a222e;">
                        <td style="padding: 12px 10px; font-weight: bold; font-size: 14px; width: 25%;">{sym_html}</td>
                        <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 25%;">Exited</td>
                        <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 30%;">Entry: ${s.get('entry_price', 0.0):.4f}<br>Exit: ${exit_price:.4f}</td>
                        <td style="padding: 12px 10px; font-weight: bold; color: {pnl_color}; font-size: 13px; width: 20%;">{pnl_pct:+.2f}%</td>
                    </tr>
                    """
                else:
                    st = "Hit Target" if s.get('status') == 'tp' else "Hit Stop Loss" if s.get('status') == 'sl' else "Closed"
                    closed_rows += f"""
                    <tr style="border-bottom: 1px solid #2a3546; background-color: #1a222e;">
                        <td style="padding: 12px 10px; font-weight: bold; font-size: 14px; width: 40%;">{sym_html}</td>
                        <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 30%;">{st}</td>
                        <td style="padding: 12px 10px; font-weight: bold; color: {pnl_color}; font-size: 13px; width: 30%;">{pnl_pct:+.2f}%</td>
                    </tr>
                    """

        if not closed_rows:
            col_count = "4" if is_premium else "3"
            closed_rows = f'<tr><td colspan="{col_count}" style="padding: 15px; text-align: center; color: #8892b0; font-size: 13px; background-color: #1a222e;">No {title.lower()} positions resolved today.</td></tr>'

        section_content += f"""
        <h3 style="font-size: 14px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; color: #FF1744; margin: 25px 0 15px 0; border-left: 3px solid #FF1744; padding-left: 10px;">🏆 Positions Closed (Last 24 Hours)</h3>
        <div style="background-color: #1a222e; border-radius: 8px; border: 1px solid #2a3546; overflow: hidden; margin-bottom: 40px;">
            <table style="width: 100%; border-collapse: collapse; text-align: left;">
                <thead>{closed_headers}</thead>
                <tbody>{closed_rows}</tbody>
            </table>
        </div>
        """

        return section_content

    content += render_section("Stock Markets", "📈", "#3cd7ff", has_stock_exchange, stock_portfolio_data, stock_open_trades, stock_hypothetical_data, stock_opened, stock_closed)
    content += render_section("Crypto Markets", "₿", "#D500F9", has_crypto_exchange, crypto_portfolio_data, crypto_open_trades, crypto_hypothetical_data, crypto_opened, crypto_closed)
    
    recommendations_section = ""
    if is_premium and recent_recommendations:
        recs_content = ""
        for rec in recent_recommendations:
            cat = rec.get("category", "stock").lower()
            sym = rec.get("symbol", "")
            icon = "📈" if cat == "stock" else "🪙"
            name = rec.get("name") or sym
            rationale = rec.get("rationale", "")
            metrics = rec.get("metrics_summary", "")
            tp = rec.get("target_price", 0)
            sl = rec.get("stop_loss", 0)
            growth = rec.get("expected_growth_pct", 0)
            timeframe = rec.get("estimated_timeframe", "")
            
            recs_content += f"""
            <div style="background-color: #1a222e; border-radius: 8px; border: 1px solid #2a3546; padding: 15px; margin-bottom: 15px; text-align: left;">
                <div style="font-size: 14px; font-weight: bold; color: #3cd7ff; margin-bottom: 5px;">{icon} {sym} <span style="color:#8892b0; font-size: 12px; font-weight:normal;">({name})</span></div>
                <div style="font-size: 12px; color: #b3a9c9; margin-bottom: 5px;">{metrics}</div>
                <div style="font-size: 12px; color: #00C853; font-weight: bold; margin-bottom: 8px;">Target: ${tp} (Stop Loss: ${sl}) | +{growth}% in {timeframe}</div>
                <div style="font-size: 11px; color: #8892b0; line-height: 1.4;"><i>{rationale}</i></div>
            </div>
            """
        
        if recs_content:
            recommendations_section = f"""
            <h2 style="font-size: 16px; font-weight: bold; text-transform: uppercase; letter-spacing: 1.5px; color: #FFD700; margin: 30px 0 20px 0; border-bottom: 1px solid #2a3546; padding-bottom: 10px;">💡 Fresh Investment Ideas</h2>
            <p style="font-size: 13px; color: #8892b0; margin: 0 0 15px 0;">Top AI-selected buys tailored to your profile generated in the last 24 hours.</p>
            {recs_content}
            <div style="text-align: center; margin-top: 15px;">
                <a href="https://bot.metaversesherpa.io/recommendations" style="display: inline-block; background: #1a222e; border: 1px solid #FFD700; color: #FFD700 !important; text-decoration: none; font-weight: bold; padding: 10px 20px; border-radius: 6px; text-transform: uppercase; font-size: 11px; letter-spacing: 1px;">View Charts & Track Recommendations</a>
            </div>
            """
    
    upsell_section = ""
    if not is_premium:
        upsell_section = f"""
        <div style="background-color: #1a1126; border: 1px solid rgba(213, 0, 249, 0.3); border-radius: 8px; padding: 20px; margin-top: 30px; text-align: center;">
            <h3 style="color: #D500F9; margin: 0 0 10px 0; font-size: 16px; font-weight: bold; text-transform: uppercase;">🚀 UNLOCK FULL AUTOPILOT</h3>
            <p style="font-size: 12px; color: #b3a9c9; margin: 0 0 15px 0; line-height: 1.5;">
                You are receiving free signals but trades are not being executed automatically. Upgrade to <b>Premium Access</b> to unlock automated fractional execution and see exact entry/SL/TP parameters in real time.
            </p>
            <a href="https://bot.metaversesherpa.io/premium" style="display: inline-block; background: linear-gradient(90deg, #D500F9 0%, #7B1FA2 100%); color: #ffffff; text-decoration: none; font-weight: bold; padding: 10px 20px; border-radius: 6px; text-transform: uppercase; font-size: 11px; letter-spacing: 1px;">Upgrade to Premium Now</a>
        </div>
        """
        
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="color-scheme" content="light dark">
        <meta name="supported-color-schemes" content="light dark">
        <title>Sherpa Daily Digest</title>
        <style>
            :root {{
                color-scheme: light dark;
                supported-color-schemes: light dark;
            }}
        </style>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: {color_bg}; color: #FFFFFF; margin: 0; padding: 0;">
        <div style="background-color: {color_bg}; padding: 20px 10px; min-height: 100%;">
            <div style="max-width: 600px; margin: 20px auto; background-color: {color_card}; border: 1px solid rgba(60, 215, 255, 0.15); border-radius: 12px; overflow: hidden; color: #FFFFFF;">
                {header_section}
                <div style="padding: 30px;">
                    {content}
                    {recommendations_section}
                    {upsell_section}
                    <a href="https://bot.metaversesherpa.io" style="display: block; width: 220px; margin: 30px auto 10px auto; text-align: center; background: linear-gradient(90deg, #3cd7ff 0%, #D500F9 100%); color: #000000 !important; text-decoration: none; font-weight: bold; padding: 12px 24px; border-radius: 8px; text-transform: uppercase; font-size: 12px; letter-spacing: 1px;">Access Trading Console</a>
                </div>
                <div style="padding: 20px; text-align: center; border-top: 1px solid #2a3546; font-size: 11px; color: #8892b0; background-color: #141A24;">
                    🏔️ Metaverse Sherpa Trading Platform
                    {{NFA_MEDIUM_HTML}}
                    <br>
                    Do you prefer silent hikes in the Metaverse? <br>
                    <a href="{{{{UNSUBSCRIBE_LINK}}}}" style="color: #3cd7ff; text-decoration: underline;">Click here to silence the noise (unsubscribe)</a>.
                </div>
            </div>
        </div>
    </body>
    </html>
    """

def get_combined_daily_summary_telegram(is_premium=False,
                                     has_stock_exchange=False, stock_portfolio_data=None, stock_open_trades=None, stock_hypothetical_data=None,
                                     has_crypto_exchange=False, crypto_portfolio_data=None, crypto_open_trades=None, crypto_hypothetical_data=None,
                                     stock_opened=None, stock_closed=None, crypto_opened=None, crypto_closed=None,
                                     recent_recommendations=None):
    lines = ["🏔️ <b>Daily Digest</b>\nMetaverse Sherpa Daily Performance Summary\n"]
    
    def render_section(title, icon, has_exchange, portfolio_data, open_trades, hypothetical_data, global_opened, global_closed):
        section_lines = [f"\n{icon} <b>{title}</b>"]
        
        if is_premium and has_exchange:
            equity = portfolio_data.get("equity", 0.0)
            daily_pnl_pct = portfolio_data.get("daily_pnl_pct", 0.0)
            daily_pnl_usd = portfolio_data.get("daily_pnl_usd", 0.0)
            sign = "+" if daily_pnl_pct >= 0 else ""
            usd_sign = "+" if daily_pnl_usd >= 0 else ""
            section_lines.append(f"<b>Portfolio Equity:</b> ${equity:,.2f} USD")
            section_lines.append(f"<b>Daily Performance:</b> {sign}{daily_pnl_pct:.2f}% ({usd_sign}${daily_pnl_usd:,.2f})\n")
        
        section_lines.append("<i>🛰️ Active Positions</i>")
        
        my_symbols = []
        has_active = False
        if is_premium and has_exchange:
            if open_trades:
                has_active = True
                open_trades_sorted = sorted(open_trades, key=lambda x: x.get('current_pnl_pct', 0.0), reverse=True)
                for t in open_trades_sorted:
                    pnl_pct = t.get("current_pnl_pct", 0.0)
                    daily_pnl_pct = t.get("daily_pnl_pct", 0.0)
                    target_pnl_pct = t.get("target_pnl_pct", 0.0)
                    sym = t['symbol']
                    my_symbols.append(sym)
                    clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                    is_long = t.get('side', '').upper() in ['BUY', 'LONG']
                    dir_emoji = "📈" if is_long else "📉"
                    sym_html = f"<b>{sym}</b>"
                    
                    section_lines.append(f"{dir_emoji} {sym_html} | Entry: ${t['entry_price']:.4f} SL: ${t['sl_price']:.4f} TP: ${t['tp_price']:.4f} | Daily: {daily_pnl_pct:+.2f}% | Total: {pnl_pct:+.2f}% | Target: +{target_pnl_pct:.1f}%")
            
            # Check global opened for missed signals
            if global_opened:
                for s in global_opened:
                    if s['symbol'] not in my_symbols:
                        has_active = True
                        pnl_pct = s.get("current_pnl_pct", 0.0)
                        daily_pnl_pct = s.get("daily_pnl_pct", 0.0)
                        target_tp_pct = s.get("target_tp_pct", 0.0)
                        sym = s['symbol']
                        clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                        is_long = s.get('side', '').upper() in ['BUY', 'LONG']
                        dir_emoji = "📈" if is_long else "📉"
                        sym_html = f"<b>{sym}</b>"
                        
                        section_lines.append(f"⚠️ {dir_emoji} {sym_html} | Not Positioned | Daily: {daily_pnl_pct:+.2f}% | Total: {pnl_pct:+.2f}% | Target: +{target_tp_pct:.1f}%")
                        
        else:
            if global_opened:
                has_active = True
                global_opened_sorted = sorted(global_opened, key=lambda x: x.get('current_pnl_pct', 0.0), reverse=True)
                for s in global_opened_sorted:
                    pnl_pct = s.get("current_pnl_pct", 0.0)
                    daily_pnl_pct = s.get("daily_pnl_pct", 0.0)
                    target_tp_pct = s.get("target_tp_pct", 0.0)
                    sym = s['symbol']
                    clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                    is_long = s.get('side', '').upper() in ['BUY', 'LONG']
                    dir_emoji = "📈" if is_long else "📉"
                    sym_html = f"<b>{sym}</b>"
                    
                    section_lines.append(f"{dir_emoji} {sym_html} | Daily: {daily_pnl_pct:+.2f}% | Total: {pnl_pct:+.2f}% | Target: +{target_tp_pct:.1f}%")

        if not has_active:
            section_lines.append(f"No active {title.lower()} positions today.")

        section_lines.append("\n<i>🏆 Positions Closed (Last 24 Hours)</i>")
        if not global_closed:
            section_lines.append(f"No {title.lower()} positions resolved today.")
        else:
            for s in global_closed:
                sym = s['symbol']
                clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                pnl_pct = s.get('pnl_pct', 0.0)
                is_long = s.get('side', '').upper() in ['BUY', 'LONG']
                dir_emoji = "📈" if is_long else "📉"
                sym_html = f"<b>{sym}</b>"
                
                if is_premium:
                    exit_price = s.get('close_price') or 0.0
                    section_lines.append(f"{dir_emoji} {sym_html} | Exited | Entry: ${s.get('entry_price', 0.0):.4f} / Exit: ${exit_price:.4f} | PnL: {pnl_pct:+.2f}%")
                else:
                    st = "Hit Target" if s.get('status') == 'tp' else "Hit Stop Loss" if s.get('status') == 'sl' else "Closed"
                    section_lines.append(f"{dir_emoji} {sym_html} | {st} | PnL: {pnl_pct:+.2f}%")

        return section_lines

    lines.extend(render_section("Stock Markets", "📈", has_stock_exchange, stock_portfolio_data, stock_open_trades, stock_hypothetical_data, stock_opened, stock_closed))
    lines.extend(render_section("Crypto Markets", "₿", has_crypto_exchange, crypto_portfolio_data, crypto_open_trades, crypto_hypothetical_data, crypto_opened, crypto_closed))

    if is_premium and recent_recommendations:
        lines.append("\n💡 <b>Fresh Investment Ideas</b>")
        lines.append("Top AI-selected buys tailored to your profile generated in the last 24 hours.\n")
        for rec in recent_recommendations:
            cat = rec.get("category", "stock").lower()
            sym = rec.get("symbol", "")
            icon = "📈" if cat == "stock" else "🪙"
            name = rec.get("name") or sym
            rationale = rec.get("rationale", "")
            tp = rec.get("target_price", 0)
            sl = rec.get("stop_loss", 0)
            growth = rec.get("expected_growth_pct", 0)
            timeframe = rec.get("estimated_timeframe", "")
            lines.append(f"{icon} <b>{sym}</b> ({name})\nTarget: ${tp} (SL: ${sl}) | +{growth}% in {timeframe}\n<i>{rationale}</i>\n")
        lines.append("<a href='https://bot.metaversesherpa.io/recommendations'>View Charts & Track Recommendations</a>")

    if not is_premium:
        lines.append("\n🚀 <b>UNLOCK FULL AUTOPILOT</b>\nUpgrade to <b>Premium Access</b> today to unlock automated fractional execution and see exact entry/SL/TP parameters in real time.\n<a href='https://bot.metaversesherpa.io/premium'>Upgrade to Premium Now</a>")

    lines.append("\n<a href='https://bot.metaversesherpa.io'>Access Trading Console</a>")
    lines.append(NFA_SHORT_TEXT)
    
    return _chunk_telegram_message("\n".join(lines))

def get_combined_weekly_summary_html(is_premium=False, 
                                     has_stock_exchange=False, stock_portfolio_data=None, stock_open_trades=None, stock_hypothetical_data=None,
                                     has_crypto_exchange=False, crypto_portfolio_data=None, crypto_open_trades=None, crypto_hypothetical_data=None,
                                     recent_recommendations=None):
    """
    Generates combined weekly stock & crypto performance update HTML.
    """
    color_bg = "#0B0E14"
    color_card = "#141A24"
    
    header_section = """
        <div style="padding: 35px 30px; text-align: center; background: #0c1f30; background-image: linear-gradient(135deg, rgba(60, 215, 255, 0.1) 0%, rgba(213, 0, 249, 0.1) 100%); border-bottom: 1px solid rgba(60, 215, 255, 0.1);">
            <h1 style="font-size: 22px; font-weight: bold; text-transform: uppercase; letter-spacing: 2px; margin: 0; color: #FFFFFF;">🏔️ Weekly Update</h1>
            <p style="font-size: 13px; color: #8892b0; margin: 8px 0 0 0;">Metaverse Sherpa Combined Weekly Performance Summary</p>
        </div>
    """
    
    content = ""
    
    # helper for rendering sections
    def render_section(title, icon, accent_color, has_exchange, portfolio_data, open_trades, hypothetical_data):
        section_content = f'<h2 style="font-size: 16px; font-weight: bold; text-transform: uppercase; letter-spacing: 1.5px; color: {accent_color}; margin: 20px 0 20px 0; border-bottom: 1px solid #2a3546; padding-bottom: 10px;">{icon} {title}</h2>'
        
        active_headers = f"""
                            <tr style="background-color: #111822;">
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'25%' if is_premium else '40%'};">Symbol</th>
                                {'<th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: 30%;">Parameters</th>' if is_premium else ''}
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'15%' if is_premium else '20%'};">Daily PnL</th>
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'15%' if is_premium else '20%'};">Total PnL</th>
                                <th style="padding: 10px; font-size: 10px; text-transform: uppercase; color: #8892b0; border-bottom: 1px solid #2a3546; width: {'15%' if is_premium else '20%'};">Target PnL</th>
                            </tr>
        """
        if is_premium:
            if has_exchange:
                equity = portfolio_data.get("equity", 0.0)
                weekly_pnl_pct = portfolio_data.get("weekly_pnl_pct", 0.0)
                weekly_pnl_usd = portfolio_data.get("weekly_pnl_usd", 0.0)
                pnl_color = "#00C853" if weekly_pnl_pct >= 0 else "#FF1744"
                sign = "+" if weekly_pnl_pct >= 0 else ""
                usd_sign = "+" if weekly_pnl_usd >= 0 else ""
                
                open_rows = ""
                if not open_trades:
                    open_rows = f'<tr><td colspan="4" style="padding: 15px; text-align: center; color: #8892b0; font-size: 13px; background-color: #1a222e;">No open {title.lower()} positions currently.</td></tr>'
                else:
                    open_trades_sorted = sorted(open_trades, key=lambda x: x.get('current_pnl_pct', 0.0), reverse=True)
                    for t in open_trades_sorted:
                        pnl_pct = t.get("current_pnl_pct", 0.0)
                        daily_pnl_pct = t.get("daily_pnl_pct", 0.0)
                        target_pnl_pct = t.get("target_pnl_pct", 0.0)
                        
                        t_pnl_color = "#00C853" if pnl_pct >= 0 else "#FF1744"
                        daily_pnl_color = "#00C853" if daily_pnl_pct >= 0 else "#FF1744"
                        t_pnl_weight = "bold" if pnl_pct >= 0 else "normal"
                        daily_pnl_weight = "bold" if daily_pnl_pct >= 0 else "normal"
                        
                        sym = t['symbol']
                        clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                        is_long = t.get('side', '').upper() in ['BUY', 'LONG']
                        dir_emoji = "📈" if is_long else "📉"
                        sym_html = f'<span style="color: {accent_color}; text-decoration: none;">{dir_emoji} {sym}</span>'
                        
                        if is_premium:
                            open_rows += f"""
                            <tr style="border-bottom: 1px solid #2a3546; background-color: #1a222e;">
                                <td style="padding: 12px 10px; font-weight: bold; font-size: 14px; width: 25%;">{sym_html}</td>
                                <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 30%;">Entry: ${t['entry_price']:.4f}<br>SL: ${t['sl_price']:.4f}<br>TP: ${t['tp_price']:.4f}</td>
                                <td style="padding: 12px 10px; font-weight: {daily_pnl_weight}; color: {daily_pnl_color}; font-size: 13px; width: 15%;">{daily_pnl_pct:+.2f}%</td>
                                <td style="padding: 12px 10px; font-weight: {t_pnl_weight}; color: {t_pnl_color}; font-size: 13px; width: 15%;">{pnl_pct:+.2f}%</td>
                                <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 15%;">+{target_pnl_pct:.1f}%</td>
                            </tr>
                            """
                        else:
                            open_rows += f"""
                            <tr style="border-bottom: 1px solid #2a3546; background-color: #1a222e;">
                                <td style="padding: 12px 10px; font-weight: bold; font-size: 14px; width: 40%;">{sym_html}</td>
                                <td style="padding: 12px 10px; font-weight: {daily_pnl_weight}; color: {daily_pnl_color}; font-size: 13px; width: 20%;">{daily_pnl_pct:+.2f}%</td>
                                <td style="padding: 12px 10px; font-weight: {t_pnl_weight}; color: {t_pnl_color}; font-size: 13px; width: 20%;">{pnl_pct:+.2f}%</td>
                                <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px; width: 20%;">+{target_pnl_pct:.1f}%</td>
                            </tr>
                            """
                
                section_content += f"""
                <div style="background-color: #1a222e; border-radius: 8px; border: 1px solid #2a3546; padding: 20px; margin-bottom: 25px; text-align: center;">
                    <div style="font-size: 11px; text-transform: uppercase; color: #8892b0; font-weight: bold; margin-bottom: 5px; letter-spacing: 0.5px;">Portfolio Equity</div>
                    <div style="font-size: 28px; font-weight: bold; color: #FFFFFF; margin-bottom: 5px;">${equity:,.2f} USD</div>
                    <div style="font-size: 16px; color: {pnl_color}; font-weight: bold;">
                        Weekly Performance: {sign}{weekly_pnl_pct:.2f}% ({usd_sign}${weekly_pnl_usd:,.2f})
                    </div>
                </div>
                
                <h3 style="font-size: 14px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; color: {accent_color}; margin: 25px 0 15px 0; border-left: 3px solid {accent_color}; padding-left: 10px;">🛰️ Currently Open Positions</h3>
                <div style="background-color: #1a222e; border-radius: 8px; border: 1px solid #2a3546; overflow: hidden; margin-bottom: 20px;">
                    <table style="width: 100%; border-collapse: collapse; text-align: left;">
                        <thead>
{active_headers}
                        </thead>
                        <tbody>
                            {open_rows}
                        </tbody>
                    </table>
                </div>
                """
            else:
                # First show hypothetical stats so they can see what they're missing
                hypo_pnl = hypothetical_data.get("cumulative_pnl", 0.0)
                hypo_balance = 1000.0 + hypo_pnl
                hypo_growth = (hypo_pnl / 1000.0) * 100
                
                wins = hypothetical_data.get("wins", 0)
                losses = hypothetical_data.get("losses", 0)
                win_rate = hypothetical_data.get("win_rate", 0.0)
                
                pnl_color = "#00C853" if hypo_pnl >= 0 else "#FF1744"
                sign = "+" if hypo_pnl >= 0 else ""
                
                section_content += f"""
                <div style="background-color: #1a222e; border-radius: 8px; border: 1px dashed {accent_color}; padding: 20px; margin-bottom: 25px; text-align: center; position: relative; overflow: hidden;">
                    <div style="position: absolute; top: 0; right: 0; background-color: {accent_color}; color: #000; font-size: 9px; font-weight: bold; padding: 3px 10px; border-bottom-left-radius: 8px; text-transform: uppercase;">Hypothetical</div>
                    <div style="font-size: 11px; text-transform: uppercase; color: #8892b0; font-weight: bold; margin-bottom: 5px; letter-spacing: 0.5px;">Simulated Portfolio Equity</div>
                    <div style="font-size: 28px; font-weight: bold; color: #FFFFFF; margin-bottom: 5px;">${hypo_balance:,.2f} USD</div>
                    <div style="font-size: 16px; color: {pnl_color}; font-weight: bold;">
                        Cumulative Performance: {sign}{hypo_growth:.2f}% ({sign}${hypo_pnl:,.2f})
                    </div>
                    <div style="font-size: 13px; color: #8892b0; margin-top: 10px;">
                        <b>Win Rate:</b> {win_rate:.1f}% ({wins} W | {losses} L)
                    </div>
                    <p style="font-size: 11px; color: #8892b0; margin: 15px 0 0 0; font-style: italic;">
                        * This is a simulation of what your {title.lower()} portfolio would look like with our automated fractional execution (starting from a $1,000 base). Connect your exchange to see your real performance!
                    </p>
                </div>
                """
                
                # Then show the connection prompt
                section_content += f"""
                <div style="background-color: #1a1126; border: 1px solid rgba(213, 0, 249, 0.3); border-radius: 8px; padding: 20px; margin-bottom: 25px; text-align: center;">
                    <h3 style="color: #FF1744; margin: 0 0 10px 0; font-size: 16px; font-weight: bold; text-transform: uppercase;">⚠️ Exchange Connection Required</h3>
                    <p style="font-size: 13px; color: #b3a9c9; margin: 0 0 15px 0; line-height: 1.5;">
                        You have Premium Access, but your exchange API keys for {title.lower()} are missing or invalid. Please connect your exchange in the trading console to enable real-time tracking and autopilot execution.
                    </p>
                    <a href="https://bot.metaversesherpa.io/#/settings" style="display: inline-block; background: linear-gradient(90deg, #3cd7ff 0%, #D500F9 100%); color: #000000 !important; text-decoration: none; font-weight: bold; padding: 10px 20px; border-radius: 6px; text-transform: uppercase; font-size: 11px; letter-spacing: 1px;">Connect Exchange</a>
                </div>
                """

        else:
            hypo_pnl = hypothetical_data.get("cumulative_pnl", 0.0)
            hypo_balance = 1000.0 + hypo_pnl
            hypo_growth = (hypo_pnl / 1000.0) * 100
            
            wins = hypothetical_data.get("wins", 0)
            losses = hypothetical_data.get("losses", 0)
            win_rate = hypothetical_data.get("win_rate", 0.0)
            
            pnl_color = "#00C853" if hypo_pnl >= 0 else "#FF1744"
            sign = "+" if hypo_pnl >= 0 else ""
            
            section_content += f"""
            <div style="background-color: #1a222e; border-radius: 8px; border: 1px dashed {accent_color}; padding: 20px; margin-bottom: 25px; text-align: center; position: relative; overflow: hidden;">
                <div style="position: absolute; top: 0; right: 0; background-color: {accent_color}; color: #000; font-size: 9px; font-weight: bold; padding: 3px 10px; border-bottom-left-radius: 8px; text-transform: uppercase;">Hypothetical</div>
                <div style="font-size: 11px; text-transform: uppercase; color: #8892b0; font-weight: bold; margin-bottom: 5px; letter-spacing: 0.5px;">Premium Access Potential Equity</div>
                <div style="font-size: 28px; font-weight: bold; color: #FFFFFF; margin-bottom: 5px;">${hypo_balance:,.2f} USD</div>
                <div style="font-size: 16px; color: {pnl_color}; font-weight: bold;">
                    Cumulative Performance: {sign}{hypo_growth:.2f}% ({sign}${hypo_pnl:,.2f})
                </div>
                <div style="font-size: 13px; color: #8892b0; margin-top: 10px;">
                    <b>Win Rate:</b> {win_rate:.1f}% ({wins} W | {losses} L)
                </div>
                <p style="font-size: 11px; color: #8892b0; margin: 15px 0 0 0; font-style: italic;">
                    * This is a simulation of what your {title.lower()} portfolio would look like if you had upgraded to Premium and used our automated fractional execution (starting from a $1,000 base).
                </p>
            </div>
            """
        return section_content

    content += render_section("Stock Markets", "📈", "#3cd7ff", has_stock_exchange, stock_portfolio_data, stock_open_trades, stock_hypothetical_data)
    content += render_section("Crypto Markets", "₿", "#D500F9", has_crypto_exchange, crypto_portfolio_data, crypto_open_trades, crypto_hypothetical_data)
    
    recommendations_section = ""
    if is_premium and recent_recommendations:
        recs_content = ""
        for rec in recent_recommendations:
            cat = rec.get("category", "stock").lower()
            sym = rec.get("symbol", "")
            icon = "📈" if cat == "stock" else "🪙"
            name = rec.get("name") or sym
            rationale = rec.get("rationale", "")
            metrics = rec.get("metrics_summary", "")
            tp = rec.get("target_price", 0)
            sl = rec.get("stop_loss", 0)
            growth = rec.get("expected_growth_pct", 0)
            timeframe = rec.get("estimated_timeframe", "")
            
            recs_content += f"""
            <div style="background-color: #1a222e; border-radius: 8px; border: 1px solid #2a3546; padding: 15px; margin-bottom: 15px; text-align: left;">
                <div style="font-size: 14px; font-weight: bold; color: #3cd7ff; margin-bottom: 5px;">{icon} {sym} <span style="color:#8892b0; font-size: 12px; font-weight:normal;">({name})</span></div>
                <div style="font-size: 12px; color: #b3a9c9; margin-bottom: 5px;">{metrics}</div>
                <div style="font-size: 12px; color: #00C853; font-weight: bold; margin-bottom: 8px;">Target: ${tp} (Stop Loss: ${sl}) | +{growth}% in {timeframe}</div>
                <div style="font-size: 11px; color: #8892b0; line-height: 1.4;"><i>{rationale}</i></div>
            </div>
            """
        
        if recs_content:
            recommendations_section = f"""
            <h2 style="font-size: 16px; font-weight: bold; text-transform: uppercase; letter-spacing: 1.5px; color: #FFD700; margin: 30px 0 20px 0; border-bottom: 1px solid #2a3546; padding-bottom: 10px;">💡 Fresh Investment Ideas</h2>
            <p style="font-size: 13px; color: #8892b0; margin: 0 0 15px 0;">Top AI-selected buys tailored to your profile generated in the last 7 days.</p>
            {recs_content}
            <div style="text-align: center; margin-top: 15px;">
                <a href="https://bot.metaversesherpa.io/recommendations" style="display: inline-block; background: #1a222e; border: 1px solid #FFD700; color: #FFD700 !important; text-decoration: none; font-weight: bold; padding: 10px 20px; border-radius: 6px; text-transform: uppercase; font-size: 11px; letter-spacing: 1px;">View Charts & Track Recommendations</a>
            </div>
            """
    
    upsell_section = ""
    if not is_premium:
        upsell_section = f"""
        <div style="background-color: #1a1126; border: 1px solid rgba(213, 0, 249, 0.3); border-radius: 8px; padding: 20px; margin-top: 30px; text-align: center;">
            <h3 style="color: #D500F9; margin: 0 0 10px 0; font-size: 16px; font-weight: bold; text-transform: uppercase;">🚀 UNLOCK FULL AUTOPILOT</h3>
            <p style="font-size: 12px; color: #b3a9c9; margin: 0 0 15px 0; line-height: 1.5;">
                Stop leaving money on the table. Upgrade to <b>Premium Access</b> today to turn those hypothetical returns into reality with automated execution.
            </p>
            <a href="https://bot.metaversesherpa.io/#/premium" style="display: inline-block; background: linear-gradient(90deg, #D500F9 0%, #7B1FA2 100%); color: #ffffff; text-decoration: none; font-weight: bold; padding: 10px 20px; border-radius: 6px; text-transform: uppercase; font-size: 11px; letter-spacing: 1px;">Upgrade to Premium Now</a>
        </div>
        """
        
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="color-scheme" content="light dark">
        <meta name="supported-color-schemes" content="light dark">
        <title>Sherpa Weekly Summary</title>
        <style>
            :root {{
                color-scheme: light dark;
                supported-color-schemes: light dark;
            }}
        </style>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: {color_bg}; color: #FFFFFF; margin: 0; padding: 0;">
        <div style="background-color: {color_bg}; padding: 20px 10px; min-height: 100%;">
            <div style="max-width: 600px; margin: 20px auto; background-color: {color_card}; border: 1px solid rgba(60, 215, 255, 0.15); border-radius: 12px; overflow: hidden; color: #FFFFFF;">
                {header_section}
                <div style="padding: 30px;">
                    {content}
                    {recommendations_section}
                    {upsell_section}
                    <a href="https://bot.metaversesherpa.io" style="display: block; width: 220px; margin: 30px auto 10px auto; text-align: center; background: linear-gradient(90deg, #3cd7ff 0%, #D500F9 100%); color: #000000 !important; text-decoration: none; font-weight: bold; padding: 12px 24px; border-radius: 8px; text-transform: uppercase; font-size: 12px; letter-spacing: 1px;">Access Trading Console</a>
                </div>
                <div style="padding: 20px; text-align: center; border-top: 1px solid #2a3546; font-size: 11px; color: #8892b0; background-color: #141A24;">
                    🏔️ Metaverse Sherpa Trading Platform
                    {NFA_MEDIUM_HTML}
                    <br>
                    Do you prefer silent hikes in the Metaverse? <br>
                    <a href="{{{{UNSUBSCRIBE_LINK}}}}" style="color: #3cd7ff; text-decoration: underline;">Click here to silence the noise (unsubscribe)</a>.
                </div>
            </div>
        </div>
    </body>
    </html>
    """


def _chunk_telegram_message(text, limit=4000):
    chunks = []
    while len(text) > limit:
        split_index = text.rfind('\n', 0, limit)
        if split_index == -1:
            split_index = limit
        chunks.append(text[:split_index])
        text = text[split_index:].lstrip()
    if text:
        chunks.append(text)
    return chunks
def get_combined_weekly_summary_telegram(is_premium=False, 
                                     has_stock_exchange=False, stock_portfolio_data=None, stock_open_trades=None, stock_hypothetical_data=None,
                                     has_crypto_exchange=False, crypto_portfolio_data=None, crypto_open_trades=None, crypto_hypothetical_data=None,
                                     recent_recommendations=None):
    lines = ["🏔️ <b>Weekly Update</b>\nMetaverse Sherpa Combined Weekly Performance Summary\n"]
    
    def render_section(title, icon, has_exchange, portfolio_data, open_trades, hypothetical_data):
        section_lines = [f"\n{icon} <b>{title}</b>"]
        if is_premium:
            if has_exchange:
                equity = portfolio_data.get("equity", 0.0)
                weekly_pnl_pct = portfolio_data.get("weekly_pnl_pct", 0.0)
                weekly_pnl_usd = portfolio_data.get("weekly_pnl_usd", 0.0)
                sign = "+" if weekly_pnl_pct >= 0 else ""
                usd_sign = "+" if weekly_pnl_usd >= 0 else ""
                
                if not open_trades:
                    section_lines.append(f"No open {title.lower()} positions currently.")
                else:
                    open_trades_sorted = sorted(open_trades, key=lambda x: x.get('current_pnl_pct', 0.0), reverse=True)
                    for t in open_trades_sorted:
                        pnl_pct = t.get("current_pnl_pct", 0.0)
                        daily_pnl_pct = t.get("daily_pnl_pct", 0.0)
                        target_pnl_pct = t.get("target_pnl_pct", 0.0)
                        sym = t['symbol']
                        clean_sym = sym.replace('/', '').replace(':USDT', '').replace(':BUSD', '')
                        is_long = t.get('side', '').upper() in ['BUY', 'LONG']
                        dir_emoji = "📈" if is_long else "📉"
                        sym_html = f"<b>{sym}</b>"
                        
                        section_lines.append(f"{dir_emoji} {sym_html} | Entry: ${t['entry_price']:.4f} SL: ${t['sl_price']:.4f} TP: ${t['tp_price']:.4f} | Daily: {daily_pnl_pct:+.2f}% | Total: {pnl_pct:+.2f}% | Target: +{target_pnl_pct:.1f}%")
                
                section_lines.append(f"\n<b>Portfolio Equity:</b> ${equity:,.2f} USD")
                section_lines.append(f"<b>7-Day Performance:</b> {sign}{weekly_pnl_pct:.2f}% ({usd_sign}${weekly_pnl_usd:,.2f})")
            else:
                section_lines.append(f"No Exchange Connected. <a href='https://bot.metaversesherpa.io/#/settings'>Connect Exchange</a>")
        else:
            hypo_pnl = hypothetical_data.get("cumulative_pnl", 0.0)
            hypo_balance = 1000.0 + hypo_pnl
            hypo_growth = (hypo_pnl / 1000.0) * 100
            wins = hypothetical_data.get("wins", 0)
            losses = hypothetical_data.get("losses", 0)
            win_rate = hypothetical_data.get("win_rate", 0.0)
            sign = "+" if hypo_pnl >= 0 else ""
            
            section_lines.append("<i>Hypothetical Premium Access Potential Equity</i>")
            section_lines.append(f"<b>${hypo_balance:,.2f} USD</b>")
            section_lines.append(f"Cumulative Performance: {sign}{hypo_growth:.2f}% ({sign}${hypo_pnl:,.2f})")
            section_lines.append(f"Win Rate: {win_rate:.1f}% ({wins} W | {losses} L)")
            section_lines.append(f"<i>* This is a simulation of what your {title.lower()} portfolio would look like if you had upgraded to Premium and used our automated fractional execution (starting from a $1,000 base).</i>")
            
        return section_lines

    lines.extend(render_section("Stock Markets", "📈", has_stock_exchange, stock_portfolio_data, stock_open_trades, stock_hypothetical_data))
    lines.extend(render_section("Crypto Markets", "₿", has_crypto_exchange, crypto_portfolio_data, crypto_open_trades, crypto_hypothetical_data))

    if is_premium and recent_recommendations:
        lines.append("\n💡 <b>Fresh Investment Ideas</b>")
        lines.append("Top AI-selected buys tailored to your profile generated in the last 7 days.\n")
        for rec in recent_recommendations:
            cat = rec.get("category", "stock").lower()
            sym = rec.get("symbol", "")
            icon = "📈" if cat == "stock" else "🪙"
            name = rec.get("name") or sym
            rationale = rec.get("rationale", "")
            tp = rec.get("target_price", 0)
            sl = rec.get("stop_loss", 0)
            growth = rec.get("expected_growth_pct", 0)
            timeframe = rec.get("estimated_timeframe", "")
            lines.append(f"{icon} <b>{sym}</b> ({name})\nTarget: ${tp} (SL: ${sl}) | +{growth}% in {timeframe}\n<i>{rationale}</i>\n")
        lines.append("<a href='https://bot.metaversesherpa.io/recommendations'>View Charts & Track Recommendations</a>")

    if not is_premium:
        lines.append("\n🚀 <b>UNLOCK FULL AUTOPILOT</b>\nStop leaving money on the table. Upgrade to <b>Premium Access</b> today to turn those hypothetical returns into reality with automated execution.\n<a href='https://bot.metaversesherpa.io/#/premium'>Upgrade to Premium Now</a>")

    lines.append("\n<a href='https://bot.metaversesherpa.io'>Access Trading Console</a>")
    lines.append(NFA_SHORT_TEXT)
    return _chunk_telegram_message("\n".join(lines))


