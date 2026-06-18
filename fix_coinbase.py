import re
import glob
import os

files = [
    "./database.py",
    "./web_api/routes_trades.py",
    "./bot/engines/sync.py",
    "./bot/engines/system.py",
    "./bot/engines/crypto.py",
    "./bot/handlers/settings/free_trades.py",
    "./bot/handlers/system.py",
    "./bot/handlers/trading.py"
]

for filepath in files:
    if not os.path.exists(filepath): continue
    with open(filepath, 'r') as f:
        content = f.read()
    
    # We want to replace lines like:
    # "password": crypto_api_password or "",
    # "password": user['api_password'],
    # "password": crypto_api_password,
    
    # We will use regex:
    # re.sub(r'(\s*)"password"\s*:\s*(.+?),', r'\1**({"password": \2} if \2 else {}),', content)
    
    new_content = re.sub(r'(\s*)"password"\s*:\s*(.+?),', r'\1**({"password": \2} if \2 else {}),', content)
    
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"Patched {filepath}")

