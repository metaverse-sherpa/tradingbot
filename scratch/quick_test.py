import sys
sys.path.append("/Users/johngiles/projects/tradingbot")
import stock_backtester_daily as sbd

def main():
    print("🏔️ Running Quick Backtest on 40 symbols...")
    data = sbd.load_data_from_db()
    print(f"Loaded data for {len(data)} symbols.")
    
    # Run with default parameters for RSI_State
    params = {
        "rsi_period": 3,
        "rsi_entry": 20,
        "atr_sl_mult": 3.0,
        "trend_ema": "ema_200",
        "long_only": True
    }
    
    h_df, t_df, metrics = sbd.run_backtest(data, "RSI_State", params, verbose=False)
    if metrics:
        print("\n🏆 RESULTS:")
        print(f"Total Trades: {metrics['total_trades']}")
        print(f"Win Rate: {metrics['win_rate']:.2f}%")
        print(f"PnL: {metrics['total_pnl_pct']:.2f}%")
        print(f"Max DD: {metrics['max_dd_pct']:.2f}%")
        print(f"Trades/Day: {metrics['trades_per_day']:.3f}")
        print(f"Avg Duration: {metrics['avg_duration_days']:.1f} days")
    else:
        print("❌ Backtest failed.")

if __name__ == "__main__":
    main()
