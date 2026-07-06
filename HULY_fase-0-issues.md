# Issues de Huly — Fase 0 (Walking skeleton)

> **Cómo usarlo:** la línea **Título** va al campo Título de Huly; lo de debajo (Contexto → Criterio PASS) va al campo Descripción. Labels sugeridos: `byox-redis`, `fase-0`, `test`. Regla: 1 solo issue "In Progress" a la vez, en orden F0-1 → F0-6. Doc de referencia: `docs/fase-0-walking-skeleton.md`.
>
> **Tip para que pegue limpio:** copia desde el **modo código/source** de Obsidian (botón editar, o `Ctrl+E`). Así el markdown viaja crudo y Huly lo renderiza bien. Aun así, abajo va todo con viñetas normales para que no se pierda nada.

---

### F0-1 · Setup

**Título:** F0-1 · Setup: entorno + estructura del proyecto

**Contexto:** preparar la práctica para poder teclear y testear la Fase 0.

**Tareas:**
- Crear venv e instalar deps: `python3 -m venv .venv && source .venv/bin/activate && pip install -r server/requirements.txt`
- Confirmar el layout de `server/myredis/` (init, main, protocol, server, commands) y `server/tests/` (conftest, unit, integration)
- `pytest --collect-only` corre sin errores de import

**Criterio PASS:**
- `pytest --collect-only` no peta (con el venv activado)

---

### F0-2 · Encoder RESP2

**Título:** F0-2 · protocol.py: encoder RESP2 (valor Python a bytes)

**Contexto:** `encode(value)` que devuelve bytes para los 5 tipos RESP2. Es la mitad "escritura" del protocolo.

**Contrato:**
- `None` a `$-1` CRLF (null bulk)
- `bool` a `:1` / `:0` (comprobar bool ANTES que int)
- `int` a `:N` · `str` a `+S` (simple) · `bytes` a `$N` + datos (bulk)
- `list` / `tuple` a `*N` + elementos (recursivo) · `Exception` a `-ERR msg`
- tipo no soportado a `TypeError`

**Cobertura / edge cases:**
- simple string, integer (y negativo), bulk, null, array, array vacío
- array anidado/mixto `[1, b"x", None]`
- error, bool True/False

**Criterio PASS:**
- Los tests de encoder de `tests/unit/test_protocol.py` en verde

---

### F0-3 · Parser incremental RESP2

**Título:** F0-3 · protocol.py: parser incremental RESP2 (bytes a valor)

**Contexto:** `RESPParser` con `feed(data)` + `parse()`. La parte difícil e interesante: framing sobre TCP (un read no es un mensaje).

**Contrato:**
- `feed(data)`: acumula en un buffer
- `parse()`: devuelve UN mensaje completo (y lo consume), o `None` si falta data
- formato inválido a `ProtocolError`
- soporta los 5 tipos + null bulk

**Cobertura / edge cases (los que importan):**
- parse de los 5 tipos + comando real (array de bulk strings)
- partial data: alimentar medio mensaje da `None`; al completar da el valor
- varios mensajes en el buffer: `+PONG` `+OK` da "PONG", "OK", None
- roundtrip: encode a feed a parse == original

**Criterio PASS:**
- Todos los tests de `tests/unit/test_protocol.py` en verde (encoder + parser)

---

### F0-4 · Servidor TCP asyncio

**Título:** F0-4 · server.py: servidor TCP asyncio (esqueleto)

**Contexto:** `RedisServer` con `start` / `serve_forever` / `_handle_client`. Un handler por conexión, event loop single-thread.

**Contrato de `_handle_client`:**
- bucle: `data = await reader.read(4096)`; si `data` está vacío, salir
- `parser.feed(data)` y drenar TODOS los mensajes: mientras `parse()` no sea None, dispatch + write + drain
- `ProtocolError`: responder error, NO matar la conexión
- al salir: cerrar el writer y esperar el cierre

**Cobertura / edge cases:**
- desconexión del cliente (read vacío) no cuelga el server
- buffer incompleto: espera más read (no responde a medias)
- varios comandos pipelined en un read: se responden todos
- `await writer.drain()` tras cada write (back-pressure)

**Criterio PASS:**
- El server arranca con `python -m myredis` y acepta conexiones (los comandos los añade F0-5)

---

### F0-5 · Registry + PING

**Título:** F0-5 · commands.py: registry + PING (dispatch)

**Contexto:** el registro de comandos y el primer handler. El dispatch traduce el array a (nombre, args).

**Contrato:**
- `CommandRegistry`: `register(name, handler)` guarda en mayúsculas; `execute(name, args)` busca el handler; si no existe, DEVUELVE un `Exception` (no lanza)
- `cmd_ping(args)`: sin args da "PONG"; con arg da `args[0]` (eco)
- el dispatch: nombre = primer elemento a mayúsculas, args = el resto

**Cobertura / edge cases:**
- PING sin args da PONG
- comando desconocido da error RESP (sin crash de la conexión)
- case-insensitive (ping / PING)

**Criterio PASS:**
- `redis-cli -p 6380 PING` responde `PONG`

---

### F0-6 · Entry point + verificación E2E

**Título:** F0-6 · Entry point + verificación end-to-end (compat cliente oficial)

**Contexto:** el arranque (`python -m myredis`) + el sello de la Fase 0: el cliente `redis-py` OFICIAL habla con tu server.

**Tareas:**
- El módulo de arranque lee `MYREDIS_HOST` / `MYREDIS_PORT` de env (default `0.0.0.0:6380`) y arranca `RedisServer`
- `conftest.py`: fixture que lanza el server como subproceso en un puerto libre y da un cliente `redis.Redis`
- `test_via_redis_py.py`: `test_ping` comprueba que `client.ping()` es True

**Criterio PASS (Fase 0 COMPLETA):**
- `pytest tests/unit/test_protocol.py -v` en verde
- `redis-cli -p 6380 PING` responde `PONG`
- `pytest tests/integration/ -k ping -v` en verde

---

## Índice de epics — fases siguientes

Créalos en Huly como issues "épica" de una línea (o milestones), en `Backlog`:

- EPIC F1 · Strings: SET/GET/DEL (+ storage.py con OrderedDict)
- EPIC F2 · Expiración: EXPIRE/TTL/PERSIST, SET EX (lazy + active sweep)
- EPIC F3 · Contadores: INCR/DECR/INCRBY/DECRBY (+ error si no-entero)
- EPIC F4 · Listas: LPUSH/RPUSH/LPOP/RPOP/LLEN/LRANGE (deque)
- EPIC F5 · Hashes: HSET/HGET/HDEL/HKEYS/HGETALL (+ WRONGTYPE)
- EPIC F6 · Persistencia RDB: SAVE/BGSAVE, snapshot atómico (temp+rename)
- EPIC F7 · Eviction LRU: maxmemory (OrderedDict.popitem)
- EPIC F8 · Pulido: INFO/DBSIZE/FLUSHDB/KEYS + benchmarks vs Redis real
- EPIC F9 · (opcional) Replicación master-slave a sistemas distribuidos
