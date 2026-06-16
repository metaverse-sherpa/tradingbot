import os
import sys
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# Add parent directory to path so we can import from tradingbot if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

import utils_gcp

SQLITE_DB_PATH = "data/bot_users.db"
DATABASE_URL = utils_gcp.get_secret("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL environment variable/secret is not set")
    sys.exit(1)

TABLES_TO_MIGRATE = [
    "Users",
    "WebUsers",
    "TheoreticalTrades",
    "AlpacaActiveTrades",
    "PortfolioBalanceHistory",
    "Config",
    "GiftCodes",
    "SharedResponseCache"
]

def generate_ddl_for_table(lite_cursor, table_name):
    lite_cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = lite_cursor.fetchall()
    
    col_defs = []
    has_serial_id = False
    
    for col in columns_info:
        name = col['name']
        ctype = col['type'].upper()
        is_pk = bool(col['pk'])
        
        # Determine PG type
        pg_type = "TEXT"
        if "INT" in ctype:
            if name.lower() == "id" and is_pk:
                pg_type = "SERIAL PRIMARY KEY"
                has_serial_id = True
            else:
                pg_type = "BIGINT"
        elif "REAL" in ctype or "FLOA" in ctype or "DOUB" in ctype or "NUM" in ctype:
            pg_type = "DOUBLE PRECISION"
        elif "BOOL" in ctype:
            pg_type = "SMALLINT"
            
        # Add primary key constraint if not already covered by SERIAL PRIMARY KEY
        if is_pk and not has_serial_id:
            pg_type += " PRIMARY KEY"
            
        col_defs.append(f"{name} {pg_type}")
        
    ddl = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    " + ",\n    ".join(col_defs) + "\n);"
    return ddl, has_serial_id

def migrate():
    print(f"Connecting to SQLite: {SQLITE_DB_PATH} ...")
    lite_conn = sqlite3.connect(SQLITE_DB_PATH)
    lite_conn.row_factory = sqlite3.Row
    lite_cursor = lite_conn.cursor()

    print(f"Connecting to PostgreSQL ...")
    pg_conn = psycopg2.connect(DATABASE_URL)
    pg_cursor = pg_conn.cursor()

    # Drop existing tables to start clean if executing a migration reset
    print("Dropping existing tables in Postgres (if any)...")
    for table in TABLES_TO_MIGRATE:
        pg_cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

    # Recreate tables dynamically matching SQLite schema exactly
    print("Analyzing SQLite schemas and creating tables in Postgres...")
    serial_tables = []
    for table in TABLES_TO_MIGRATE:
        ddl, has_serial_id = generate_ddl_for_table(lite_cursor, table)
        print(f"Executing DDL for '{table}':\n{ddl}\n")
        pg_cursor.execute(ddl)
        if has_serial_id:
            serial_tables.append(table)

    # Perform table data transfer
    for table in TABLES_TO_MIGRATE:
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
        if table in serial_tables:
            print(f"  Resetting sequence for table '{table}'...")
            pg_cursor.execute(f"SELECT setval(pg_get_serial_sequence('{table.lower()}', 'id'), COALESCE(max(id), 1)) FROM {table};")

    pg_conn.commit()
    print("Migration committed successfully!")
    
    lite_conn.close()
    pg_conn.close()
    print("Database connections closed cleanly.")

if __name__ == "__main__":
    migrate()
