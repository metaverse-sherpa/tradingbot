from database import db_session

with db_session() as conn:
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE \"FAQs\" ADD COLUMN url TEXT")
        conn.commit()
        print("Success")
    except Exception as e:
        print("Error:", str(e))
        conn.rollback()
