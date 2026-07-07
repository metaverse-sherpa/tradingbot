import requests
import json

data = {
    "category": "stock",
    "symbol": "BTC",
    "quantity": 10.0,
    "avg_entry_price": 50000.0,
    "purchase_date": "2024-01-01",
    "dividend_yield": 0.0
}

# we need an auth token or cookie, this is tough
