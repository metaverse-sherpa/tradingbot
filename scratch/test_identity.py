import database
import json
import os
import sqlite3

chat_id = 1567788633 # Your chat_id from the logs

def run_test():
    print(f"--- STARTING IDENTITY STRESS TEST FOR CHAT_ID: {chat_id} ---")
    
    # 1. Check Initial State
    user = database.get_user(chat_id)
    if not user:
        print(">>> ERROR: User not found in database.")
        return
    
    initial_state = user.get('undercover_mode')
    print(f"Phase 1: Initial Undercover State = {initial_state}")

    # 2. Toggle the State
    print("Phase 2: Toggling Identity...")
    database.toggle_undercover(chat_id)

    # 3. Verify the Change
    user_new = database.get_user(chat_id)
    new_state = user_new.get('undercover_mode')
    print(f"Phase 3: New Undercover State = {new_state}")

    # 4. Results
    if new_state != initial_state and new_state is not None:
        print("\n>>> SUCCESS: IDENTITY TOGGLE IS HARDENED AND FUNCTIONAL! 🏔️")
    else:
        print("\n>>> FAILURE: Identity did not change or returned None. Check database.py mappings.")

if __name__ == "__main__":
    run_test()
