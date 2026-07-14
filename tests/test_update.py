import logging
logging.basicConfig(level=logging.INFO)

from database import db_session

with db_session() as conn:
    c = conn.cursor()
    c.execute('''
        UPDATE faqs
        SET url = %s
        WHERE id = %s
    ''', ('/premium', 1))
    
    if c.rowcount == 0:
        print("FAQ not found")
        
    conn.commit()
    print("Updated FAQ 1 url to /premium")
    
    c.execute("SELECT id, url FROM faqs WHERE id = 1")
    print("Result:", c.fetchall())
