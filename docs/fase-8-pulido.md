# Fase 8 — Pulido: INFO / DBSIZE / FLUSHDB / KEYS + config + benchmark

> **Meta:** rematar el clon con los comandos "de servidor" que faltan, centralizar la configuración, y **medir** contra Redis real. Aquí cierras el proyecto y lo dejas listo para portfolio.
>
> **Prerrequisito:** F1–F7. Tocas `commands.py`, creas `config.py` y un `benchmarks/`.

## 1. Comandos de servidor/keyspace

**Contratos:**
- `DBSIZE` → nº de claves. `len(self.storage)`.
- `FLUSHDB` → borra todo, "OK".
- `KEYS pattern` → claves que casan el glob (`*`, `?`). Usa `fnmatch`.
- `EXISTS` (ya lo tienes de F1), `ECHO msg`, `PING` (F0), `COMMAND` (devuelve algo trivial para que `redis-cli` no se queje).
- `INFO` → un bloque de texto con estadísticas (versión, nº claves, memoria...). redis-py lo parsea.

```python
import fnmatch

async def cmd_dbsize(self, args):
    return len(self.storage)

async def cmd_flushdb(self, args):
    self.storage.flush()
    return "OK"

async def cmd_keys(self, args):
    self._check_argc(args, 1, "keys")
    pat = _to_bytes(args[0])
    return [k for k in self.storage.keys() if fnmatch.fnmatchcase(k, pat)]

async def cmd_echo(self, args):
    self._check_argc(args, 1, "echo")
    return _to_bytes(args[0])

async def cmd_info(self, args):
    lines = [
        "# Server", "redis_version:myredis-0.8", "",
        "# Keyspace", f"db0:keys={len(self.storage)}",
    ]
    return "\r\n".join(lines).encode()      # bulk string
```
Regístralos todos. Con esto llegas a ~30 comandos, como el modelo.

> `fnmatch.fnmatchcase` con bytes: en Python 3.12 funciona con bytes; si te da problemas, decodifica clave y patrón a str, casa, y devuelve las claves originales (bytes).

## 2. `config.py` — centralizar los ajustes
Hasta ahora leías env vars sueltas. Agrúpalas en un dataclass:
```python
import os
from dataclasses import dataclass

@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 6380
    maxmemory: int = 0
    dbfilename: str = "dump.rdb"
    snapshot_interval: int = 60

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
`__main__.py` pasa a hacer `RedisServer(Config.from_env())`.

## 3. `benchmarks/compare_with_real_redis.py`
Mide tu server vs Redis real (arranca ambos con docker-compose o a mano):
```python
import time, redis

def bench(client, op, n=10000):
    start = time.time()
    for i in range(n):
        op(client, i)
    return n / (time.time() - start)

# conecta a tu server (6380) y a un Redis real (6379), corre SET/GET/LPUSH...
# imprime ops/s de cada uno y el ratio
```
**Resultado esperado:** tu server ~10-20× más lento que Redis real. **Y está bien** — Redis es C con allocator propio; el punto es que la **arquitectura es la misma**. Documenta el número en el README (es un dato honesto y muestra que mides).

## 4. Verificación
```bash
pytest tests/ -v
redis-cli -p 6380 DBSIZE
redis-cli -p 6380 KEYS 'user:*'
redis-cli -p 6380 INFO
python benchmarks/compare_with_real_redis.py
```

## 5. Cierre para portfolio
Con F0–F8 tienes un **Redis-compatible completo**. Para el repo:
- **README** con el demo (`redis-cli` oficial habla con tu server), los comandos, el benchmark, y "cómo probarlo".
- Considera **ADRs** (decisiones: pickle vs AOF, LRU vs LFU, asyncio vs threading) — como el modelo.
- Un **vídeo-walkthrough** (recuerda: `wf-recorder` en tu Wayland).

## Siguiente
F8 cierra el clon básico. **Fase 9 (Replicación)** es opcional y es tu entrada a **sistemas distribuidos** — merece su propia sesión.

## Conexiones
- `PHASES.md` · `HULY_fase-8-issues.md` · [[chat-claude-2026-05-11-booking-clone-portfolio-leverage-4-dimensiones]] (estrategia portfolio)
