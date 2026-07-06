# Fase 2 — Expiración: EXPIRE / TTL / PERSIST (+ SET EX)

> **Meta:** que las claves puedan **caducar**. Añades TTLs al almacén, un módulo de expiración (lazy + active) y los comandos EXPIRE/TTL/PERSIST + la opción EX de SET.
> **Prerrequisito:** Fase 1 (SET/GET/DEL/EXISTS). **Archivo nuevo:** `expiration.py`. Tocas `storage.py`, `commands.py` y `server.py`.
> **Estilo:** contrato + edge cases + código guiado + tests. Tecléalo tú.

## 1. Concepto: dos formas de expirar (las dos, como Redis real)

- **Lazy (perezosa):** cuando **lees/tocas** una clave, compruebas si ya caducó; si sí, la borras y devuelves nil. Barata pero deja "muertos" ocupando memoria si nadie los toca.
- **Active (activa):** un bucle en segundo plano **muestrea** 20 claves con TTL al azar, borra las caducadas, y **repite si más del 25% estaban muertas** (heurística de Redis). Libera memoria de las que nadie lee.

Las dos juntas: lazy garantiza corrección (nunca devuelves algo caducado), active mantiene la memoria a raya.

## 2. `storage.py` — añadir TTLs

Tu `Storage` guarda los vencimientos en un **dict aparte** (la mayoría de claves NO tienen TTL → así no gastas memoria en ellas):

```python
# en __init__ añade:
self._expirations: dict[bytes, float] = {}   # key -> timestamp epoch de caducidad

# y estos métodos:
def set_expiration(self, key: bytes, ts: float) -> None:
    self._expirations[key] = ts

def get_expiration(self, key: bytes) -> float | None:
    return self._expirations.get(key)

def remove_expiration(self, key: bytes) -> None:
    self._expirations.pop(key, None)

def keys_with_expiration(self) -> list[tuple[bytes, float]]:
    return list(self._expirations.items())
```
> Y en `delete()`, acuérdate de limpiar también el TTL: `self._expirations.pop(key, None)`.

## 3. `expiration.py` — el gestor (NUEVO)

**Contrato:** `is_expired(key)` dice si caducó; `check_and_expire(key)` la borra si caducó (lazy); `active_sweep()` hace la ronda activa.

```python
"""Expiración de claves: lazy (al acceder) + active (barrido en background)."""
import random
import time


class ExpirationManager:
    def __init__(self, storage) -> None:
        self.storage = storage

    def is_expired(self, key: bytes, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        ts = self.storage.get_expiration(key)
        return ts is not None and now >= ts

    def check_and_expire(self, key: bytes) -> bool:
        """Lazy: si la clave caducó, la borra. Devuelve True si la borró."""
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
```

## 4. `commands.py` — enganchar lazy + comandos nuevos

**Cambio clave:** `cmd_get` (y toda lectura) llama primero a `expiration.check_and_expire(key)` para no devolver caducados. El registry ahora recibe también el `expiration`.

```python
# el registry recibe expiration:
def __init__(self, storage: Storage, expiration: ExpirationManager) -> None:
    self.storage = storage
    self.expiration = expiration
    ...

# en cmd_get, ANTES de leer:
async def cmd_get(self, args):
    self._check_argc(args, 1, "get")
    key = _to_bytes(args[0])
    self.expiration.check_and_expire(key)     # ← lazy
    value = self.storage.get(key)
    ...
```

Comandos nuevos (**contratos**):
- `EXPIRE key seconds` → pone TTL = ahora + seconds. Devuelve `1` si la clave existe, `0` si no.
- `TTL key` → segundos restantes; **`-1`** si no tiene TTL; **`-2`** si la clave no existe.
- `PERSIST key` → quita el TTL. Devuelve `1` si tenía TTL, `0` si no.
- `SET key value EX seconds` → SET que además pone TTL. (Y `SET` **sin** EX debe **quitar** cualquier TTL previo.)

