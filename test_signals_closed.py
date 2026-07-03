from database import db_session
with db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT symbol, open_time, close_time FROM TheoreticalTrades WHERE symbol LIKE '%/%' LIMIT 10")
    rows = c.fetchall()
    for r in rows:
        print(r)
