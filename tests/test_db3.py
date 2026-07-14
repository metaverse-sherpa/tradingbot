import logging
logging.basicConfig(level=logging.INFO)

from database import db_session

with db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT id, question, answer, order_index, created_at, url FROM faqs")
    rows = c.fetchall()
    
    print("Rows:", rows)
    if rows:
        print("Keys:", rows[0].keys())
        print("url in keys:", 'url' in rows[0].keys())
        print("url value:", rows[0]['url'])
