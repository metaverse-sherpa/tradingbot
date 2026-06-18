import re

with open('web_api/db_web.py', 'r') as f:
    content = f.read()

reconstruct_func = '''
def reconstruct_pem(flat_key):
    if not flat_key: return flat_key
    if "-----BEGIN" in flat_key and "-----END" in flat_key and "\\n" not in flat_key:
        import re as r
        match = r.match(r'(-----BEGIN.*?-----)(.*?)(-----END.*?-----)', flat_key)
        if match:
            header, body, footer = match.groups()
            body = body.replace(" ", "")
            wrapped_body = "\\n".join([body[i:i+64] for i in range(0, len(body), 64)])
            return f"{header}\\n{wrapped_body}\\n{footer}"
    return flat_key

def update_web_user_keys(user_id, exchange_id, api_key, api_secret, api_password, bingx_futures_type='standard', coinbase_sandbox=True):
    api_secret = reconstruct_pem(api_secret)
'''

content = re.sub(
    r"def update_web_user_keys\(user_id, exchange_id, api_key, api_secret, api_password, bingx_futures_type='standard', coinbase_sandbox=True\):",
    reconstruct_func.strip(),
    content
)

with open('web_api/db_web.py', 'w') as f:
    f.write(content)

