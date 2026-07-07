import sys
sys.path.append('.')
from server import app
from flask import g
import jwt

app.config['TESTING'] = True
client = app.test_client()

with app.app_context():
    @app.before_request
    def set_user():
        g.user = {"id": 1, "premium_expiry": 99999999999}
        
    # We must override the require_auth decorator properly or just mock out check_token
    # Actually, simpler: patch the decorator.
    
    # Or just use the right auth token
    from web_api.config import Config
    import datetime
    token = jwt.encode({
        "user_id": 1,
        "email": "test@metaversesherpa.io",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }, Config.JWT_SECRET, algorithm="HS256")
    
    res = client.get('/api/portfolio', headers={"Authorization": f"Bearer {token}"})
    print(res.status_code)
    try:
        data = res.get_json()
        for p in data['positions']:
            if p['symbol'] in ['BTC', 'ETH']:
                print(f"SYMBOL: {p['symbol']}, CATEGORY: {p['category']}")
    except:
        print(res.data.decode())
