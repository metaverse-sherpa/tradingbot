import asyncio
import database

async def main():
    users = database.get_all_active_users()
    bingx_user = None
    for u in users:
        if u.get("exchange_id") == "bingx":
            bingx_user = u
            break
            
    if not bingx_user:
        print("❌ Error: No active user found.")
        return
        
    client = database.get_exchange_client(bingx_user)
    try:
        await client.load_markets()
        
        # Test 1: Place order on BTC/USDT with defaultType = 'future'
        # Let's inspect what endpoints are called or if we can use standard futures params
        print("\n--- Placing order on BTC/USDT (Standard Futures) ---")
        try:
            # BTC/USDT is the spot/standard futures symbol in CCXT for BingX
            order = await client.create_order("BTC/USDT", "market", "buy", 0.0001)
            print("Success:", order)
        except Exception as e:
            print("Error on BTC/USDT:", e)

        # Test 2: Let's check if there's a specific standard futures symbol or if we need to pass standard parameter
        print("\n--- Placing order with standard futures param ---")
        try:
            # Some exchanges or CCXT versions require passing standard: True in params
            order = await client.create_order("BTC/USDT", "market", "buy", 0.0001, params={"standard": True})
            print("Success standard: True:", order)
        except Exception as e:
            print("Error with standard: True:", e)
            
    except Exception as e:
        print("Main execution error:", e)
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
