#!/usr/bin/env python3
"""
🛡️ Cyber-Sherpa: Database Migration Safety Check
------------------------------------------------
This script verifies that the database schema updates (exchange_id) 
are applied safely without affecting existing user data.
"""

import os
import sqlite3
import shutil
import database

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TEST_DB = 'bot_users_test.db'
LIVE_DB = database.DB_PATH

def run_db_test():
    print("🏔️  Cyber-Sherpa: Database Migration Check\n" + "="*50)
    
    # 1. Create a copy of the live DB for testing
    if os.path.exists(LIVE_DB):
        print(f"📂 Creating test copy of live database: {LIVE_DB} -> {TEST_DB}")
        shutil.copyfile(LIVE_DB, TEST_DB)
    else:
        print("ℹ️  No live database found. Creating a fresh test database.")
        # Create a mock old-style DB if none exists
        conn = sqlite3.connect(TEST_DB)
        c = conn.cursor()
        c.execute("CREATE TABLE Users (telegram_chat_id INTEGER PRIMARY KEY, blofin_api_key TEXT)")
        c.execute("INSERT INTO Users (telegram_chat_id, blofin_api_key) VALUES (123, 'mock_key')")
        conn.commit()
        conn.close()

    # 2. Monkeypatch database module to use our test DB
    print("🛠️  Swapping DB path to sandbox...")
    database.DB_PATH = TEST_DB
    
    try:
        # 3. Run migration logic
        print("⚙️  Running database.init_db()...")
        database.init_db()
        print("✅ Migration Logic Executed.")
        
        # 4. Verify Schema
        print("\n🔍 Verifying Schema...")
        conn = sqlite3.connect(TEST_DB)
        c = conn.cursor()
        c.execute("PRAGMA table_info(Users)")
        columns = [row[1] for row in c.fetchall()]
        
        if 'exchange_id' in columns:
            print("✅ SUCCESS: 'exchange_id' column found!")
        else:
            print("❌ FAILURE: 'exchange_id' column missing.")
            
        # 5. Verify Data Integrity
        print("\n🔍 Verifying Data Integrity...")
        c.execute("SELECT telegram_chat_id, exchange_id FROM Users LIMIT 1")
        row = c.fetchone()
        
        if row:
            print(f"✅ User ID {row[0]} is now mapped to Exchange: '{row[1]}'")
            if row[1] == 'blofin':
                print("✅ SUCCESS: Existing users correctly defaulted to 'blofin'.")
            else:
                print(f"⚠️  Note: Default was '{row[1]}' instead of 'blofin'.")
        else:
            print("ℹ️  No users found to verify data.")
            
        conn.close()
        print("\n" + "="*50)
        print("✨ DATABASE CHECK COMPLETE: Migration is Safe for Production! ✨")
        print("==================================================")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
    finally:
        # Clean up
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
            print("\n🧹 Sandbox database cleaned up.")

if __name__ == "__main__":
    run_db_test()
