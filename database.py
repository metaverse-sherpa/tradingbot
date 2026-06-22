import sqlite3
import os
import time
import asyncio
import ccxt.async_support as ccxt
import ccxt as ccxt_sync
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Disable fetchCurrencies globally in CCXT to prevent the library from querying private wallet endpoints
# (such as wallets/v1/capital/config/getall on BingX) which require Account Transfer/Wallet permissions.
# This allows balance syncing and trading to succeed using only Read and Futures permissions.
try:
    _original_async_init = ccxt.Exchange.__init__
    def _new_async_init(self, *args, **kwargs):
        _original_async_init(self, *args, **kwargs)
        self.has['fetchCurrencies'] = False
    ccxt.Exchange.__init__ = _new_async_init
except Exception as patch_err:
    pass

try:
    _original_sync_init = ccxt_sync.Exchange.__init__
    def _new_sync_init(self, *args, **kwargs):
        _original_sync_init(self, *args, **kwargs)
        self.has['fetchCurrencies'] = False
    ccxt_sync.Exchange.__init__ = _new_sync_init
except Exception as patch_err:
    pass

load_dotenv()

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    with open(".env", "a") as f:
        f.write(f"\nENCRYPTION_KEY={ENCRYPTION_KEY}\n")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

from contextlib import contextmanager

from db_adapter import db_session_adapter

@contextmanager
def db_session():
    with db_session_adapter(DB_PATH, sqlite_timeout=30.0) as session:
        yield session

def get_exchange_client(user):
    """
    Factory function to create a CCXT exchange client for a specific user.
    """
    ex_id = user.get('exchange_id', 'blofin')
    if ex_id == 'alpaca':
        ex_id = 'blofin'
    config = {
        "apiKey": user["api_key"],
        "secret": user["api_secret"],
        **({"password": user["api_password"]} if user["api_password"] else {}),
        "options": {"defaultType": "swap"},
        "enableRateLimit": True,
    }
    client = getattr(ccxt, ex_id)(config)
    if ex_id == 'coinbase':
        sandbox = user.get('coinbase_sandbox')
        if sandbox is None or sandbox in (1, True, '1', 'true', 'True'):
            client.urls['api']['rest'] = 'https://api-sandbox.coinbase.com'
    return client

def normalize_symbol(symbol, exchange_id):
    """
    Handles exchange-specific symbol dialects.
    """
    if not symbol:
        return symbol

    # Clean symbol inputs (standardize slashes, uppercase)
    sym = symbol.upper().replace('-', '/')

    # Exchange-specific symbol mapping tables
    MAPPINGS = {
        'coinbase': {
            'BTC/USDT:USDT': 'BTC/USDC:USDC',
            'BTC/USDT': 'BTC/USDC:USDC',
            'ETH/USDT:USDT': 'ETH/USDC:USDC',
            'ETH/USDT': 'ETH/USDC:USDC',
            'SOL/USDT:USDT': 'SOL/USDC:USDC',
            'SOL/USDT': 'SOL/USDC:USDC',
            'ADA/USDT:USDT': 'ADA/USDC:USDC',
            'ADA/USDT': 'ADA/USDC:USDC',
            'DOGE/USDT:USDT': 'DOGE/USDC:USDC',
            'DOGE/USDT': 'DOGE/USDC:USDC',
            'LINK/USDT:USDT': 'LINK/USDC:USDC',
            'LINK/USDT': 'LINK/USDC:USDC',
            'DOT/USDT:USDT': 'DOT/USDC:USDC',
            'DOT/USDT': 'DOT/USDC:USDC',
            'SHIB/USDT:USDT': '1000SHIB/USDC:USDC',
            'SHIB/USDT': '1000SHIB/USDC:USDC',
            'PEPE/USDT:USDT': '1000PEPE/USDC:USDC',
            'PEPE/USDT': '1000PEPE/USDC:USDC',
        },
        'bingx': {
            'TON/USDT:USDT': 'TONCOIN/USDT:USDT',
            'TON/USDT': 'TONCOIN/USDT:USDT',
            'PEPE/USDT:USDT': '1000PEPE/USDT:USDT',
            'PEPE/USDT': '1000PEPE/USDT:USDT',
        },
        'binance': {
            'PEPE/USDT:USDT': '1000PEPE/USDT:USDT',
            'PEPE/USDT': '1000PEPE/USDT:USDT',
            'SHIB/USDT:USDT': '1000SHIB/USDT:USDT',
            'SHIB/USDT': '1000SHIB/USDT:USDT',
        },
        'mexc': {
            'TON/USDT:USDT': 'TONCOIN/USDT:USDT',
            'TON/USDT': 'TONCOIN/USDT:USDT',
        },
        'bybit': {
            'PEPE/USDT:USDT': '1000PEPE/USDT:USDT',
            'PEPE/USDT': '1000PEPE/USDT:USDT',
            'SHIB/USDT:USDT': '1000SHIB/USDT:USDT',
            'SHIB/USDT': '1000SHIB/USDT:USDT',
            'BONK/USDT:USDT': '1000BONK/USDT:USDT',
            'BONK/USDT': '1000BONK/USDT:USDT',
        }
    }

    ex_id = exchange_id.lower()
    if ex_id in MAPPINGS and sym in MAPPINGS[ex_id]:
        return MAPPINGS[ex_id][sym]

    # Fallback to mexc split behavior if mexc (after checking the mapping table)
    if ex_id == 'mexc':
        return sym.split(":")[0]

    return symbol

def process_exchange_trades_for_symbol(trades, exchange_id):
    """
    Groups and calculates PnL of trades for a symbol, computing PnL
    locally if the exchange (e.g. BingX) does not report realized PnL on fills.
    """
    sorted_trades = sorted(trades, key=lambda x: x.get('timestamp', 0))
    
    positions = {
        "LONG": {"qty": 0.0, "entry": 0.0},
        "SHORT": {"qty": 0.0, "entry": 0.0}
    }
    
    results = []
    
    for t in sorted_trades:
        info = t.get("info", {})
        side = t.get('side', '').lower() # 'buy' or 'sell'
        
        # Determine raw/computed position side
        t_pos_side = info.get('positionSide', '').upper()
        if not t_pos_side or t_pos_side in ['BOTH', 'NET']:
            # Fallback based on side
            t_pos_side = 'LONG' if side == 'buy' else 'SHORT'
            
        qty = float(t.get('amount') or 0)
        price = float(t.get('price') or 0)
        
        # Check if the exchange provides realized PnL
        reported_pnl = None
        if exchange_id == 'blofin':
            reported_pnl = info.get("fillPnl")
        else:
            reported_pnl = info.get("realizedPnl")
            
        gross_pnl = 0.0
        is_closing_fill = False
        
        if reported_pnl is not None and str(reported_pnl) != '' and str(reported_pnl).lower() != 'none':
            try:
                gross_pnl = float(reported_pnl)
                is_closing_fill = (gross_pnl != 0.0)
            except ValueError:
                pass
        else:
            # Exchange does not report realized PnL on trades (e.g., BingX)
            # We calculate PnL locally based on position side
            pos = positions[t_pos_side]
            is_increase = (side == 'buy') if t_pos_side == 'LONG' else (side == 'sell')
            
            if is_increase:
                new_qty = pos["qty"] + qty
                if new_qty > 0:
                    pos["entry"] = ((pos["entry"] * pos["qty"]) + (price * qty)) / new_qty
                pos["qty"] = new_qty
            else:
                is_closing_fill = True
                closed_qty = min(pos["qty"], qty)
                if closed_qty > 0 and pos["entry"] > 0:
                    if t_pos_side == 'LONG':
                        gross_pnl = (price - pos["entry"]) * closed_qty
                    else: # SHORT
                        gross_pnl = (pos["entry"] - price) * closed_qty
                
                pos["qty"] = max(0.0, pos["qty"] - qty)
                if pos["qty"] == 0.0:
                    pos["entry"] = 0.0
                    
        # Calculate fee
        fee_cost = 0.0
        fee_data = t.get('fee')
        if fee_data and isinstance(fee_data, dict):
            fee_cost = float(fee_data.get('cost') or 0)
        elif info.get('commission') is not None:
            try:
                fee_cost = abs(float(info.get('commission')))
            except ValueError:
                pass
                
        # We include the trade if the exchange reports a non-zero PnL,
        # or if we calculated it as a closing fill
        if is_closing_fill or gross_pnl != 0.0:
            net_pnl = gross_pnl - (fee_cost * 2)
            results.append({
                "trade": t,
                "gross_pnl": gross_pnl,
                "fee": fee_cost,
                "net_pnl": net_pnl
            })
            
    return results

def get_exchange_balance_params(exchange_id, futures_type='perpetual'):
    """
    Returns the unified CCXT parameters for balance fetching
    representing the correct futures/swap trading account.
    """
    if exchange_id == 'coinbase':
        return {"type": "spot"}     # Use spot balance since Coinbase sweeps spot funds for margin automatically
    elif exchange_id == 'bingx':
        return {"type": "swap"}     # USDT-M Perpetual Account
    elif exchange_id == 'bitget':
        return {"type": "swap"}     # USDT perpetual swaps (usdt_futures)
    elif exchange_id == 'mexc':
        return {"type": "swap"}     # Perpetual Swap
    elif exchange_id == 'binance':
        return {"type": "future"}   # USDⓈ-M Futures (UMFUTURE)
    return {"type": "futures"}      # Fallback (e.g. Blofin)




def encrypt(data):
    if not data: return data
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt(data):
    if not data: return data
    return cipher_suite.decrypt(data.encode()).decode()

