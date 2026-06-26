import database
import time
import live_bot_multi_alpaca

with database.db_session() as conn:
    c = conn.cursor()
    # Get all active theoretical trades
    c.execute("SELECT id, symbol, entry_price, position_size FROM TheoreticalTrades WHERE status = 'open'")
    open_theoretical = c.fetchall()
    
    # Get all active Alpaca trades
    c.execute("SELECT DISTINCT symbol FROM AlpacaActiveTrades WHERE close_time IS NULL")
    active_alpaca_symbols = [row[0] for row in c.fetchall()]
    
    closed_count = 0
    now_ts = int(time.time())
    
    for t_trade in open_theoretical:
        sym = t_trade['symbol']
        if sym not in active_alpaca_symbols:
            # Calculate PnL based on latest available daily close
            indicator_dict, df = live_bot_multi_alpaca.calculate_symbol_indicators_and_signal(sym)
            entry_price = t_trade['entry_price']
            position_size = t_trade['position_size'] or 1000.0
            
            if df is not None and not df.empty:
                close_price = df.iloc[-1]['close']
                pnl_raw = close_price - entry_price
                pnl_pct = (pnl_raw / entry_price) * 100
                pnl_usdt = position_size * (pnl_pct / 100)
            else:
                pnl_raw, pnl_pct, pnl_usdt = 0.0, 0.0, 0.0
                
            c.execute("""
                UPDATE TheoreticalTrades 
                SET close_time = ?, status = 'dynamic_exit', pnl_raw = ?, pnl_pct = ?, pnl_usdt = ?
                WHERE id = ?
            """, (now_ts, pnl_raw, pnl_pct, pnl_usdt, t_trade['id']))
            closed_count += 1
            print(f"Closed stranded Alpha Signal for {sym} at approx PnL {pnl_pct:+.2f}%")
            
    print(f"Cleanup complete. Closed {closed_count} stranded signals.")
