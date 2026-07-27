from db_adapter import db_session
with db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT symbol, target_price, stop_loss, status FROM AIRecommendations WHERE symbol IN ('SHIB', 'SOL', '1000SHIB', '1000SHIB-USDT-SWAP')")
    rows = c.fetchall()
    print("AIRecommendations:")
    for r in rows:
        print(dict(r) if hasattr(r, 'keys') else r)
    
    c.execute("SELECT symbol, tp_price, sl_price, status FROM TheoreticalTrades WHERE symbol LIKE '%SHIB%' OR symbol LIKE '%SOL%'")
    rows = c.fetchall()
    print("TheoreticalTrades:")
    for r in rows:
        print(dict(r) if hasattr(r, 'keys') else r)
