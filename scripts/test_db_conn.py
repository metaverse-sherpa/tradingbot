import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database

print("Testing PostgreSQL database connection...")
try:
    database.init_db()
    print("database.init_db() executed successfully!")
    
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM Users")
        count = c.fetchone()[0]
        print(f"Postgres Users table row count: {count}")
        
    print("PostgreSQL Connection and Querying Verified Successfully!")
except Exception as e:
    print(f"Connection test failed: {e}")
