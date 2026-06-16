import os
import re
import sqlite3
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL and (DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")))

# Postgres Pool & Adapters Initialization
pg_pool = None
if USE_POSTGRES:
    try:
        import psycopg2
        from psycopg2 import pool
        from psycopg2.extras import DictCursor
        
        # Parse connection URL to ensure thread-safe pooling config
        pg_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=30,
            dsn=DATABASE_URL
        )
        print("Database Adapter: Initialized PostgreSQL connection pool successfully.")
    except ImportError:
        print("Database Adapter Error: psycopg2 is not installed. Please install psycopg2-binary.")
        USE_POSTGRES = False
    except Exception as e:
        print(f"Database Adapter Error: Failed to initialize PostgreSQL pool: {e}")
        USE_POSTGRES = False


def translate_query(sql):
    if not sql or not isinstance(sql, str):
        return sql

    # 1. Translate table list query
    if "sqlite_master" in sql:
        sql = sql.replace(
            "SELECT name FROM sqlite_master WHERE type='table'",
            "SELECT table_name AS name FROM information_schema.tables WHERE table_schema='public'"
        )

    # 2. Translate SQLite PRAGMA table_info to Postgres information_schema query
    pragma_match = re.search(r"PRAGMA table_info\((\w+)\)", sql, re.IGNORECASE)
    if pragma_match:
        table_name = pragma_match.group(1)
        # Returns column name as 'name' to match sqlite3 table_info structure
        return f"""
            SELECT column_name AS name, data_type AS type 
            FROM information_schema.columns 
            WHERE table_name = '{table_name.lower()}'
        """

    # 3. Translate placeholders: ? -> %s
    # Note: Using a simple replace since '?' is not used in literal strings in these queries.
    sql = sql.replace('?', '%s')

    # 4. Translate SQLite INSERT OR IGNORE -> Postgres ON CONFLICT DO NOTHING
    if "INSERT OR IGNORE" in sql:
        match = re.search(r"INSERT OR IGNORE INTO (\w+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)", sql, re.IGNORECASE)
        if match:
            table = match.group(1)
            cols = match.group(2)
            vals = match.group(3)
            pkey = "key" if table.lower() == "config" else "code"
            sql = f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT ({pkey}) DO NOTHING"

    # 5. Translate SQLite INSERT OR REPLACE -> Postgres ON CONFLICT DO UPDATE
    if "INSERT OR REPLACE" in sql:
        match = re.search(r"INSERT OR REPLACE INTO (\w+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)", sql, re.IGNORECASE)
        if match:
            table = match.group(1)
            cols = match.group(2)
            vals = match.group(3)
            if table.lower() == "sharedresponsecache":
                sql = f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT (cache_key) DO UPDATE SET expiry = EXCLUDED.expiry, data = EXCLUDED.data"
            elif table.lower() == "config":
                sql = f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            elif table.lower() == "stockdailydata":
                sql = f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT (symbol, date) DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume"

    # 6. Translate SQLite string functions/types if necessary
    # Convert AUTOINCREMENT -> SERIAL in table creations (if run)
    sql = re.sub(r"\bAUTOINCREMENT\b", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bINTEGER PRIMARY KEY\s+AUTOINCREMENT\b", "SERIAL PRIMARY KEY", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bINTEGER PRIMARY KEY\b", "SERIAL PRIMARY KEY" if "id" in sql.lower() else "INTEGER PRIMARY KEY", sql, flags=re.IGNORECASE)

    return sql


class PgCursorAdapter:
    def __init__(self, raw_cursor):
        self._cursor = raw_cursor

    def execute(self, sql, params=None):
        translated_sql = translate_query(sql)
        # Convert params tuples to lists if psycopg2 complains, but tuples are fine
        return self._cursor.execute(translated_sql, params)

    def executemany(self, sql, seq_of_params):
        translated_sql = translate_query(sql)
        return self._cursor.executemany(translated_sql, seq_of_params)

    def fetchone(self):
        row = self._cursor.fetchone()
        return row  # DictRow matches sqlite3.Row index and name-based access

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        # Emulate sqlite3 lastrowid via returning id
        try:
            self._cursor.execute("SELECT LASTVAL();")
            return self._cursor.fetchone()[0]
        except Exception:
            return None

    def close(self):
        self._cursor.close()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PgConnectionAdapter:
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        # Use DictCursor to emulate sqlite3.Row dict-like behavior
        from psycopg2.extras import DictCursor
        raw_cursor = self._conn.cursor(cursor_factory=DictCursor)
        return PgCursorAdapter(raw_cursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        # We don't close the connection from pool, we put it back in the session finally block
        pass

    def execute(self, sql, params=None):
        cursor = self.cursor()
        cursor.execute(sql, params)
        return cursor

    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def db_session_adapter(sqlite_db_path, sqlite_timeout=30.0):
    if USE_POSTGRES and pg_pool:
        conn = None
        try:
            conn = pg_pool.getconn()
            conn.autocommit = False
            adapter = PgConnectionAdapter(conn)
            yield adapter
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                pg_pool.putconn(conn)
    else:
        # Fallback to standard SQLite connection
        conn = sqlite3.connect(sqlite_db_path, timeout=sqlite_timeout)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=30000;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
