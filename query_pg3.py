from db_adapter import db_session_adapter
with db_session_adapter() as conn:
    c = conn.cursor()
    c.execute("SELECT symbol, target_price, stop_loss, status FROM AIRecommendations WHERE symbol IN ('SHIB', 'SOL', '1000SHIB', '1000SHIB-USDT-SWAP')")
    rows = c.fetchall()
    print("AIRecommendations:")
    for r in rows:
        print(dict(r) if hasattr(r, 'keys') else r)
