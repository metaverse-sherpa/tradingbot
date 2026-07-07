import sys
import json
import traceback
sys.path.append('.')
from server import app
from web_api.routes_portfolio import analyze_portfolio
from flask import g

with app.app_context():
    # Mock g.user
    g.user = {"id": 1, "premium_expiry": 99999999999}
    try:
        # Instead of calling the route which runs require_auth, let's call the underlying logic directly!
        # Oh wait, analyze_portfolio is wrapped by require_auth! 
        # We can unwrap it.
        # It's wrapped twice: @require_auth, @require_premium
        # original_func = analyze_portfolio.__wrapped__.__wrapped__ 
        
        # We can just generate a fake JWT and use app.test_client()
        import jwt
        import datetime
        token = jwt.encode({"user_id": 1, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}, app.config["SECRET_KEY"], algorithm="HS256")
        client = app.test_client()
        res = client.post('/api/portfolio/analyze', headers={"Authorization": f"Bearer {token}"})
        print(f"Status: {res.status_code}")
        print(f"Response: {res.data.decode()}")
    except Exception as e:
        traceback.print_exc()