def encrypt_with_public_key(public_key_pem: str, plaintext: str) -> str:
    """
    Encrypts plaintext using the user's public key (PEM/SPKI base64 format).
    Returns base64 encoded ciphertext.
    """
    if not public_key_pem or not plaintext:
        return ""
    try:
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        import base64

        pem_data = public_key_pem.strip()
        if not pem_data.startswith("-----BEGIN PUBLIC KEY-----"):
            # Format raw SPKI base64 into standard PEM
            base64_clean = "".join(pem_data.split())
            lines = [base64_clean[i:i+64] for i in range(0, len(base64_clean), 64)]
            pem_data = "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----"

        pub_key = load_pem_public_key(pem_data.encode())
        
        ciphertext = pub_key.encrypt(
            plaintext.encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return base64.b64encode(ciphertext).decode('utf-8')
    except Exception as e:
        print(f"Encryption error: {e}")
        return ""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DB_PATH = os.path.join(BASE_DIR, 'bot_users.db')
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATA_DB_PATH = os.path.join(DATA_DIR, 'bot_users.db')

# Ensure directory exists with dynamic fallback
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception as e:
    print(f"Warning: Could not create data directory {DATA_DIR}: {e}")

# Default path is under the data directory
DB_PATH = DATA_DB_PATH

# 1. Automatic migration from root folder to data/ folder if root exists and data/ is writable
if os.path.exists(ROOT_DB_PATH) and not os.path.exists(DATA_DB_PATH):
    try:
        import shutil
        shutil.copy2(ROOT_DB_PATH, DATA_DB_PATH)
        # Rename the root database to a backup to avoid duplicate DB operations
        os.rename(ROOT_DB_PATH, os.path.join(BASE_DIR, 'bot_users.db.backup'))
        print(f"Successfully migrated active database from root to {DATA_DB_PATH}")
    except Exception as e:
        print(f"Warning: Failed to migrate database to data/ folder: {e}")
        # Fallback to root database if copy failed
        DB_PATH = ROOT_DB_PATH

# 2. Test sqlite3 connection to DB_PATH, fallback to ROOT_DB_PATH if it fails (e.g. permission issues on data/)
try:
    conn = sqlite3.connect(DB_PATH)
    conn.close()
except sqlite3.OperationalError as e:
    print(f"Warning: DB_PATH {DB_PATH} is not writable or accessible ({e}). Falling back to root database {ROOT_DB_PATH}.")
    DB_PATH = ROOT_DB_PATH
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.close()
    except sqlite3.OperationalError as re:
        print(f"Critical: Root database also inaccessible: {re}")
        # Revert to DATA_DB_PATH to let the init_db call bubble up standard errors
        DB_PATH = DATA_DB_PATH


def init_db():
    # Configure WAL mode and synchronous settings once on startup
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception as pragma_err:
        print(f"Warning: Failed to set WAL/synchronous pragmas on database startup: {pragma_err}")

    with db_session() as conn:
        c = conn.cursor()
        
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in c.fetchall()}

        if "Users" not in existing_tables:
            c.execute('''CREATE TABLE IF NOT EXISTS Users
                         (telegram_chat_id INTEGER PRIMARY KEY,
                          blofin_api_key TEXT,
                          blofin_api_secret TEXT,
                          blofin_api_password TEXT,
                          exchange_id TEXT DEFAULT 'blofin',
                          starting_equity REAL,
                          is_active BOOLEAN,
                          total_wins INTEGER DEFAULT 0,
                          total_losses INTEGER DEFAULT 0,
                          total_trades_opened INTEGER DEFAULT 0,
                          cumulative_pnl REAL DEFAULT 0.0,
                          last_fetch_timestamp INTEGER DEFAULT 0,
                          strategy TEXT DEFAULT 'Valkyrie Elite Scalper',
                          source_wallet TEXT,
                          stock_risk_pct REAL DEFAULT 2.0,
                          alpaca_start_equity REAL)'''
            )
        
        c.execute("PRAGMA table_info(Users)")
        existing_cols = {row['name'] for row in c.fetchall()}

        # Ensure columns exist for older databases
        cols = [
            ("exchange_id", "TEXT DEFAULT 'blofin'"),
            ("cumulative_pnl", "REAL DEFAULT 0.0"),
            ("last_fetch_timestamp", "INTEGER DEFAULT 0"),
            ("strategy", "TEXT DEFAULT 'Valkyrie Elite Scalper'"),
            ("hide_dollars", "BOOLEAN DEFAULT 0"),
            ("risk_pct", "REAL DEFAULT 1.0"),
            ("enabled_symbols", "TEXT"),
            ("referred_by", "INTEGER"),
            ("premium_expiry", "INTEGER DEFAULT 0"),
            ("referral_count", "INTEGER DEFAULT 0"),
            ("has_open_positions", "BOOLEAN DEFAULT 0"),
            ("history_cache", "TEXT"),
            ("source_wallet", "TEXT"),
            ("undercover_mode", "BOOLEAN DEFAULT 0"),
            ("last_audit_stats", "TEXT"),
            ("referral_credits", "REAL DEFAULT 0.0"),
            ("full_name", "TEXT"),
            ("username", "TEXT"),
            ("is_admin", "BOOLEAN DEFAULT 0"),
            ("custom_equity_type", "TEXT DEFAULT 'all'"),
            ("custom_equity_value", "REAL"),
            ("alpaca_api_key", "TEXT"),
            ("alpaca_api_secret", "TEXT"),
            ("alpaca_endpoint", "TEXT"),
            ("active_crypto_strategy", "TEXT DEFAULT 'Valkyrie Elite Scalper'"),
            ("active_stock_strategy", "TEXT DEFAULT 'None'"),
            ("stock_risk_pct", "REAL DEFAULT 2.0"),
            ("alpaca_start_equity", "REAL"),
            ("premium_referrals", "INTEGER DEFAULT 0"),
            ("premium_expired_notified", "BOOLEAN DEFAULT 0"),
            ("had_premium_before", "BOOLEAN DEFAULT 0"),
            ("referral_reward_triggered", "BOOLEAN DEFAULT 0"),
            ("bingx_futures_type", "TEXT DEFAULT 'standard'"),
            ("coinbase_sandbox", "INTEGER DEFAULT 1")
        ]
        for col_name, col_def in cols:
            if col_name not in existing_cols:
                try: c.execute(f"ALTER TABLE Users ADD COLUMN {col_name} {col_def}")
                except: pass
            
        # Backward-compatible data migration
        try:
            # 1. Migrate stock strategy users
            c.execute("SELECT 1 FROM Users WHERE (active_stock_strategy IS NULL OR active_stock_strategy = 'None') AND strategy = 'Sherpa Velocity Pullback' LIMIT 1")
            if c.fetchone():
                c.execute("""
                    UPDATE Users 
                    SET active_stock_strategy = 'Sherpa Velocity Pullback', active_crypto_strategy = 'None'
                    WHERE (active_stock_strategy IS NULL OR active_stock_strategy = 'None') AND strategy = 'Sherpa Velocity Pullback'
                """)
            # 2. Migrate crypto strategy users
            c.execute("SELECT 1 FROM Users WHERE active_crypto_strategy IS NULL OR active_crypto_strategy = '' LIMIT 1")
            if c.fetchone():
                c.execute("""
                    UPDATE Users 
                    SET active_crypto_strategy = COALESCE(strategy, 'Valkyrie Elite Scalper'), active_stock_strategy = 'None'
                    WHERE active_crypto_strategy IS NULL OR active_crypto_strategy = ''
                """)
            # 3. Ensure no NULL values exist for the new fields
            c.execute("SELECT 1 FROM Users WHERE active_crypto_strategy IS NULL LIMIT 1")
            if c.fetchone():
                c.execute("UPDATE Users SET active_crypto_strategy = 'Valkyrie Elite Scalper' WHERE active_crypto_strategy IS NULL")
            c.execute("SELECT 1 FROM Users WHERE active_stock_strategy IS NULL LIMIT 1")
            if c.fetchone():
                c.execute("UPDATE Users SET active_stock_strategy = 'None' WHERE active_stock_strategy IS NULL")
            # 4. Repair exchange_id for users who had it set to 'alpaca' but have crypto keys
            c.execute("SELECT 1 FROM Users WHERE exchange_id = 'alpaca' AND blofin_api_key IS NOT NULL AND blofin_api_key != '' LIMIT 1")
            if c.fetchone():
                c.execute("""
                    UPDATE Users
                    SET exchange_id = 'blofin'
                    WHERE exchange_id = 'alpaca' AND blofin_api_key IS NOT NULL AND blofin_api_key != ''
                """)
            # 5. Force-migrate all users away from disabled Mean Reversion Scalper to Valkyrie Elite Scalper
            c.execute("""
                UPDATE Users
                SET active_crypto_strategy = 'Valkyrie Elite Scalper', strategy = 'Valkyrie Elite Scalper'
                WHERE active_crypto_strategy = 'Mean Reversion Scalper' OR strategy = 'Mean Reversion Scalper'
            """)
            c.execute("""
                UPDATE WebUsers
                SET active_crypto_strategy = 'Valkyrie Elite Scalper'
                WHERE active_crypto_strategy = 'Mean Reversion Scalper'
            """)
            conn.commit()
        except Exception as migration_err:
            pass
        
        # 💎 Institutional Config Table
        if "Config" not in existing_tables:
            c.execute('''CREATE TABLE IF NOT EXISTS Config
                         (key TEXT PRIMARY KEY, value TEXT)''')
        
        # 🎁 Gift Codes Table
        if "GiftCodes" not in existing_tables:
            c.execute('''CREATE TABLE IF NOT EXISTS GiftCodes
                         (code TEXT PRIMARY KEY, 
                          target_chat_id INTEGER, 
                          target_username TEXT,
                          expiry_days INTEGER DEFAULT 30, 
                          is_used BOOLEAN DEFAULT 0,
                          created_at INTEGER)''')
        
        # 🩹 Migration: Ensure target_username column exists
        c.execute("PRAGMA table_info(GiftCodes)")
        existing_gift_cols = {row['name'] for row in c.fetchall()}
        if "target_username" not in existing_gift_cols:
            try: c.execute("ALTER TABLE GiftCodes ADD COLUMN target_username TEXT")
            except: pass
        
        # Set default master wallet if not exists
        c.execute("SELECT 1 FROM Config WHERE key = 'master_usdt_wallet'")
        if not c.fetchone():
            c.execute("INSERT OR IGNORE INTO Config (key, value) VALUES ('master_usdt_wallet', 'YOUR_MASTER_TRON_ADDRESS_HERE')")
        
        # 🧪 Theoretical Trades Table
        if "TheoreticalTrades" not in existing_tables:
            c.execute('''CREATE TABLE IF NOT EXISTS TheoreticalTrades
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          symbol TEXT,
                          strategy TEXT,
                          side TEXT,
                          entry_price REAL,
                          tp_price REAL,
                          sl_price REAL,
                          open_time INTEGER,
                          close_time INTEGER,
                          status TEXT DEFAULT 'open',
                          position_size REAL DEFAULT 0.0,
                          pnl_raw REAL DEFAULT 0.0,
                          pnl_pct REAL DEFAULT 0.0,
                          pnl_usdt REAL DEFAULT 0.0)''')
                          
        # 🦙 Real Alpaca Fractional Trades Table
        if "AlpacaActiveTrades" not in existing_tables:
            c.execute('''CREATE TABLE IF NOT EXISTS AlpacaActiveTrades
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          telegram_chat_id INTEGER,
                          symbol TEXT,
                          qty REAL,
                          entry_price REAL,
                          tp_price REAL,
                          sl_price REAL,
                          open_time INTEGER,
                          close_time INTEGER,
                          close_price REAL,
                          pnl_raw REAL,
                          pnl_pct REAL,
                          status TEXT DEFAULT 'open',
                          web_user_id INTEGER)''')
                      
        # 🩹 Migration: Ensure new AlpacaActiveTrades columns exist
        c.execute("PRAGMA table_info(AlpacaActiveTrades)")
        existing_alpaca_cols = {row['name'] for row in c.fetchall()}
        
        alpaca_cols = {
            "close_time": "INTEGER",
            "close_price": "REAL",
            "pnl_raw": "REAL",
            "pnl_pct": "REAL",
            "web_user_id": "INTEGER"
        }
        for col_name, col_def in alpaca_cols.items():
            if col_name not in existing_alpaca_cols:
                try: c.execute(f"ALTER TABLE AlpacaActiveTrades ADD COLUMN {col_name} {col_def}")
                except: pass
                
        c.execute("PRAGMA table_info(WebUsers)")
        existing_webusers_cols = {row['name'] for row in c.fetchall()}
        webusers_cols = {
            "reset_token": "TEXT",
            "reset_token_expiry": "INTEGER"
        }
        for col_name, col_def in webusers_cols.items():
            if col_name not in existing_webusers_cols:
                try: c.execute(f"ALTER TABLE WebUsers ADD COLUMN {col_name} {col_def}")
                except: pass

                      
        # Set default theoretical balance
        c.execute("SELECT 1 FROM Config WHERE key = 'theoretical_balance'")
        if not c.fetchone():
            c.execute("INSERT OR IGNORE INTO Config (key, value) VALUES ('theoretical_balance', '1000.0')")

        # 🌐 Web Application Users Table
        if "WebUsers" not in existing_tables:
            c.execute('''CREATE TABLE IF NOT EXISTS WebUsers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                google_id TEXT UNIQUE,
                password_hash TEXT,
                full_name TEXT,
                telegram_chat_id INTEGER,
                exchange_id TEXT DEFAULT 'blofin',
                api_key TEXT,
                api_secret TEXT,
                api_password TEXT,
                alpaca_api_key TEXT,
                alpaca_api_secret TEXT,
                alpaca_endpoint TEXT,
                is_active BOOLEAN DEFAULT 0,
                risk_pct REAL DEFAULT 1.0,
                stock_risk_pct REAL DEFAULT 2.0,
                enabled_symbols TEXT,
                hide_dollars BOOLEAN DEFAULT 0,
                custom_equity_type TEXT DEFAULT 'all',
                custom_equity_value REAL,
                active_crypto_strategy TEXT DEFAULT 'Valkyrie Elite Scalper',
                active_stock_strategy TEXT DEFAULT 'None',
                source_wallet TEXT,
                premium_expiry INTEGER DEFAULT 0,
                referral_credits REAL DEFAULT 0.0,
                referred_by INTEGER,
                referral_count INTEGER DEFAULT 0,
                total_wins INTEGER DEFAULT 0,
                total_losses INTEGER DEFAULT 0,
                cumulative_pnl REAL DEFAULT 0.0,
                has_open_positions BOOLEAN DEFAULT 0,
                history_cache TEXT,
                last_audit_stats TEXT,
                avatar_url TEXT,
                created_at INTEGER,
                referral_reward_triggered BOOLEAN DEFAULT 0,
                alpaca_start_equity REAL
            )''')

        if "PortfolioBalanceHistory" not in existing_tables:
            c.execute('''CREATE TABLE IF NOT EXISTS PortfolioBalanceHistory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                encrypted_crypto_balance TEXT,
                encrypted_stock_balance TEXT,
                FOREIGN KEY(user_id) REFERENCES WebUsers(id)
            )''')

        # Migration: Ensure WebUsers has additional columns
        c.execute("PRAGMA table_info(WebUsers)")
        existing_web_cols_2 = {row['name'] for row in c.fetchall()}
        
        web_cols_additional = {
            "avatar_url": "TEXT",
            "premium_referrals": "INTEGER DEFAULT 0",
            "referral_reward_triggered": "BOOLEAN DEFAULT 0",
            "email_notifications": "INTEGER DEFAULT 1",
            "email_frequency": "TEXT DEFAULT 'realtime'",
            "browser_notifications": "INTEGER DEFAULT 1",
            "public_key": "TEXT",
            "encrypted_private_key": "TEXT",
            "bingx_futures_type": "TEXT DEFAULT 'standard'",
            "alpaca_start_equity": "REAL",
            "coinbase_sandbox": "INTEGER DEFAULT 1"
        }
        for col_name, col_def in web_cols_additional.items():
            if col_name not in existing_web_cols_2:
                try: c.execute(f"ALTER TABLE WebUsers ADD COLUMN {col_name} {col_def}")
                except: pass



