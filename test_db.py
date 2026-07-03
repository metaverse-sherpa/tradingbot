from database import db_session
import json
with db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT symbol, pnl_pct FROM TheoreticalTrades WHERE symbol LIKE '%/%' AND status != 'open' LIMIT 5")
    rows = c.fetchall()
    for r in rows:
        print(f"{r[0]} | {r[1]}")
