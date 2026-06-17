import sys
import os
import time

# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
from web_api.db_web import db_session

# Initialize Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, auth

cred_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "firebase-adminsdk.json")
if not firebase_admin._apps:
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()

def migrate_users():
    print("Fetching users from PostgreSQL database...")
    
    email_users = []
    google_users = []
    
    with db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT id, email, password_hash, google_id, full_name FROM webusers")
        rows = c.fetchall()
        
        for row in rows:
            user_id = row[0]
            email = row[1]
            password_hash = row[2]
            google_id = row[3]
            display_name = row[4]
            
            if not email:
                continue
                
            email_clean = email.strip().lower()
            
            if google_id:
                google_users.append({
                    "id": user_id,
                    "email": email_clean,
                    "google_id": google_id,
                    "display_name": display_name
                })
            elif password_hash:
                email_users.append({
                    "id": user_id,
                    "email": email_clean,
                    "password_hash": password_hash,
                    "display_name": display_name
                })

    print(f"Found {len(email_users)} email/password users and {len(google_users)} Google Auth users.")
    
    # 1. Import Email/Password Users in batches of 1000
    import_records = []
    for u in email_users:
        # We can use 'user_{id}' as uid to ensure uniqueness and reference to local DB
        uid = f"user_{u['id']}"
        
        # password_hash must be byte string
        pw_hash = u['password_hash'].encode('utf-8')
        
        import_records.append(auth.ImportUserRecord(
            uid=uid,
            email=u['email'],
            display_name=u['display_name'] or u['email'].split('@')[0],
            password_hash=pw_hash
        ))
        
    if import_records:
        print(f"Importing {len(import_records)} email/password users to Firebase...")
        hash_alg = auth.UserImportHash.bcrypt()
        
        # Batch by 1000
        for i in range(0, len(import_records), 1000):
            batch = import_records[i:i+1000]
            try:
                res = auth.import_users(batch, hash_alg=hash_alg)
                print(f"Batch {i//1000 + 1}: Imported {res.success_count} successfully, {res.failure_count} failures.")
                for err in res.errors:
                    print(f"  Error at index {err.index}: {err.reason}")
            except Exception as e:
                print(f"Batch {i//1000 + 1} failed: {e}")

    # 2. Import Google Users in batches of 1000
    google_records = []
    for u in google_users:
        uid = f"google_{u['google_id']}"
        provider_info = auth.UserImportProvider(
            uid=u['google_id'],
            provider_id='google.com',
            email=u['email']
        )
        google_records.append(auth.ImportUserRecord(
            uid=uid,
            email=u['email'],
            display_name=u['display_name'] or u['email'].split('@')[0],
            provider_data=[provider_info]
        ))
        
    if google_records:
        print(f"Importing {len(google_records)} Google Auth users to Firebase...")
        for i in range(0, len(google_records), 1000):
            batch = google_records[i:i+1000]
            try:
                res = auth.import_users(batch)
                print(f"Batch {i//1000 + 1}: Imported {res.success_count} successfully, {res.failure_count} failures.")
                for err in res.errors:
                    print(f"  Error at index {err.index}: {err.reason}")
            except Exception as e:
                print(f"Batch {i//1000 + 1} failed: {e}")

if __name__ == "__main__":
    migrate_users()