def reset_crypto_stats(chat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE Users 
            SET starting_equity = NULL, 
                cumulative_pnl = 0.0, 
                total_wins = 0, 
                total_losses = 0, 
                total_trades_opened = 0, 
                last_audit_stats = NULL 
            WHERE telegram_chat_id = ?
        ''', (chat_id,))

def reset_stock_stats(chat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE Users 
            SET alpaca_start_equity = NULL
            WHERE telegram_chat_id = ?
        ''', (chat_id,))

def upsert_user(chat_id, api_key, api_secret, api_pass, exchange_id, is_active=False, full_name=None, username=None):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT 1 FROM Users WHERE telegram_chat_id = ?', (chat_id,))
        if c.fetchone():
            c.execute('''
                UPDATE Users 
                SET blofin_api_key = ?, blofin_api_secret = ?, blofin_api_password = ?, exchange_id = ?, is_active = ?, full_name = ?, username = ?
                WHERE telegram_chat_id = ?
            ''', (encrypt(api_key), encrypt(api_secret), encrypt(api_pass), exchange_id, is_active, full_name, username, chat_id))
            reset_crypto_stats(chat_id)
        else:
            c.execute('''
                INSERT INTO Users (telegram_chat_id, blofin_api_key, blofin_api_secret, blofin_api_password, exchange_id, is_active, full_name, username)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (chat_id, encrypt(api_key), encrypt(api_secret), encrypt(api_pass), exchange_id, is_active, full_name, username))

def get_user(chat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM Users WHERE telegram_chat_id = ?', (chat_id,))
        row = c.fetchone()
    if row:
        row_dict = dict(row)
        def_syms = "BTC,ETH,SOL,DOGE,ADA,LINK,DOT,TON,ZEC,PEPE,BNB,NEAR,SUI,NOT,TAO,ONDO,ENA,FET,WIF"
        return {
            "api_key": decrypt(row_dict.get('blofin_api_key')),
            "api_secret": decrypt(row_dict.get('blofin_api_secret')),
            "api_password": decrypt(row_dict.get('blofin_api_password')),
            "equity": row_dict.get('starting_equity'),
            "is_active": row_dict.get('is_active'),
            "wins": row_dict.get('total_wins') or 0,
            "losses": row_dict.get('total_losses') or 0,
            "opened": row_dict.get('total_trades_opened') or 0,
            "cum_pnl": row_dict.get('cumulative_pnl') or 0.0,
            "last_ts": row_dict.get('last_fetch_timestamp') or 0,
            "strategy": row_dict.get('strategy') or 'Valkyrie Elite Scalper',
            "hide_dollars": bool(row_dict.get('hide_dollars')),
            "risk_pct": row_dict.get('risk_pct') if row_dict.get('risk_pct') is not None else 1.0,
            "enabled_symbols": (row_dict.get('enabled_symbols') if row_dict.get('enabled_symbols') else def_syms).split(","),
            "exchange_id": row_dict.get('exchange_id') or 'blofin',
            "referred_by": row_dict.get('referred_by'),
            "premium_expiry": row_dict.get('premium_expiry') or 0,
            "referral_count": row_dict.get('referral_count') or 0,
            "has_open_positions": bool(row_dict.get('has_open_positions')),
            "telegram_chat_id": chat_id,
            "undercover_mode": row_dict.get('undercover_mode') or 0,
            "source_wallet": row_dict.get('source_wallet'),
            "last_audit_stats": row_dict.get('last_audit_stats'),
            "referral_credits": row_dict.get('referral_credits') or 0.0,
            "full_name": row_dict.get('full_name'),
            "username": row_dict.get('username'),
            "is_admin": bool(row_dict.get('is_admin')),
            "custom_equity_type": row_dict.get('custom_equity_type') or 'all',
            "custom_equity_value": row_dict.get('custom_equity_value'),
            "alpaca_api_key": decrypt(row_dict.get('alpaca_api_key')) if row_dict.get('alpaca_api_key') else None,
            "alpaca_api_secret": decrypt(row_dict.get('alpaca_api_secret')) if row_dict.get('alpaca_api_secret') else None,
            "alpaca_endpoint": row_dict.get('alpaca_endpoint'),
            "alpaca_start_equity": row_dict.get('alpaca_start_equity'),
            "active_crypto_strategy": row_dict.get('active_crypto_strategy') or 'Valkyrie Elite Scalper',
            "active_stock_strategy": row_dict.get('active_stock_strategy') or 'None',
            "stock_risk_pct": row_dict.get('stock_risk_pct') if row_dict.get('stock_risk_pct') is not None else 2.0,
            "premium_referrals": row_dict.get('premium_referrals') or 0,
            "premium_expired_notified": bool(row_dict.get('premium_expired_notified')),
            "had_premium_before": bool(row_dict.get('had_premium_before')),
            "referral_reward_triggered": bool(row_dict.get('referral_reward_triggered')),
            "bingx_futures_type": row_dict.get('bingx_futures_type') or 'perpetual',
            "coinbase_sandbox": row_dict.get('coinbase_sandbox') if row_dict.get('coinbase_sandbox') is not None else 1
        }
    return None

def update_last_audit(chat_id, stats_dict):
    import json
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET last_audit_stats = ? WHERE telegram_chat_id = ?", (json.dumps(stats_dict), chat_id))

def add_referral_credit(chat_id, amount=5.0):
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET referral_credits = referral_credits + ? WHERE telegram_chat_id = ?", (amount, chat_id))

def consume_referral_credits(chat_id, amount):
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET referral_credits = MAX(0, referral_credits - ?) WHERE telegram_chat_id = ?", (amount, chat_id))

def get_user_from_web_row(row):
    if not row:
        return None
    def_syms = "BTC,ETH,SOL,DOGE,ADA,LINK,DOT,TON,ZEC,PEPE,BNB,NEAR,SUI,NOT,TAO,ONDO,ENA,FET,WIF"
    
    # Decrypt keys
    api_key = None
    if row.get('api_key'):
        try: api_key = decrypt(row['api_key'])
        except: api_key = row['api_key']
    api_secret = None
    if row.get('api_secret'):
        try: api_secret = decrypt(row['api_secret'])
        except: api_secret = row['api_secret']
    api_password = None
    if row.get('api_password'):
        try: api_password = decrypt(row['api_password'])
        except: api_password = row['api_password']
    alpaca_api_key = None
    if row.get('alpaca_api_key'):
        try: alpaca_api_key = decrypt(row['alpaca_api_key'])
        except: alpaca_api_key = row['alpaca_api_key']
    alpaca_api_secret = None
    if row.get('alpaca_api_secret'):
        try: alpaca_api_secret = decrypt(row['alpaca_api_secret'])
        except: alpaca_api_secret = row['alpaca_api_secret']
        
    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "api_password": api_password,
        "equity": None,
        "is_active": bool(row.get('is_active')),
        "wins": row.get('total_wins') or 0,
        "losses": row.get('total_losses') or 0,
        "opened": 0,
        "cum_pnl": row.get('cumulative_pnl') or 0.0,
        "last_ts": 0,
        "strategy": row.get('active_crypto_strategy') or 'Valkyrie Elite Scalper',
        "hide_dollars": bool(row.get('hide_dollars')),
        "risk_pct": row.get('risk_pct') if row.get('risk_pct') is not None else 1.0,
        "enabled_symbols": (row.get('enabled_symbols') if row.get('enabled_symbols') else def_syms).split(","),
        "exchange_id": row.get('exchange_id') or 'blofin',
        "referred_by": row.get('referred_by'),
        "premium_expiry": row.get('premium_expiry') or 0,
        "referral_count": row.get('referral_count') or 0,
        "has_open_positions": bool(row.get('has_open_positions')),
        "telegram_chat_id": row.get('telegram_chat_id'),
        "web_user_id": row.get('id'),
        "undercover_mode": 0,
        "source_wallet": row.get('source_wallet'),
        "last_audit_stats": row.get('last_audit_stats'),
        "referral_credits": row.get('referral_credits') or 0.0,
        "full_name": row.get('full_name'),
        "username": None,
        "is_admin": False,
        "custom_equity_type": row.get('custom_equity_type') or 'all',
        "custom_equity_value": row.get('custom_equity_value'),
        "alpaca_api_key": alpaca_api_key,
        "alpaca_api_secret": alpaca_api_secret,
        "alpaca_endpoint": row.get('alpaca_endpoint'),
        "alpaca_start_equity": row.get('alpaca_start_equity'),
        "active_crypto_strategy": row.get('active_crypto_strategy') or 'Valkyrie Elite Scalper',
        "active_stock_strategy": row.get('active_stock_strategy') or 'None',
        "stock_risk_pct": row.get('stock_risk_pct') if row.get('stock_risk_pct') is not None else 2.0,
        "premium_referrals": row.get('premium_referrals') or 0,
        "premium_expired_notified": False,
        "had_premium_before": False,
        "referral_reward_triggered": bool(row.get('referral_reward_triggered')),
        "bingx_futures_type": row.get('bingx_futures_type') or 'perpetual',
        "coinbase_sandbox": row.get('coinbase_sandbox') if row.get('coinbase_sandbox') is not None else 1
    }

def get_all_active_users():
    with db_session() as conn:
        c = conn.cursor()
        
        # 1. Fetch active users from Users (Telegram)
        c.execute("SELECT telegram_chat_id FROM Users WHERE is_active = 1 AND blofin_api_key IS NOT NULL AND blofin_api_key != ''")
        tg_chat_ids = [row[0] for row in c.fetchall()]
        active_users = [get_user(cid) for cid in tg_chat_ids]
        
        # 2. Fetch active users from WebUsers (Web-only or not synced)
        try:
            c.execute("SELECT * FROM WebUsers WHERE is_active = 1 AND api_key IS NOT NULL AND api_key != ''")
            web_rows = c.fetchall()
            for r in web_rows:
                web_user = dict(r)
                tg_id = web_user.get('telegram_chat_id')
                if tg_id and tg_id in tg_chat_ids:
                    continue
                formatted_web_user = get_user_from_web_row(web_user)
                active_users.append(formatted_web_user)
        except Exception as e:
            print(f"Error querying WebUsers in get_all_active_users: {e}")
            
    return active_users

def get_all_active_stock_users():
    with db_session() as conn:
        c = conn.cursor()
        
        # 1. Fetch active stock users from Users (Telegram)
        c.execute("SELECT telegram_chat_id FROM Users WHERE is_active = 1 AND alpaca_api_key IS NOT NULL AND alpaca_api_key != ''")
        tg_chat_ids = [row[0] for row in c.fetchall()]
        active_users = [get_user(cid) for cid in tg_chat_ids]
        
        # 2. Fetch active stock users from WebUsers (Web-only or not synced)
        try:
            c.execute("SELECT * FROM WebUsers WHERE is_active = 1 AND alpaca_api_key IS NOT NULL AND alpaca_api_key != ''")
            web_rows = c.fetchall()
            for r in web_rows:
                web_user = dict(r)
                tg_id = web_user.get('telegram_chat_id')
                if tg_id and tg_id in tg_chat_ids:
                    continue
                formatted_web_user = get_user_from_web_row(web_user)
                active_users.append(formatted_web_user)
        except Exception as e:
            print(f"Error querying WebUsers in get_all_active_stock_users: {e}")
            
    return active_users

def set_active(chat_id, is_active):
    with db_session() as conn:
        c = conn.cursor()
        val = 1 if is_active else 0
        c.execute("UPDATE Users SET is_active = ? WHERE telegram_chat_id = ?", (val, chat_id))
        # Sync to WebUsers if linked
        try:
            c.execute("UPDATE WebUsers SET is_active = ? WHERE telegram_chat_id = ?", (val, chat_id))
        except Exception as e:
            print(f"Sync to WebUsers status failed: {e}")

def update_user_preference(chat_id, key, value):
    with db_session() as conn:
        c = conn.cursor()
        # Map key to column name (Whitelist)
        cols = {
            "strategy": "strategy", 
            "hide_dollars": "hide_dollars", 
            "risk_pct": "risk_pct", 
            "enabled_symbols": "enabled_symbols", 
            "exchange_id": "exchange_id",
            "custom_equity_type": "custom_equity_type",
            "custom_equity_value": "custom_equity_value",
            "alpaca_api_key": "alpaca_api_key",
            "alpaca_api_secret": "alpaca_api_secret",
            "alpaca_endpoint": "alpaca_endpoint",
            "active_crypto_strategy": "active_crypto_strategy",
            "active_stock_strategy": "active_stock_strategy",
            "stock_risk_pct": "stock_risk_pct"
        }
        if key in cols:
            col_name = cols[key]
            if key in ["alpaca_api_key", "alpaca_api_secret"] and value:
                value = encrypt(value)
            if key == "enabled_symbols" and isinstance(value, list):
                value = ",".join(value)
            # Use parameter substitution for the value, but we still have to format the column name
            # since SQL parameters don't work for column/table names. Whitelist ensures safety.
            c.execute(f"UPDATE Users SET {col_name} = ? WHERE telegram_chat_id = ?", (value, chat_id))
            
            # Sync corresponding fields to WebUsers if linked
            web_sync_cols = {
                "active_crypto_strategy": "active_crypto_strategy",
                "active_stock_strategy": "active_stock_strategy",
                "risk_pct": "risk_pct",
                "stock_risk_pct": "stock_risk_pct",
                "custom_equity_type": "custom_equity_type",
                "custom_equity_value": "custom_equity_value",
                "hide_dollars": "hide_dollars"
            }
            if key in web_sync_cols:
                web_col = web_sync_cols[key]
                try:
                    c.execute(f"UPDATE WebUsers SET {web_col} = ? WHERE telegram_chat_id = ?", (value, chat_id))
                except Exception as e:
                    print(f"Sync preference {key} to WebUsers failed: {e}")

def increment_opened(chat_id):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE Users SET total_trades_opened = total_trades_opened + 1 WHERE telegram_chat_id = ?', (chat_id,))

def update_user_crypto_strategy(chat_id, strategy):
    update_user_preference(chat_id, "active_crypto_strategy", strategy)
    update_user_preference(chat_id, "strategy", strategy)  # Keep backward compatibility

def update_user_stock_strategy(chat_id, strategy):
    update_user_preference(chat_id, "active_stock_strategy", strategy)

async def rebuild_history_cache_from_engine(chat_id, exchange, web_user_id=None):
    """
    Called from the engine loop (running on the VPS with active whitelisting)
    to rebuild the history_cache column for the user in the database.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Rebuilding history cache from engine for chat_id: {chat_id} web_user_id: {web_user_id}")
    try:
        await exchange.load_markets()
        import live_bot_multi
        all_closed = []
        
        # Determine enabled symbols
        enabled_symbols = []
        user_data = get_user(chat_id) if chat_id else None
        if not user_data and web_user_id:
            from web_api.db_web import get_web_user_by_id
            web_raw = get_web_user_by_id(web_user_id)
            user_data = get_user_from_web_row(web_raw) if web_raw else None
        if user_data:
            enabled_symbols = user_data.get('enabled_symbols', [])
            
        symbols_to_check = [sym for sym in live_bot_multi.SYMBOLS if sym.split("/")[0] in enabled_symbols]
        if not symbols_to_check:
            symbols_to_check = live_bot_multi.SYMBOLS
            
        sem = asyncio.Semaphore(2) # rate limit helper
        
        async def fetch_sym_history(sym):
            try:
                norm_sym = normalize_symbol(sym, exchange.id)
                if norm_sym not in exchange.markets:
                    return
                since = int((time.time() - 90 * 86400) * 1000) # 90 days ago
                async with sem:
                    await asyncio.sleep(0.1) # tiny throttle
                    trades = await exchange.fetch_my_trades(norm_sym, since=since, limit=50)
                pnl_results = process_exchange_trades_for_symbol(trades, exchange.id)
                
                order_groups = {}
                for res in pnl_results:
                    t = res["trade"]
                    net_pnl = res["net_pnl"]
                    side_raw = t.get('side', 'buy').lower()
                    is_long = (side_raw == 'sell')
                    
                    order_id = t.get('order') or t.get('id') or f"{t['timestamp']}_{sym}"
                    if order_id not in order_groups:
                        order_groups[order_id] = []
                        
                    order_groups[order_id].append({
                        "net_pnl": net_pnl,
                        "price": t['price'],
                        "amount": t['amount'],
                        "timestamp": t['timestamp'],
                        "is_long": is_long
                    })
                        
                for order_id, fills in order_groups.items():
                    total_net_pnl = sum(f['net_pnl'] for f in fills)
                    total_amount = sum(f['amount'] for f in fills)
                    total_cost = sum(f['price'] * f['amount'] for f in fills)
                    avg_price = total_cost / total_amount if total_amount > 0 else fills[0]['price']
                    
                    max_timestamp = max(f['timestamp'] for f in fills)
                    is_long = fills[0]['is_long']
                    
                    try:
                        market = exchange.market(norm_sym)
                        contract_size = float(market.get('contractSize', 1))
                        initial_margin = (avg_price * total_amount * contract_size) / 20
                        roe_val = (total_net_pnl / initial_margin) * 100 if initial_margin > 0 else 0
                    except:
                        roe_val = 0
                        
                    all_closed.append({
                        "symbol": sym,
                        "timestamp": max_timestamp,
                        "net_pnl": total_net_pnl,
                        "price": avg_price,
                        "amount": total_amount,
                        "side": "l" if is_long else "s",
                        "roe_val": roe_val
                    })
            except Exception as sym_err:
                logger.error(f"Error fetching history for {sym}: {sym_err}")
 
        # Fetch in parallel
        await asyncio.gather(*(fetch_sym_history(sym) for sym in symbols_to_check))
        
        all_closed.sort(key=lambda x: x['timestamp'], reverse=True)
        last_50 = all_closed[:50]
        
        if last_50:
            set_history_cache(chat_id, last_50, web_user_id=web_user_id)
            logger.info(f"Rebuild cache success. Saved {len(last_50)} trades for chat_id {chat_id} web_user_id {web_user_id}.")
    except Exception as e:
        logger.error(f"Failed to rebuild history cache from engine: {e}")
 
async def update_user_stats_from_engine(chat_id, equity, exchange, application, web_user_id=None):
    """
    Syncs trades from exchange and updates DB stats.
    Sends Telegram notifications for closed trades.
    """
    if chat_id:
        user = get_user(chat_id)
    elif web_user_id:
        from web_api.db_web import get_web_user_by_id
        web_raw = get_web_user_by_id(web_user_id)
        user = get_user_from_web_row(web_raw) if web_raw else None
    else:
        return
        
    if not user: return
    
    last_ts = user['last_ts']
    if last_ts == 0:
        last_ts = int((time.time() - 90 * 86400) * 1000) # 90 days ago
        
    wins = user['wins']
    losses = user['losses']
    cum_pnl = user['cum_pnl']
    now_ts = int(time.time() * 1000)
    
    import live_bot_multi
    
    try:
        # 🕵️ Smart UI: Sync Position Status
        try:
            positions = await exchange.fetch_positions()
            has_active = any(float(p.get("contracts", 0) or 0) != 0 for p in positions)
            # We'll update this in the DB at the end of the function with the other stats
        except:
            has_active = False

        # Optimization: If the user currently has no active positions AND had no open positions recorded in the DB,
        # skip fetching trade history entirely since no trade could have closed.
        if not has_active and not user.get('has_open_positions', False):
            with db_session() as conn:
                c = conn.cursor()
                if chat_id:
                    c.execute("UPDATE Users SET has_open_positions = 0, last_fetch_timestamp = ? WHERE telegram_chat_id = ?", (now_ts, chat_id))
                elif web_user_id:
                    c.execute("UPDATE WebUsers SET has_open_positions = 0 WHERE id = ?", (web_user_id,))
            return
 
        new_closed = []
        
        # Determine enabled symbols
        enabled_symbols = user.get('enabled_symbols', [])
        symbols_to_check = [sym for sym in live_bot_multi.SYMBOLS if sym.split("/")[0] in enabled_symbols]
        
        sem = asyncio.Semaphore(2) # rate limit helper
        
        # We'll process all symbols in parallel for this user
        async def process_symbol_trades(sym):
            nonlocal wins, losses, cum_pnl
            try:
                norm_sym = normalize_symbol(sym, exchange.id)
                if norm_sym not in exchange.markets:
                    return []
                    
                params = {'instType': 'SWAP'} if exchange.id == 'blofin' else {}
                async with sem:
                    await asyncio.sleep(0.1) # tiny throttle
                    trades = await exchange.fetch_my_trades(norm_sym, since=last_ts, params=params)
                
                symbol_new_closed = []
                for t in trades:
                    if t['timestamp'] <= last_ts: continue
                    
                    try:
                        info = t.get("info", {})
                        # PnL Reconstruction
                        gross_pnl = 0
                        if exchange.id == 'blofin':
                            gross_pnl = float(info.get("fillPnl") or 0)
                        else:
                            # Binance/MEXC/Bybit/Bitget
                            gross_pnl = float(info.get("realizedPnl") or info.get("profit") or 0)
                        
                        if gross_pnl != 0:
                            fee = float(info.get("fee") or t.get("fee", {}).get("cost", 0))
                            net_pnl = gross_pnl - (fee * 2)
                            
                            try:
                                market = exchange.market(norm_sym)
                                contract_size = float(market.get('contractSize', 1))
                                initial_margin = (float(t['price']) * float(t['amount']) * contract_size) / 20
                                roe_pct = (net_pnl / initial_margin) * 100 if initial_margin > 0 else 0
                            except:
                                roe_pct = 0
                            
                            cum_pnl += net_pnl
                            share_data = None
                            
                            side_raw = t.get('side', 'buy').lower()
                            is_long = (side_raw == 'sell')
                            direction_str = "LONG" if is_long else "SHORT"
                            
                            from bot.config import CRYPTO_LEVERAGE
                            leverage = int(CRYPTO_LEVERAGE)
                            
                            if net_pnl > 0:
                                wins += 1
                                header = "🏆 *Trade Won!*"
                                side_code = "l" if is_long else "s"
                                share_data = f"sh_{sym}_{side_code}_{roe_pct:.2f}_{t.get('price', 0)}_{t.get('price', 0)}_{net_pnl:.2f}"
                            else:
                                losses += 1
                                header = "❌ *Trade Lost*"
                                
                            symbol_new_closed.append({
                                "msg": f"{header}\n\nSymbol: `{sym}`\nDirection: *{direction_str} {leverage}x*\nPnL: *${net_pnl:.2f}*\nROE: *{roe_pct:+.2f}%*",
                                "share_data": share_data
                            })
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).error(f"Error processing trade {t.get('id', 'unknown')}: {e}")
                return symbol_new_closed
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error fetching trades for {sym}: {e}")
                return []
 
        results = await asyncio.gather(*(process_symbol_trades(sym) for sym in symbols_to_check))
        for r in results:
            new_closed.extend(r)
            
        if new_closed:
            clear_history_cache(chat_id, web_user_id=web_user_id)
 
        # Robust engine cache synchronization: check if cache is empty or if we had new closed trades
        cache_empty = False
        try:
            with db_session() as conn:
                c = conn.cursor()
                if chat_id:
                    c.execute("SELECT history_cache FROM Users WHERE telegram_chat_id = ?", (chat_id,))
                else:
                    c.execute("SELECT history_cache FROM WebUsers WHERE id = ?", (web_user_id,))
                row = c.fetchone()
                if not row or not row[0]:
                    cache_empty = True
        except Exception as cache_check_err:
            import logging
            logging.getLogger(__name__).error(f"Error checking cache: {cache_check_err}")
 
        if new_closed or cache_empty:
            try:
                await rebuild_history_cache_from_engine(chat_id, exchange, web_user_id=web_user_id)
            except Exception as cache_rebuild_err:
                import logging
                logging.getLogger(__name__).error(f"Error rebuilding cache: {cache_rebuild_err}")
            
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        # Update DB
        with db_session() as conn:
            c = conn.cursor()
            if chat_id:
                c.execute('''UPDATE Users SET total_wins = ?, total_losses = ?, cumulative_pnl = ?, last_fetch_timestamp = ?, starting_equity = ?, has_open_positions = ?
                             WHERE telegram_chat_id = ?''', (wins, losses, cum_pnl, now_ts, equity, 1 if has_active else 0, chat_id))
                try:
                    c.execute('''UPDATE WebUsers SET total_wins = ?, total_losses = ?, cumulative_pnl = ?, has_open_positions = ?
                                 WHERE telegram_chat_id = ?''', (wins, losses, cum_pnl, 1 if has_active else 0, chat_id))
                except:
                    pass
            elif web_user_id:
                c.execute('''UPDATE WebUsers SET total_wins = ?, total_losses = ?, cumulative_pnl = ?, has_open_positions = ?
                             WHERE id = ?''', (wins, losses, cum_pnl, 1 if has_active else 0, web_user_id))
        
        # Notify User
        if chat_id:
            for nc in new_closed:
                markup = None
                if nc.get("share_data"):
                    btn = InlineKeyboardButton("📸 Share Result", callback_data=nc["share_data"])
                    markup = InlineKeyboardMarkup([[btn]])
                
                await application.bot.send_message(
                    chat_id=chat_id, 
                    text=nc['msg'], 
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Critical error in sync_trades_from_exchange for {chat_id or web_user_id}: {e}")

def set_referrer(chat_id, referrer_id):
    """Links a new user to a referrer and increments the referrer's count."""
    if chat_id == referrer_id: return False # No self-referral
    
    with db_session() as conn:
        c = conn.cursor()
        # Check if user already has a referrer
        c.execute("SELECT referred_by FROM Users WHERE telegram_chat_id = ?", (chat_id,))
        row = c.fetchone()
        
        # If user exists and doesn't have a referrer yet
        if row and row[0] is None:
            c.execute("UPDATE Users SET referred_by = ? WHERE telegram_chat_id = ?", (referrer_id, chat_id))
            c.execute("UPDATE Users SET referral_count = referral_count + 1 WHERE telegram_chat_id = ?", (referrer_id,))
            return True # Linked successfully
    
    return False

def add_premium_days(chat_id, days):
    """Extends a user's premium status by X days."""
    user = get_user(chat_id)
    if not user: return
    
    now = int(time.time())
    current_expiry = max(user['premium_expiry'], now)
    new_expiry = current_expiry + (days * 86400)
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET premium_expiry = ?, premium_expired_notified = 0, had_premium_before = 1 WHERE telegram_chat_id = ?", (new_expiry, chat_id))

def revoke_premium(chat_id):
    """Revokes a user's premium status immediately."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET premium_expiry = 0, premium_expired_notified = 1 WHERE telegram_chat_id = ?", (chat_id,))

def get_referral_stats(chat_id):
    """Returns the total number of referrals for a user."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT referral_count FROM Users WHERE telegram_chat_id = ?", (chat_id,))
        row = c.fetchone()
    return row[0] if row else 0

def update_user_wallet(chat_id, wallet_address):
    """Updates the user's source wallet address for payment verification."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET source_wallet = ? WHERE telegram_chat_id = ?", (wallet_address, chat_id))

def get_expired_unnotified_users():
    """Returns a list of chat_ids for users whose premium expired but haven't been notified."""
    now = int(time.time())
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id FROM Users WHERE premium_expiry > 0 AND premium_expiry < ? AND premium_expired_notified = 0", (now,))
        return [row[0] for row in c.fetchall()]

def set_premium_expired_notified(chat_id, value=True):
    """Marks a user as notified about their premium expiration."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET premium_expired_notified = ? WHERE telegram_chat_id = ?", (int(value), chat_id))

def check_and_award_referral_bonus(referrer_id):
    """Awards 30 days of premium for every 3 premium referrals."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT premium_referrals FROM Users WHERE telegram_chat_id = ?", (referrer_id,))
        row = c.fetchone()
        count = row[0] if row else 0

    if count > 0 and count % 3 == 0:
        add_premium_days(referrer_id, 30)
        return True # Reward granted
    return False

def award_premium_referral(referrer_id):
    """Increments premium_referrals and checks for the bonus."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET premium_referrals = premium_referrals + 1 WHERE telegram_chat_id = ?", (referrer_id,))
    return check_and_award_referral_bonus(referrer_id)

def update_position_status(chat_id, has_active, web_user_id=None):
    """Updates the has_open_positions flag in the database."""
    with db_session() as conn:
        c = conn.cursor()
        if chat_id:
            c.execute("UPDATE Users SET has_open_positions = ? WHERE telegram_chat_id = ?", (1 if has_active else 0, chat_id))
            try:
                c.execute("UPDATE WebUsers SET has_open_positions = ? WHERE telegram_chat_id = ?", (1 if has_active else 0, chat_id))
            except:
                pass
        elif web_user_id:
            c.execute("UPDATE WebUsers SET has_open_positions = ? WHERE id = ?", (1 if has_active else 0, web_user_id))

def update_user_strategy(chat_id, strategy_name):
    """Updates the user's active trading strategy."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET strategy = ? WHERE telegram_chat_id = ?", (strategy_name, chat_id))

def set_history_cache(chat_id, trades, web_user_id=None):
    """Stores the last 10 trades as a JSON blob."""
    import json
    with db_session() as conn:
        c = conn.cursor()
        if chat_id:
            c.execute("UPDATE Users SET history_cache = ? WHERE telegram_chat_id = ?", (json.dumps(trades), chat_id))
            try:
                c.execute("UPDATE WebUsers SET history_cache = ? WHERE telegram_chat_id = ?", (json.dumps(trades), chat_id))
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to sync WebUsers history_cache: {e}")
        elif web_user_id:
            c.execute("UPDATE WebUsers SET history_cache = ? WHERE id = ?", (json.dumps(trades), web_user_id))

def clear_history_cache(chat_id, web_user_id=None):
    """Clears the trade history cache."""
    with db_session() as conn:
        c = conn.cursor()
        if chat_id:
            c.execute("UPDATE Users SET history_cache = NULL WHERE telegram_chat_id = ?", (chat_id,))
            try:
                c.execute("UPDATE WebUsers SET history_cache = NULL WHERE telegram_chat_id = ?", (chat_id,))
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to sync WebUsers clear cache: {e}")
        elif web_user_id:
            c.execute("UPDATE WebUsers SET history_cache = NULL WHERE id = ?", (web_user_id,))

def is_premium(user):
    """Returns True if the user has an active premium subscription or is the Admin."""
    if not user: return False
    # 👑 Overlord Privilege (Suspended in Undercover Mode)
    if user.get('telegram_chat_id') == 1567788633 and not user.get('undercover_mode'):
        return True
    return user.get('premium_expiry', 0) > time.time()

def set_admin_status(chat_id, status: bool):
    """Promotes or demotes a user to Admin status."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Users SET is_admin = ? WHERE telegram_chat_id = ?", (1 if status else 0, chat_id))

def is_admin(chat_id):
    """Returns True if the user is an Admin in the database."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT is_admin FROM Users WHERE telegram_chat_id = ?", (chat_id,))
        row = c.fetchone()
        return bool(row[0]) if row else False

def get_all_admins():
    """Returns a list of all telegram_chat_ids for users with is_admin=1."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id FROM Users WHERE is_admin = 1")
        return [row[0] for row in c.fetchall()]

def toggle_undercover(chat_id):
    """Toggles the undercover mode for the founder."""
    with db_session() as conn:
        c = conn.cursor()
        # Robust toggle logic: if 1 then 0, else 1 (handles NULLs)
        c.execute("""
            UPDATE Users 
            SET undercover_mode = CASE WHEN undercover_mode = 1 THEN 0 ELSE 1 END 
            WHERE telegram_chat_id = ?
        """, (chat_id,))

def get_premium_days_left(user):
    """Returns the number of days remaining in the user's premium subscription."""
    if not user: return 0
    expiry = user.get('premium_expiry', 0)
    now = time.time()
    if expiry <= now: return 0
    return int((expiry - now) / 86400)

# --- Administrative Controls ---

def get_config(key, default=None):
    """Retrieves a global configuration value."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM Config WHERE key = ?", (key,))
        row = c.fetchone()
    return row[0] if row else default

def update_config(key, value):
    """Updates a global configuration value."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO Config (key, value) VALUES (?, ?)", (key, value))

def get_platform_stats():
    """Returns high-level platform analytics for the admin."""
    with db_session() as conn:
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM Users")
        total_users = c.fetchone()[0]
        
        c.execute("SELECT SUM(referral_count) FROM Users")
        total_referrals = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM Users WHERE premium_expiry > ?", (time.time(),))
        premium_users = c.fetchone()[0]
    
    return {
        "total_users": total_users,
        "total_referrals": total_referrals,
        "premium_users": premium_users
    }
def get_detailed_user_report():
    """Returns a list of all users with their institutional status and referral info."""
    with db_session() as conn:
        # We need to manually set row_factory because db_session already sets it,
        # but let's be explicit if we wanted something else.
        # Actually sqlite3.Row is already set in db_session.
        c = conn.cursor()
        c.execute('''
            SELECT 
                telegram_chat_id,
                premium_expiry,
                referral_count,
                referred_by,
                is_active,
                full_name,
                username
            FROM Users
        ''')
        rows = c.fetchall()
        report = []
        now = time.time()
        for r in rows:
            item = dict(r)
            item['is_premium'] = r['premium_expiry'] > now
            
            # Check if linked to the Web App and get their email
            c.execute("SELECT email FROM WebUsers WHERE telegram_chat_id = ?", (r['telegram_chat_id'],))
            web_user = c.fetchone()
            if web_user:
                item['web_email'] = web_user['email']
                item['is_web_linked'] = True
            else:
                item['web_email'] = None
                item['is_web_linked'] = False
            
            # 🤝 Map Recruits (Fetch their names/IDs)
            c.execute("SELECT full_name, username, telegram_chat_id FROM Users WHERE referred_by = ?", (r['telegram_chat_id'],))
            recruits = c.fetchall()
            item['recruit_list'] = [dict(rec) for rec in recruits]
            
            report.append(item)
    return report

def get_all_users():
    """Returns all unique users for global reports."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM Users")
        rows = c.fetchall()
    return [dict(r) for r in rows]

def get_all_broadcast_targets():
    """Returns all unique chat IDs for global announcements."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id FROM Users")
        rows = c.fetchall()
    return [r[0] for r in rows]
def create_gift_code(target_chat_id=None, target_username=None, days=30):
    """Generates a unique gift code tied to an ID or a proactive username claim."""
    import secrets
    import string
    # Clean username
    if target_username:
        target_username = target_username.lstrip('@')
        
    code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    with db_session() as conn:
        c = conn.cursor()
        c.execute('INSERT INTO GiftCodes (code, target_chat_id, target_username, expiry_days, is_used, created_at) VALUES (?, ?, ?, ?, 0, ?)', 
                  (code, target_chat_id, target_username, days, int(time.time())))
    return code

def redeem_gift_code(chat_id, code, current_username=None):
    """Activates a gift code and grants institutional premium power."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT target_chat_id, target_username, expiry_days, is_used FROM GiftCodes WHERE code = ?', (code,))
        row = c.fetchone()
        if not row:
            return False, "❌ Invalid gift code."
        
        target_id, target_username, days, is_used = row['target_chat_id'], row['target_username'], row['expiry_days'], row['is_used']
        if is_used:
            return False, "❌ This code has already been redeemed."
        
        # Validation Logic
        if target_id and int(target_id) != int(chat_id):
            return False, "❌ This code is tied to a different user ID."
        
        if target_username:
            clean_current = current_username.lstrip('@') if current_username else None
            if target_username.lower() != (clean_current.lower() if clean_current else ""):
                return False, f"❌ This code is reserved for @{target_username}."    
        # Grant premium
        current_time = int(time.time())
        c.execute('SELECT premium_expiry FROM Users WHERE telegram_chat_id = ?', (chat_id,))
        u_row = c.fetchone()
        current_expiry = u_row['premium_expiry'] if u_row else 0
        
        new_expiry = max(current_expiry, current_time) + (days * 86400)
        c.execute('UPDATE Users SET premium_expiry = ? WHERE telegram_chat_id = ?', (new_expiry, chat_id))
        c.execute('UPDATE GiftCodes SET is_used = 1 WHERE code = ?', (code,))
        
    return True, f"✅ Success! You have been granted {days} days of Premium Institutional access."

def redeem_gift_code_web(web_user_id, code):
    """Redeems a gift code for a web user, synchronizing premium status to linked bot account if exists."""
    with db_session() as conn:
        c = conn.cursor()
        
        # 1. Fetch gift code
        c.execute('SELECT target_chat_id, target_username, expiry_days, is_used FROM GiftCodes WHERE code = ?', (code,))
        row = c.fetchone()
        if not row:
            return False, "❌ Invalid gift code."
            
        target_id, target_username, days, is_used = row['target_chat_id'], row['target_username'], row['expiry_days'], row['is_used']
        if is_used:
            return False, "❌ This code has already been redeemed."
            
        # 2. Fetch web user details
        c.execute('SELECT telegram_chat_id, premium_expiry FROM WebUsers WHERE id = ?', (web_user_id,))
        w_row = c.fetchone()
        if not w_row:
            return False, "❌ User not found."
        telegram_chat_id = w_row['telegram_chat_id']
        w_expiry = w_row['premium_expiry'] or 0
        
        # 3. Check optional reservations
        if target_id:
            if not telegram_chat_id or int(target_id) != int(telegram_chat_id):
                return False, "❌ This code is reserved for a specific Telegram account. Please link your Telegram or redeem it inside the Telegram bot."
                
        if target_username:
            username = None
            if telegram_chat_id:
                c.execute('SELECT username FROM Users WHERE telegram_chat_id = ?', (telegram_chat_id,))
                u_row = c.fetchone()
                if u_row:
                    username = u_row['username']
            clean_target = target_username.lstrip('@')
            clean_current = username.lstrip('@') if username else None
            if not clean_current or clean_target.lower() != clean_current.lower():
                return False, f"❌ This code is reserved for @{clean_target}. Please link your @{clean_target} Telegram account to redeem this."
                
        # 4. Grant premium in WebUsers
        current_time = int(time.time())
        new_expiry = max(w_expiry, current_time) + (days * 86400)
        c.execute('UPDATE WebUsers SET premium_expiry = ? WHERE id = ?', (new_expiry, web_user_id))
        
        # 5. Sync to linked Users table (Bot) if linked
        if telegram_chat_id:
            c.execute('SELECT premium_expiry FROM Users WHERE telegram_chat_id = ?', (telegram_chat_id,))
            u_row = c.fetchone()
            current_expiry = u_row['premium_expiry'] if u_row else 0
            new_bot_expiry = max(current_expiry, current_time) + (days * 86400)
            c.execute('UPDATE Users SET premium_expiry = ? WHERE telegram_chat_id = ?', (new_bot_expiry, telegram_chat_id))
            
        # 6. Mark as used
        c.execute('UPDATE GiftCodes SET is_used = 1 WHERE code = ?', (code,))
        
    return True, f"✅ Success! You have been granted {days} days of Premium Institutional access."

def get_chat_id_by_username(username):
    """Resolves a @username to a telegram_chat_id from the database."""
    clean_username = username.lstrip('@')
    with db_session() as conn:
        c = conn.cursor()
        c.execute('SELECT telegram_chat_id FROM Users WHERE username = ? OR username = ? OR full_name LIKE ?', 
                  (clean_username, f"@{clean_username}", f"%{clean_username}%"))
        row = c.fetchone()
    return row[0] if row else None

def get_open_theoretical_trades():
    """Returns all currently open theoretical trades."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM TheoreticalTrades WHERE status = 'open'")
        rows = c.fetchall()
    return [dict(r) for r in rows]

def get_active_theoretical_trade_by_symbol(symbol):
    """Returns the currently open theoretical trade for a specific symbol."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM TheoreticalTrades WHERE symbol = ? AND status = 'open' LIMIT 1", (symbol,))
        row = c.fetchone()
    return dict(row) if row else None

def add_theoretical_trade(symbol, strategy, side, entry_price, tp_price, sl_price, open_time, position_size):
    """Inserts a new open theoretical trade in the database."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO TheoreticalTrades 
                     (symbol, strategy, side, entry_price, tp_price, sl_price, open_time, status, position_size)
                     VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)''',
                  (symbol, strategy, side, entry_price, tp_price, sl_price, open_time, position_size))

