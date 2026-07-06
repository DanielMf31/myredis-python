# Fase 1 — Strings: SET / GET / DEL / EXISTS

> **Meta:** que tu server **guarde y devuelva datos**. Añades el almacén (`storage.py`) y cuatro comandos. Al terminar, `redis-cli -p 6380 SET foo bar` / `GET foo` / `DEL foo` / `EXISTS foo` funcionan con el cliente oficial.
>
> **Prerrequisito:** Fase 0 completa (PING responde). Reutilizas `protocol.py` y `server.py` tal cual; solo tocas 2 sitios y añades 1 archivo.
>
> **Cómo usarlo:** contrato + edge cases + código comentado + tests. Tecléalo tú; intenta cada pieza antes de mirar mi versión.

---

## 1. Qué cambia respecto a la Fase 0

La tubería (`red → parse → dispatch → handler → encode → write`) ya está. Solo añades:

1. **`storage.py`** (nuevo) — el almacén clave→valor en memoria.
2. **`commands.py`** — 4 handlers nuevos + helpers de validación; el registry ahora recibe el `storage`.
3. **`server.py`** — 2 líneas: crear el `Storage` y pasárselo al registry.

Nada de `protocol.py` ni del bucle de conexión cambia. Esa es la gracia del walking skeleton: **crecer es colgar comandos del registry.**

---

## 2. `storage.py` — el almacén (Issue F1-1)

**Contrato:** un KV en memoria con `get`/`set`/`delete`/`exists`, todo O(1). Claves y valores son `bytes`. (Uso `OrderedDict` en vez de `dict` mirando al futuro: en fases posteriores da LRU O(1); ahora es inofensivo.)

**Edge cases:** `get` de clave inexistente → `None`; `delete` devuelve si existía; `set` sobrescribe.

```python
"""Almacén en memoria. Fase 1: clave-valor básico (sin TTL/LRU/persistencia)."""
from collections import OrderedDict
from typing import Any


class Storage:
    def __init__(self) -> None:
        self._data: "OrderedDict[bytes, Any]" = OrderedDict()

    def set(self, key: bytes, value: Any) -> None:
        self._data[key] = value
        self._data.move_to_end(key)      # LRU: útil en fases futuras, inofensivo ahora

    def get(self, key: bytes) -> Any | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def delete(self, key: bytes) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    def exists(self, key: bytes) -> bool:
        return key in self._data

    # --- Bonus (para DBSIZE / FLUSHDB / KEYS) ---
    def __len__(self) -> int:
        return len(self._data)

    def flush(self) -> None:
        self._data.clear()

    def keys(self) -> list[bytes]:
        return list(self._data.keys())
```

**Tests** — `server/tests/unit/test_storage.py`:

```python
from myredis.storage import Storage


def test_set_get():
    s = Storage(); s.set(b"k", b"v"); assert s.get(b"k") == b"v"

def test_get_missing():
    assert Storage().get(b"nope") is None

def test_set_overwrite():
    s = Storage(); s.set(b"k", b"v1"); s.set(b"k", b"v2"); assert s.get(b"k") == b"v2"

def test_delete():
    s = Storage(); s.set(b"k", b"v")
    assert s.delete(b"k") is True
    assert s.delete(b"k") is False

def test_exists():
    s = Storage(); s.set(b"k", b"v")
    assert s.exists(b"k") is True
    assert s.exists(b"nope") is False
```

---

## 3. `commands.py` — los 4 handlers (Issues F1-2 y F1-3)

**Contratos (convención Redis):**
- `SET key value` → devuelve `"OK"` (simple string). Mínimo 2 args.
- `GET key` → `bytes` o `None` (nil si no existe). Exactamente 1 arg. **WRONGTYPE** si el valor no es bytes (en fases futuras habrá listas/hashes).
- `DEL key [key...]` → `int` = cuántas claves existentes se borraron.
- `EXISTS key [key...]` → `int` = cuántas existen (cuenta duplicados).

**Patrón de validación:** `_check_argc*` primero → `_to_bytes` cada arg → tocar storage. Los errores de validación se lanzan como `ValueError` y `execute` los convierte en error RESP.

El archivo completo de Fase 1 (crece sobre el de Fase 0):

