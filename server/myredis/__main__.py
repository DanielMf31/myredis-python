"""Entry point: python -m myredis"""

import asyncio
import os

from myredis.server import RedisServer

async def main() -> None:
    host = os.environ.get("MYREDIS_HOST", "0.0.0.0")
    port = int(os.environ.get("MYREDIS_PORT", "6380"))
    server = RedisServer(host, port)
    await server.start()
    await server.server_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nmyredis apagado")

        