def close_theoretical_trade(trade_id, close_price, close_time, status, pnl_raw, pnl_pct, pnl_usdt):
    """Closes an open theoretical trade and updates its performance metrics."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''UPDATE TheoreticalTrades 
                     SET close_time = ?, status = ?, pnl_raw = ?, pnl_pct = ?, pnl_usdt = ? 
                     WHERE id = ?''',
                  (close_time, status, pnl_raw, pnl_pct, pnl_usdt, trade_id))

def get_theoretical_balance():
    """Gets the current simulated compounding balance."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM Config WHERE key = 'theoretical_balance'")
        row = c.fetchone()
    return float(row[0]) if row else 1000.0

def update_theoretical_balance(balance):
    """Updates the simulated compounding balance."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("UPDATE Config SET value = ? WHERE key = 'theoretical_balance'", (str(balance),))

def get_theoretical_stats():
    """Computes high-level theoretical performance stats."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM TheoreticalTrades")
        total_trades = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM TheoreticalTrades WHERE status != 'open' AND pnl_usdt > 0")
        wins = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM TheoreticalTrades WHERE status != 'open' AND pnl_usdt <= 0")
        losses = c.fetchone()[0]
        
        c.execute("SELECT SUM(pnl_usdt) FROM TheoreticalTrades WHERE status != 'open'")
        pnl_sum = c.fetchone()[0] or 0.0
        
        # Calculate win rate
        total_closed = wins + losses
        win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
        
        # Simulated Balance
        c.execute("SELECT value FROM Config WHERE key = 'theoretical_balance'")
        bal_row = c.fetchone()
        current_balance = float(bal_row[0]) if bal_row else 1000.0
        
    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "cumulative_pnl": pnl_sum,
        "current_balance": current_balance
    }

