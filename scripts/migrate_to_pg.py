import os
import sys
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Add parent directory to path so we can import from tradingbot if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

SQLITE_DB_PATH = "data/bot_users.db"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable is not set in .env")
    sys.exit(1)

TABLE_SCHEMAS = {
    "Users": """
        CREATE TABLE IF NOT EXISTS Users (
            telegram_chat_id BIGINT PRIMARY KEY,
            blofin_api_key TEXT,
            blofin_api_secret TEXT,
            blofin_api_password TEXT,
            exchange_id TEXT DEFAULT 'blofin',
            starting_equity REAL,
            is_active SMALLINT DEFAULT 0,
            total_wins INTEGER DEFAULT 0,
            total_losses INTEGER DEFAULT 0,
            total_trades_opened INTEGER DEFAULT 0,
            cumulative_pnl REAL DEFAULT 0.0,
            last_fetch_timestamp INTEGER DEFAULT 0,
            strategy TEXT DEFAULT 'Valkyrie Elite Scalper',
            source_wallet TEXT,
            stock_risk_pct REAL DEFAULT 2.0,
            alpaca_start_equity REAL,
            hide_dollars SMALLINT DEFAULT 0,
            risk_pct REAL DEFAULT 1.0,
            enabled_symbols TEXT,
            referred_by BIGINT,
            premium_expiry BIGINT DEFAULT 0,
            referral_count INTEGER DEFAULT 0,
            has_open_positions SMALLINT DEFAULT 0,
            history_cache TEXT,
            undercover_mode SMALLINT DEFAULT 0,
            last_audit_stats TEXT,
            referral_credits REAL DEFAULT 0.0,
            full_name TEXT,
            username TEXT,
            is_admin SMALLINT DEFAULT 0,
            custom_equity_type TEXT DEFAULT 'all',
            custom_equity_value REAL,
            alpaca_api_key TEXT,
            alpaca_api_secret TEXT,
            alpaca_endpoint TEXT,
            active_crypto_strategy TEXT DEFAULT 'Valkyrie Elite Scalper',
            active_stock_strategy TEXT DEFAULT 'None',
            premium_referrals INTEGER DEFAULT 0,
            premium_expired_notified SMALLINT DEFAULT 0,
            had_premium_before SMALLINT DEFAULT 0,
            referral_reward_triggered SMALLINT DEFAULT 0,
            bingx_futures_type TEXT DEFAULT 'standard'
        );
    """,
    "WebUsers": """
        CREATE TABLE IF NOT EXISTS WebUsers (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            google_id TEXT UNIQUE,
            full_name TEXT,
            avatar_url TEXT,
            telegram_chat_id BIGINT,
            exchange_id TEXT DEFAULT 'blofin',
            api_key TEXT,
            api_secret TEXT,
            api_password TEXT,
            alpaca_api_key TEXT,
            alpaca_api_secret TEXT,
            alpaca_endpoint TEXT,
            is_active SMALLINT DEFAULT 0,
            risk_pct REAL DEFAULT 1.0,
            stock_risk_pct REAL DEFAULT 2.0,
            enabled_symbols TEXT,
            hide_dollars SMALLINT DEFAULT 0,
            custom_equity_type TEXT DEFAULT 'all',
            custom_equity_value REAL,
            active_crypto_strategy TEXT DEFAULT 'Valkyrie Elite Scalper',
            active_stock_strategy TEXT DEFAULT 'None',
            source_wallet TEXT,
            premium_expiry BIGINT DEFAULT 0,
            referral_credits REAL DEFAULT 0.0,
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            total_wins INTEGER DEFAULT 0,
            total_losses INTEGER DEFAULT 0,
            cumulative_pnl REAL DEFAULT 0.0,
            has_open_positions SMALLINT DEFAULT 0,
            history_cache TEXT,
            last_audit_stats TEXT,
            created_at BIGINT,
            reset_token TEXT,
            reset_token_expiry BIGINT,
            email_notifications SMALLINT DEFAULT 1,
            email_frequency TEXT DEFAULT 'realtime',
            browser_notifications SMALLINT DEFAULT 1,
            public_key TEXT,
            encrypted_private_key TEXT,
            bingx_futures_type TEXT DEFAULT 'standard'
        );
    """,
    "TheoreticalTrades": """
        CREATE TABLE IF NOT EXISTS TheoreticalTrades (
            id SERIAL PRIMARY KEY,
            symbol TEXT,
            strategy TEXT,
            side TEXT,
            entry_price REAL,
            tp_price REAL,
            sl_price REAL,
            open_time BIGINT,
            close_time BIGINT,
            status TEXT,
            position_size REAL,
            pnl_raw REAL,
            pnl_pct REAL,
            pnl_usdt REAL
        );
    """,
    "AlpacaActiveTrades": """
        CREATE TABLE IF NOT EXISTS AlpacaActiveTrades (
            id SERIAL PRIMARY KEY,
            telegram_chat_id BIGINT,
            symbol TEXT,
            qty REAL,
            entry_price REAL,
            tp_price REAL,
            sl_price REAL,
            close_time BIGINT,
            close_price REAL,
            pnl_raw REAL,
            pnl_pct REAL,
            status TEXT,
            web_user_id INTEGER
        );
    """,
    "PortfolioBalanceHistory": """
        CREATE TABLE IF NOT EXISTS PortfolioBalanceHistory (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            timestamp BIGINT,
            encrypted_crypto_balance TEXT,
            encrypted_stock_balance TEXT
        );
    """,
    "Config": """
        CREATE TABLE IF NOT EXISTS Config (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """,
    "GiftCodes": """
        CREATE TABLE IF NOT EXISTS GiftCodes (
            code TEXT PRIMARY KEY,
            target_chat_id BIGINT,
            target_username TEXT,
            expiry_days INTEGER DEFAULT 30,
            is_used SMALLINT DEFAULT 0,
            created_at BIGINT
        );
    """,
    "SharedResponseCache": """
        CREATE TABLE IF NOT EXISTS SharedResponseCache (
            cache_key TEXT PRIMARY KEY,
            expiry REAL,
            data TEXT
        );
    """
}

