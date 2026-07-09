"""Entry point: python -m myredis"""

import asyncio
import os

from myredis.server import RedisServer
from myredis.eviction import parse_memory
from myredis.config import Config

async def main() -> None:
   
    await RedisServer(Config.from_env()).start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nmyredis apagado")

        