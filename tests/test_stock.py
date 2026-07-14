import sys
import pandas as pd
from datetime import datetime, timedelta
sys.path.append('.')
from stock_backtester_daily import run_backtest, load_data_from_db

data_dict = load_data_from_db()

engine_strategy = "Velocity_Pullback"
best_params = {
    "rsi_period": 4,
    "rsi_entry": 15,
    "rsi_exit": 70,
    "atr_sl_mult": 3.0,
    "trend_ema": "ema_200",
    "long_only": True,
    "mode": "LONG",
    "leverage": 1.6,
    "rr_ratio": 1.6
}

end_dt = datetime.now()
start_dt = end_dt - timedelta(days=5*365)

h_df, t_df, metrics = run_backtest(
    data_dict,
    engine_strategy,
    best_params,
    verbose=False,
    initial_cash=10000.0,
    pct_per_trade=0.02,
    start_date=start_dt.strftime("%Y-%m-%d"),
    end_date=end_dt.strftime("%Y-%m-%d")
)

print(metrics)
if not metrics:
    print("NO TRADES EXECUTED!")
