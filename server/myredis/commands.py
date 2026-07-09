"""Registro y ejecución de comandos. Fase 0: solo PING"""

from typing import Any, Awaitable, Callable
from myredis.storage import Storage
from myredis.expiration import ExpirationManager
from myredis.persistence import Persistence
from myredis.eviction import EvictionManager
from collections import deque
import asyncio
import time

WRITE_COMMANDS = {"SET", "DEL", "EXPIRE", "PERSIST", "INCR", 
                  "DECR", "INCRBY", "DECRBY", "RPUSH", 
                  "LPUSH", "LPOP", "RPOP", "HSET", "HDEL",}


CommandHandler = Callable[[list], Awaitable[Any]]

def _to_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, int):
        return str(value).encode()
    raise TypeError(f"cannot convert {type(value).__name__} to bytes")



class CommandRegistry:
    def __init__(self, storage: Storage, expiration: ExpirationManager, persistence: Persistence, eviction: EvictionManager) -> None:
        self.storage = storage
        self.expiration = expiration
        self.persistence = persistence
        self.eviction = eviction
        self._handlers: dict[str, CommandHandler] = {}
        self._register_all()

    def _get_list(self, key: bytes, create: bool = False):
        self.expiration.check_and_expire(key)
        value = self.storage.get(key)
        if value is None:
            if create:
                d = deque()
                self.storage.set(key, d)
                return d
            return None
        if not isinstance(value, deque):
            raise ValueError("WRONGTYPE Operation against a key holding the wrong kind of value")
        return value
    
    def _get_hash(self, key: bytes, create: bool = False):
        self.expiration.check_and_expire(key)
        value = self.storage.get(key)
        if value is None:
            if create:
                h = {}
                self.storage.set(key, h)
                return h
            return None
        if not isinstance(value, dict):
            raise ValueError("WRONGTYPE Operation agains a key holding the wrong kind of value")
        return value
    
    def _drop_if_empty(self, key: bytes, d) -> None:
        if len(d) == 0:
            self.storage.delete(key)

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
        self.register("INCR", self.cmd_incr)
        self.register("DECR", self.cmd_decr)
        self.register("INCRBY", self.cmd_incrby)
        self.register("DECRBY", self.cmd_decrby)
        self.register("RPUSH", self.cmd_rpush)
        self.register("LPUSH", self.cmd_lpush)
        self.register("LPOP", self.cmd_lpop)
        self.register("RPOP", self.cmd_rpop)
        self.register("LLEN", self.cmd_llen)
        self.register("LRANGE", self.cmd_lrange)
        self.register("HSET", self.cmd_hset)
        self.register("HGET", self.cmd_hget)
        self.register("HDEL", self.cmd_hdel)
        self.register("HKEYS", self.cmd_hkeys)
        self.register("HGETALL", self.cmd_hgetall)
        self.register("HLEN", self.cmd_hlen)
        self.register("SAVE", self.cmd_save)
        self.register("BGSAVE", self.cmd_bgsave)

    async def execute(self, name: str, args: list) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            return Exception(f"ERR uknow command '{name}'")
        try:
            result = await handler(args)
        except ValueError as e:
            return Exception(str(e))
        if name in WRITE_COMMANDS:
            self.eviction.maybe_evict()
        return result
        
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
    
    async def _incr_by(self, key: bytes, delta: int) -> int:
        self.expiration.check_and_expire(key)
        current = self.storage.get(key)
        if current is None:
            value = 0
        else:
            if not isinstance(current, bytes):
                raise ValueError("WRONGTYPE Operation agains a key holding the wrong kind of value")
            try:
                value = int(current)
            except ValueError:
                raise ValueError("ERR value is not an integer or out of range")
        value += delta
        self.storage.set(key, str(value).encode())
        return value
    
    async def cmd_incr(self, args: list) -> int:
        self._check_argc(args, 1, "incr")
        return await self._incr_by(_to_bytes(args[0]), 1)
    
    async def cmd_decr(self, args: list) -> int:
        self._check_argc(args, 1, "decr")
        return await self._incr_by(_to_bytes(args[0]), -1)
    
    async def cmd_incrby(self, args: list) -> int:
        self._check_argc(args, 2, "incrby")
        return await self._incr_by(_to_bytes(args[0]), int(_to_bytes(args[1])))
    
    async def cmd_decrby(self, args: list) -> int:
        self._check_argc(args, 2, "decrby")
        return await self._incr_by(_to_bytes(args[0]), -int(_to_bytes(args[1])))
    
    async def cmd_rpush(self, args: list) -> int:
        self._check_argc_min(args, 2, "rpush")
        key = _to_bytes(args[0])
        d = self._get_list(key, create=True)
        for v in args[1:]:
            d.append(_to_bytes(v))
        return len(d)
    
    async def cmd_lpush(self, args: int) -> int:
        self._check_argc_min(args, 2, "lpush")
        key = _to_bytes(args[0])
        d = self._get_list(key, create=True)
        for v in args[1:]:
            d.appendleft(_to_bytes(v))
        return len(d)
    
    async def cmd_lpop(self, args: list) -> Any:
        self._check_argc(args, 1, "lpop")
        key = _to_bytes(args[0])
        d = self._get_list(key, create=True)
        if d is None or len(d) == 0:
            return None
        v = d.popleft()
        self._drop_if_empty(key, d)
        return v
    
    async def cmd_rpop(self, args: list) -> Any:
        self._check_argc(args, 1, "rpop")
        key = _to_bytes(args[0])
        d = self._get_list(key)
        if d is None or len(d) == 0:
            return None
        v = d.pop()
        self._drop_if_empty(key, d) 
        return v

    async def cmd_llen(self, args: list) -> int:
        self._check_argc(args, 1, "llen")
        d = self._get_list(_to_bytes(args[0]))
        return len(d) if d is not None else 0
    
    async def cmd_lrange(self, args: list) -> list:
        self._check_argc(args, 3, "lrange")
        d = self._get_list(_to_bytes(args[0]))
        if d is None:
            return []
        items = list(d)
        start, stop = int((args[1])), int((args[2]))
        n = len(items)
        if start < 0: start = max(0, n + start)
        if stop < 0: stop = n + stop
        return items[start:stop + 1]
    
    async def cmd_hset(self, args: list):
        self._check_argc_min(args, 3, "hset")
        key = _to_bytes(args[0])
        h = self._get_hash(key, create=True)
        pares = args[1:]
        nuevos = 0
        for i in range(0, len(pares) -1, 2):
            field, value = _to_bytes(pares[i]), _to_bytes(pares[i + 1])
            if field not in h:
                nuevos += 1
            h[field] = value
        return nuevos
        
    async def cmd_hget(self, args: list):
        self._check_argc(args, 2, "hget")
        h = self._get_hash(_to_bytes(args[0]))
        if h is None:
            return None
        return h.get(_to_bytes(args[1]))
    
    async def cmd_hdel(self, args: list):
        self._check_argc_min(args, 2, "hdel")
        key = _to_bytes(args[0])
        h = self._get_hash(key)
        if h is None:
            return 0
        borrados = 0
        for f in args[1:]:
            if h.pop(_to_bytes(f), None) is not None:
                borrados += 1
        if len(h) == 0:
            self.storage.delete(key)
        return borrados
        
    async def cmd_hkeys(self, args: list):
        self._check_argc(args, 1, "hkeys")
        h = self._get_hash(_to_bytes(args[0]))
        return list(h.keys()) if h is not None else []
    
    async def cmd_hgetall(self, args: list):
        self._check_argc(args, 1, "hgetall")
        h = self._get_hash(_to_bytes(args[0]))
        if h is None:
            return []
        out = []
        for f, v in h.items():
            out.append(f)
            out.append(v)
        return out
    
    async def cmd_hlen(self, args: list):
      self._check_argc(args, 1, "hlen")
      h = self._get_hash(_to_bytes(args[0]))
      return len(h) if h is not None else 0
    
    async def cmd_save(self, args):
        await self.persistence.save()
        return "OK"

    async def cmd_bgsave(self, args):
        asyncio.create_task(self.persistence.save())   # no espera
        return "Background saving started"
