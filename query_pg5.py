import database
with database.db_session() as conn:
    c = conn.cursor()
    try:
        c.execute("SELECT target_price, stop_loss, created_at FROM AIRecommendations WHERE (symbol = %s OR symbol LIKE %s OR %s LIKE '%%' || symbol || '%%') AND status = 'active' AND target_price > 0 AND stop_loss > 0 ORDER BY id DESC LIMIT 1", ("1000SHIB-USDT-SWAP", "%SHIB%", "SHIB/USDT"))
        print(c.fetchone())
    except Exception as e:
        print("EXCEPTION:", e)
