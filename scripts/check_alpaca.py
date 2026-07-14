import asyncio
import sys
sys.path.append("/home/gilesasp/tradingbot")
import database

async def get_pos():
    users = database.get_all_active_stock_users()
    if users:
        print(await database.make_alpaca_request_async(users[0], "GET", "/v2/positions"))

asyncio.run(get_pos())
