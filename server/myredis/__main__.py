"""Entry point: python -m myredis"""

import asyncio
import os

from myredis.server import RedisServer
from myredis.eviction import parse_memory

async def main() -> None:
    host = os.environ.get("MYREDIS_HOST", "0.0.0.0")
    port = int(os.environ.get("MYREDIS_PORT", "6380"))
    max_mem = parse_memory(os.environ.get("MYREDIS_MAXMEMORY", "0"))
    server = RedisServer(host, port, max_mem)
    await server.start()
    await server.server_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nmyredis apagado")

        