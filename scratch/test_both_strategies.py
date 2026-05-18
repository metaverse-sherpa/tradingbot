import sys
sys.path.append("/Users/johngiles/projects/tradingbot/scripts")
from sherpa_visual_audit import run_visual_audit

print("1. RUNNING VALKYRIE ELITE SCALPER BACKTEST ($180 starting balance, 1.5% Risk):")
stats_valk, _, _ = run_visual_audit(
    risk_val_pct=1.5,
    enabled_symbols=["SOL", "LINK", "BTC", "ADA", "DOT", "ETH", "SUI"],
    user_id="1567788633",
    start_balance=180.0,
    strategy_name="Valkyrie Elite Scalper"
)
print(stats_valk)

print("\n2. RUNNING MEAN REVERSION SCALPER BACKTEST ($188 starting balance, 1.5% Risk):")
stats_mr, _, _ = run_visual_audit(
    risk_val_pct=1.5,
    enabled_symbols=None, # All symbols
    user_id="1567788633",
    start_balance=188.0,
    strategy_name="Mean Reversion Scalper"
)
print(stats_mr)
