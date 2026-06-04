import sys
import os
import pandas as pd
import numpy as np

# Ensure root import path is correct
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from stock_backtester_daily import load_data_from_db, run_backtest

def main():
    print("🏔️ Loading Daily Historical Stock Data...")
    try:
        data_dict = load_data_from_db()
    except Exception as e:
        print(f"❌ Error loading database: {e}")
        return
        
    print(f"✅ Loaded data for {len(data_dict)} stocks.")
    print("🔍 Sweeping parameter combinations. This may take 1-2 minutes...")
    
    strategies = ['Velocity_Pullback', 'RSI_Pullback', 'RSI_State', 'BB_Mean_Reversion', 'SuperTrend_Pullback']
    leverages = [1.0, 1.5, 2.0]
    risks = [0.01, 0.015, 0.02, 0.03]
    rr_ratios = [1.5, 2.0, 2.5]
    rsi_entries = [10, 15, 20, 25]
    atr_sl_mults = [1.5, 2.0, 2.5, 3.0, 3.5]
    
    matches = []
    
    for strat in strategies:
        print(f"  -> Sweeping {strat}...")
        for lev in leverages:
            for risk in risks:
                for rr in rr_ratios:
                    for rsi_entry in rsi_entries:
                        for atr in atr_sl_mults:
                            exits = [70] if strat != "Velocity_Pullback" else [65, 70, 75]
                            for rsi_exit in exits:
                                params = {
                                    "rsi_period": 2 if strat == "Velocity_Pullback" else 4,
                                    "rsi_entry": rsi_entry,
                                    "rsi_exit": rsi_exit,
                                    "atr_sl_mult": atr,
                                    "trend_ema": "ema_200",
                                    "long_only": True,
                                    "mode": "LONG",
                                    "leverage": lev,
                                    "rr_ratio": rr
                                }
                                try:
                                    h_df, t_df, metrics = run_backtest(
                                        data_dict,
                                        strat,
                                        params,
                                        verbose=False,
                                        initial_cash=1000.0,
                                        pct_per_trade=risk,
                                        start_date="2021-05-19",
                                        end_date="2026-05-19"
                                    )
                                    if not metrics:
                                        continue
                                        
                                    pnl = metrics.get('total_pnl_pct', 0)
                                    wr = metrics.get('win_rate', 0)
                                    dd = metrics.get('max_dd_pct', 0)
                                    tpd = metrics.get('trades_per_day', 0)
                                    
                                    if wr > 60.0 and pnl > 100.0 and dd < 30.0 and tpd > 0.5:
                                        match_info = {
                                            "strategy": strat,
                                            "leverage": lev,
                                            "risk_pct": risk * 100.0,
                                            "rr_ratio": rr,
                                            "rsi_entry": rsi_entry,
                                            "rsi_exit": rsi_exit,
                                            "atr_sl_mult": atr,
                                            "pnl": pnl,
                                            "win_rate": wr,
                                            "max_dd": dd,
                                            "trades_per_day": tpd,
                                            "total_trades": metrics.get('total_trades', 0)
                                        }
                                        matches.append(match_info)
                                        print(f"🔥 FOUND MATCH: {strat} | Lev: {lev} | Risk: {risk*100}% | RR: {rr} | RSI Entry: {rsi_entry} | RSI Exit: {rsi_exit} | ATR Mult: {atr} | PnL: {pnl:.2f}% | WR: {wr:.2f}% | DD: {dd:.2f}% | TPD: {tpd:.2f}")
                                except Exception as e:
                                    pass
                                    
    print("\n" + "="*80)
    print(f"Sweep Completed! Found {len(matches)} matching configurations.")
    print("="*80)
    
    if matches:
        # Sort matches by PnL descending
        matches.sort(key=lambda x: x['pnl'], reverse=True)
        print("\nTop 5 configurations matching all targets:")
        for idx, m in enumerate(matches[:5]):
            print(f"\n#{idx+1}: Strategy: {m['strategy']}")
            print(f"  Leverage: {m['leverage']}x | Risk %: {m['risk_pct']}% | R:R Ratio: {m['rr_ratio']}")
            print(f"  RSI Entry: {m['rsi_entry']} | RSI Exit: {m['rsi_exit']} | ATR Mult: {m['atr_sl_mult']}")
            print(f"  Metrics -> PnL: {m['pnl']:.2f}% | Win Rate: {m['win_rate']:.2f}% | Drawdown: {m['max_dd']:.2f}% | Trades/Day: {m['trades_per_day']:.3f} ({m['total_trades']} total)")
    else:
        print("❌ No parameter combinations met all target criteria.")

if __name__ == "__main__":
    main()
