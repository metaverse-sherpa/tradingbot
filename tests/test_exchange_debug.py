import database
from web_api.db_web import get_web_user_by_email

email = "metaversesherpa@gmail.com"

# 1. Raw database query (no decryption)
print("=== RAW DATABASE ROW ===")
with database.db_session() as conn:
    c = conn.cursor()
    c.execute('SELECT id, email, exchange_id, api_key, api_secret, api_password, alpaca_api_key, alpaca_api_secret, alpaca_endpoint, telegram_chat_id FROM WebUsers WHERE email = ?', (email,))
    row = c.fetchone()
    if row:
        d = dict(row)
        for k, v in d.items():
            # truncate long encrypted values
            val_str = str(v)
            if len(val_str) > 40:
                val_str = val_str[:40] + "..."
            print(f"  {k}: {val_str}  (type={type(v).__name__}, bool={bool(v)})")
    else:
        print("  USER NOT FOUND IN DB")

# 2. Decrypted result from db_web
print("\n=== DECRYPTED via get_web_user_by_email ===")
user = get_web_user_by_email(email)
if user:
    for k in ("api_key", "api_secret", "api_password", "alpaca_api_key", "alpaca_api_secret", "exchange_id", "telegram_chat_id"):
        v = user.get(k)
        val_str = repr(v)
        if len(val_str) > 60:
            val_str = val_str[:60] + "..."
        print(f"  {k}: {val_str}  (bool={bool(v)})")
else:
    print("  USER NOT FOUND")

# 3. Check telegram user too
print("\n=== TELEGRAM USER ===")
tg_id = user.get("telegram_chat_id") if user else None
if tg_id:
    try:
        tg_user = database.get_user(int(tg_id))
        if tg_user:
            for k in ("api_key", "api_secret", "api_password", "alpaca_api_key", "alpaca_api_secret", "exchange_id"):
                v = tg_user.get(k)
                val_str = repr(v)
                if len(val_str) > 60:
                    val_str = val_str[:60] + "..."
                print(f"  {k}: {val_str}  (bool={bool(v)})")
        else:
            print(f"  No telegram user found for tg_id={tg_id}")
    except Exception as e:
        print(f"  Error getting telegram user: {e}")
else:
    print(f"  No telegram_chat_id linked")

# 4. Final has_exchange_keys computation
print("\n=== FINAL COMPUTATION ===")
tg_user = None
if tg_id:
    try:
        tg_user = database.get_user(int(tg_id))
    except:
        pass
has_exchange = bool((tg_user or {}).get("api_key") or user.get("api_key"))
has_alpaca = bool((tg_user or {}).get("alpaca_api_key") or user.get("alpaca_api_key"))
print(f"  has_exchange_keys: {has_exchange}")
print(f"  has_alpaca_keys: {has_alpaca}")
