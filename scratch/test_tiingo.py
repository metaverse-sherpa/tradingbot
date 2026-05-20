import requests
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("TIINGO_API_KEY")

print(f"Key loaded: {api_key[:6]}..." if api_key else "No key found")

# Test daily endpoint for AAPL
ticker = "AAPL"
url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
params = {
    "startDate": "2026-05-01",
    "token": api_key
}

try:
    response = requests.get(url, params=params, timeout=10)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Successfully fetched {len(data)} daily bars for {ticker}.")
        if data:
            print("First bar:", data[0])
            print("Last bar:", data[-1])
    else:
        print("Error response:", response.text)
except Exception as e:
    print("Error:", e)
