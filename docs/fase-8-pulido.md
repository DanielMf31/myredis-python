# Fase 8 — Pulido: DBSIZE / KEYS / TYPE / INFO / FLUSHDB + config + benchmark

> **Meta:** rematar el clon con los comandos "de servidor/keyspace" que faltan, **centralizar la configuración** en un `Config`, y **medir** contra Redis real. Con esto cierras un Redis-compatible completo, listo para portfolio.
>
> **Prerrequisito:** F1–F7. **Archivo nuevo:** `config.py` (+ `benchmarks/`). Tocas `storage.py`, `commands.py`, `server.py` y `__main__.py`.
>
> **Cómo usarlo:** contrato + edge cases + código comentado + los tests que debe pasar. Tecléalo tú en `server/myredis/`; intenta cada pieza antes de mirar mi versión. No copies-pegues.

---

## 1. Conceptos (qué entender antes de teclear)

### 1.1 Comandos "de servidor" vs "de datos"
Hasta ahora todos tus comandos leían/escribían **datos** (SET, LPUSH…). Ahora añades comandos que hablan **del server**: cuántas claves hay (`DBSIZE`), cuáles casan un patrón (`KEYS`), de qué tipo es una clave (`TYPE`), estadísticas (`INFO`), vaciar (`FLUSHDB`). Son los que usa `redis-cli` para "curiosear" y los que muchas herramientas esperan.

### 1.2 Glob, no regex
`KEYS user:*` usa **globbing** (`*`, `?`, `[abc]`), no expresiones regulares. En Python lo tienes gratis con **`fnmatch`**.

### 1.3 Configuración centralizada
Vienes leyendo env vars sueltas (`MYREDIS_HOST`, `MYREDIS_PORT`, `MYREDIS_DBFILENAME`, `MYREDIS_MAXMEMORY`) desde distintos sitios. Un **`dataclass Config`** las agrupa en un solo objeto: `__main__` construye `Config.from_env()` y `RedisServer` recibe **un** `config` en vez de 4 parámetros sueltos. Menos hilos que pasar, un único sitio de verdad.

### 1.4 Medir es parte de la ingeniería
Un benchmark honesto (tu server vs Redis real) te dice el **orden de magnitud** de tu overhead. Que seas ~10–20× más lento es esperado y correcto (Redis es C con allocator propio); el valor está en **la misma arquitectura** y en que **mides** en vez de suponer.

---

## 2. `storage.py` — keys / flush / type_of (Issue F8-1)

**Contrato:** `keys()` → lista de claves; `flush()` → vacía todo (datos, expiraciones, contador); `type_of(key)` → `"string"`/`"list"`/`"hash"`/`"none"`.

```python
from collections import deque

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
```

(`dbsize()`/`__len__` ya los añadiste en la Fase 7.)

---

## 3. `commands.py` — los comandos de servidor (Issue F8-1)

**Contratos:**
- `DBSIZE` → `int` (nº de claves). 0 args.
- `FLUSHDB` / `FLUSHALL` → `"OK"`. Vacían el almacén.
- `KEYS pattern` → array de claves que casan el glob. 1 arg.
- `TYPE key` → simple string `"string"`/`"list"`/`"hash"`/`"none"`. 1 arg.
- `ECHO msg` → devuelve `msg` (bulk). 1 arg.
- `INFO [section]` → bulk string con estadísticas (redis-py lo parsea a dict).
- `COMMAND` → respuesta trivial (array vacío) para que `redis-cli` no proteste al conectar.

**Edge cases:** `KEYS` sobre patrón sin match → `[]`; `TYPE` de clave inexistente → `"none"`; `FLUSHDB` deja `DBSIZE` en 0.

```python
import fnmatch

# --- registrar en _register_all ---
self.register("DBSIZE", self.cmd_dbsize)
self.register("FLUSHDB", self.cmd_flushdb)
self.register("FLUSHALL", self.cmd_flushall)
self.register("KEYS", self.cmd_keys)
self.register("TYPE", self.cmd_type)
self.register("ECHO", self.cmd_echo)
self.register("INFO", self.cmd_info)
self.register("COMMAND", self.cmd_command)

# --- handlers ---
async def cmd_dbsize(self, args: list) -> Any:
    self._check_argc(args, 0, "dbsize")
    return self.storage.dbsize()

async def cmd_flushdb(self, args: list) -> Any:
    self.storage.flush()
    return "OK"

async def cmd_flushall(self, args: list) -> Any:
    self.storage.flush()
    return "OK"

async def cmd_keys(self, args: list) -> Any:
    self._check_argc(args, 1, "keys")
    pat = _to_bytes(args[0])
    return [k for k in self.storage.keys() if fnmatch.fnmatchcase(k, pat)]

async def cmd_type(self, args: list) -> Any:
    self._check_argc(args, 1, "type")
    key = _to_bytes(args[0])
    self.expiration.check_and_expire(key)         # una clave caducada es "none"
    return self.storage.type_of(key)              # simple string

async def cmd_echo(self, args: list) -> Any:
    self._check_argc(args, 1, "echo")
    return _to_bytes(args[0])

async def cmd_info(self, args: list) -> Any:
    lines = [
        "# Server", "redis_version:myredis-0.8", "",
        "# Memory", f"used_memory:{self.storage.memory_usage()}", "",
        "# Keyspace", f"db0:keys={self.storage.dbsize()},expires=0", "",
        "# Replication", "role:master",
    ]
    return "\r\n".join(lines).encode()            # bulk string; redis-py .info() lo parsea

async def cmd_command(self, args: list) -> Any:
    return []                                     # trivial: array vacío
```

