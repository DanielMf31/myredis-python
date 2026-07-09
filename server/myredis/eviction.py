"""Eviction LRU: cuando el almacén supera maxmeory, echa las claves menos usadas"""

from myredis.storage import Storage

def parse_memory(text) -> int:
    """'5kb' -> 5120, '100mb' -> 104857600, '0' -> 0 (sin límite). Acepta int/str"""
    text = str(text).strip().lower()
    for suf, mult in (("kb", 1024), ("mb", 1024 ** 2), ("gb", 1024 ** 3), ("b", 1)):
        if text.endswith(suf):
            return int(float(text[: -len(suf)]) * mult)
    return int(text)

class EvictionManager:
    def __init__(self, storage: Storage, maxmemory: int = 0) -> None:
        self.storage = storage
        self.maxmemory = maxmemory

    def needs_eviction(self) -> bool:
        return self.maxmemory > 0 and self.storage.memory_usage() > self.maxmemory
    
    def maybe_evict(self) -> int:
        """Evica LRU hasta bajar de maxmery. Devuelve n* de claves expulsadas"""
        evicted = 0
        while self.needs_eviction() and len(self.storage) > 0:
            if self.storage.evict_lru() is None:
                break
            evicted += 1
        return evicted
    
