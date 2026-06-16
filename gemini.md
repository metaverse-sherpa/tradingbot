Stack: Flask backend, Python-Telegram-Bot, SQLite (WAL mode), CCXT, Vanilla JS + Tailwind CSS SPA
Style: Asynchronous python loop, Flask Blueprints, symmetric encryption (Fernet) for API keys, in-memory response cache
DB schema: docs/db_schema.md (read when needed). SQLite file at `data/bot_users.db`.
API docs: Registered in `web_api/` blueprints (read routes_*.py when needed)
CRITICAL: Do NOT read, query, or troubleshoot using any local SQLite databases (.db, .sqlite). Always use the active Google Cloud MCP server tools to inspect the live remote state.
VPS Operations:
- Telegram bot daemon: `sudo systemctl restart tradingbot`
- Webapp screen session: `screen -S webapp -X quit 2>/dev/null && screen -dmS webapp bash -c "source venv/bin/activate && gunicorn --workers 4 --worker-class gevent --bind 0.0.0.0:5001 server:app"`
- Vacuum system logs: `sudo journalctl --vacuum-size=500M`