```python
import time

async def cmd_expire(self, args):
    self._check_argc(args, 2, "expire")
    key = _to_bytes(args[0]); seconds = int(args[1])
    if not self.storage.exists(key):
        return 0
    self.storage.set_expiration(key, time.time() + seconds)
    return 1

async def cmd_ttl(self, args):
    self._check_argc(args, 1, "ttl")
    key = _to_bytes(args[0])
    self.expiration.check_and_expire(key)
    if not self.storage.exists(key):
        return -2
    ts = self.storage.get_expiration(key)
    if ts is None:
        return -1
    return int(ts - time.time())

async def cmd_persist(self, args):
    self._check_argc(args, 1, "persist")
    key = _to_bytes(args[0])
    if self.storage.get_expiration(key) is None:
        return 0
    self.storage.remove_expiration(key)
    return 1

# cmd_set: parsea EX/PX opcional y quita TTL si no viene EX
async def cmd_set(self, args):
    self._check_argc_min(args, 2, "set")
    key = _to_bytes(args[0]); value = _to_bytes(args[1])
    self.storage.set(key, value)
    self.storage.remove_expiration(key)                 # SET limpia TTL previo
    # opciones EX/PX (case-insensitive)
    i = 2
    while i < len(args):
        opt = _to_bytes(args[i]).upper()
        if opt == b"EX":
            self.storage.set_expiration(key, time.time() + int(args[i + 1])); i += 2
        elif opt == b"PX":
            self.storage.set_expiration(key, time.time() + int(args[i + 1]) / 1000); i += 2
        else:
            i += 1
    return "OK"
```
Registra los nuevos en `_register_all`: `EXPIRE`, `TTL`, `PERSIST`.

## 5. `server.py` — el barrido activo en segundo plano

Tu server crea el `ExpirationManager` y lanza un **bucle de fondo** que llama a `active_sweep` cada poco:

```python
from myredis.expiration import ExpirationManager

# en __init__:
self.storage = Storage()
self.expiration = ExpirationManager(self.storage)
self.commands = CommandRegistry(self.storage, self.expiration)
self._tasks: set = set()

# un helper para tareas de fondo:
def _spawn(self, coro):
    t = asyncio.create_task(coro)
    self._tasks.add(t)
    t.add_done_callback(self._tasks.discard)

# el bucle de expiración:
async def _expiration_loop(self):
    while True:
        await asyncio.sleep(1)          # cada segundo
        self.expiration.active_sweep()

# en start(), tras arrancar el server:
self._spawn(self._expiration_loop())
```
> Nota `asyncio`: usa `asyncio.sleep`, **nunca** `time.sleep` (bloquearía el event loop). Y guarda la referencia de la task (`self._tasks`) o el GC te la mata.

## 6. Tests (integración con redis-py)
```python
def test_ttl_sin_expiracion(redis_client):
    redis_client.set("k", "v")
    assert redis_client.ttl("k") == -1

def test_expire_y_ttl(redis_client):
    redis_client.set("k", "v")
    assert redis_client.expire("k", 100) is True
    assert 0 < redis_client.ttl("k") <= 100

def test_persist(redis_client):
    redis_client.set("k", "v", ex=100)
    assert redis_client.persist("k") is True
    assert redis_client.ttl("k") == -1

def test_set_ex(redis_client):
    redis_client.set("k", "v", ex=100)
    assert 0 < redis_client.ttl("k") <= 100
```

## 7. Verificación
```bash
pytest tests/ -v
python -m myredis  # y en otra terminal:
redis-cli -p 6380 SET k v EX 100
redis-cli -p 6380 TTL k        # -> (integer) ~100
redis-cli -p 6380 PERSIST k    # -> (integer) 1
redis-cli -p 6380 TTL k        # -> (integer) -1
```

## Siguiente
F2 hecha → **Fase 3 (INCR/DECR)**. Edge case para tu bitácora: ¿qué devuelve `TTL` para una clave inexistente (`-2`) vs sin TTL (`-1`)? Esa distinción es sutil y cae en interviews.

## Conexiones
- `docs/fase-1-strings.md` · `PHASES.md` · `HULY_fase-2-issues.md` · [[disenar-funciones-y-programas]]
