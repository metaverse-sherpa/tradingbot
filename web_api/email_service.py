import os
import threading
import logging

# Import utils_gcp to fetch secrets from Google Secret Manager
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils_gcp import get_secret

logger = logging.getLogger("email_service")

# Resend API Key
RESEND_API_KEY = get_secret("RESEND_API_KEY") or os.getenv("RESEND_API_KEY", "")

SENDER_EMAIL = get_secret("SMTP_SENDER_EMAIL") or os.getenv("SMTP_SENDER_EMAIL", "")

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

def get_daily_summary_html(signals_opened, signals_closed, is_premium_user=False, user_stats=None):
    """
    Generates premium responsive HTML email template for daily trading summaries.
    """
    from bot.config import is_stock
    color_bg = "#0B0E14"
    color_card = "#141A24"
    
    opened_rows = ""
    if not signals_opened:
        opened_rows = '<tr><td colspan="4" style="padding: 15px; text-align: center; color: #8892b0; font-size: 13px; background-color: #1a222e;">No new signals opened today.</td></tr>'
    else:
        for s in signals_opened:
            sym = s['symbol']
            if is_stock(sym):
                symbol_link = f'<a href="https://marketmasters.ai/stocks/{sym}" style="color: #3cd7ff; text-decoration: underline;">{sym}</a>'
            else:
                clean_sym = sym.split("/")[0].split(":")[0].replace("USDT", "")
                symbol_link = f'<a href="https://marketmasters.ai/currency/{clean_sym}USDT" style="color: #3cd7ff; text-decoration: underline;">{clean_sym}</a>'
            direction_color = "#00C853" if s['side'] in ['buy', 'long', 'LONG'] else "#FF1744"
            direction_label = "LONG" if s['side'] in ['buy', 'long', 'LONG'] else "SHORT"
            
            if 'current_pnl_pct' in s:
                pnl_pct = s['current_pnl_pct']
                tp_pct = s.get('target_tp_pct', 0.0)
                pnl_color = "#00C853" if pnl_pct >= 0 else "#FF1744"
                pnl_str = f"{pnl_pct:+.2f}%"
                tp_str = f"{tp_pct:+.2f}%"
                display_val = f'<span style="color: {pnl_color}; font-weight: bold;">{pnl_str}</span> / <span style="color: #00C853;">{tp_str}</span>'
            else:
                display_val = f"${s['entry_price']:.4f}"
                
            opened_rows += f"""
            <tr style="border-bottom: 1px solid #2a3546; background-color: #1a222e;">
                <td style="padding: 12px 10px; font-weight: bold; color: #3cd7ff; font-size: 14px;">{symbol_link}</td>
                <td style="padding: 12px 10px; font-weight: bold; color: {direction_color}; font-size: 12px;">{direction_label}</td>
                <td style="padding: 12px 10px; color: #FFFFFF; font-size: 13px;">{display_val}</td>
                <td style="padding: 12px 10px; color: #8892b0; font-size: 12px;">{s['strategy']}</td>
            </tr>
            """
            
    closed_rows = ""
    if not signals_closed:
        closed_rows = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: #8892b0; font-size: 13px; background-color: #1a222e;">No positions resolved today.</td></tr>'
    else:
        for s in signals_closed:
            sym = s['symbol']
            if is_stock(sym):
                symbol_link = f'<a href="https://marketmasters.ai/stocks/{sym}" style="color: #3cd7ff; text-decoration: underline;">{sym}</a>'
            else:
                clean_sym = sym.split("/")[0].split(":")[0].replace("USDT", "")
                symbol_link = f'<a href="https://marketmasters.ai/currency/{clean_sym}USDT" style="color: #3cd7ff; text-decoration: underline;">{clean_sym}</a>'
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
            <tr style="border-bottom: 1px solid #2a3546; background-color: #1a222e;">
                <td style="padding: 12px 10px; font-weight: bold; color: #3cd7ff; font-size: 14px;">{symbol_link}</td>
                <td style="padding: 12px 10px; font-weight: bold; color: {direction_color}; font-size: 12px;">{direction_label}</td>
                <td style="padding: 12px 10px; font-weight: bold; color: {pnl_color}; font-size: 13px;">{pnl_str}</td>
                <td style="padding: 12px 10px; color: #FFFFFF; font-size: 12px;">{s['status'].upper()}</td>
                <td style="padding: 12px 10px; color: #8892b0; font-size: 12px;">{s['strategy']}</td>
            </tr>
            """
            
    # Generate Premium Stats HTML
    premium_stats_section = ""
    if is_premium_user:
        crypto_stats = user_stats.get("crypto", {}) if user_stats else {}
        stock_stats = user_stats.get("stock", {}) if user_stats else {}
        
        # Crypto card
        if crypto_stats.get("linked"):
            c_eq = crypto_stats.get("equity", 0.0)
            c_pnl_pct = crypto_stats.get("daily_pnl_pct", 0.0)
            c_pnl_usd = crypto_stats.get("daily_pnl_usd", 0.0)
            c_color = "#00C853" if c_pnl_pct >= 0 else "#FF1744"
            c_sign = "+" if c_pnl_pct >= 0 else ""
            c_usd_sign = "+" if c_pnl_usd >= 0 else ""
            c_wr = crypto_stats.get("win_rate", 0.0)
            c_open = crypto_stats.get("open_trades", 0)
            c_wins = crypto_stats.get("wins", 0)
            c_losses = crypto_stats.get("losses", 0)
            
            c_overall_pnl_pct = crypto_stats.get("overall_pnl_pct", 0.0)
            c_overall_color = "#00C853" if c_overall_pnl_pct >= 0 else "#FF1744"
            c_overall_sign = "+" if c_overall_pnl_pct >= 0 else ""
            
            c_open_display = f'<a href="https://bot.metaversesherpa.io/#/trades?tab=crypto" style="color: #3cd7ff; text-decoration: underline; font-weight: bold;">{c_open}</a>' if c_open > 0 else f"{c_open}"
            
            crypto_block = f"""
            <div style="background-color: #141A24; border: 1px solid rgba(60, 215, 255, 0.15); border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                <div style="font-size: 11px; text-transform: uppercase; color: #8892b0; font-weight: bold; margin-bottom: 5px; letter-spacing: 0.5px;">🪙 Crypto Portfolio</div>
                <div style="font-size: 20px; font-weight: bold; color: #FFFFFF; margin-bottom: 10px;">
                    ${c_eq:,.2f} 
                    <span style="font-size: 14px; color: {c_color}; margin-left: 8px;">{c_sign}{c_pnl_pct:.2f}% ({c_usd_sign}${c_pnl_usd:,.2f})</span>
                </div>
                <table style="width: 100%; font-size: 12px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 8px;">
                    <tr>
                        <td style="color: #8892b0;">Daily PnL</td>
                        <td align="right" style="color: {c_color}; font-weight: bold;">{c_sign}{c_pnl_pct:.2f}% ({c_usd_sign}${c_pnl_usd:,.2f})</td>
                    </tr>
                    <tr>
                        <td style="color: #8892b0;">Overall PnL</td>
                        <td align="right" style="color: {c_overall_color}; font-weight: bold;">{c_overall_sign}{c_overall_pnl_pct:.2f}%</td>
                    </tr>
                    <tr>
                        <td style="color: #8892b0;">Open Trades</td>
                        <td align="right" style="color: #FFFFFF; font-weight: bold;">{c_open_display}</td>
                    </tr>
                    <tr>
                        <td style="color: #8892b0;">Win Rate</td>
                        <td align="right" style="color: #00C853; font-weight: bold;">{c_wr:.1f}% <span style="color: #8892b0; font-weight: normal; font-size: 11px;">({c_wins}W / {c_losses}L)</span></td>
                    </tr>
                </table>
            </div>
            """
        else:
            crypto_block = f"""
            <div style="background-color: #141A24; border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 15px; margin-bottom: 15px; text-align: center;">
                <div style="font-size: 11px; text-transform: uppercase; color: #8892b0; font-weight: bold; margin-bottom: 5px;">🪙 Crypto Portfolio</div>
                <p style="font-size: 12px; color: #8892b0; margin: 8px 0;">Link your crypto exchange to track live equity, daily performance, and stats.</p>
                <a href="https://bot.metaversesherpa.io/#/settings" style="font-size: 11px; color: #3cd7ff; text-decoration: underline; font-weight: bold;">Configure Crypto API</a>
            </div>
            """
            
        # Stock card
        if stock_stats.get("linked"):
            s_eq = stock_stats.get("equity", 0.0)
            s_pnl_pct = stock_stats.get("daily_pnl_pct", 0.0)
            s_pnl_usd = stock_stats.get("daily_pnl_usd", 0.0)
            s_color = "#00C853" if s_pnl_pct >= 0 else "#FF1744"
            s_sign = "+" if s_pnl_pct >= 0 else ""
            s_usd_sign = "+" if s_pnl_usd >= 0 else ""
            s_wr = stock_stats.get("win_rate", 0.0)
            s_open = stock_stats.get("open_trades", 0)
            s_wins = stock_stats.get("wins", 0)
            s_losses = stock_stats.get("losses", 0)
            
            s_overall_pnl_pct = stock_stats.get("overall_pnl_pct", 0.0)
            s_overall_color = "#00C853" if s_overall_pnl_pct >= 0 else "#FF1744"
            s_overall_sign = "+" if s_overall_pnl_pct >= 0 else ""
            
            s_open_display = f'<a href="https://bot.metaversesherpa.io/#/trades?tab=stock" style="color: #3cd7ff; text-decoration: underline; font-weight: bold;">{s_open}</a>' if s_open > 0 else f"{s_open}"
            
            stock_block = f"""
            <div style="background-color: #141A24; border: 1px solid rgba(60, 215, 255, 0.15); border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                <div style="font-size: 11px; text-transform: uppercase; color: #8892b0; font-weight: bold; margin-bottom: 5px; letter-spacing: 0.5px;">🦙 Stocks Portfolio</div>
                <div style="font-size: 20px; font-weight: bold; color: #FFFFFF; margin-bottom: 10px;">
                    ${s_eq:,.2f} 
                    <span style="font-size: 14px; color: {s_color}; margin-left: 8px;">{s_sign}{s_pnl_pct:.2f}% ({s_usd_sign}${s_pnl_usd:,.2f})</span>
                </div>
                <table style="width: 100%; font-size: 12px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 8px;">
                    <tr>
                        <td style="color: #8892b0;">Daily PnL</td>
                        <td align="right" style="color: {s_color}; font-weight: bold;">{s_sign}{s_pnl_pct:.2f}% ({s_usd_sign}${s_pnl_usd:,.2f})</td>
                    </tr>
                    <tr>
                        <td style="color: #8892b0;">Overall PnL</td>
                        <td align="right" style="color: {s_overall_color}; font-weight: bold;">{s_overall_sign}{s_overall_pnl_pct:.2f}%</td>
                    </tr>
                    <tr>
                        <td style="color: #8892b0;">Open Trades</td>
                        <td align="right" style="color: #FFFFFF; font-weight: bold;">{s_open_display}</td>
                    </tr>
                    <tr>
                        <td style="color: #8892b0;">Win Rate</td>
                        <td align="right" style="color: #00C853; font-weight: bold;">{s_wr:.1f}% <span style="color: #8892b0; font-weight: normal; font-size: 11px;">({s_wins}W / {s_losses}L)</span></td>
                    </tr>
                </table>
            </div>
            """
        else:
            stock_block = f"""
            <div style="background-color: #141A24; border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 15px; margin-bottom: 15px; text-align: center;">
                <div style="font-size: 11px; text-transform: uppercase; color: #8892b0; font-weight: bold; margin-bottom: 5px;">🦙 Stocks Portfolio</div>
                <p style="font-size: 12px; color: #8892b0; margin: 8px 0;">Link your Alpaca account to track live equity, daily performance, and stats.</p>
                <a href="https://bot.metaversesherpa.io/#/settings" style="font-size: 11px; color: #3cd7ff; text-decoration: underline; font-weight: bold;">Configure Alpaca API</a>
            </div>
            """
            
        premium_stats_section = f"""
        <h3 style="font-size: 15px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; color: #3cd7ff; margin: 25px 0 15px 0; border-left: 3px solid #3cd7ff; padding-left: 10px;">📊 Personal Portfolio Performance</h3>
        {crypto_block}
        {stock_block}
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
                background-color: {color_bg} !important;
                color: #FFFFFF !important;
            }}
        </style>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: {color_bg}; color: #FFFFFF; margin: 0; padding: 0;">
        <div style="background-color: {color_bg}; padding: 20px 10px; min-height: 100%;">
            <div style="max-width: 600px; margin: 20px auto; background-color: {color_card}; border: 1px solid rgba(60, 215, 255, 0.15); border-radius: 12px; overflow: hidden; color: #FFFFFF;">
                <div style="padding: 35px 30px; text-align: center; background: #0c1f30; background-image: linear-gradient(135deg, rgba(60, 215, 255, 0.1) 0%, rgba(12, 31, 48, 0.5) 100%); border-bottom: 1px solid rgba(60, 215, 255, 0.1);">
                    <h1 style="font-size: 22px; font-weight: bold; text-transform: uppercase; letter-spacing: 2px; margin: 0; color: #3cd7ff;">🏔️ Daily Signals Digest</h1>
                    <p style="font-size: 13px; color: #8892b0; margin: 8px 0 0 0;">Metaverse Sherpa Institutional Algorithmic Performance Summary</p>
                </div>
                <div style="padding: 30px;">
                    
                    <h3 style="font-size: 15px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; color: #D500F9; margin: 0 0 15px 0; border-left: 3px solid #D500F9; padding-left: 10px;">🛰️ New Signals Opened</h3>
                    <div style="background-color: #1a222e; border-radius: 8px; border: 1px solid #2a3546; margin-bottom: 30px; overflow: hidden;">
                        <table style="width: 100%; border-collapse: collapse; text-align: left;">
                            <thead>
                                <tr style="background-color: #111822;">
                                    <th style="padding: 12px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8892b0; border-bottom: 1px solid #2a3546;">Symbol</th>
                                    <th style="padding: 12px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8892b0; border-bottom: 1px solid #2a3546;">Side</th>
                                    <th style="padding: 12px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8892b0; border-bottom: 1px solid #2a3546;">PnL / Target</th>
                                    <th style="padding: 12px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8892b0; border-bottom: 1px solid #2a3546;">Strategy</th>
                                </tr>
                            </thead>
                            <tbody>
                                {opened_rows}
                            </tbody>
                        </table>
                    </div>

                    <h3 style="font-size: 15px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; color: #D500F9; margin: 0 0 15px 0; border-left: 3px solid #D500F9; padding-left: 10px;">🏆 Signals Resolved</h3>
                    <div style="background-color: #1a222e; border-radius: 8px; border: 1px solid #2a3546; margin-bottom: 30px; overflow: hidden;">
                        <table style="width: 100%; border-collapse: collapse; text-align: left;">
                            <thead>
                                <tr style="background-color: #111822;">
                                    <th style="padding: 12px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8892b0; border-bottom: 1px solid #2a3546;">Symbol</th>
                                    <th style="padding: 12px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8892b0; border-bottom: 1px solid #2a3546;">Side</th>
                                    <th style="padding: 12px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8892b0; border-bottom: 1px solid #2a3546;">PnL</th>
                                    <th style="padding: 12px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8892b0; border-bottom: 1px solid #2a3546;">Status</th>
                                    <th style="padding: 12px 10px; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: #8892b0; border-bottom: 1px solid #2a3546;">Strategy</th>
                                </tr>
                            </thead>
                            <tbody>
                                {closed_rows}
                            </tbody>
                        </table>
                    </div>
                    
                    {premium_stats_section}
                    
                    <a href="https://bot.metaversesherpa.io" style="display: block; width: 220px; margin: 20px auto 10px auto; text-align: center; background: linear-gradient(90deg, #3cd7ff 0%, #00C853 100%); color: #000000 !important; text-decoration: none; font-weight: bold; padding: 12px 24px; border-radius: 8px; text-transform: uppercase; font-size: 12px; letter-spacing: 1px;">Access Trading Console</a>
                </div>
                <div style="padding: 20px; text-align: center; border-top: 1px solid #2a3546; font-size: 11px; color: #8892b0; background-color: #141A24;">
                    🏔️ Metaverse Sherpa Institutional Trading Platform • Secure Military-Grade Encryption Active
                    <br><br>
                    Do you prefer silent hikes in the Metaverse? <br>
                    <a href="{{UNSUBSCRIBE_LINK}}" style="color: #3cd7ff; text-decoration: underline;">Click here to silence the noise (unsubscribe)</a>.
                </div>
            </div>
        </div>
    </body>
    </html>
    """


