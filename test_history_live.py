import urllib.request
import json

# Use the API directly
try:
    resp = urllib.request.urlopen("http://127.0.0.1:5000/api/trades/history")
    print(resp.read().decode())
except Exception as e:
    print(e)
