from database import db_session
import json
with db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT open_time FROM TheoreticalTrades WHERE status = 'open' LIMIT 5")
    rows = c.fetchall()
    print("open_time values:", [r[0] for r in rows])
