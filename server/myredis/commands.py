"""Registro y ejecución de comandos. Fase 0: solo PING"""

from typing import Any, Awaitable, Callable
from myredis.storage import Storage
from myredis.expiration import ExpirationManager
import time

CommandHandler = Callable[[list], Awaitable[any]]

def _to_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, int):
        return str(value).encode()
    raise TypeError(f"cannot convert {type(value).__name__} to bytes")

class CommandRegistry:
    def __init__(self, storage: Storage, expiration: ExpirationManager) -> None:
        self.storage = storage
        self.expiration = expiration
        self._handlers: dict[str, CommandHandler] = {}
        self._register_all()

    def register(self, name: str, handler: CommandHandler) -> None:
        self._handlers[name.upper()] = handler

    def _register_all(self) -> None:
        self.register("PING", self.cmd_ping)
        self.register("SET", self.cmd_set)
        self.register("GET", self.cmd_get)
        self.register("DEL", self.cmd_del)
        self.register("EXISTS", self.cmd_exists)
        self.register("EXPIRE", self.cmd_expire)
        self.register("TTL", self.cmd_ttl)
        self.register("PERSIST", self.cmd_persist)

    async def execute(self, name: str, args: list) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            return Exception(f"ERR uknow command '{name}'")
        try:
            return await handler(args)
        except ValueError as e:
            return Exception(str(e))
        
    @staticmethod
    def _check_argc(args: list, expected: int, cmd: str) -> None:
        if len(args) != expected:
            raise ValueError(f"ERR wrong number of arguments for '{cmd}'")
    
    @staticmethod
    def _check_argc_min(args: list, minimum: int, cmd: str) -> None:
        if len(args) < minimum:
            raise ValueError(f"ERR wrong number of arguments for '{cmd}'")
    

    
    async def cmd_ping(self, args: list) -> Any:
        return "PONG" if not args else args[0]
    
    async def cmd_set(self, args: list) -> Any:
        """
        Comando SET key value EX/PX seconds

        Guarda en data la clave valor. Al guardar o sobreescribir la misma
        clave, se elimina el TTL anterior

        Args
            - args: lista de argumentos.
        
        Returns
            

        
        """
        self._check_argc_min(args, 2, "set")
        key = _to_bytes(args[0])
        value = _to_bytes(args[1])
        self.storage.set(key,value)
        self.storage.remove_expiration(key)

        i = 2
        while i < len(args):
            opt = _to_bytes(args[i]).upper()
            if opt == b"EX":
                self.storage.set_expiration(key, time.time() + int(args[i + 1]))
                i += 2
            elif opt == b"PX":
                self.storage.set_expiration(key, time.time() + int(args[i + 1]) / 1000)
                i += 2
            else: 
                i += 1
        return "OK"
    
    async def cmd_get(self, args: list) -> Any:
        self._check_argc(args, 1, "get")
        key = _to_bytes(args[0])
        self.expiration.check_and_expire(key)
        value = self.storage.get(_to_bytes(args[0]))
        if value is not None and not isinstance(value, bytes):
            raise ValueError("WRONGTYPE Operation against a key holding the wrong kind of value")
        return value
    
    async def cmd_del(self, args: list) -> Any:
        self._check_argc_min(args, 1, "del")
        return sum(1 for a in args if self.storage.delete(_to_bytes(a)))

    async def cmd_exists(self, args: list) -> Any:
        self._check_argc_min(args, 1, "exists")
        return sum(1 for a in args if self.storage.exists(_to_bytes(a)))
    
    async def cmd_expire(self, args):
        self._check_argc(args, 2, "expire")
        key = _to_bytes(args[0])
        seconds = int(args[1])
        if not self.storage.exists(key):
            return 0
        self.storage.set_expiration(key, time.time() + seconds)
        return 1
    async def cmd_ttl(self, args: list) -> int:
        """
        Busca en data la key introducida y devuelve el tiempo restante
        hasta que caduce la TTL

        Args:
            args: lista de argumentos del comando

        Returns:
            Entero con el tiempo necesario para que caduque la key 

        
        """
        self._check_argc(args, 1, "ttl")
        key = _to_bytes(args[0])
        self.expiration.check_and_expire(key)
        if not self.storage.exists(key):
            return -2
        ts = self.storage.get_expiration(key)
        if ts is None:
            return -1
        return int(ts - time.time())
    
    async def cmd_persist(self, args) -> int:
        """
        
        Aplicación comando PERSIST key.

        Quita el TTL de la key.

        Args:
            args: lista de argumentos para el comando. En este caso,
            solo:
                - key (clave en data)

        Returns:
            0 si la clave NO tenía TTL
            1 si la clave SI tenía TTL
          """
        self._check_argc(args, 1, "persist")
        key = _to_bytes(args[0])
        if self.storage.get_expiration is None:
            return 0
        self.storage.remove_expiration(key)
        return 1