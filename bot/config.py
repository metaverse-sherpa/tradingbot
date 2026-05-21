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

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", 1567788633))

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

# Setup Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("bot")

# Silence chatty libraries to save disk space on VPS
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logging.getLogger("ccxt.blofin").setLevel(logging.WARNING)
