# myredis

**Un almacén de datos en memoria compatible con Redis, hecho desde cero en Python.**

`myredis` habla el protocolo **RESP2** real, así que los **clientes oficiales `redis-cli` y `redis-py` hablan con él sin saber que no es Redis**. Está escrito usando **solo la librería estándar de Python** (`asyncio`) — cero dependencias externas — como una inmersión profunda en cómo funciona de verdad una base de datos en memoria por dentro: el protocolo de red, el event loop, la caducidad de claves, el volcado a disco, la gestión de memoria y la replicación.

Español · [English](README.md)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Protocolo](https://img.shields.io/badge/protocolo-RESP2-DC382D?logo=redis&logoColor=white)
![Dependencias](https://img.shields.io/badge/dependencias-solo%20librer%C3%ADa%20est%C3%A1ndar-2ea44f)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)
![Licencia](https://img.shields.io/badge/licencia-MIT-blue)

---

## Demo

[![demo de myredis](https://img.youtube.com/vi/VIDEO_ID/maxresdefault.jpg)](https://youtu.be/VIDEO_ID)

*Un recorrido de ~5 minutos: manejando `myredis` con el `redis-cli` oficial, viendo caducar claves, la persistencia sobreviviendo a un reinicio, y un tour por la arquitectura.*

---

## Puntos clave

- **Compatible de serie** con los clientes oficiales de Redis (`redis-cli`, `redis-py`) — mismo protocolo RESP2.
- **Cero dependencias** — Python puro, solo librería estándar (`asyncio`, `dict`, `deque`, `OrderedDict`).
- **Parser RESP incremental** que maneja correctamente la fragmentación de TCP y el pipelining de comandos.
- **Caducidad de claves lazy + activa** — las dos estrategias del Redis real.
- **Persistencia tipo RDB** con snapshots atómicos que sobreviven a los reinicios.
- **Eviction LRU** bajo un `maxmemory` configurable.
- **Replicación máster–réplica** — un caché de un nodo convertido en un pequeño sistema distribuido.
- **Verificado contra el cliente real**: si `redis-py` puede manejarlo, el protocolo es correcto.
- Construido **incrementalmente en 9 rebanadas verticales** — cada fase entrega un programa que funciona y se prueba de punta a punta.

---

## Mapa de funcionalidades

`myredis` se construyó en nueve fases incrementales. Cada fase añade una **capacidad de cara al usuario** y mantiene todo ejecutable y probado — nunca "el parser perfecto antes de tener nada corriendo", siempre un programa vivo que crece.

<picture><source media="(prefers-color-scheme: dark)" srcset="diagrams/phases-dark.svg"><img alt="Fases de construcción" src="diagrams/phases.svg"></picture>

| Fase | Capacidad | Comandos |
|:---:|---|---|
| **0** | Servidor TCP RESP2 — la tubería completa | `PING` |
| **1** | Almacén clave–valor | `SET` · `GET` · `DEL` · `EXISTS` |
| **2** | Caducidad de claves (lazy al acceder + barrido activo) | `EXPIRE` · `TTL` · `PERSIST` · `SET … EX/PX` |
| **3** | Contadores atómicos | `INCR` · `DECR` · `INCRBY` · `DECRBY` |
| **4** | Listas | `LPUSH` · `RPUSH` · `LPOP` · `RPOP` · `LLEN` · `LRANGE` |
| **5** | Hashes | `HSET` · `HGET` · `HDEL` · `HKEYS` · `HGETALL` |
| **6** | Persistencia — snapshot RDB atómico | `SAVE` · `BGSAVE` |
| **7** | Gestión de memoria — eviction LRU con `maxmemory` | — |
| **8** | Introspección y herramientas | `INFO` · `DBSIZE` · `FLUSHDB` · `KEYS` |
| **9** | Replicación máster–réplica | `REPLICAOF` |

> Cada fase está documentada en [`docs/`](docs/) con su razonamiento de diseño, casos límite y pasos de verificación.

---

## Arquitectura

Un event loop `asyncio` de un solo hilo atiende cada conexión.

<picture><source media="(prefers-color-scheme: dark)" srcset="diagrams/architecture-dark.svg"><img alt="Arquitectura" src="diagrams/architecture.svg"></picture>

| Módulo | Responsabilidad |
|---|---|
| `protocol.py` | **Encoder** RESP2 (valor Python -> bytes) y **parser incremental** (bytes -> comando). |
| `server.py`   | Servidor TCP `asyncio`: una corrutina por conexión + un bucle de expiración en segundo plano. |
| `commands.py` | **Registro** de comandos y handlers; parsea argumentos y formatea respuestas. |
| `storage.py`  | El almacén en memoria: claves -> valores (`bytes`, `deque`, `dict`) + gestión de TTLs. |
| `expiration.py` | Caducidad lazy (al acceder) y activa (barrido muestreado en segundo plano). |
| `persistence.py` | Snapshot tipo RDB a disco con escritura atómica; recarga al arrancar. |

### Ciclo de vida de un comando

Cada comando sigue el mismo camino, de los bytes RESP crudos a una respuesta RESP:

<picture><source media="(prefers-color-scheme: dark)" srcset="diagrams/command-lifecycle-dark.svg"><img alt="Ciclo de vida de un comando" src="diagrams/command-lifecycle.svg"></picture>

---

## Decisiones de diseño

Lo que lo hace más que un juguete:

- **Parser RESP incremental.** TCP no entrega un mensaje por `read()` — una lectura puede darte medio comando o varios comandos pipelined pegados. El parser bufferiza los bytes y va devolviendo mensajes completos, respondiendo "faltan datos" cuando el buffer es corto, así que es correcto ante fragmentación y pipelining.
- **Atomicidad sin locks.** Como todo el servidor corre en un único event loop `asyncio`, una operación es atómica entre puntos `await` — sin necesidad de mutex. (El mismo diseño en un lenguaje con hilos requeriría bloqueo explícito; este proyecto hace ese trade-off visible.)
- **Expiración lazy + activa.** Las claves caducan *lazy* al tocarlas (corrección) **y** mediante un *barrido activo* que muestrea claves con TTL y libera la memoria que nadie lee — la misma heurística del Redis real.
- **La estructura de datos correcta por tipo.** `deque` para listas (push/pop O(1) en ambos extremos), `OrderedDict` para el eviction LRU (O(1) "mover al final" / "sacar el más viejo").
- **Persistencia a prueba de caídas.** Los snapshots se escriben a un fichero temporal y luego se hace un `os.replace` atómico — una caída a media escritura nunca corrompe el snapshot existente.
- **Testeado contra el cliente *real*.** La suite de integración arranca el servidor y lo maneja con la librería oficial `redis-py`. Si el cliente real queda satisfecho, la implementación de RESP es correcta — no solo "correcta según mis propios tests".

La expiración de dos estrategias es la pieza más delicada — lazy para corrección, activa para liberar memoria:

<picture><source media="(prefers-color-scheme: dark)" srcset="diagrams/expiration-dark.svg"><img alt="Caducidad de claves" src="diagrams/expiration.svg"></picture>

---

## Puesta en marcha

```bash
git clone https://github.com/DanielMf31/myredis-python.git
cd myredis-python

python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt      # solo pytest + redis-py, para los tests

cd server
python -m myredis                            # escuchando en 0.0.0.0:6380
```

Luego, desde otra terminal, háblale con el **CLI oficial de Redis**:

```bash
redis-cli -p 6380 PING            # PONG
redis-cli -p 6380 SET user:1 dani # OK
redis-cli -p 6380 GET user:1      # "dani"
redis-cli -p 6380 SET tmp x EX 5  # caduca en 5s
redis-cli -p 6380 TTL tmp         # (integer) 5
redis-cli -p 6380 RPUSH log a b c # (integer) 3
redis-cli -p 6380 LRANGE log 0 -1 # a b c
redis-cli -p 6380 INCR hits       # (integer) 1
```

---

## Cómo verificar que funciona

**Ejecuta la suite de tests** (unit + integración contra el cliente real `redis-py`):

```bash
cd server && source ../.venv/bin/activate
pytest -v
```

**Háblale desde Python** con el cliente oficial:

```python
import redis
r = redis.Redis(host="127.0.0.1", port=6380)
r.set("framework", "myredis")
print(r.get("framework"))         # b'myredis'
r.rpush("langs", "python", "go")
print(r.lrange("langs", 0, -1))   # [b'python', b'go']
```

**Comprueba que la persistencia sobrevive a un reinicio:**

```bash
redis-cli -p 6380 SET keep me
redis-cli -p 6380 SAVE            # snapshot a disco
# para el servidor (Ctrl-C) y arráncalo de nuevo:
python -m myredis
redis-cli -p 6380 GET keep        # "me"  <- sobrevivió al reinicio
```

---

## Fuera de alcance (deliberado)

Para mantener el foco en los **internals** en vez de reimplementar todo Redis, se excluyen a propósito: cluster / sharding, Pub/Sub, transacciones (`MULTI`/`EXEC`), scripting Lua, Streams, sorted sets, AOF, RESP3 y TLS/AUTH. El objetivo es entender *cómo funciona el núcleo*, no lanzar una base de datos de producción.

---

## Stack técnico

**Python 3.12** · `asyncio` · solo librería estándar (`dict`, `deque`, `OrderedDict`) · **pytest** y el cliente oficial **redis-py** para los tests. Sin frameworks, sin dependencias de runtime externas.

> Los diagramas se escriben en Graphviz (`diagrams/*.dot`) y se renderizan a SVG — ejecuta `make -C diagrams` para regenerarlos.

---

## Autor

**Daniel M.F.** — ingeniero de mecatrónica + software.
[GitHub](https://github.com/DanielMf31) · [LinkedIn](LINKEDIN_URL)

Hecho como estudio práctico de los internals de bases de datos y sistemas. Bajo licencia MIT.
