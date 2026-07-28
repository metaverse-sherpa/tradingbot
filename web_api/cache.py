import threading
import sqlite3
import json
import time
import os

# Thread-safe lock
RESPONSE_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 60  # Cache for 60 seconds

CACHE_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "api_cache.db")

from contextlib import contextmanager

@contextmanager
def cache_db_session():
    os.makedirs(os.path.dirname(CACHE_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

class SqliteSharedCache:
    def __init__(self):
        # Create table if not exists
        try:
            with cache_db_session() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS SharedResponseCache (
                        cache_key TEXT PRIMARY KEY,
                        expiry REAL,
                        data TEXT
                    )
                """)
        except Exception as e:
            print(f"Error initializing SharedResponseCache: {e}")

    def _serialize_key(self, key):
        # key is a tuple: (cache_type, user_id, optional_segment)
        if isinstance(key, tuple):
            return ":".join(str(x) for x in key)
        return str(key)

    def clear_user_cache(self, user_id):
        # Clear any keys that start with a prefix that contains the user_id
        # Our keys look like "open_trades:1:crypto" or "stats:1"
        try:
            with cache_db_session() as conn:
                c = conn.cursor()
                c.execute("DELETE FROM SharedResponseCache WHERE cache_key LIKE ?", (f"%:{user_id}%",))
                c.execute("DELETE FROM SharedResponseCache WHERE cache_key LIKE ?", (f"%:{user_id}",))
        except Exception as e:
            print(f"Error clearing user cache: {e}")

    def __contains__(self, key):
        skey = self._serialize_key(key)
        try:
            with cache_db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT 1 FROM SharedResponseCache WHERE cache_key = ? AND expiry > ?", (skey, time.time()))
                return c.fetchone() is not None
        except Exception as e:
            print(f"Error checking cache contains: {e}")
        return False

    def get(self, key, default=(0, None)):
        skey = self._serialize_key(key)
        try:
            with cache_db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT expiry, data FROM SharedResponseCache WHERE cache_key = ? AND expiry > ?", (skey, time.time()))
                row = c.fetchone()
                if row:
                    expiry = row[0]
                    data = json.loads(row[1])
                    return (expiry, data)
        except Exception as e:
            print(f"Error reading from cache: {e}")
        return default

    def __getitem__(self, key):
        return self.get(key, default=(0, None))

    def __setitem__(self, key, value):
        # value is a tuple: (expiry_timestamp, data)
        skey = self._serialize_key(key)
        expiry, data = value
        try:
            with cache_db_session() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO SharedResponseCache (cache_key, expiry, data)
                    VALUES (?, ?, ?)
                """, (skey, expiry, json.dumps(data)))
        except Exception as e:
            print(f"Error writing to cache: {e}")

# Instantiated shared cache as a drop-in replacement for the in-memory dict
RESPONSE_CACHE = SqliteSharedCache()
