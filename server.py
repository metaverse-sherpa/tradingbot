import os
import sys
import time

# Set Matplotlib config directory to a writable local path in the workspace to prevent slow font cache rebuilds
os.environ['MPLCONFIGDIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", ".matplotlib")

from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from flask_socketio import SocketIO

# Add root folder to path so imports work perfectly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database
import utils_gcp

# Initialize Database on Startup
database.init_db()

USE_REACT = os.getenv("SERVE_REACT_APP", "0") == "1"
static_dir = 'webapp-react/dist' if USE_REACT else 'webapp'
app = Flask(__name__, static_folder=static_dir, static_url_path='')
# Configure Flask session secret
app.secret_key = utils_gcp.get_secret("FLASK_SECRET_KEY") or "metaverse-sherpa-secret-key"

# Enable CORS for frontend origin
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                FRONTEND_ORIGIN,
                "https://bot.metaversesherpa.io",
                "http://localhost:5173",
                "http://127.0.0.1:5173"
            ]
        }
    },
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization"]
)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

def broadcast_trade_update(trade_data):
    """Broadcasts trade updates to connected clients via WebSockets."""
    socketio.emit('trade_update', trade_data)

# ----------------- Register Blueprints -----------------
from web_api.routes_auth import auth_bp
from web_api.routes_settings import settings_bp
from web_api.routes_trades import trades_bp
from web_api.routes_premium import premium_bp

app.register_blueprint(auth_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(trades_bp)
app.register_blueprint(premium_bp)

# ----------------- Serve Frontend -----------------
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_index(path):
    if path.startswith('api') or path.startswith('favicon'):
        from flask import abort
        abort(404)
        
    if USE_REACT:
        return app.send_static_file('index.html')
    else:
        if path == '':
            return app.send_static_file('index.html')
        from flask import abort
        abort(404)

from web_api.auth import require_auth, require_premium, require_auth_web, require_premium_web

@app.route('/api')
@app.route('/api/')
@app.route('/api-docs')
@app.route('/api/docs')
def serve_api_docs():
    import os
    from flask import send_from_directory
    api_dir = os.path.join(app.root_path, 'api')
    return send_from_directory(api_dir, 'index.html')


@app.route('/favicon.svg')
def favicon_svg():
    from flask import send_from_directory
    return send_from_directory('webapp', 'favicon.svg', mimetype='image/svg+xml')

@app.route('/favicon.ico')
def favicon_ico():
    from flask import send_from_directory
    return send_from_directory('webapp', 'favicon.svg', mimetype='image/svg+xml')

# ----------------- Unsubscribe Endpoint -----------------
@app.route('/unsubscribe', methods=['GET'])
def unsubscribe_page():
    email = request.args.get('email', '').strip().lower()
    if not email:
        return "<h3>Missing email parameter.</h3>", 400
        
    # Update DB
    from database import db_session
    with db_session() as conn:
        c = conn.cursor()
        c.execute('UPDATE WebUsers SET email_notifications = 0 WHERE email = ?', (email,))
        success = conn.changes() > 0
        
    if success:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Unsubscribed Successfully</title>
            <style>
                body {
                    background-color: #0B0E14;
                    color: #FFFFFF;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                }
                .card {
                    background-color: #141A24;
                    border: 1px solid rgba(60, 215, 255, 0.15);
                    border-radius: 12px;
                    padding: 40px;
                    text-align: center;
                    max-width: 400px;
                }
                h2 { color: #3cd7ff; margin-top: 0; }
                p { color: rgba(255,255,255,0.7); font-size: 14px; line-height: 1.6; }
                .btn {
                    display: inline-block;
                    margin-top: 20px;
                    background: linear-gradient(90deg, #3cd7ff 0%, #00C853 100%);
                    color: #000000;
                    text-decoration: none;
                    font-weight: bold;
                    padding: 10px 20px;
                    border-radius: 6px;
                    font-size: 13px;
                }
            </style>
        </head>
        <body>
            <div class="card">
                <h2>🏔️ Trail Silenced Successfully</h2>
                <p>You have been unsubscribed from Metaverse Sherpa trading email alerts.</p>
                <p>If this was a mistake, you can easily turn email notifications back on anytime in your account Settings page.</p>
                <a href="https://bot.metaversesherpa.io" class="btn">Return to Dashboard</a>
            </div>
        </body>
        </html>
        """, 200
    else:
        return "<h3>Account not found or already unsubscribed.</h3>", 404

# ----------------- Config Endpoint -----------------
@app.route('/api/config', methods=['GET'])
def get_config():
    google_client_id = utils_gcp.get_secret("GOOGLE_CLIENT_ID")
    return jsonify({"google_client_id": google_client_id}), 200

# ----------------- Health Endpoint -----------------
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "timestamp": int(time.time())}), 200

@app.after_request
def add_security_headers(response):
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
    return response

# ----------------- Global Error Handler -----------------
@app.errorhandler(Exception)
def handle_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e

    # Log locally
    app.logger.error(f"Unhandled exception in WebAPI: {e}", exc_info=True)

    # Send Telegram alert
    from utils_error import send_telegram_alert
    try:
        send_telegram_alert(f"WebAPI ({request.method} {request.path})", e)
    except Exception as telegram_err:
        app.logger.error(f"Failed to send Telegram error alert: {telegram_err}")

    return jsonify({"error": "Internal Server Error"}), 500

# Start Flask Server
if __name__ == '__main__':
    port = int(os.getenv("PORT", 5001))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
