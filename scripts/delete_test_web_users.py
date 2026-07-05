#!/usr/bin/env python3
"""
Diagnostic script to find load-test web users.
Connects to the VPS PostgreSQL database via DATABASE_URL from GCP secrets.
"""

import sys
import os
import re

# Add project root to path so we can import utils_gcp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

import utils_gcp
import psycopg2

def main():
    url = utils_gcp.get_secret("DATABASE_URL")
    if not url:
        print("Error: DATABASE_URL not found in GCP secrets.")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    # Find ALL users with 'metaversesherpa.io' to see what's in the DB
    cur.execute("""
        SELECT id, email, telegram_chat_id 
        FROM WebUsers 
        WHERE email LIKE '%metaversesherpa.io%'
        LIMIT 20
    """)
    rows = cur.fetchall()

    print(f"Found {len(rows)} users with 'metaversesherpa.io' in their email.")
    for uid, email, tg_id in rows:
        print(f"  id={uid}  email='{email}'  tg='{tg_id}' (type: {type(tg_id)})")

    # Let's also check for 'user%' just in case
    cur.execute("""
        SELECT id, email, telegram_chat_id 
        FROM WebUsers 
        WHERE email LIKE 'user%'
        LIMIT 20
    """)
    rows = cur.fetchall()
    
    print(f"\nFound {len(rows)} users with email starting with 'user'.")
    for uid, email, tg_id in rows:
        print(f"  id={uid}  email='{email}'  tg='{tg_id}'")

    conn.close()

if __name__ == "__main__":
    main()
