import sqlite3

conn = sqlite3.connect('data/bot_users.db')
c = conn.cursor()
c.execute('''
SELECT 
    u1.id, 
    u1.email, 
    u1.full_name, 
    u1.premium_expiry, 
    u1.created_at, 
    u1.telegram_chat_id, 
    COALESCE(u1.referred_by, t.referred_by) as referred_by, 
    t.username as telegram_username,
    u2.email as referrer_email_by_id,
    u3.email as referrer_email_by_tg,
    t2.username as referrer_tg_username,
    t2.full_name as referrer_tg_fullname
FROM WebUsers u1
LEFT JOIN Users t ON u1.telegram_chat_id = t.telegram_chat_id
LEFT JOIN WebUsers u2 ON COALESCE(u1.referred_by, t.referred_by) = u2.id
LEFT JOIN WebUsers u3 ON COALESCE(u1.referred_by, t.referred_by) = u3.telegram_chat_id
LEFT JOIN Users t2 ON COALESCE(u1.referred_by, t.referred_by) = t2.telegram_chat_id
ORDER BY u1.created_at DESC 
LIMIT 10
''')
for r in c.fetchall():
    print(r)