def get_theoretical_stats_by_strategy(strategy_name):
    """Computes theoretical performance stats for a specific strategy."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM TheoreticalTrades WHERE strategy = ?", (strategy_name,))
        total_trades = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM TheoreticalTrades WHERE strategy = ? AND status != 'open' AND pnl_usdt > 0", (strategy_name,))
        wins = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM TheoreticalTrades WHERE strategy = ? AND status != 'open' AND pnl_usdt <= 0", (strategy_name,))
        losses = c.fetchone()[0]
        
        c.execute("SELECT SUM(pnl_usdt) FROM TheoreticalTrades WHERE strategy = ? AND status != 'open'", (strategy_name,))
        pnl_sum = c.fetchone()[0] or 0.0
        
        # Calculate win rate
        total_closed = wins + losses
        win_rate = (wins / total_closed * 100) if total_closed > 0 else 0.0
        
    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "cumulative_pnl": pnl_sum
    }

def get_recent_theoretical_trades(limit=10):
    """Returns the most recent theoretical trades (open and closed)."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM TheoreticalTrades ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
    return [dict(r) for r in rows]

def get_theoretical_trade(trade_id):
    """Returns a theoretical trade by ID."""
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM TheoreticalTrades WHERE id = ?", (trade_id,))
        row = c.fetchone()
    return dict(row) if row else None