def migrate():
    print(f"Connecting to SQLite: {SQLITE_DB_PATH} ...")
    lite_conn = sqlite3.connect(SQLITE_DB_PATH)
    lite_conn.row_factory = sqlite3.Row
    lite_cursor = lite_conn.cursor()

    print(f"Connecting to PostgreSQL ...")
    pg_conn = psycopg2.connect(DATABASE_URL)
    pg_cursor = pg_conn.cursor()

    # Drop existing tables to start clean if executing a migration reset
    # (Optional: can comment this out if only migrating schemas without dropping)
    # For a safe migration, we drop constraints first
    print("Dropping existing tables in Postgres (if any)...")
    for table in TABLE_SCHEMAS.keys():
        pg_cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

    # Recreate tables with correct schemas
    print("Recreating clean table structures in Postgres...")
    for table, ddl in TABLE_SCHEMAS.items():
        pg_cursor.execute(ddl)

    # Perform table data transfer
    for table in TABLE_SCHEMAS.keys():
        print(f"Migrating table '{table}'...")
        # Get data from SQLite
        lite_cursor.execute(f"SELECT * FROM {table}")
        rows = lite_cursor.fetchall()
        
        if not rows:
            print(f"  No records found for table '{table}'. Skipping.")
            continue
            
        columns = list(rows[0].keys())
        
        # Format INSERT SQL: INSERT INTO TableName (col1, col2) VALUES %s
        insert_query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s"
        
        # Extract rows values
        values = []
        for r in rows:
            val_tuple = tuple(r[col] for col in columns)
            values.append(val_tuple)

        # Batch insert into Postgres
        execute_values(pg_cursor, insert_query, values)
        print(f"  Successfully migrated {len(rows)} rows into Postgres '{table}'.")

        # Reset identity sequences for SERIAL primary keys
        if table in ["WebUsers", "TheoreticalTrades", "AlpacaActiveTrades", "PortfolioBalanceHistory"]:
            print(f"  Resetting sequence for table '{table}'...")
            pg_cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table.lower()}', 'id'), COALESCE(max(id), 1)) FROM {table};")

    pg_conn.commit()
    print("Migration committed successfully!")
    
    lite_conn.close()
    pg_conn.close()
    print("Database connections closed cleanly.")

if __name__ == "__main__":
    migrate()
