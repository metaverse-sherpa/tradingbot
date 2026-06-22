Stack: Flask backend, Python-Telegram-Bot, SQLite (WAL mode), CCXT, Vanilla JS + Tailwind CSS SPA
Style: Asynchronous python loop, Flask Blueprints, symmetric encryption (Fernet) for API keys, in-memory response cache
DB schema: docs/db_schema.md (read when needed). SQLite file at `data/bot_users.db`. PostgreSQL database on VPS
API docs: Registered in `web_api/` blueprints (read routes_*.py when needed)
CRITICAL: Do NOT read, query, or troubleshoot using any local PostgreSQL databases. Always use the active Google Cloud MCP server tools to inspect the live remote state.
VPS Operations:
- Telegram bot daemon: `sudo systemctl restart tradingbot`
- Web Server daemon: `sudo systemctl reload webapi`
- Vacuum system logs: `sudo journalctl --vacuum-size=500M`
Deployment: We push the files to Github and a workflow pushes them to the VPS and restarts the services.