# --- Alpaca Active Trades Helpers ---

def add_alpaca_active_trade(chat_id, symbol, qty, entry_price, tp_price, sl_price, open_time, web_user_id=None):
    with db_session() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO AlpacaActiveTrades (telegram_chat_id, symbol, qty, entry_price, tp_price, sl_price, open_time, status, web_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
        ''', (chat_id, symbol, float(qty), float(entry_price), float(tp_price), float(sl_price), open_time, web_user_id))

def get_open_alpaca_trades():
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM AlpacaActiveTrades WHERE status = 'open'")
        rows = c.fetchall()
    return [dict(r) for r in rows]

def get_open_alpaca_trades_by_user(chat_id, web_user_id=None):
    with db_session() as conn:
        c = conn.cursor()
        if chat_id:
            c.execute("SELECT * FROM AlpacaActiveTrades WHERE status = 'open' AND telegram_chat_id = ?", (chat_id,))
        elif web_user_id:
            c.execute("SELECT * FROM AlpacaActiveTrades WHERE status = 'open' AND web_user_id = ?", (web_user_id,))
        else:
            return []
        rows = c.fetchall()
    return [dict(r) for r in rows]

def get_closed_alpaca_trades_by_user(chat_id, limit=10, web_user_id=None):
    with db_session() as conn:
        c = conn.cursor()
        if chat_id:
            c.execute("SELECT * FROM AlpacaActiveTrades WHERE status = 'closed' AND telegram_chat_id = ? ORDER BY close_time DESC LIMIT ?", (chat_id, limit))
        elif web_user_id:
            c.execute("SELECT * FROM AlpacaActiveTrades WHERE status = 'closed' AND web_user_id = ? ORDER BY close_time DESC LIMIT ?", (web_user_id, limit))
        else:
            return []
        rows = c.fetchall()
    return [dict(r) for r in rows]

def close_alpaca_trade(trade_id, close_time=None, close_price=None, pnl_raw=None, pnl_pct=None):
    with db_session() as conn:
        c = conn.cursor()
        
        # Get chat_id and web_user_id to clear cache
        c.execute("SELECT telegram_chat_id, web_user_id FROM AlpacaActiveTrades WHERE id = ?", (trade_id,))
        row = c.fetchone()
        chat_id = row[0] if row else None
        web_user_id = row[1] if row else None
        
        c.execute("""
            UPDATE AlpacaActiveTrades 
            SET status = 'closed', 
                close_time = ?, 
                close_price = ?, 
                pnl_raw = ?, 
                pnl_pct = ? 
            WHERE id = ?
        """, (close_time, close_price, pnl_raw, pnl_pct, trade_id))
        
        if chat_id:
            c.execute("UPDATE Users SET history_cache = NULL WHERE telegram_chat_id = ?", (chat_id,))
            try:
                c.execute("UPDATE WebUsers SET history_cache = NULL WHERE telegram_chat_id = ?", (chat_id,))
            except:
                pass
        elif web_user_id:
            c.execute("UPDATE WebUsers SET history_cache = NULL WHERE id = ?", (web_user_id,))

def make_alpaca_request(user, method, path, params=None, json_data=None):
    import requests
    endpoint = user.get("alpaca_endpoint") or "https://api.alpaca.markets"
    # Ensure no trailing slash
    endpoint = endpoint.rstrip('/')
    # If the user included /v2 in their custom endpoint base URL, normalize it to prevent duplication with /v2 paths
    if endpoint.endswith('/v2'):
        endpoint = endpoint[:-3]
    url = f"{endpoint}{path}"
    
    headers = {
        "APCA-API-KEY-ID": user.get("alpaca_api_key") or "",
        "APCA-API-SECRET-KEY": user.get("alpaca_api_secret") or "",
        "Content-Type": "application/json"
    }
    
    response = requests.request(method, url, headers=headers, params=params, json=json_data, timeout=10)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        try:
            err_json = response.json()
            detailed_msg = err_json.get("message") or err_json.get("desc") or str(http_err)
        except Exception:
            detailed_msg = response.text or str(http_err)
        raise Exception(f"{detailed_msg} (HTTP {response.status_code})")
        
    try:
        return response.json()
    except Exception:
        return {"status": "success", "code": response.status_code}

async def make_alpaca_request_async(user, method, path, params=None, json_data=None):
    import asyncio
    return await asyncio.to_thread(make_alpaca_request, user, method, path, params, json_data)

# --- 🚫 Strategy Disablement & Graceful Retirement ---

def get_disabled_strategies():
    """Returns a list of disabled strategies from Config."""
    disabled = get_config("disabled_strategies", "")
    return [d.strip() for d in disabled.split(",") if d.strip()]

def is_strategy_disabled(strategy_name):
    """Returns True if the strategy is disabled."""
    return strategy_name in get_disabled_strategies()

def toggle_strategy(strategy_name):
    """Toggles a strategy's disabled state. Automatically migrates users with 0 open positions."""
    disabled_list = get_disabled_strategies()
    if strategy_name in disabled_list:
        disabled_list.remove(strategy_name)
        new_val = ",".join(disabled_list)
        update_config("disabled_strategies", new_val)
        return False # Strategy is now active (Enabled)
    else:
        disabled_list.append(strategy_name)
        new_val = ",".join(disabled_list)
        update_config("disabled_strategies", new_val)
        
        # Strategy disabled! Run immediate migration for users who have no open positions
        with db_session() as conn:
            c = conn.cursor()
            if strategy_name == "Mean Reversion Scalper":
                c.execute("""
                    UPDATE Users 
                    SET active_crypto_strategy = 'Valkyrie Elite Scalper', strategy = 'Valkyrie Elite Scalper'
                    WHERE (active_crypto_strategy = 'Mean Reversion Scalper' OR strategy = 'Mean Reversion Scalper')
                      AND (has_open_positions = 0 OR has_open_positions IS NULL)
                """)
                c.execute("""
                    UPDATE WebUsers 
                    SET active_crypto_strategy = 'Valkyrie Elite Scalper'
                    WHERE active_crypto_strategy = 'Mean Reversion Scalper'
                      AND (has_open_positions = 0 OR has_open_positions IS NULL)
                """)
            elif strategy_name == "Valkyrie Elite Scalper":
                c.execute("""
                    UPDATE Users 
                    SET active_crypto_strategy = 'Mean Reversion Scalper', strategy = 'Mean Reversion Scalper'
                    WHERE (active_crypto_strategy = 'Valkyrie Elite Scalper' OR strategy = 'Valkyrie Elite Scalper')
                      AND (has_open_positions = 0 OR has_open_positions IS NULL)
                """)
                c.execute("""
                    UPDATE WebUsers 
                    SET active_crypto_strategy = 'Mean Reversion Scalper'
                    WHERE active_crypto_strategy = 'Valkyrie Elite Scalper'
                      AND (has_open_positions = 0 OR has_open_positions IS NULL)
                """)
            elif strategy_name == "Sherpa Velocity Pullback":
                c.execute("""
                    UPDATE Users 
                    SET active_stock_strategy = 'None'
                    WHERE active_stock_strategy = 'Sherpa Velocity Pullback'
                      AND (has_open_positions = 0 OR has_open_positions IS NULL)
                """)
                c.execute("""
                    UPDATE WebUsers 
                    SET active_stock_strategy = 'None'
                    WHERE active_stock_strategy = 'Sherpa Velocity Pullback'
                      AND (has_open_positions = 0 OR has_open_positions IS NULL)
                """)
            conn.commit()
        return True # Strategy is now disabled

def migrate_user_if_no_open_positions(chat_id, web_user_id=None):
    """If the user has a disabled strategy active and 0 open positions, migrates them to an enabled alternative."""
    if chat_id:
        user = get_user(chat_id)
    elif web_user_id:
        from web_api.db_web import get_web_user_by_id
        web_raw = get_web_user_by_id(web_user_id)
        user = get_user_from_web_row(web_raw) if web_raw else None
    else:
        return
        
    if not user:
        return
        
    disabled_list = get_disabled_strategies()
    if not disabled_list:
        return
        
    active_crypto = user.get('active_crypto_strategy', 'Valkyrie Elite Scalper')
    active_stock = user.get('active_stock_strategy', 'None')
    has_open = user.get('has_open_positions', False)
    
    if not has_open:
        with db_session() as conn:
            c = conn.cursor()
            if active_crypto in disabled_list:
                next_strat = 'Valkyrie Elite Scalper' if active_crypto == 'Mean Reversion Scalper' else 'Mean Reversion Scalper'
                if next_strat in disabled_list:
                    next_strat = 'None'
                if chat_id:
                    c.execute("UPDATE Users SET active_crypto_strategy = ?, strategy = ? WHERE telegram_chat_id = ?", (next_strat, next_strat, chat_id))
                    try:
                        c.execute("UPDATE WebUsers SET active_crypto_strategy = ? WHERE telegram_chat_id = ?", (next_strat, chat_id))
                    except:
                        pass
                elif web_user_id:
                    c.execute("UPDATE WebUsers SET active_crypto_strategy = ? WHERE id = ?", (next_strat, web_user_id))
                
            if active_stock in disabled_list:
                if chat_id:
                    c.execute("UPDATE Users SET active_stock_strategy = 'None' WHERE telegram_chat_id = ?", (chat_id,))
                    try:
                        c.execute("UPDATE WebUsers SET active_stock_strategy = 'None' WHERE telegram_chat_id = ?", (chat_id,))
                    except:
                        pass
                elif web_user_id:
                    c.execute("UPDATE WebUsers SET active_stock_strategy = 'None' WHERE id = ?", (web_user_id,))
            conn.commit()


