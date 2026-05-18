import sys
sys.path.append("/Users/johngiles/projects/tradingbot/scripts")
from sherpa_visual_audit import run_visual_audit

stats, path, _ = run_visual_audit(
    risk_val_pct=1.5,
    enabled_symbols=["SOL", "LINK", "BTC", "ADA", "DOT"],
    user_id="1567788633",
    start_balance=180.0,
    strategy_name="Valkyrie Elite Scalper"
)
print("Final Validated Stats for $180 start cash:")
print(stats)
print("Saved chart to:", path)