> `FLUSHDB`/`FLUSHALL` deben estar en el `WRITE_COMMANDS` de la Fase 7 (mutan el almacén). `fnmatch.fnmatchcase` funciona con `bytes` en Python 3.12; si te diera guerra, decodifica clave y patrón a `str`, casa, y devuelve las claves originales en bytes.

---

## 4. `config.py` — centralizar los ajustes (NUEVO, Issue F8-2)

**Contrato:** `Config.from_env()` lee todas las `MYREDIS_*` y devuelve un objeto con valores por defecto sensatos.

```python
"""Configuración del server, leída de variables de entorno MYREDIS_*. Fase 8."""
import os
from dataclasses import dataclass

from myredis.eviction import parse_memory


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 6380
    maxmemory: int = 0                    # bytes; 0 = sin límite
    dbfilename: str = "dump.rdb"
    snapshot_interval: int = 60           # segundos entre snapshots automáticos

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            host=os.environ.get("MYREDIS_HOST", "0.0.0.0"),
            port=int(os.environ.get("MYREDIS_PORT", "6380")),
            maxmemory=parse_memory(os.environ.get("MYREDIS_MAXMEMORY", "0")),
            dbfilename=os.environ.get("MYREDIS_DBFILENAME", "dump.rdb"),
            snapshot_interval=int(os.environ.get("MYREDIS_SNAPSHOT_INTERVAL", "60")),
        )
```

Y `RedisServer` pasa a recibir **un** `Config` (refactor de la firma):

```python
from myredis.config import Config

class RedisServer:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.storage = Storage()
        self.persistence = Persistence(self.storage, path=config.dbfilename)
        self.expiration = ExpirationManager(self.storage)
        self.eviction = EvictionManager(self.storage, config.maxmemory)
        self.commands = CommandRegistry(self.storage, self.expiration,
                                        self.persistence, self.eviction)
        self._server = None
        self._tasks = set()

    async def start(self) -> None:
        self.persistence.load()
        self._server = await asyncio.start_server(
            self._handle_client, self.config.host, self.config.port)   # ← config
        # ... igual que F6, pero _snapshot_loop usa self.config.snapshot_interval ...
```

Y `__main__.py` se simplifica:

```python
import asyncio
from myredis.server import RedisServer
from myredis.config import Config

async def main() -> None:
    await RedisServer(Config.from_env()).start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nmyredis apagado")
```

---

## 5. `benchmarks/compare_with_real_redis.py` — medir vs Redis real

**Contrato:** conecta a tu server (6380) y a un Redis real (6379), mide ops/s de SET/GET/LPUSH en cada uno, imprime el ratio.

```python
"""Benchmark: myredis (6380) vs Redis real (6379). Requiere ambos corriendo."""
import time
import redis


def bench(client, op, n=20000) -> float:
    op(client, 0)                                  # warm-up
    start = time.perf_counter()
    for i in range(n):
        op(client, i)
    return n / (time.perf_counter() - start)       # ops/s


OPS = {
    "SET":   lambda c, i: c.set(f"k{i}", "v"),
    "GET":   lambda c, i: c.get(f"k{i % 1000}"),
    "LPUSH": lambda c, i: c.lpush("mylist", i),
}


def main() -> None:
    mine = redis.Redis(port=6380)
    real = redis.Redis(port=6379)
    print(f"{'op':6} {'myredis':>12} {'redis':>12} {'ratio':>8}")
    for name, op in OPS.items():
        a = bench(mine, op)
        b = bench(real, op)
        print(f"{name:6} {a:>12.0f} {b:>12.0f} {b / a:>7.1f}x")


if __name__ == "__main__":
    main()
```

**Resultado esperado:** ~10–20× más lento que Redis real. Documenta el número en el README — es un dato honesto y demuestra que **mides**, no supones.

---

## 6. Tests

**Unit** — `server/tests/unit/test_tooling.py` (Storage) y `server/tests/unit/test_config.py`:

