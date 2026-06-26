import asyncio
import database
import datetime

async def main():
    SYMBOLS = ['MS', 'CAT', 'AAPL', 'GS']
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id FROM Users WHERE alpaca_api_key IS NOT NULL LIMIT 1")
        row = c.fetchone()
        
    if not row:
        print("No users found.")
        return
        
    user = database.get_user(row['telegram_chat_id'])
    
    # Fetch all closed orders specifically filtering by symbol
    # Alpaca api allows symbols=MS,CAT,AAPL,GS
    sym_str = ",".join(SYMBOLS)
    orders = await database.make_alpaca_request_async(user, "GET", f"/v2/orders?status=all&symbols={sym_str}&limit=500")
    
    # Group by symbol
    symbol_orders = {s: [] for s in SYMBOLS}
    for o in orders:
        if o['symbol'] in SYMBOLS and o['status'] == 'filled':
            symbol_orders[o['symbol']].append(o)
            
    with database.db_session() as conn:
        c = conn.cursor()
        
        for sym in SYMBOLS:
            ords = sorted(symbol_orders[sym], key=lambda x: x['filled_at'])
            buy_order = None
            sell_order = None
            
            for o in ords:
                if o['side'] == 'buy':
                    buy_order = o
                elif o['side'] == 'sell' and buy_order is not None:
                    sell_order = o
                    
            if buy_order and sell_order:
                entry_price = float(buy_order['filled_avg_price'])
                close_price = float(sell_order['filled_avg_price'])
                
                open_time = int(datetime.datetime.fromisoformat(buy_order['filled_at'].replace('Z', '+00:00')).timestamp())
                close_time = int(datetime.datetime.fromisoformat(sell_order['filled_at'].replace('Z', '+00:00')).timestamp())
                
                pnl_raw = close_price - entry_price
                pnl_pct = (pnl_raw / entry_price) * 100
                pnl_usdt = 1000.0 * (pnl_pct / 100) # standard $1000 theoretical position size
                
                c.execute("""
                    INSERT INTO TheoreticalTrades (symbol, strategy, side, entry_price, tp_price, sl_price, open_time, close_time, status, position_size, pnl_raw, pnl_pct, pnl_usdt)
                    VALUES (?, 'Sherpa Velocity Pullback', 'LONG', ?, ?, ?, ?, ?, 'dynamic_exit', ?, ?, ?, ?)
                """, (sym, entry_price, entry_price*1.1, entry_price*0.9, open_time, close_time, 1000.0, pnl_raw, pnl_pct, pnl_usdt))
                print(f"Recovered {sym}: Entry {entry_price}, Close {close_price}, PnL% {pnl_pct:.2f}%")
            else:
                print(f"Could not fully recover {sym} (missing buy or sell order).")
        conn.commit()

if __name__ == "__main__":
    asyncio.run(main())
