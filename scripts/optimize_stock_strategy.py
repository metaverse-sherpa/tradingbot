import os
import sys
import pandas as pd
import numpy as np

# Ensure root dir is in path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from stock_backtester_daily import load_data_from_db, run_backtest

def main():
    print("🏔️ Starting Stock Strategy Optimization (5-Year: May 19, 2021 to May 19, 2026, 2x Leverage Sweep)...")
    try:
        data_dict = load_data_from_db()
    except Exception as e:
        print(f"❌ Error loading stock database: {e}")
        return

    print(f"Loaded data for {len(data_dict)} symbols.")

    # Sweep settings
    rsi_periods = [2, 3, 4]
    rsi_entries = [10, 15, 20]
    rsi_exits = [65, 70, 75]
    atr_sl_mults = [2.0, 2.5, 3.0]
    risk_pcts = [0.01, 0.015, 0.02, 0.03]
    modes = ["LONG", "SHORT", "BOTH"]

    best_results = []
    
    total_runs = len(rsi_periods) * len(rsi_entries) * len(rsi_exits) * len(atr_sl_mults) * len(risk_pcts) * len(modes)
    run_count = 0
    print(f"Grid search space: {total_runs} combinations...")

    for rsi_p in rsi_periods:
        for rsi_ent in rsi_entries:
            for rsi_ex in rsi_exits:
                for atr_m in atr_sl_mults:
                    for risk in risk_pcts:
                        for mode in modes:
                            run_count += 1
                            if run_count % 200 == 0:
                                print(f"Progress: {run_count}/{total_runs} sweeps completed...")

                            opt_params = {
                                "rsi_period": rsi_p,
                                "rsi_entry": rsi_ent,
                                "rsi_exit": rsi_ex,
                                "atr_sl_mult": atr_m,
                                "trend_ema": "ema_200",
                                "long_only": (mode == "LONG"),
                                "mode": mode,
                                "leverage": 2.0
                            }

                            h_df, t_df, metrics = run_backtest(
                                data_dict,
                                "Velocity_Pullback",
                                opt_params,
                                verbose=False,
                                initial_cash=1000.0,
                                pct_per_trade=risk,
                                start_date="2021-05-19",
                                end_date="2026-05-19"
                            )

                            if not metrics or metrics.get("total_trades", 0) == 0:
                                continue

                            pnl = metrics["total_pnl_pct"]
                            wr = metrics["win_rate"]
                            dd = metrics["max_dd_pct"]

                            # Constraints: wr >= 60%, dd < 25%
                            if wr >= 60.0 and dd < 25.0:
                                best_results.append({
                                    "pnl": pnl,
                                    "win_rate": wr,
                                    "dd": dd,
                                    "risk": risk,
                                    "mode": mode,
                                    "params": opt_params,
                                    "metrics": metrics
                                })

    # Sort results by PnL descending
    best_results.sort(key=lambda x: x["pnl"], reverse=True)

    print("\n" + "="*90)
    print("🏆 TOP 10 STRATEGY CONFIGURATIONS (2x Leverage, WR > 60%, Drawdown < 25%)")
    print("="*90)
    for idx, res in enumerate(best_results[:10]):
        p = res["params"]
        m = res["metrics"]
        print(f"#{idx+1} | Mode: {res['mode']:<5} | Risk: {res['risk']*100:<4}% | PnL: {res['pnl']:>6.2f}% | WR: {res['win_rate']:>6.2f}% | MaxDD: {res['dd']:>6.2f}% | Sharpe: {m['sharpe_ratio']:>4.2f}")
        print(f"    Params: RSI Period {p['rsi_period']}, Entry {p['rsi_entry']}, Exit {p['rsi_exit']}, ATR Mult {p['atr_sl_mult']:.1f} | Trades: {m['total_trades']}")
    print("="*90)

if __name__ == "__main__":
    main()
