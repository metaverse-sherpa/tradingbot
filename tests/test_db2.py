import logging
logging.basicConfig(level=logging.INFO)

from database import db_session

with db_session() as conn:
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE faqs ADD COLUMN url TEXT")
        conn.commit()
        print("Successfully added url column to faqs!")
    except Exception as e:
        print("Error adding column:", str(e))
        conn.rollback()
