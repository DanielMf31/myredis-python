import random
import time
from myredis.storage import Storage

class ExpirationManager:
    
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def is_expired(self, key: bytes, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        ts = self.storage.get_expiration(key)
        return ts is not None and now >= ts
    
    def check_and_expire(self, key: bytes) -> bool:
        """Lazy: si la clave caducó, la borra. Devuelve True si la borró"""
        if self.is_expired(key):
            self.storage.delete(key)
            return True
        return False
    
    def active_sweep(self, sample_size: int = 20, threshold: float = 0.25) -> int:
        """Active: muestrea claves con TTL, borra las caducadas; repite si >25%."""
        borradas = 0
        while True:
            items = self.storage.keys_with_expiration()
            if not items:
                return borradas
            muestra = random.sample(items, min(sample_size, len(items)))
            now = time.time()
            caducadas = 0
            for key, ts in muestra:
                if now >= ts:
                    self.storage.delete(key)
                    caducadas += 1
                borradas += caducadas
                if caducadas / len(muestra) <= threshold:
                    return borradas