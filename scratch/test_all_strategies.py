import sys
sys.path.append("/Users/johngiles/projects/tradingbot")
import stock_backtester_daily as sbd

def main():
    print("🏔️ Loading stock data...")
    data = sbd.load_data_from_db()
    
    # 1. Test RSI_Pullback (Larry Connors style)
    params_rsi_pb = {
        "rsi_period": 3,
        "rsi_entry": 15,
        "atr_sl_mult": 3.0,
        "trend_ema": "ema_200",
        "long_only": True
    }
    
    # 2. Test BB_Mean_Reversion
    params_bb = {
        "bb_window": 20,
        "bb_mult": 2.0,
        "atr_sl_mult": 3.0,
        "trend_ema": "ema_150",
        "long_only": True
    }
    
    # 3. Test SuperTrend_Pullback
    params_st = {
        "st_period": 10,
        "st_mult": 3.0,
        "rsi_period": 4,
        "rsi_entry": 25,
        "atr_sl_mult": 3.0,
        "trend_ema": "ema_200",
        "long_only": True
    }
    
    strategies = {
        "RSI_Pullback": params_rsi_pb,
        "BB_Mean_Reversion": params_bb,
        "SuperTrend_Pullback": params_st
    }
    
    for name, params in strategies.items():
        print(f"\n🏔️ Running {name}...")
        try:
            h_df, t_df, metrics = sbd.run_backtest(data, name, params, verbose=False)
            if metrics:
                print(f"[{name}] Trades: {metrics['total_trades']} | Win Rate: {metrics['win_rate']:.2f}% | PnL: {metrics['total_pnl_pct']:.2f}% | Max DD: {metrics['max_dd_pct']:.2f}% | Freq: {metrics['trades_per_day']:.3f}/day")
            else:
                print(f"❌ {name} failed or no trades.")
        except Exception as e:
            print(f"❌ Error for {name}: {e}")

if __name__ == "__main__":
    main()
