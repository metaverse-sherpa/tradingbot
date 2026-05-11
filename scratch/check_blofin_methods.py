import ccxt
ex = ccxt.blofin()
print("Searching for deposit methods in Blofin CCXT...")
for m in dir(ex):
    if 'deposit' in m.lower():
        print(f"Found: {m}")
