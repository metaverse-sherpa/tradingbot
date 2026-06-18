import re

with open('web_api/routes_trades.py', 'r') as f:
    content = f.read()

# We want fetch_crypto_balance to return a tuple (total_equity, True) instead of just total_equity.
content = content.replace("return total_equity", "return (total_equity, True)")

# The fallback should be (db_fallback, False)
content = content.replace(
    "balance_crypto = run_with_timeout(fetch_crypto_balance, 6.0, db_fallback)",
    "balance_crypto, crypto_auth_success = run_with_timeout(fetch_crypto_balance, 6.0, (db_fallback, False))"
)

# And if segment not matching or keys missing:
content = content.replace(
    "balance_crypto = float((tg_user or {}).get(\"equity\") or user.get(\"equity\") or 0.0)",
    "balance_crypto, crypto_auth_success = float((tg_user or {}).get(\"equity\") or user.get(\"equity\") or 0.0), False"
)

# fetch_stock_balance to return (portfolio_value, True)
content = content.replace("return float(res.get(\"portfolio_value\", 0.0))", "return (float(res.get(\"portfolio_value\", 0.0)), True)")

# stock fallback to (0.0, False)
content = content.replace(
    "balance_stock = run_with_timeout(fetch_stock_balance, 6.0, 0.0)",
    "balance_stock, stock_auth_success = run_with_timeout(fetch_stock_balance, 6.0, (0.0, False))"
)

content = content.replace(
    '''    if segment == 'crypto':
        response_data = {
            "crypto_balance": balance_crypto,
        }''',
    '''    if segment == 'crypto':
        response_data = {
            "crypto_balance": balance_crypto,
            "crypto_auth_success": crypto_auth_success,
        }'''
)

content = content.replace(
    '''    elif segment == 'stock':
        response_data = {
            "stock_balance": balance_stock,
        }''',
    '''    elif segment == 'stock':
        response_data = {
            "stock_balance": balance_stock,
            "stock_auth_success": stock_auth_success,
        }'''
)

content = content.replace(
    '''    else:
        response_data = {
            "crypto_balance": balance_crypto,
            "stock_balance": balance_stock,
        }''',
    '''    else:
        response_data = {
            "crypto_balance": balance_crypto,
            "crypto_auth_success": crypto_auth_success,
            "stock_balance": balance_stock,
            "stock_auth_success": stock_auth_success,
        }'''
)

with open('web_api/routes_trades.py', 'w') as f:
    f.write(content)