```python
"""Registro y ejecución de comandos. Fase 1: PING + SET/GET/DEL/EXISTS."""
from typing import Any, Awaitable, Callable

from myredis.storage import Storage

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
    def __init__(self, storage: Storage) -> None:      # ← ahora recibe el storage
        self.storage = storage
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

    async def execute(self, name: str, args: list) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            return Exception(f"ERR unknown command '{name}'")
        try:
            return await handler(args)
        except ValueError as e:            # validación / WRONGTYPE → error RESP
            return Exception(str(e))

    # --- helpers ---
    @staticmethod
    def _check_argc(args: list, expected: int, cmd: str) -> None:
        if len(args) != expected:
            raise ValueError(f"ERR wrong number of arguments for '{cmd}'")

    @staticmethod
    def _check_argc_min(args: list, minimum: int, cmd: str) -> None:
        if len(args) < minimum:
            raise ValueError(f"ERR wrong number of arguments for '{cmd}'")

    # --- handlers ---
    async def cmd_ping(self, args: list) -> Any:
        return "PONG" if not args else args[0]

    async def cmd_set(self, args: list) -> Any:
        self._check_argc_min(args, 2, "set")
        self.storage.set(_to_bytes(args[0]), _to_bytes(args[1]))
        return "OK"

    async def cmd_get(self, args: list) -> Any:
        self._check_argc(args, 1, "get")
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
```

> Nota: en Fase 0 `execute` no capturaba nada; ahora envuelve el handler en `try/except ValueError` para que una validación fallida sea un **error RESP** limpio y no tumbe la conexión.

---

## 4. `server.py` — enganchar el storage (2 líneas)

En `RedisServer.__init__`, crea el `Storage` y pásalo al registry:

```python
from myredis.storage import Storage
# ...
    def __init__(self, host: str = "0.0.0.0", port: int = 6380) -> None:
        self.host = host
        self.port = port
        self.storage = Storage()                     # ← nuevo
        self.commands = CommandRegistry(self.storage)  # ← ahora con storage
        self._server = None
```

Todo lo demás de `server.py` (el bucle `_handle_client`, `_dispatch`) queda **igual** que en Fase 0.

---

## 5. Tests de integración (Issue F1-4)

Añade a `server/tests/integration/test_via_redis_py.py` (el `redis_client` viene del `conftest.py` de Fase 0):

```python
def test_set_get(redis_client):
    assert redis_client.set("foo", "bar") is True
    assert redis_client.get("foo") == b"bar"

def test_get_nonexistent(redis_client):
    assert redis_client.get("nope") is None

def test_delete(redis_client):
    redis_client.set("a", "1"); redis_client.set("b", "2")
    assert redis_client.delete("a", "b", "c") == 2      # solo existentes

def test_exists(redis_client):
    redis_client.set("foo", "bar")
    assert redis_client.exists("foo") == 1
    assert redis_client.exists("nope") == 0
```

> Estos tests dependen de que el **encoder RESP** de tu Fase 0 sea correcto: `"OK"`→simple string, `int`→`:`, `None`→nil bulk, `bytes`→bulk. Si algo falla aquí, revisa el encoder antes que el handler.

---

## 6. Verificación de la Fase 1

```bash
cd server && source ../.venv/bin/activate

pytest tests/unit -v                 # storage + protocol (F0) en verde

python -m myredis                    # arranca en :6380
#   en otra terminal:
redis-cli -p 6380 SET foo bar        # -> OK
redis-cli -p 6380 GET foo            # -> "bar"
redis-cli -p 6380 GET nope           # -> (nil)
redis-cli -p 6380 DEL foo            # -> (integer) 1
redis-cli -p 6380 EXISTS foo         # -> (integer) 0

pytest tests/integration -k "set or get or delete or exists" -v   # verde
```

**Fase 1 hecha** = unit verde + los comandos funcionan con `redis-cli` + integración verde.

## 7. Bonus opcional (si quieres más)

Triviales sobre el `storage` que ya tienes:
- **DBSIZE** → `len(self.storage)`; **FLUSHDB** → `self.storage.flush(); return "OK"`. Test: `test_dbsize_flushdb`.
- **KEYS pattern** → `fnmatch` sobre `self.storage.keys()` (glob). Test: `test_keys_pattern`. (Un poco más: parsear el patrón.)

## 8. Cuando termines
- Post-mortem en tu bitácora: ¿algún edge case (WRONGTYPE, contar duplicados en EXISTS)?
- Cierra F1-1…F1-4 en Huly → **Fase 2 (EXPIRE/TTL/PERSIST)**, donde aparece la expiración lazy + active.

## Conexiones
- `docs/fase-0-walking-skeleton.md` — la base que esto reutiliza
- [[disenar-funciones-y-programas]] — contratos + edge cases
- `PHASES.md` — el mapa · `HULY_fase-1-issues.md` — los Issues
