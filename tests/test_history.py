import database
import json
with database.db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT history_cache FROM WebUsers WHERE is_active=1 AND history_cache IS NOT NULL LIMIT 1")
    row = c.fetchone()
    if row:
        print(json.dumps(json.loads(row[0])[:2], indent=2))
