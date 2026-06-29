import ccxt.async_support as ccxt
import asyncio

async def test():
    print("Testing CCXT Bybit")
    ex = ccxt.bybit()
    # print available options
    print(ex.options.get('defaultType'))
    await ex.close()

asyncio.run(test())
