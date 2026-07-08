# Fase 7 — Eviction LRU: maxmemory + expulsar lo menos usado

> **Meta:** que el server **no crezca sin límite**. Cuando la memoria supera `maxmemory`, expulsas (evictas) las claves **menos usadas recientemente** (LRU). Al terminar, con `MYREDIS_MAXMEMORY=5kb` el almacén se **estabiliza** en vez de tragarse la RAM.
>
> **Prerrequisito:** F1 (más rico con F4/F5). **Archivo nuevo:** `eviction.py`. Tocas `storage.py`, `commands.py`, `server.py` y `__main__.py`.
>
> **Cómo usarlo:** contrato + edge cases + código comentado + los tests que debe pasar. Tecléalo tú en `server/myredis/`; intenta cada pieza antes de mirar mi versión. No copies-pegues.

---

## 1. Conceptos (qué entender antes de teclear)

### 1.1 LRU = Least Recently Used
Cuando no cabe todo, ¿qué tiras? La política **LRU** tira lo que **hace más tiempo que no se toca**, apostando a que lo reciente se volverá a usar (localidad temporal). No es la única (Redis tiene LFU, random, TTL…), pero LRU es la clásica y la que ya tienes medio montada.

### 1.2 Por qué tu `OrderedDict` ya es medio LRU
Desde la Fase 1, tu `Storage.set` y `Storage.get` llaman a **`self._data.move_to_end(key)`**. Es decir: **cada acceso empuja la clave al final**. Consecuencia:
- El **final** del `OrderedDict` = lo más reciente (MRU).
- El **principio** = lo más antiguo sin tocar (LRU).

Evictar es, por tanto, **`self._data.popitem(last=False)`** — sacar el primero. O(1). Toda la fase se apoya en esto. (`OrderedDict` = hash table para acceso O(1) + lista doblemente enlazada para el orden O(1); por eso es la estructura correcta.)

### 1.3 Contabilidad de memoria (aproximada)
Necesitas saber cuánto ocupas para decidir cuándo evictar. Llevamos un contador `_bytes` que se ajusta en `set`/`delete` con una **estimación** del tamaño (longitud de clave + valor). No es exacto (Redis tampoco; muestrea), y el crecimiento *in-place* de listas/hashes no se contabiliza al byte — pero basta para el mecanismo y para los tests (que usan strings). Anótalo: *"mi maxmemory es aproximado."*

### 1.4 Cuándo se dispara
Tras **cada escritura** compruebas si te pasaste de `maxmemory` y, si sí, evictas en bucle hasta bajar. El punto natural para ese hook es **`CommandRegistry.execute()`**, justo después de ejecutar un comando de escritura.

---

## 2. `storage.py` — contabilidad + evict_lru (Issue F7-1)

**Contrato:** el `Storage` sabe cuánta memoria (aprox.) usa (`memory_usage()`), cuántas claves tiene (`dbsize()`/`__len__`), y sabe **expulsar la LRU** (`evict_lru()` → devuelve la clave evictada, o `None` si está vacío).

**Edge cases:** `evict_lru()` sobre almacén vacío → `None`; tras `restore()` (Fase 6) hay que **recomputar `_bytes`** (porque `restore` no pasa por `set`).

Cambios sobre tu `Storage`:

```python
from collections import OrderedDict, deque

class Storage:
    def __init__(self) -> None:
        self._data: "OrderedDict[bytes, Any]" = OrderedDict()
        self._expirations: dict[bytes, float] = {}
        self._bytes = 0                                   # ← contador de memoria aprox.

    @staticmethod
    def _sizeof(value) -> int:
        """Estimación barata del tamaño en bytes de un valor."""
        if isinstance(value, bytes):
            return len(value)
        if isinstance(value, deque):
            return sum(len(x) for x in value)
        if isinstance(value, dict):
            return sum(len(k) + len(v) for k, v in value.items())
        return 8

    def set(self, key: bytes, value: Any) -> None:
        if key in self._data:
            self._bytes -= self._sizeof(self._data[key])  # quita el valor viejo
        else:
            self._bytes += self._sizeof(key)              # clave nueva: cuenta la clave
        self._data[key] = value
        self._data.move_to_end(key)                       # LRU: recién escrita = MRU
        self._bytes += self._sizeof(value)                # suma el valor nuevo

    def delete(self, key: bytes) -> bool:
        if key in self._data:
            self._bytes -= self._sizeof(key) + self._sizeof(self._data[key])
            del self._data[key]
            self._expirations.pop(key, None)
            return True
        return False

    def evict_lru(self) -> bytes | None:
        """Expulsa la clave menos usada (el frente del OrderedDict). O(1)."""
        if not self._data:
            return None
        key, value = self._data.popitem(last=False)       # ← el más viejo
        self._bytes -= self._sizeof(key) + self._sizeof(value)
        self._expirations.pop(key, None)
        return key

    def memory_usage(self) -> int:
        return self._bytes

    def dbsize(self) -> int:
        return len(self._data)

    def __len__(self) -> int:
        return len(self._data)
```

