---
title: "BYOX Redis (práctica) — Hoja de fases"
date: 2026-07-01
tags: [programacion/roadmap, build-things, build-things/byox]
type: doc
status: vivo
source: claude-code
aliases: [fases redis, byox redis phases, roadmap redis practica]
---

# BYOX Redis (práctica) — Hoja de fases

> Reconstrucción **desde cero en Python** de un servidor Redis-compatible. Se construye **por fases incrementales**: cada fase deja un programa que **funciona y se prueba** (walking skeleton que crece). Nunca construimos horizontal (todo el parser perfecto antes de tener nada corriendo); siempre vertical (algo vivo, creciendo).

## Objetivo global

Un server que habla **RESP2** y con el que el **`redis-cli` oficial** funciona sin saber que es custom. Solo librería estándar (asyncio + `dict`/`deque`/`OrderedDict`). Cada pieza: **diseño (contrato + edge cases) → teclear → test con `redis-cli`/`redis-py` real**.

## Regla de trabajo

- **1 fase = varios Issues de Huly.** 1 issue "In Progress" a la vez (límite de WIP).
- **Diseña antes de teclear** ([[disenar-funciones-y-programas]]): contrato + edge cases + los tests que debe pasar.
- **Mira el modelo `../06_build_your_own_redis/` solo si atascas**; entiende → cierra → teclea de tu cabeza.
- **Post-mortem** de cada fase en tu bitácora: qué edge case se te escapó.

---

## FASE 0 — Walking skeleton (PING) ⏳ ← EMPIEZA AQUÍ

**Meta:** el esqueleto mínimo de punta a punta — servidor TCP + RESP mínimo + `PING → PONG`, probado con `redis-cli` real. Demuestra **toda la tubería** (`red → feed/parse → dispatch → cmd_ping → encode → write`) con una sola pieza.

**Piezas:** `protocol.py` (encode + `RESPParser`) · `server.py` (recortado: `start`/`serve_forever`/`_handle_client`/`_dispatch`) · `commands.py` (registry + `cmd_ping`) · `__main__.py`. **NO** hacen falta `storage`/`config`/`expiration`/`persistence`/`eviction`.

**Doc:** `docs/fase-0-walking-skeleton.md` · **Issues:** `docs/issues/fase-0.md` (F0-1…F0-6).

**Hecho cuando:** `pytest tests/unit/test_protocol.py` verde + `redis-cli -p 6380 PING` → `PONG` + `pytest tests/integration/ -k ping` verde.

---

## FASE 1 — Strings: SET / GET / DEL / EXISTS ⏳

**Meta:** que el server **guarde y devuelva datos**. Añades el almacén y cuatro comandos; reutilizas `protocol.py` y `server.py` de la F0 (crecer = colgar comandos del registry).

**Piezas:** `storage.py` (nuevo: KV `get`/`set`/`delete`/`exists` sobre `OrderedDict`) · `commands.py` (+4 handlers + helpers `_to_bytes`/`_check_argc`, el registry ahora recibe el `storage`) · `server.py` (2 líneas: crear `Storage` y pasarlo). **Bonus:** DBSIZE/FLUSHDB/KEYS.

**Doc:** `docs/fase-1-strings.md` · **Issues:** `docs/issues/fase-1.md` (F1-1…F1-4).

**Hecho cuando:** `pytest tests/unit` verde + `redis-cli SET/GET/DEL/EXISTS` funcionan + `pytest tests/integration -k "set or get or delete or exists"` verde.

---

## Índice de fases siguientes (epics — se detallan al llegar)

| Fase | Epic | Añade | Estado |
|---|---|---|---|
| **F0** | Walking skeleton (PING) | TCP + RESP + dispatch | ⏳ **actual** |
| F1 | Strings: SET/GET/DEL/EXISTS | `storage.py` + 4 comandos | ⏳ **detallada** (`docs/fase-1-strings.md`) |
| F2 | Expiración | `EXPIRE`/`TTL`/`PERSIST`, `SET ... EX` (lazy + active sweep) | ⏳ (`docs/fase-2-expiracion.md`) |
| F3 | Contadores | `INCR`/`DECR`/`INCRBY`/`DECRBY` (+ error si no-entero) | ⏳ (`docs/fase-3-contadores.md`) |
| F4 | Listas | `LPUSH`/`RPUSH`/`LPOP`/`RPOP`/`LLEN`/`LRANGE` (`deque`) | ⏳ (`docs/fase-4-listas.md`) |
| F5 | Hashes | `HSET`/`HGET`/`HDEL`/`HKEYS`/`HGETALL` (+ WRONGTYPE) | ⏳ (`docs/fase-5-hashes.md`) |
| F6 | Persistencia | RDB snapshot (`SAVE`/`BGSAVE`), escritura atómica temp+rename | ⏳ (`docs/fase-6-persistencia.md`) |
| F7 | Eviction | LRU con `maxmemory` (`OrderedDict.popitem`) | ⏳ (`docs/fase-7-eviction.md`) |
| F8 | Pulido | `INFO`/`DBSIZE`/`FLUSHDB`/`KEYS`, benchmarks vs Redis real | ⏳ (`docs/fase-8-pulido.md`) |
| **F9** | **Replicación** (opcional) | master-slave → **primer sistema distribuido real** | ⏳ (`docs/fase-9-replicacion.md`, diseño) |

> **F9 es la joya para ti:** convierte esto de un cache de un nodo en un **problema de sistemas distribuidos** (el máster sigue al réplica, log de replicación, qué pasa si el máster cae) — el campo que dijiste que te fascina.

## Fuera de alcance (deliberado)

❌ Cluster/sharding · Pub/Sub · MULTI/EXEC · Lua · Streams · Sorted sets · AOF · RESP3 · TLS/AUTH · rendimiento nivel-C. (Justificado como en el ADR-0006 del modelo: el punto es **entender los internals**, no reimplementar Redis entero.)

## Conexiones
- [[00_README]] · [[MOC_Build_Things]] · [[disenar-funciones-y-programas]]
- Modelo: `../06_build_your_own_redis/` (README + ARCHITECTURE + docs + ADRs)
