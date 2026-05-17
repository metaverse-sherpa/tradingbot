import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    exchange = ccxt.blofin({
        'apiKey': os.getenv('BLOFIN_API_LOCAL_KEY'),
        'secret': os.getenv('BLOFIN_API_LOCAL_SECRET'),
        'password': 'football69',
    })
    try:
        trades = await exchange.fetch_my_trades('BTC/USDT:USDT', params={'instType': 'SWAP'})
        print("Success:", len(trades))
    except Exception as e:
        print("Error:", e)
    finally:
        await exchange.close()

asyncio.run(main())