```python
# test_tooling.py
from myredis.storage import Storage
from collections import deque

def test_keys_y_flush():
    s = Storage(); s.set(b"a", b"1"); s.set(b"b", b"2")
    assert set(s.keys()) == {b"a", b"b"}
    s.flush()
    assert s.keys() == [] and s.dbsize() == 0

def test_type_of():
    s = Storage()
    s.set(b"s", b"v")
    s.set(b"l", deque([b"a"]))
    s.set(b"h", {b"f": b"v"})
    assert s.type_of(b"s") == "string"
    assert s.type_of(b"l") == "list"
    assert s.type_of(b"h") == "hash"
    assert s.type_of(b"nope") == "none"
```

```python
# test_config.py
from myredis.config import Config

def test_from_env(monkeypatch):
    monkeypatch.setenv("MYREDIS_PORT", "7000")
    monkeypatch.setenv("MYREDIS_MAXMEMORY", "5kb")
    cfg = Config.from_env()
    assert cfg.port == 7000
    assert cfg.maxmemory == 5120

def test_defaults(monkeypatch):
    for v in ("MYREDIS_HOST", "MYREDIS_PORT", "MYREDIS_MAXMEMORY", "MYREDIS_DBFILENAME"):
        monkeypatch.delenv(v, raising=False)
    cfg = Config.from_env()
    assert cfg.port == 6380 and cfg.maxmemory == 0
```

**Integración** — `server/tests/integration/test_tooling.py`:

```python
def _norm(t):
    return t if isinstance(t, bytes) else t.encode()

def test_dbsize_flushdb(myredis_server):
    with myredis_server() as c:
        c.set("a", "1"); c.set("b", "2")
        assert c.dbsize() == 2
        c.flushdb()
        assert c.dbsize() == 0

def test_keys_pattern(myredis_server):
    with myredis_server() as c:
        c.set("user:1", "a"); c.set("user:2", "b"); c.set("post:1", "c")
        assert set(c.keys("user:*")) == {b"user:1", b"user:2"}
        assert c.keys("nada:*") == []

def test_type(myredis_server):
    with myredis_server() as c:
        c.set("s", "v"); c.rpush("l", "a"); c.hset("h", mapping={"f": "v"})
        assert _norm(c.execute_command("TYPE", "s")) == b"string"
        assert _norm(c.execute_command("TYPE", "l")) == b"list"
        assert _norm(c.execute_command("TYPE", "h")) == b"hash"
        assert _norm(c.execute_command("TYPE", "nope")) == b"none"

def test_info(myredis_server):
    with myredis_server() as c:
        raw = c.execute_command("INFO")
        assert b"role:master" in raw
        assert b"redis_version" in raw
```

---

## 7. Verificación de la Fase 8

```bash
cd server && source ../.venv/bin/activate

pytest tests/unit/test_tooling.py tests/unit/test_config.py -v
pytest tests/integration/test_tooling.py -v

python -m myredis                                   # con el nuevo Config
redis-cli -p 6380 SET user:1 ana                   # -> OK
redis-cli -p 6380 DBSIZE                           # -> (integer) 1
redis-cli -p 6380 KEYS 'user:*'                    # -> 1) "user:1"
redis-cli -p 6380 TYPE user:1                      # -> string
redis-cli -p 6380 INFO | head                      # -> # Server ... role:master
redis-cli -p 6380 FLUSHDB                          # -> OK

# benchmark (arranca también un Redis real en 6379):
python benchmarks/compare_with_real_redis.py
```

**Fase 8 hecha** = unit + integración de tooling verdes + `redis-cli INFO`/`DBSIZE`/`KEYS`/`TYPE` funcionan + benchmark corre y anotas el ratio en el README.

## 8. Cuando termines
- Con F0–F8 tienes un **Redis-compatible completo**. Para el repo: README con demo + comandos + ratio del benchmark; **ADRs** (pickle vs AOF, LRU vs LFU, asyncio vs threading); un **vídeo-walkthrough** (`wf-recorder` en tu Wayland).
- Cierra F8-1…F8-3 en Huly → **Fase 9 (Replicación)**: opcional, tu entrada real a sistemas distribuidos.

## El edge case para tu bitácora
`Config.from_env()` es un patrón que verás en todo backend serio: **la configuración entra por los bordes** (env/flags) y el núcleo recibe un objeto ya validado. Nunca leas `os.environ` en medio de la lógica — céntralo.

## Conexiones
- `docs/fase-7-eviction.md` (de donde sale `dbsize`/`memory_usage`) · `PHASES.md` · `issues/fase-8.md` · [[chat-claude-2026-05-11-booking-clone-portfolio-leverage-4-dimensiones]] (estrategia portfolio)
