import sqlite3
import json
import os
from dotenv import load_dotenv

# Run this script on your VPS to retroactively fix the Trade History PnLs.
# Usage: python3 fix_pnl.py

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_DB_PATH = os.path.join(BASE_DIR, "data", "bot_users.db")

def fix_history_cache():
    conn = sqlite3.connect(USER_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # We need to delete ALL closed trades that were corrupted by the bug, not just those < -40%.
    c.execute("SELECT id, symbol, entry_price, close_price, pnl_raw, pnl_pct FROM AlpacaActiveTrades WHERE status = 'closed'")
    bad_trades = c.fetchall()
    
    for row in bad_trades:
        trade_id = row['id']
        sym = row['symbol']
        entry_price = float(row['entry_price'])
        close_price = float(row['close_price'])
        
        # Heuristic to fix bad entries created by the previous daily open price bug.
        # If entry_price was vastly inflated (e.g. 1415 vs 444), we'll try to estimate the true entry 
        # based on a normal small PnL difference, or if they have the Alpaca app, they can see the true PnL.
        # Actually, let's just set the PnL to 0 for these drastically wrong trades so it stops ruining the Win Rate,
        # OR we can just delete them from the local DB so the robust Alpaca API fallback reconstructs them properly!
        
        # Deleting the local bad closed trades is much safer, because routes_trades.py's Alpaca API fallback 
        # is actually mathematically correct and will recreate them seamlessly from the real Alpaca API history!
        print(f"Deleting corrupted local trade record for {sym} (ID: {trade_id}) to force Alpaca API fallback...")
        c.execute("DELETE FROM AlpacaActiveTrades WHERE id = ?", (trade_id,))
        
    # Now clear the history cache for all WebUsers so the dashboard is forced to re-fetch and rebuild
    print("Clearing dashboard history cache to force a fresh sync...")
    c.execute("UPDATE WebUsers SET history_cache = NULL")
    c.execute("UPDATE Users SET history_cache = NULL")
    
    conn.commit()
    conn.close()
    print("Done! The dashboard will now reconstruct the trade history using the real Alpaca API data.")

if __name__ == "__main__":
    fix_history_cache()
