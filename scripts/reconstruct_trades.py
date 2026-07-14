import asyncio
import database
import json
import time

async def main():
    with database.db_session() as conn:
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id FROM Users WHERE alpaca_api_key IS NOT NULL LIMIT 1")
        row = c.fetchone()
        
    if not row:
        print("No active users to query Alpaca")
        return
        
    user = database.get_user(row['telegram_chat_id'])
    
    # Get closed orders from Alpaca for the last week
    import datetime
    start_time = (datetime.datetime.now() - datetime.timedelta(days=14)).isoformat() + "Z"
    
    try:
        orders = await database.make_alpaca_request_async(user, "GET", f"/v2/orders?status=closed&limit=500&after={start_time}")
        print(f"Fetched {len(orders)} closed orders.")
        for order in orders:
            if order['symbol'] in ['GOOGL', 'AMZN', 'QCOM', 'MU', 'MS', 'CAT', 'ANET', 'AAPL', 'GS']:
                print(f"Found order: {order['symbol']} | Side: {order['side']} | Filled at: {order['filled_at']} | Avg price: {order['filled_avg_price']}")
    except Exception as e:
        print(f"Error fetching orders: {e}")

if __name__ == "__main__":
    asyncio.run(main())
