"""Almacén en memoria. Fase 1: clave-valor básico (sin TTL/LRU/persistencia)"""

from collections import OrderedDict
from typing import Any

class Storage:
    def __init__(self) -> None:
        self._data: "OrderedDict[bytes, Any]" = OrderedDict()
        self._expirations: dict[bytes, float] = {}

    def snapshot(self) -> dict:
        """Foto del estado para persistir"""
        return {"data": dict(self._data), "expirations": dict(self._expirations)}
    
    def restore(self, snap: dict) -> None:
        """Recarga el estado desde una foto."""
        from collections import OrderedDict
        self._data = OrderedDict(snap.get("data", {}))
        self._expirations = dict(snap.get("expirations", {}))

    def set(self, key: bytes, value: Any) -> None:
        self._data[key] = value
        self._data.move_to_end(key)

    def get(self, key: bytes) -> Any | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]
    
    def delete(self, key: bytes) -> bool:
        if key in self._data:
            del self._data[key]
            self._expirations.pop(key, None)
            return True
        return False
    
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
    
