# Fase 7 — Eviction LRU: maxmemory

> **Meta:** cuando la memoria supera un límite, **echar las claves menos usadas recientemente** (LRU) para hacer sitio. Aquí por fin cobra sentido el `OrderedDict` que usas desde la Fase 1.
>
> **Prerrequisito:** F1. **Archivo nuevo:** `eviction.py`. Tocas `storage.py`, `config.py` (o env), `commands.py`/`server.py` (disparar tras escrituras).

## 1. Concepto: por qué OrderedDict da LRU en O(1)
- **LRU** (Least Recently Used) = "el que hace más que no se toca, fuera".
- Un **`OrderedDict`** mantiene el **orden de inserción/acceso**. Cada vez que **accedes** a una clave, haces `move_to_end(key)` → esa clave pasa a ser "la más reciente" (al final).
- Para **desalojar**, sacas **el primero** con `popitem(last=False)` → ese es, por construcción, el **menos usado recientemente**. **O(1)**.
- Combina hash table (acceso O(1)) + linked list (orden O(1)) — la razón exacta de elegir OrderedDict.

## 2. `storage.py` — tracking de memoria + evict

Necesitas estimar cuánta memoria usas y saber cuándo pasarte:

```python
# en __init__:
self.maxmemory = maxmemory              # bytes; 0 = sin límite
self._bytes = 0                          # estimación

def _estimate(self, key: bytes, value) -> int:
    n = len(key) + 64                    # overhead aproximado por entrada
    if isinstance(value, bytes):
        n += len(value)
    elif isinstance(value, (list,)) or hasattr(value, "__len__"):
        n += 64 * len(value)             # aprox para deque/dict
    return n

# ajusta _bytes en set() y delete():
#   set:    self._bytes += self._estimate(key, value)   (y resta el viejo si existía)
#   delete: self._bytes -= self._estimate(key, value_borrado)

def needs_eviction(self) -> bool:
    return self.maxmemory > 0 and self._bytes > self.maxmemory

def evict_lru(self) -> bool:
    """Echa la clave menos usada recientemente. False si no hay nada que echar."""
    if not self._data:
        return False
    key, value = self._data.popitem(last=False)     # ← el más viejo
    self._bytes -= self._estimate(key, value)
    self._expirations.pop(key, None)
    return True
```
> Y recuerda: `get()` y `set()` hacen **`move_to_end(key)`** (ya lo tienes desde F1) — eso es lo que mantiene el orden LRU vivo.

## 3. `eviction.py` — el disparador (NUEVO)
```python
"""Política de eviction: echa claves LRU mientras se supere maxmemory."""


class EvictionManager:
    def __init__(self, storage) -> None:
        self.storage = storage

    def maybe_evict(self) -> int:
        """Echa claves hasta bajar del límite. Devuelve cuántas echó."""
        echadas = 0
        while self.storage.needs_eviction():
            if not self.storage.evict_lru():
                break                      # no queda nada que echar
            echadas += 1
        return echadas
```

## 4. Disparar tras cada escritura
En los comandos que **escriben** (SET, LPUSH, HSET, INCR...), tras modificar, llama a `eviction.maybe_evict()`. Lo más limpio: hazlo en un punto central. Por ejemplo, tras el dispatch de un comando de escritura, o dentro de cada `cmd_set/...`:
```python
# al final de cmd_set (y demás escrituras):
self.eviction.maybe_evict()
```
El registry recibe también `eviction`; y `config.py` (o env `MYREDIS_MAXMEMORY`) fija el límite. Acepta formatos tipo `100mb`:
```python
def parse_memory(s: str) -> int:
    s = s.strip().lower()
    mult = {"kb": 1024, "mb": 1024**2, "gb": 1024**3}
    for suf, m in mult.items():
        if s.endswith(suf):
            return int(float(s[:-2]) * m)
    return int(s)
```

## 5. Tests
```python
def test_evicta_los_viejos(...):
    # arranca con MYREDIS_MAXMEMORY pequeño (p.ej. unos pocos KB)
    # mete muchas claves; las primeras (menos usadas) deben desaparecer
    # y las últimas seguir estando
    ...

def test_get_refresca_lru(...):
    # mete A, B; haz GET A (lo refresca); llena hasta forzar 1 eviction;
    # debe caer B (más viejo), no A
    ...
```
> El test de LRU es fino: comprueba que **un GET refresca** la clave (la salva de ser desalojada). Ese es el corazón del algoritmo.

## 6. Verificación
```bash
MYREDIS_MAXMEMORY=5kb python -m myredis   # límite bajito
# mete muchas claves con un bucle de redis-cli SET; comprueba con DBSIZE
# que se estabiliza (las viejas se van echando)
```

## Siguiente
F7 → **Fase 8 (Pulido)**: INFO/DBSIZE/FLUSHDB/KEYS + benchmark vs Redis real. Cierras el clon.

## El edge case para tu bitácora
La estimación de memoria es **aproximada** (Python no te da el tamaño exacto fácil). Redis real usa su propio allocator y lo sabe al byte. Aquí es una heurística — suficiente para el propósito educativo, pero anótalo: *"mi maxmemory es aproximado."*

## Conexiones
- `docs/fase-1-strings.md` · `PHASES.md` · `HULY_fase-7-issues.md`
