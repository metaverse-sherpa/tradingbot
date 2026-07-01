import os
import sys
import logging
from dotenv import load_dotenv

# Base directory definitions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# Add scripts directory to path for imports
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.append(SCRIPTS_DIR)

import database
import utils_gcp

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = utils_gcp.get_secret("TELEGRAM_BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", 1567788633))
CRYPTO_LEVERAGE = 20.0

# --- Institutional Revenue Constants ---
MASTER_USDT_WALLET = "TUhiPWBbrJKV7cyrnSawZ7JUdLN8Qcg6u3"

def get_master_wallet():
    """Retrieves the master wallet from database config."""
    return database.get_config('master_usdt_wallet', MASTER_USDT_WALLET)

def format_price(price, symbol=""):
    """Formats price beautifully based on symbol type and magnitude."""
    if not isinstance(price, (int, float)):
        try:
            price = float(price)
        except Exception:
            return str(price)
            
    symbol_str = str(symbol).upper()
    if symbol_str and "/" not in symbol_str and ":" not in symbol_str and "USDT" not in symbol_str:
        return f"{price:,.2f}"
        
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 1:
        return f"{price:,.4f}"
    else:
        return f"{price:.8f}".rstrip('0').rstrip('.') or "0"

def get_currency(symbol):
    """Determines simulated trade currency base."""
    symbol_str = str(symbol).upper()
    if symbol_str and "/" not in symbol_str and ":" not in symbol_str and "USDT" not in symbol_str:
        return "USD"
    return "USDT"

def is_stock(symbol):
    """Determines if a symbol is a stock ticker."""
    symbol_str = str(symbol).upper()
    return symbol_str and "/" not in symbol_str and ":" not in symbol_str and "USDT" not in symbol_str

def get_symbol_link(symbol, text=None):
    """Returns a clickable Markdown link for the given symbol."""
    symbol_str = str(symbol).upper()
    is_stk = is_stock(symbol_str)
    
    if is_stk:
        url = f"https://marketmasters.ai/stocks/{symbol_str}"
    else:
        clean_sym = symbol_str.split(":")[0].replace("/", "")
        url = f"https://marketmasters.ai/currency/{clean_sym}"
        
    display_text = text if text else symbol_str
    
    # Use standard Markdown link formatting.
    # Note: Telegram MarkdownV2 requires escaping the URL parenthesis if there's any, but these URLs don't have them.
    # However, to avoid parsing issues in MarkdownV2 when `display_text` is already escaped, 
    # we just wrap it directly. It works in both Markdown and MarkdownV2.
    return f"[{display_text}]({url})"

# Setup Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("bot")

# Silence chatty libraries to save disk space on VPS
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("ccxt.blofin").setLevel(logging.WARNING)
