import sys
import os
import pandas as pd
import numpy as np
import pickle
from multiprocessing import Pool, cpu_count

# Ensure root import path is correct
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from stock_backtester_daily import load_data_from_db, run_backtest, calculate_indicators

# Global dictionary to hold precalculated indicators per strategy in each worker
PRECALCULATED_DATA = None

def init_worker():
    global PRECALCULATED_DATA
    try:
        # Load from disk cache once per worker process
        with open("scratch/precalculated_indicators.pkl", "rb") as f:
            PRECALCULATED_DATA = pickle.load(f)
    except Exception as e:
        print(f"Worker failed to load cache: {e}")

def evaluate_config(args):
    global PRECALCULATED_DATA
    if PRECALCULATED_DATA is None:
        return None
        
    strat, lev, risk, rr, rsi_entry, rsi_exit, atr = args
    
    # Retrieve the precalculated indicators for this strategy
    processed_data = PRECALCULATED_DATA.get(strat)
    if not processed_data:
        return None
        
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
        from stock_backtester_daily import GLOBAL_STOCK_INDICATORS_CACHE
        
        # Inject our precalculated indicators directly into the cache key for this config
        params_key = frozenset((k, v if not isinstance(v, list) else tuple(v)) for k, v in params.items())
        cache_key = (strat, params_key)
        GLOBAL_STOCK_INDICATORS_CACHE[cache_key] = processed_data
        
        h_df, t_df, metrics = run_backtest(
            processed_data, # Pass processed_data directly
            strat,
            params,
            verbose=False,
            initial_cash=1000.0,
            pct_per_trade=risk,
            start_date="2021-05-19",
            end_date="2026-05-19"
        )
        if not metrics:
            return None
            
        pnl = metrics.get('total_pnl_pct', 0)
        wr = metrics.get('win_rate', 0)
        dd = metrics.get('max_dd_pct', 0)
        tpd = metrics.get('trades_per_day', 0)
        
        if wr > 60.0 and pnl > 100.0 and dd < 30.0 and tpd > 0.5:
            return {
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
    except Exception as e:
        pass
    return None

def main():
    print("🏔️ Loading Daily Historical Stock Data...")
    try:
        data_dict = load_data_from_db()
    except Exception as e:
        print(f"❌ Error loading database: {e}")
        return
        
    print(f"✅ Loaded data for {len(data_dict)} stocks.")
    
    strategies = ['Velocity_Pullback', 'RSI_Pullback', 'RSI_State', 'BB_Mean_Reversion', 'SuperTrend_Pullback']
    
    print("⚡ Precalculating technical indicators for all strategies...")
    parent_cache = {}
    for strat in strategies:
        params = {"rsi_period": 2 if strat == "Velocity_Pullback" else 4}
        processed_data = {}
        for sym, df in data_dict.items():
            processed_data[sym] = calculate_indicators(df, strat, params)
        parent_cache[strat] = processed_data
    
    # Save cache to disk for child processes to load
    os.makedirs("scratch", exist_ok=True)
    with open("scratch/precalculated_indicators.pkl", "wb") as f:
        pickle.dump(parent_cache, f, protocol=pickle.HIGHEST_PROTOCOL)
    print("✅ Precalculation cached to scratch/precalculated_indicators.pkl.")
    
    leverages = [1.0, 1.5, 2.0]
    risks = [0.01, 0.015, 0.02, 0.03]
    rr_ratios = [1.5, 2.0, 2.5]
    rsi_entries = [10, 15, 20, 25]
    atr_sl_mults = [1.5, 2.0, 2.5, 3.0, 3.5]
    
    tasks = []
    for strat in strategies:
        for lev in leverages:
            for risk in risks:
                for rr in rr_ratios:
                    for rsi_entry in rsi_entries:
                        for atr in atr_sl_mults:
                            exits = [70] if strat != "Velocity_Pullback" else [65, 70, 75]
                            for rsi_exit in exits:
                                tasks.append((strat, lev, risk, rr, rsi_entry, rsi_exit, atr))
                                
    num_tasks = len(tasks)
    num_cpus = cpu_count()
    print(f"🔍 Starting parallel sweep of {num_tasks} configurations using {num_cpus} CPU cores...")
    
    matches = []
    completed_count = 0
    with Pool(num_cpus, initializer=init_worker) as pool:
        for result in pool.imap_unordered(evaluate_config, tasks, chunksize=100):
            completed_count += 1
            if completed_count % 100 == 0 or completed_count == num_tasks:
                print(f"📊 Progress: {completed_count}/{num_tasks} configurations evaluated ({completed_count/num_tasks*100:.1f}%)", flush=True)
            if result:
                matches.append(result)
                print(f"🔥 MATCH: {result['strategy']} | Lev: {result['leverage']} | Risk: {result['risk_pct']}% | RR: {result['rr_ratio']} | RSI Entry: {result['rsi_entry']} | RSI Exit: {result['rsi_exit']} | ATR Mult: {result['atr_sl_mult']} | PnL: {result['pnl']:.2f}% | WR: {result['win_rate']:.2f}% | DD: {result['max_dd']:.2f}% | TPD: {result['trades_per_day']:.2f}", flush=True)

    # Clean up temporary pickle file
    if os.path.exists("scratch/precalculated_indicators.pkl"):
        try:
            os.remove("scratch/precalculated_indicators.pkl")
        except Exception:
            pass

    print("\n" + "="*80)
    print(f"Sweep Completed! Found {len(matches)} matching configurations.")
    print("="*80)
    
    if matches:
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