Y en `restore()` (de la Fase 6), recomputa el contador tras cargar:

```python
def restore(self, snap: dict) -> None:
    from collections import OrderedDict
    self._data = OrderedDict(snap.get("data", {}))
    self._expirations = dict(snap.get("expirations", {}))
    self._bytes = sum(self._sizeof(k) + self._sizeof(v) for k, v in self._data.items())  # ← recomputar
```

> `get()` no cambia respecto a fases previas: ya hace `move_to_end`, que es lo que **salva de la eviction** a una clave recién leída (el corazón de LRU).

---

## 3. `eviction.py` — la política (NUEVO, Issue F7-2)

**Contrato:**
- `parse_memory("5kb"/"100mb"/"0")` → bytes (`int`). `0` = sin límite.
- `EvictionManager.maybe_evict()` → evicta LRU mientras se supere `maxmemory`; devuelve cuántas expulsó.

**Edge cases:** `maxmemory=0` → nunca evicta; almacén vacío → 0; la clave recién escrita (MRU) no es la primera candidata.

```python
"""Eviction LRU: cuando el almacén supera maxmemory, echa las claves menos usadas. Fase 7."""
from myredis.storage import Storage


def parse_memory(text) -> int:
    """'5kb' -> 5120, '100mb' -> 104857600, '0' -> 0 (sin límite). Acepta int/str."""
    text = str(text).strip().lower()
    for suf, mult in (("kb", 1024), ("mb", 1024 ** 2), ("gb", 1024 ** 3), ("b", 1)):
        if text.endswith(suf):
            return int(float(text[: -len(suf)]) * mult)
    return int(text)                          # bytes pelados ("100" -> 100)


class EvictionManager:
    def __init__(self, storage: Storage, maxmemory: int = 0) -> None:
        self.storage = storage
        self.maxmemory = maxmemory            # 0 = sin límite

    def needs_eviction(self) -> bool:
        return self.maxmemory > 0 and self.storage.memory_usage() > self.maxmemory

    def maybe_evict(self) -> int:
        """Evicta LRU hasta bajar de maxmemory. Devuelve nº de claves expulsadas."""
        evicted = 0
        while self.needs_eviction() and len(self.storage) > 0:
            if self.storage.evict_lru() is None:
                break
            evicted += 1
        return evicted
```

---

## 4. `commands.py` — disparar la eviction tras cada escritura (el hook)

Aquí es donde el doc antiguo se quedaba en "hazlo en un punto central". El punto concreto es **`execute()`**: tras ejecutar un comando de **escritura**, comprueba memoria. Necesitas (a) saber qué comandos escriben, y (b) que el registry tenga el `eviction`.

```python
# arriba de commands.py: el conjunto de comandos que MUTAN el almacén
WRITE_COMMANDS = {
    "SET", "DEL", "EXPIRE", "PERSIST", "INCR", "DECR", "INCRBY", "DECRBY",
    "RPUSH", "LPUSH", "LPOP", "RPOP", "HSET", "HDEL",
}

class CommandRegistry:
    def __init__(self, storage, expiration, persistence, eviction) -> None:  # ← +eviction
        self.storage = storage
        self.expiration = expiration
        self.persistence = persistence
        self.eviction = eviction
        self._handlers = {}
        self._register_all()

    async def execute(self, name: str, args: list) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            return Exception(f"ERR unknown command '{name}'")
        try:
            result = await handler(args)
        except ValueError as e:
            return Exception(str(e))
        if name in WRITE_COMMANDS:
            self.eviction.maybe_evict()       # ← tras escribir, ¿me pasé de memoria?
        return result
```

> Por qué **después** del handler: la clave recién escrita ya está dentro y marcada como MRU, así que la eviction expulsa las **viejas**, no la que acabas de meter. (Redis real puede rechazar la escritura con `OOM` si ni evictando cabe; nosotros nos quedamos en el caso simple "evicta y sigue".)

---

## 5. `server.py` / `__main__.py` — leer maxmemory

En `RedisServer.__init__`, crea el `EvictionManager` y pásalo al registry (delta sobre la Fase 6):

```python
from myredis.eviction import EvictionManager

    def __init__(self, host="0.0.0.0", port=6380, dbfilename="dump.rdb", maxmemory=0) -> None:
        # ... storage, persistence, expiration ...
        self.eviction = EvictionManager(self.storage, maxmemory)                # ← nuevo
        self.commands = CommandRegistry(self.storage, self.expiration,
                                        self.persistence, self.eviction)         # ← +eviction
```

