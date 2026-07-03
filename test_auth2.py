import os
import json
from flask import Flask, g
from web_api.routes_auth import auth_bp
from web_api import db_web

app = Flask(__name__)
app.register_blueprint(auth_bp)

@app.route("/test")
def test():
    user = db_web.get_web_user_by_email("metaversesherpa@gmail.com")
    g.user = user
    from web_api.routes_auth import sync_firebase_user
    # mock request json
    from flask import request
    class MockRequest:
        json = {}
        headers = {"Authorization": "Bearer fake"}
    
    with app.test_request_context('/api/auth/sync', method='POST', json={}):
        g.user = user
        res = sync_firebase_user()
        return res

if __name__ == "__main__":
    with app.app_context():
        # we can't easily mock require_auth_web, so let's just run the code
        pass
