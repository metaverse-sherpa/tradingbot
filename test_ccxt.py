from database import get_exchange_client, db_session
with db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT * FROM WebUsers LIMIT 1")
    row = c.fetchone()
    if row:
        user = dict(row)
        client = get_exchange_client(user, is_async=False)
        positions = client.fetch_positions()
        import json
        for p in positions:
            if float(p.get('contracts', 0) or 0) != 0:
                print(json.dumps(p, indent=2))