Y en `__main__.py`, lee `MYREDIS_MAXMEMORY` con `parse_memory`:

```python
from myredis.eviction import parse_memory
# ...
maxmem = parse_memory(os.environ.get("MYREDIS_MAXMEMORY", "0"))   # "0" = sin límite
server = RedisServer(host, port, dbfilename=dbfile, maxmemory=maxmem)
```

---

## 6. Tests

**Unit** — `server/tests/unit/test_eviction.py`:

```python
from myredis.storage import Storage
from myredis.eviction import EvictionManager, parse_memory


def test_parse_memory():
    assert parse_memory("5kb") == 5120
    assert parse_memory("1mb") == 1024 * 1024
    assert parse_memory("0") == 0
    assert parse_memory("100") == 100

def test_evict_lru_quita_la_mas_vieja():
    s = Storage()
    for k in (b"a", b"b", b"c"):
        s.set(k, b"x")
    assert s.evict_lru() == b"a"          # la más antigua (front)
    assert s.get(b"a") is None
    assert s.get(b"b") == b"x"

def test_get_refresca_lru():
    s = Storage()
    for k in (b"a", b"b", b"c"):
        s.set(k, b"x")
    s.get(b"a")                            # 'a' pasa a MRU
    assert s.evict_lru() == b"b"           # ahora la más vieja es 'b'

def test_maybe_evict_respeta_maxmemory():
    s = Storage()
    for i in range(200):
        s.set(f"k{i}".encode(), b"x" * 50)
    em = EvictionManager(s, maxmemory=parse_memory("1kb"))
    em.maybe_evict()
    assert s.memory_usage() <= parse_memory("1kb")

def test_maxmemory_cero_no_evicta():
    s = Storage()
    for i in range(50):
        s.set(f"k{i}".encode(), b"x" * 100)
    assert EvictionManager(s, maxmemory=0).maybe_evict() == 0
```

**Integración** — `server/tests/integration/test_eviction.py` (server real con `MYREDIS_MAXMEMORY`):

```python
def test_evicta_los_viejos(myredis_server):
    with myredis_server(MYREDIS_MAXMEMORY="5kb") as c:
        for i in range(500):
            c.set(f"k{i}", "x" * 100)
        assert c.get("k0") is None                 # la primera (más vieja) fue evictada
        assert c.get("k499") == b"x" * 100         # la última sigue viva

def test_get_salva_de_eviction(myredis_server):
    with myredis_server(MYREDIS_MAXMEMORY="5kb") as c:
        c.set("importante", "x" * 100)
        for i in range(500):
            c.get("importante")                    # tocarla la mantiene reciente
            c.set(f"k{i}", "x" * 100)
        assert c.get("importante") == b"x" * 100   # sobrevivió por ser MRU
```

---

## 7. Verificación de la Fase 7

```bash
cd server && source ../.venv/bin/activate

pytest tests/unit/test_eviction.py -v                    # LRU + parse_memory
pytest tests/integration/test_eviction.py -v             # se estabiliza + LRU salva

# a mano:
MYREDIS_MAXMEMORY=5kb python -m myredis                   # arranca con límite
#   en otra terminal, mete muchas claves:
for i in $(seq 1 500); do redis-cli -p 6380 SET k$i "$(head -c 100 /dev/zero | tr '\0' x)" >/dev/null; done
redis-cli -p 6380 GET k1     # -> (nil)     (evictada)
redis-cli -p 6380 GET k500   # -> "xxxx…"   (la última, viva)
```

**Fase 7 hecha** = unit verde + el almacén se estabiliza bajo `MYREDIS_MAXMEMORY` + una clave leída sobrevive a la eviction.

## 8. Cuando termines
- Post-mortem: ¿por qué `get` "salva" una clave? ¿qué política usarías para un caché de sesiones (LRU) vs para contadores (LFU)? ¿qué haría Redis si ni evictando cabe (OOM)?
- Cierra F7-1/F7-2 en Huly → **Fase 8 (pulido: DBSIZE/KEYS/INFO + config + benchmark)**.

## El edge case para tu bitácora
El truco de toda la fase es una sola línea que ya tenías desde F1: **`move_to_end` en cada acceso**. La estructura de datos correcta (`OrderedDict`) convirtió "expulsar la menos usada" en un `popitem(last=False)` O(1). *Elegir bien la estructura de datos es la mitad del diseño.*

## Conexiones
- `docs/fase-1-strings.md` (de dónde sale `OrderedDict`/`move_to_end`) · `docs/fase-6-persistencia.md` · `PHASES.md` · `issues/fase-7.md` · [[disenar-funciones-y-programas]]
