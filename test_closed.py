from database import db_session
import json
with db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT symbol FROM TheoreticalTrades WHERE status != 'open' ORDER BY close_time DESC LIMIT 50")
    rows = c.fetchall()
    print(json.dumps([r[0] for r in rows]))
