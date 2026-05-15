import sys
import os
import asyncio

# Add scripts directory to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, "scripts"))

from sherpa_visual_audit import run_visual_audit, generate_comparison_chart

def refresh():
    print("🏔️  Refreshing Metaverse Sherpa Bot Visuals...")
    
    # 1. Regenerate Master Audit (1% Risk, All Symbols)
    print("  [+] Regenerating Master Audit (Blofin Native)...")
    # run_visual_audit(risk, symbols, user_id, start_balance)
    # The script saves to results/master_audit.png if user_id='admin' and is_master=True
    # In the script, is_master=True if enabled_symbols is None and risk == 1.5
    # Wait, we changed default risk to 1.0. Let's check the is_master logic in sherpa_visual_audit.py
    run_visual_audit(1.0, None, user_id="admin", start_balance=10000.0)
    
    # 2. Regenerate Upsell Comparison
    print("  [+] Regenerating Upsell Comparison Chart...")
    generate_comparison_chart()
    
    print("\n✅ Visuals Refreshed. The bot will now serve Blofin-Native results.")

if __name__ == "__main__":
    refresh()
