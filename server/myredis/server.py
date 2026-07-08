"""Servidor TCP asyncio. Fase 0: solo el esqueleto."""

import asyncio
from myredis.protocol import RESPParser, encode, ProtocolError
from myredis.commands import CommandRegistry
from myredis.storage import Storage
from myredis.expiration import ExpirationManager
from myredis.persistence import Persistence

class RedisServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 6380) -> None:
        self.host = host
        self.port = port
        self.storage = Storage()
        self.persistence = Persistence(self.storage, path="dump.rdb")
        self.expiration = ExpirationManager(self.storage)
        self.commands = CommandRegistry(self.storage, self.expiration, self.persistence)
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set = set()


    async def start(self) -> None:
        self.persistence.load()
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self._spawn(self._snapshot_loop())
        addr = self._server.sockets[0].getsockname()
        print(f"myredis escuchando en {addr}")
        self._spawn(self._expiration_loop())
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        parser = RESPParser()
        try: 
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                parser.feed(data)
                while True:
                    try:
                        message = parser.parse()
                    except ProtocolError as e:
                        writer.write(encode(Exception(str(e))))
                        await writer.drain()
                        break
                    if message is None:
                        break

                    response = await(self._dispatch(message))
                    writer.write(response)
                    await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, message: object) -> bytes:
        
        if not isinstance(message, list) or not message:
            return encode(Exception("ERR protocol error"))
        
        cmd_name = message[0].decode("utf-8", "replace").upper()
        args = message[1:]
        result = await self.commands.execute(cmd_name, args)
        return encode(result)
    
    async def _expiration_loop(self):
        while True:
            await asyncio.sleep(1)
            self.expiration.active_sweep()

    async def _snapshot_loop(self):
        while True:
            await asyncio.sleep(60)
            await self.persistence.save()

    def _spawn(self, coro):
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
    
    
