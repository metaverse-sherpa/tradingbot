import sys
import server
from web_api.db_web import get_web_user_by_id

app = server.app

with app.app_context():
    user = get_web_user_by_id(1)
    from flask import g, request
    with app.test_request_context('/api/trades/history?limit=10'):
        g.user = user
        response = server.get_trades_history.__wrapped__()
        print(response[0].get_data(as_text=True))

