import re

with open('web_api/routes_trades.py', 'r') as f:
    content = f.read()

# Fix in profile route
content = re.sub(
    r'user\["has_exchange_keys"\] = bool\(\(tg_user or \{\}\)\.get\("api_key"\) or user\.get\("api_key"\)\)\n\s+user\["has_alpaca_keys"\] = bool\(\(tg_user or \{\}\)\.get\("alpaca_api_key"\) or user\.get\("alpaca_api_key"\)\)\n\s+user\["exchange_id"\] = user\.get\("exchange_id"\) or \(tg_user or \{\}\)\.get\("exchange_id"\)',
    r'''user["has_exchange_keys"] = bool((tg_user or {}).get("api_key") or user.get("api_key"))
    user["has_alpaca_keys"] = bool((tg_user or {}).get("alpaca_api_key") or user.get("alpaca_api_key"))
    
    if tg_user and tg_user.get("api_key"):
        user["exchange_id"] = tg_user.get("exchange_id", "blofin")
    else:
        user["exchange_id"] = user.get("exchange_id", "blofin")''',
    content
)

# Fix in get_balance (crypto)
content = re.sub(
    r'crypto_api_key = \(tg_user or \{\}\)\.get\("api_key"\) or user\.get\("api_key"\)\n\s+crypto_api_secret = \(tg_user or \{\}\)\.get\("api_secret"\) or user\.get\("api_secret"\)\n\s+crypto_api_password = \(tg_user or \{\}\)\.get\("api_password"\) or user\.get\("api_password"\) or ""\n\s+crypto_exchange_id = \(tg_user or \{\}\)\.get\("exchange_id"\) or user\.get\("exchange_id", "blofin"\)',
    r'''if tg_user and tg_user.get("api_key"):
        crypto_api_key = tg_user.get("api_key")
        crypto_api_secret = tg_user.get("api_secret")
        crypto_api_password = tg_user.get("api_password") or ""
        crypto_exchange_id = tg_user.get("exchange_id", "blofin")
    else:
        crypto_api_key = user.get("api_key")
        crypto_api_secret = user.get("api_secret")
        crypto_api_password = user.get("api_password") or ""
        crypto_exchange_id = user.get("exchange_id", "blofin")''',
    content
)

# Fix in get_balance (alpaca)
content = re.sub(
    r'alpaca_key = \(tg_user or \{\}\)\.get\("alpaca_api_key"\) or user\.get\("alpaca_api_key"\)\n\s+alpaca_secret = \(tg_user or \{\}\)\.get\("alpaca_api_secret"\) or user\.get\("alpaca_api_secret"\)\n\s+if \(not segment or segment == \'stock\'\) and alpaca_key and alpaca_secret:\n\s+def fetch_stock_balance\(\):\n\s+alpaca_user = tg_user or user',
    r'''if tg_user and tg_user.get("alpaca_api_key"):
        alpaca_key = tg_user.get("alpaca_api_key")
        alpaca_secret = tg_user.get("alpaca_api_secret")
        alpaca_user = tg_user
    else:
        alpaca_key = user.get("alpaca_api_key")
        alpaca_secret = user.get("alpaca_api_secret")
        alpaca_user = user
    
    if (not segment or segment == 'stock') and alpaca_key and alpaca_secret:
        def fetch_stock_balance():''',
    content
)

# Fix in history
content = re.sub(
    r'crypto_api_key = \(tg_user\.get\("api_key"\) if tg_user else None\) or user\.get\("api_key"\)\n\s+crypto_api_secret = \(tg_user\.get\("api_secret"\) if tg_user else None\) or user\.get\("api_secret"\)\n\s+crypto_api_password = \(tg_user\.get\("api_password"\) if tg_user else None\) or user\.get\("api_password"\) or ""\n\s+crypto_exchange_id = \(tg_user\.get\("exchange_id"\) if tg_user else None\) or user\.get\("exchange_id", "blofin"\)',
    r'''if tg_user and tg_user.get("api_key"):
            crypto_api_key = tg_user.get("api_key")
            crypto_api_secret = tg_user.get("api_secret")
            crypto_api_password = tg_user.get("api_password") or ""
            crypto_exchange_id = tg_user.get("exchange_id", "blofin")
        else:
            crypto_api_key = user.get("api_key")
            crypto_api_secret = user.get("api_secret")
            crypto_api_password = user.get("api_password") or ""
            crypto_exchange_id = user.get("exchange_id", "blofin")''',
    content
)

with open('web_api/routes_trades.py', 'w') as f:
    f.write(content)

print("Replacement done.")
