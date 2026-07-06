import asyncio
import json
import logging
import websockets
from bot.config import logger

async def blofin_ws_client():
    uri = "wss://openapi.blofin.com/ws/public"
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                logger.info("Connected to Blofin WebSocket.")
                
                async def heartbeat():
                    while True:
                        try:
                            await asyncio.sleep(20)
                            await websocket.send("ping")
                        except Exception:
                            break
                
                ping_task = asyncio.create_task(heartbeat())

                # Subscribe to a channel, e.g., BTC-USDT ticker
                sub_msg = {
                    "op": "subscribe",
                    "args": [{"channel": "tickers", "instId": "BTC-USDT"}]
                }
                await websocket.send(json.dumps(sub_msg))
                
                try:
                    async for message in websocket:
                        if message == "pong":
                            continue
                        # TODO: Process ticker updates and trigger broadcast if conditions met
                        pass
                finally:
                    ping_task.cancel()
        except Exception as e:
            logger.error(f"Blofin WS Error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

async def coinbase_ws_client():
    uri = "wss://ws-feed.exchange.coinbase.com"
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                logger.info("Connected to Coinbase WebSocket.")
                sub_msg = {
                    "type": "subscribe",
                    "product_ids": ["BTC-USD"],
                    "channels": ["ticker"]
                }
                await websocket.send(json.dumps(sub_msg))
                
                async for message in websocket:
                    # TODO: Process ticker updates
                    pass
        except Exception as e:
            logger.error(f"Coinbase WS Error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

async def alpaca_ws_client():
    uri = "wss://stream.data.alpaca.markets/v2/iex"
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                logger.info("Connected to Alpaca WebSocket.")
                from utils_gcp import get_secret
                alpaca_key = get_secret("ALPACA_API_KEY")
                alpaca_secret = get_secret("ALPACA_API_SECRET")
                
                if alpaca_key and alpaca_secret:
                    auth_msg = {
                        "action": "auth",
                        "key": alpaca_key,
                        "secret": alpaca_secret
                    }
                    await websocket.send(json.dumps(auth_msg))
                else:
                    logger.warning("Alpaca WS Error: No API keys configured. Disabling Alpaca WS.")
                    return # Exit the background task if no keys are found
                
                async for message in websocket:
                    # TODO: Process ticker updates
                    pass
        except Exception as e:
            logger.error(f"Alpaca WS Error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

async def websocket_engine(application):
    """
    Main background task to manage all exchange WebSocket connections.
    """
    logger.info("Starting Exchange WebSockets Engine...")
    
    # Run all exchange clients concurrently
    await asyncio.gather(
        blofin_ws_client(),
        coinbase_ws_client(),
        alpaca_ws_client(),
        return_exceptions=True
    )
