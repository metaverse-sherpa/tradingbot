import re

with open('web_api/routes_trades.py', 'r') as f:
    content = f.read()

# Fix in get_stats (line 325 approx)
content = re.sub(
    r'crypto_api_key = tg_user\.get\("api_key"\)\n\s+crypto_api_secret = tg_user\.get\("api_secret"\)\n\s+crypto_api_password = tg_user\.get\("api_password"\)\n\s+crypto_exchange_id = tg_user\.get\("exchange_id", "blofin"\)',
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

# Fix in get_open_trades (line 673 approx)
content = re.sub(
    r'crypto_api_key = merged_user\.get\("api_key"\)\n\s+crypto_api_secret = merged_user\.get\("api_secret"\)\n\s+crypto_api_password = merged_user\.get\("api_password"\) or ""\n\s+crypto_exchange_id = merged_user\.get\("exchange_id", "blofin"\)',
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

# Fix in get_stats inner loop (line 2069 approx)
content = re.sub(
    r'crypto_api_key = tg_user\.get\("api_key"\)\n\s+crypto_api_secret = tg_user\.get\("api_secret"\)\n\s+crypto_api_password = tg_user\.get\("api_password"\)\n\s+crypto_exchange_id = tg_user\.get\("exchange_id", "blofin"\)',
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

print("Replacement 2 done.")
