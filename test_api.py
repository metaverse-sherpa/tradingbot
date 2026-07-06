import sys
import json
sys.path.append('.')
from web_api.routes_trades import run_backtest
from flask import Flask, request, g

app = Flask(__name__)

with app.test_request_context('/api/backtest/run', method='POST', json={
    "strategy": "Sherpa Velocity Pullback",
    "capital": 10000,
    "risk_pct": 2.0,
    "period": "Last 5 Years"
}):
    g.user = {"id": 1, "email": "test@test.com"}
    response = run_backtest()
    if isinstance(response, tuple):
        resp, status = response
        print(f"Status: {status}")
        print(resp.get_data(as_text=True))
    else:
        print(response)
