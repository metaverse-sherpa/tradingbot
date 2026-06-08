import threading
import sqlite3
import json
import time
from database import db_session

# Thread-safe lock
RESPONSE_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 60  # Cache for 60 seconds

class SqliteSharedCache:
    def __init__(self):
        # Create table if not exists
        try:
            with db_session() as conn:
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
        # key is a tuple: (cache_type, user_id)
        if isinstance(key, tuple):
            return f"{key[0]}:{key[1]}"
        return str(key)

    def __contains__(self, key):
        skey = self._serialize_key(key)
        try:
            with db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT expiry FROM SharedResponseCache WHERE cache_key = ?", (skey,))
                row = c.fetchone()
                if row:
                    expiry = row[0]
                    return time.time() < expiry
        except Exception as e:
            print(f"Error checking cache contains: {e}")
        return False

    def __getitem__(self, key):
        skey = self._serialize_key(key)
        try:
            with db_session() as conn:
                c = conn.cursor()
                c.execute("SELECT expiry, data FROM SharedResponseCache WHERE cache_key = ?", (skey,))
                row = c.fetchone()
                if row:
                    expiry = row[0]
                    data = json.loads(row[1])
                    return (expiry, data)
        except Exception as e:
            print(f"Error reading from cache: {e}")
        raise KeyError(key)

    def __setitem__(self, key, value):
        # value is a tuple: (expiry_timestamp, data)
        skey = self._serialize_key(key)
        expiry, data = value
        try:
            with db_session() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO SharedResponseCache (cache_key, expiry, data)
                    VALUES (?, ?, ?)
                """, (skey, expiry, json.dumps(data)))
        except Exception as e:
            print(f"Error writing to cache: {e}")

# Instantiated shared cache as a drop-in replacement for the in-memory dict
RESPONSE_CACHE = SqliteSharedCache()
