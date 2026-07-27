import database
with database.db_session() as conn:
    c = conn.cursor()
    c.execute("SELECT target_price, stop_loss, created_at, symbol FROM AIRecommendations WHERE (symbol = %s OR symbol LIKE %s OR %s LIKE '%' || symbol || '%') AND status = 'active' AND target_price > 0 AND stop_loss > 0 ORDER BY id DESC LIMIT 1", ("1000SHIB-USDT-SWAP", "%SHIB%", "SHIB/USDT"))
    print("SHIB:", c.fetchone())
    
    c.execute("SELECT target_price, stop_loss, created_at, symbol FROM AIRecommendations WHERE (symbol = %s OR symbol LIKE %s OR %s LIKE '%' || symbol || '%') AND status = 'active' AND target_price > 0 AND stop_loss > 0 ORDER BY id DESC LIMIT 1", ("SOL-USDT-SWAP", "%SOL%", "SOL/USDT"))
    print("SOL:", c.fetchone())
