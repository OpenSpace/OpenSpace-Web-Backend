import asyncio
import websockets
import logging
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO)

BASE_PORT = 4682
MAX_OFFSET = 100
MAX_MSG_SIZE = 10 * 1024 * 1024  # 10 MB

async def handler(connection):  # connection is ServerConnection
    # Correct way to get path in websockets 11+
    path = connection.request.path
    print(f"✅ Connection received with path: {path}")

    # Special case for /ws (HMR or dev websocket)
    if path == "/ws":
        target_uri = "ws://openspaceweb.com:4690/ws"
        logging.info(f"Proxying /ws to {target_uri}")
        try:
            # async with websockets.connect(target_uri) as target_ws:
            async with websockets.connect(target_uri, max_size=MAX_MSG_SIZE) as target_ws:
                logging.info(f"Connected to target WebSocket at {target_uri}")

                async def forward(source, target):
                    try:
                        async for message in source:
                            await target.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        pass

                await asyncio.gather(
                    forward(connection, target_ws),
                    forward(target_ws, connection)
                )
        except Exception as e:
            logging.error(f"Error connecting to target: {e}")
            await connection.close(code=1011, reason='Target connection failed')
        return

    if not path.startswith('/'):
        await connection.close(code=1008, reason='Invalid path')
        return

    try:
        port = int(path.strip('/'))
    except ValueError:
        await connection.close(code=1008, reason='Invalid port format')
        return

    if not (port == 8443 or BASE_PORT <= port <= BASE_PORT + MAX_OFFSET):
        await connection.close(code=1008, reason='Invalid port range')
        return

    target_uri = f"ws://openspaceweb.com:{port}"
    logging.info(f"Proxying to {target_uri}")
    print(f"Proxying to {target_uri}")

    try:
        # async with websockets.connect(target_uri) as target_ws:
        async with websockets.connect(target_uri, max_size=MAX_MSG_SIZE) as target_ws:
            await connection.send('{"status": "ready"}')  # Only after successful target connect
            logging.info(f"Connected to target WebSocket at {target_uri}")
            print(f"Connected to target WebSocket at {target_uri}")

            async def forward(source, target):
                try:
                    async for message in source:
                        logging.info(f"Forwarding message: {message}")
                        await target.send(message)
                except websockets.exceptions.ConnectionClosed:
                    pass

            await asyncio.gather(
                forward(connection, target_ws),
                forward(target_ws, connection)
            )

    except Exception as e:
        logging.error(f"Error connecting to target: {e}")
        await connection.close(code=1011, reason='Target connection failed')

async def main():
    # async with websockets.serve(handler, '0.0.0.0', 8080):
    async with websockets.serve(
        handler, '0.0.0.0', 8080, max_size=MAX_MSG_SIZE
    ):
        logging.info("✅ WebSocket proxy running on port 8080")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
