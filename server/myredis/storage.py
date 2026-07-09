"""Almacén en memoria. Fase 1: clave-valor básico (sin TTL/LRU/persistencia)"""

from collections import OrderedDict, deque
from typing import Any

class Storage:
    def __init__(self) -> None:
        self._data: "OrderedDict[bytes, Any]" = OrderedDict()
        self._expirations: dict[bytes, float] = {}
        self._bytes = 0

    def keys(self) -> list[bytes]:
        return list(self._data.keys())
    
    def flush(self) -> None:
        self._data.clear()
        self._expirations.clear()
        self._bytes = 0

    def type_of(self, key: bytes) -> str:
        if key not in self._data:
            return "none"
        v = self._data[key]
        if isinstance(v, bytes):
            return "string"
        if isinstance(v, deque):
            return "list"
        if isinstance(v, dict):
            return "hash"
        return "none"
    
    @staticmethod
    def _sizeof(value) -> int:
        """Estimación barata del tamaño en bytes de un valor"""
        if isinstance(value, bytes):
            return len(value)
        if isinstance(value, deque):
            return sum(len(x) for x in value)
        if isinstance(value, dict):
            return sum(len(k) + len(v) for k, v in value.items())
        return 8

    def snapshot(self) -> dict:
        """Foto del estado para persistir"""
        return {"data": dict(self._data), "expirations": dict(self._expirations)}
    
    def restore(self, snap: dict) -> None:
        """Recarga el estado desde una foto."""
        from collections import OrderedDict
        self._data = OrderedDict(snap.get("data", {}))
        self._expirations = dict(snap.get("expirations", {}))
        self._bytes = sum(self._sizeof(k) + self._sizeof(v) for k, v in self._data.items())

    def set(self, key: bytes, value: Any) -> None:
        if key in self._data:
            self._bytes -= self._sizeof(self._data[key])
        else:
            self._bytes += self._sizeof(key)

        self._data[key] = value
        self._data.move_to_end(key)
        self._bytes += self._sizeof(value)


    def get(self, key: bytes) -> Any | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]
    
    def delete(self, key: bytes) -> bool:
        if key in self._data:
            self._bytes -= self._sizeof(key) + self._sizeof(self._data[key])
            del self._data[key]
            self._expirations.pop(key, None)
            return True
        return False
    
    def evict_lru(self) -> bytes | None:
        """Expulsa la clave menos usada (el frente del OrderedDict). O(1)"""
        if not self._data:
            return None
        
        key, value = self._data.popitem(last=False)
        self._bytes -= self._sizeof(key) + self._sizeof(value)
        self._expirations.pop(key, None)
        return key
    
    def memory_usage(self) -> int:
        return self._bytes
    
    def dbsize(self) -> int:
        return len(self._data)
    
    def __len__(self) -> int:
        return len(self._data)
    
    def exists(self, key: bytes) -> bool:
        """
        
        Comprueba si una key está dentro de data.

        Devuelve True si está, False si no
        
        
        """
        if key in self._data:
            return True
        return False
    
    ## TTL methods

    def set_expiration(self, key: bytes, ts: float) -> None:
        self._expirations[key] = ts

    def get_expiration(self, key: bytes) -> float:
        """Devuelve el TTL de la key en float"""
        return self._expirations.get(key)
    
    def remove_expiration(self, key: bytes) -> None:
        self._expirations.pop(key, None)

    def keys_with_expiration(self) -> list[tuple[bytes, float]]:
        return list(self._expirations.items())
    
