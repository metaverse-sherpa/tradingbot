import sys, time
sys.path.append(".")
from web_api.routes_portfolio import get_portfolio_news
from flask import Flask, g
import database
app = Flask(__name__)
with app.app_context():
    g.user = {"id": 1}
    s = time.time()
    try:
        # get_portfolio_news() depends on require_auth/require_premium which accesses request. We can't run it easily outside of Flask test client.
        pass
    except Exception as e:
        print(e)
