import threading
import sqlite3
import json
import time
import os

# Thread-safe lock
RESPONSE_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 60  # Cache for 60 seconds
_L1_MAX_ITEMS = 500
_L1_TTL_CAP = 10.0  # Keep L1 short so multi-worker invalidations stay fresh

CACHE_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "api_cache.db")


class SqliteSharedCache:
    def __init__(self):
        self._local = threading.local()
        self._l1 = {}  # {skey: (l1_expiry, full_expiry, data)}
        self._l1_lock = threading.Lock()
        self._write_count = 0
        os.makedirs(os.path.dirname(CACHE_DB_PATH), exist_ok=True)
        # Initialize WAL mode and table once at startup instead of on every query
        try:
            conn = sqlite3.connect(CACHE_DB_PATH, timeout=10.0)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA busy_timeout=10000;")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS SharedResponseCache (
                        cache_key TEXT PRIMARY KEY,
                        expiry REAL,
                        data TEXT
                    )
                """)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            print(f"Error initializing SharedResponseCache: {e}")

    def _get_conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(CACHE_DB_PATH, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=10000;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            self._local.conn = conn
        return conn

    def _serialize_key(self, key):
        # key is a tuple: (cache_type, user_id, optional_segment)
        if isinstance(key, tuple):
            return ":".join(str(x) for x in key)
        return str(key)

    def clear_user_cache(self, user_id):
        # Clear any keys that start with a prefix that contains the user_id
        # Our keys look like "open_trades:1:crypto" or "stats:1"
        uid_token = f":{user_id}"
        with self._l1_lock:
            to_del = [k for k in self._l1 if uid_token in k]
            for k in to_del:
                self._l1.pop(k, None)
        try:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM SharedResponseCache WHERE cache_key LIKE ?", (f"%:{user_id}%",))
            conn.commit()
        except Exception as e:
            print(f"Error clearing user cache: {e}")

    def __contains__(self, key):
        expiry, data = self.get(key, default=(0, None))
        return expiry > time.time() and data is not None

    def get(self, key, default=(0, None)):
        skey = self._serialize_key(key)
        now = time.time()

        # L1 fast path (no SQLite I/O)
        with self._l1_lock:
            l1_entry = self._l1.get(skey)
            if l1_entry is not None:
                l1_exp, full_exp, data = l1_entry
                if now < l1_exp and now < full_exp:
                    return (full_exp, data)
                self._l1.pop(skey, None)

        # L2 SQLite shared across workers
        try:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT expiry, data FROM SharedResponseCache WHERE cache_key = ? AND expiry > ?", (skey, now))
            row = c.fetchone()
            if row:
                expiry = row[0]
                data = json.loads(row[1])
                with self._l1_lock:
                    if len(self._l1) >= _L1_MAX_ITEMS:
                        self._l1.clear()
                    self._l1[skey] = (min(expiry, now + _L1_TTL_CAP), expiry, data)
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
        now = time.time()
        with self._l1_lock:
            if len(self._l1) >= _L1_MAX_ITEMS:
                self._l1.clear()
            self._l1[skey] = (min(expiry, now + _L1_TTL_CAP), expiry, data)
        try:
            conn = self._get_conn()
            conn.execute("""
                INSERT OR REPLACE INTO SharedResponseCache (cache_key, expiry, data)
                VALUES (?, ?, ?)
            """, (skey, expiry, json.dumps(data)))
            self._write_count += 1
            if self._write_count % 100 == 0:
                conn.execute("DELETE FROM SharedResponseCache WHERE expiry < ?", (now,))
            conn.commit()
        except Exception as e:
            print(f"Error writing to cache: {e}")


# Instantiated shared cache as a drop-in replacement for the in-memory dict
RESPONSE_CACHE = SqliteSharedCache()
