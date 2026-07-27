import sqlite3
conn = sqlite3.connect('data/bot_users.db')
c = conn.cursor()
c.execute("SELECT target_price, stop_loss, created_at, symbol, status FROM AIRecommendations WHERE (symbol = 'SOL' OR symbol LIKE '%SOL%' OR 'SOL/USDT' LIKE '%%' || symbol || '%%')")
print(c.fetchall())
