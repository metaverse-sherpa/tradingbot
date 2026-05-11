import sqlite3
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# We generate a master encryption key if it doesn't exist
# This ensures API keys are NEVER saved in plain text
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    with open(".env", "a") as f:
        f.write(f"\nENCRYPTION_KEY={ENCRYPTION_KEY}\n")

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt(data):
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt(data):
    return cipher_suite.decrypt(data.encode()).decode()

def init_db():
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Users
                 (telegram_chat_id INTEGER PRIMARY KEY,
                  blofin_api_key TEXT,
                  blofin_api_secret TEXT,
                  blofin_api_password TEXT,
                  starting_equity REAL,
                  is_active BOOLEAN,
                  total_wins INTEGER,
                  total_losses INTEGER,
                  total_trades_opened INTEGER)''')
    
    # Try to add new columns if they don't exist (for seamless upgrades)
    try: c.execute("ALTER TABLE Users ADD COLUMN cumulative_pnl REAL DEFAULT 0.0")
    except: pass
    try: c.execute("ALTER TABLE Users ADD COLUMN last_fetch_timestamp INTEGER DEFAULT 0")
    except: pass
    
    conn.commit()
    conn.close()

def upsert_user(chat_id, api_key, api_secret, api_pass, equity):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('''INSERT INTO Users (telegram_chat_id, blofin_api_key, blofin_api_secret, blofin_api_password, starting_equity, is_active, total_wins, total_losses, total_trades_opened, cumulative_pnl, last_fetch_timestamp)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                 ON CONFLICT(telegram_chat_id) DO UPDATE SET
                 blofin_api_key=excluded.blofin_api_key,
                 blofin_api_secret=excluded.blofin_api_secret,
                 blofin_api_password=excluded.blofin_api_password,
                 starting_equity=excluded.starting_equity,
                 is_active=excluded.is_active''',
              (chat_id, encrypt(api_key), encrypt(api_secret), encrypt(api_pass), equity, True, 0, 0, 0, 0.0, 0))
    conn.commit()
    conn.close()

def get_user(chat_id):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('SELECT blofin_api_key, blofin_api_secret, blofin_api_password, starting_equity, is_active, total_wins, total_losses, total_trades_opened, cumulative_pnl, last_fetch_timestamp FROM Users WHERE telegram_chat_id = ?', (chat_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "api_key": decrypt(row[0]),
            "api_secret": decrypt(row[1]),
            "api_password": decrypt(row[2]),
            "equity": row[3],
            "is_active": row[4],
            "wins": row[5],
            "losses": row[6],
            "opened": row[7],
            "cum_pnl": row[8] if len(row) > 8 and row[8] is not None else 0.0,
            "last_ts": row[9] if len(row) > 9 and row[9] is not None else 0
        }
    return None

def set_active(chat_id, active):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('UPDATE Users SET is_active = ? WHERE telegram_chat_id = ?', (active, chat_id))
    conn.commit()
    conn.close()

def update_user_stats(chat_id, wins, losses, cum_pnl, last_ts):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('''UPDATE Users 
                 SET total_wins = ?, total_losses = ?, cumulative_pnl = ?, last_fetch_timestamp = ? 
                 WHERE telegram_chat_id = ?''', 
              (wins, losses, cum_pnl, last_ts, chat_id))
    conn.commit()
    conn.close()

def increment_opened(chat_id):
    conn = sqlite3.connect('bot_users.db')
    c = conn.cursor()
    c.execute('UPDATE Users SET total_trades_opened = total_trades_opened + 1 WHERE telegram_chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
