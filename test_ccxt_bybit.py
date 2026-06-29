import ccxt.async_support as ccxt
import asyncio

async def test():
    print("Testing CCXT Bybit methods")
    ex = ccxt.bybit()
    print("Has fetchPositionMode:", ex.has.get('fetchPositionMode'))
    print("Has setPositionMode:", ex.has.get('setPositionMode'))
    await ex.close()

asyncio.run(test())
