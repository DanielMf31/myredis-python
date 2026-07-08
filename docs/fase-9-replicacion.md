# Fase 9 — Replicación master-réplica (+ diseño de Raft)

> **Meta:** convertir tu Redis de un nodo en un **sistema distribuido**. Primero construyes **replicación master-réplica** (una réplica sigue al máster en vivo, con código y tests). Luego diseñamos **Raft** —el consenso que resuelve lo que la replicación simple no puede— como capítulo de diseño.
>
> **Prerrequisito:** F1–F8. **Archivo nuevo:** `replication.py`. Tocas `commands.py` y `server.py`.
>
> **Cómo usarlo:** la **Parte A** es código guiado (tecléalo tú, como siempre) + tests. La **Parte B** (Raft) es **diseño**: contratos, máquina de estados y estrategia de tests, sin implementación entera (es casi un proyecto aparte). Es la fase más intrincada: poco código, muchísima materia gris.

---

# PARTE A — Replicación master-réplica

## 1. Conceptos (qué entender antes de teclear)

### 1.1 Lo que no existe en un solo proceso
Hasta F8 todo era un nodo. Con dos aparecen los problemas de **sistemas distribuidos**:
- **Fallo parcial:** el máster cae mientras la réplica sigue viva (o al revés).
- **Consistencia eventual:** la réplica va **por detrás** del máster (replicación asíncrona).
- **Orden:** los cambios deben aplicarse en la réplica **en el mismo orden** que en el máster.

### 1.2 Arquitectura (como Redis, simplificado)
```
   cliente escribe
        │
        ▼
   [ MÁSTER ] ──(1) snapshot inicial (RDB)──▶ [ RÉPLICA ]  (solo-lectura)
        │                                          ▲
        └──(2) stream de comandos de escritura─────┘
```
1. **Full resync:** cuando la réplica se conecta, el máster le manda un **snapshot** de todo el estado (reusas tu RDB de F6: `Storage.snapshot()` + `pickle`).
2. **Propagación:** a partir de ahí, el máster **reenvía cada comando de escritura** a la réplica, que lo **aplica en orden**.
3. La réplica es **solo-lectura**: rechaza escrituras de clientes normales (`READONLY`); solo aplica lo que viene del máster.

### 1.3 El protocolo de replicación (sobre tu RESP)
No inventas un protocolo nuevo: reutilizas RESP.
- La réplica manda el comando `PSYNC` al máster.
- El máster responde con **un bulk string** que contiene el snapshot pickled, y **deja la conexión abierta** como *feed*.
- Por ese feed, el máster va escribiendo cada comando de escritura como un **array RESP de bulk strings** (idéntico a lo que manda un cliente). La réplica los parsea con el mismo `RESPParser` y los aplica con `commands.execute`.

---

## 2. `replication.py` — el gestor (NUEVO, Issue F9-1/F9-2/F9-3)

**Contrato:**
- Lleva el **rol** (`"master"`/`"replica"`) y, si es réplica, la dirección del máster.
- Máster: `add_replica(writer)` manda el snapshot y registra el feed; `propagate(cmd, args)` reenvía una escritura a todas las réplicas.
- `info()` → el bloque `role:...` para `INFO`.

**Edge cases:** una réplica que se cae hay que sacarla del set (si no, `propagate` peta); `propagate` sin réplicas es un no-op.

```python
"""Replicación master-réplica. Fase 9."""
import pickle

from myredis.protocol import encode
from myredis.commands import _to_bytes


class ReplicationManager:
    def __init__(self, storage) -> None:
        self.storage = storage
        self.role = "master"                 # "master" | "replica"
        self.master_addr: tuple[str, int] | None = None
        self.replicas: set = set()           # writers de las réplicas conectadas (lado máster)
        self.offset = 0                      # bytes propagados (para INFO)

    # ---------- lado MÁSTER ----------
    async def add_replica(self, writer) -> None:
        """Manda el snapshot inicial y registra el feed de esta réplica."""
        blob = pickle.dumps(self.storage.snapshot())
        writer.write(encode(blob))           # snapshot como bulk string
        await writer.drain()
        self.replicas.add(writer)

    async def propagate(self, cmd_name: str, args: list) -> None:
        """Reenvía un comando de escritura a todas las réplicas, en orden."""
        if not self.replicas:
            return
        payload = encode([cmd_name.encode()] + [_to_bytes(a) for a in args])
        self.offset += len(payload)
        for w in list(self.replicas):
            try:
                w.write(payload)
                await w.drain()
            except Exception:
                self.replicas.discard(w)     # réplica muerta: fuera del set

    # ---------- INFO ----------
    def info(self) -> str:
        if self.role == "master":
            return (f"role:master\r\nconnected_slaves:{len(self.replicas)}\r\n"
                    f"master_repl_offset:{self.offset}")
        host, port = self.master_addr
        return (f"role:slave\r\nmaster_host:{host}\r\nmaster_port:{port}\r\n"
                f"master_link_status:up")
```

---

## 3. `commands.py` — READONLY + INFO replication

Dos cambios (el registry recibe ahora también `replication`):

```python
# read-only: una réplica rechaza escrituras de clientes normales.
# En execute(), antes de ejecutar un comando de escritura:
if self.replication.role == "replica" and name in WRITE_COMMANDS:
    return Exception("READONLY You can't write against a read only replica.")

# INFO usa el rol real:
async def cmd_info(self, args: list) -> Any:
    lines = ["# Server", "redis_version:myredis-0.9", "",
             "# Replication", self.replication.info()]
    return "\r\n".join(lines).encode()
```

> Ojo: los comandos que vienen **del máster** los aplica la réplica llamando a `commands.execute` directamente, así que ese `execute` NO debe bloquearlos. Truco: cuando el enlace de réplica aplica el stream, temporalmente trata el rol como "master aplicando", o mejor: aplica los comandos del stream **saltándose** el chequeo (llamando a los handlers con un flag). La forma más simple: el enlace de réplica pone `self.replication.role` a un estado interno mientras aplica, o expón un `execute(..., from_master=True)`. Elige y anótalo.

---

## 4. `server.py` — PSYNC, REPLICAOF, propagación y el enlace de réplica

Los cambios de red viven aquí (necesitan los `reader`/`writer`).

```python
# helper de framing: lee un mensaje RESP completo (o None si EOF)
async def _read_message(reader, parser):
    while True:
        msg = parser.parse()
        if msg is not None:
            return msg
        data = await reader.read(4096)
        if not data:
            return None
        parser.feed(data)


class RedisServer:
    # en _handle_client, tras parsear un mensaje, ANTES del dispatch normal:
    #   if cmd == "PSYNC":  ->  esta conexión se convierte en feed de réplica
    async def _handle_psync(self, reader, writer) -> None:
        await self.replication.add_replica(writer)   # snapshot + registrar
        while await reader.read(4096):                # mantener viva la conexión
            pass
        self.replication.replicas.discard(writer)     # la réplica se fue

    # _dispatch (lado máster/cliente): REPLICAOF, read-only y propagación
    async def _dispatch(self, message) -> bytes:
        if not isinstance(message, list) or not message:
            return encode(Exception("ERR protocol error"))
        cmd_name = message[0].decode("utf-8", "replace").upper()
        args = message[1:]

        if cmd_name == "REPLICAOF":
            return await self._handle_replicaof(args)

        result = await self.commands.execute(cmd_name, args)
        # si soy máster y fue una escritura con éxito -> propaga a las réplicas
        if (self.replication.role == "master"
                and cmd_name in WRITE_COMMANDS
                and not isinstance(result, Exception)):
            await self.replication.propagate(cmd_name, args)
        return encode(result)

    async def _handle_replicaof(self, args) -> bytes:
        host = args[0].decode(); port = args[1].decode()
        if host.upper() == "NO" and port.upper() == "ONE":      # REPLICAOF NO ONE
            self.replication.role = "master"
            self.replication.master_addr = None
            return encode("OK")
        self.replication.role = "replica"
        self.replication.master_addr = (host, int(port))
        self._spawn(self._replica_link())                        # conectar al máster
        return encode("OK")

    async def _replica_link(self) -> None:
        """Lado RÉPLICA: conecta al máster, hace full resync, aplica el stream."""
        host, port = self.replication.master_addr
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(encode([b"PSYNC"])); await writer.drain()
        parser = RESPParser()
        blob = await _read_message(reader, parser)               # 1) snapshot (bulk = bytes)
        self.storage.restore(pickle.loads(blob))
        while True:                                              # 2) stream de escrituras
            message = await _read_message(reader, parser)
            if message is None:
                break                                            # máster cayó (F9.4: reconectar)
            cmd = message[0].decode("utf-8", "replace").upper()
            await self.commands.execute(cmd, message[1:], from_master=True)  # aplica, no bloquea
```

> **Sub-fases** (constrúyelo así, no de golpe): **F9.1** PSYNC + snapshot (la réplica arranca con el estado). **F9.2** propagación (sigue al máster en vivo). **F9.3** read-only + `INFO replication`. **F9.4** reconexión: si `_read_message` devuelve `None`, reintenta `open_connection` con backoff y vuelve a resync.

---

## 5. Tests — `server/tests/integration/test_replication.py`

Usan la fábrica `myredis_server` para levantar **dos** servers y apuntar la réplica al máster. Como la replicación es asíncrona, se espera con un pequeño *poll*.

```python
import time
import pytest
import redis


def _wait(fn, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


def test_replica_hace_full_resync_y_sigue_al_master(myredis_server):
    with myredis_server() as master, myredis_server() as replica:
        master.set("antes", "1")                                 # dato previo al sync
        replica.execute_command("REPLICAOF", master.myredis_host, master.myredis_port)
        assert _wait(lambda: replica.get("antes") == b"1")       # full resync
        master.set("despues", "2")                               # propagación en vivo
        assert _wait(lambda: replica.get("despues") == b"2")


def test_replica_es_readonly(myredis_server):
    with myredis_server() as master, myredis_server() as replica:
        replica.execute_command("REPLICAOF", master.myredis_host, master.myredis_port)
        _wait(lambda: b"role:slave" in replica.execute_command("INFO"))
        with pytest.raises(redis.ResponseError):
            replica.set("x", "1")                                # READONLY


def test_info_replication_roles(myredis_server):
    with myredis_server() as master, myredis_server() as replica:
        replica.execute_command("REPLICAOF", master.myredis_host, master.myredis_port)
        assert _wait(lambda: b"role:slave" in replica.execute_command("INFO"))
        assert b"role:master" in master.execute_command("INFO")
```

## 6. Verificación de la Parte A

```bash
cd server && source ../.venv/bin/activate
pytest tests/integration/test_replication.py -v

# a mano (dos terminales):
MYREDIS_PORT=6380 python -m myredis      # máster
MYREDIS_PORT=6381 python -m myredis      # futura réplica
redis-cli -p 6380 SET k hola
redis-cli -p 6381 REPLICAOF 127.0.0.1 6380     # -> OK
redis-cli -p 6381 GET k                        # -> "hola"  (full resync)
redis-cli -p 6380 SET k2 mundo
redis-cli -p 6381 GET k2                        # -> "mundo" (propagación)
redis-cli -p 6381 SET x 1                       # -> (error) READONLY
```

**Parte A hecha** = la réplica hace full resync, sigue al máster en vivo, rechaza escrituras, e `INFO` da los roles.

---

# PARTE B — Diseño de Raft (por qué y cómo el consenso resuelve lo que la replicación no)

> Esto es **diseño**, no implementación guiada. El objetivo es que entiendas Raft lo bastante para diseñarlo sobre myredis (contratos, máquina de estados, tests) y, si algún día lo construyes, sea el mini-proyecto del **[[catalogo-byox-infra]]**.

## B.1 Por qué la replicación de la Parte A no basta
Tu máster es un **punto único de fallo** y un **punto único de verdad**. Si cae:
- Si **no** promocionas a nadie → te quedas sin escrituras (indisponible).
- Si **auto-promocionas** una réplica → y resulta que el máster no estaba muerto sino **particionado** (los dos vivos, sin verse) → tienes **dos másters** aceptando escrituras que **divergen**: **split-brain**. Al sanar la partición, ¿qué escritura gana? No hay respuesta segura.

El problema de fondo: **ponerse de acuerdo, a pesar de fallos, en (a) quién manda y (b) en qué orden se aplican las escrituras.** Eso es **consenso**. Raft es un algoritmo de consenso diseñado para ser *entendible*.

## B.2 La idea central de Raft: un log replicado
En vez de replicar "el estado", Raft replica **un log de comandos** idéntico y **ordenado** en todos los nodos. Si todos aplican **el mismo log en el mismo orden** a la misma máquina de estados (tu `Storage`), todos convergen al mismo estado (**State Machine Safety**). Todo Raft gira en torno a mantener ese log consistente eligiendo **un único líder por término** que lo dicta.

## B.3 Máquina de estados de un nodo
```
            timeout de elección
   ┌─────────┐ ───────────────▶ ┌───────────┐ ── gana mayoría ──▶ ┌────────┐
   │FOLLOWER │                   │ CANDIDATE │                     │ LEADER │
   └─────────┘ ◀─── ve líder ─── └───────────┘ ◀── ve líder de     └────────┘
        ▲            de término                    término ≥        │
        │            ≥ el suyo                                       │
        └───────────────── descubre término mayor ───────────────────┘
```
- **Término (`term`):** un reloj lógico que solo sube. Cada elección abre un término nuevo. Si un nodo ve un `term` mayor que el suyo, se rinde a follower y adopta ese término. Es la regla que evita dos líderes en el mismo término.

## B.4 (1) Elección de líder
- Cada follower tiene un **election timeout aleatorio** (p. ej. 150–300 ms). Si no oye al líder en ese tiempo, sube su `currentTerm`, pasa a **candidate**, **se vota a sí mismo** y manda `RequestVote` a todos.
- Un nodo concede el voto si (a) no ha votado ya en ese término y (b) el log del candidato está **al menos tan al día** como el suyo (restricción de elección — B.6).
- El candidato que reúne **mayoría** (quórum, `⌊N/2⌋+1`) se hace **leader** y manda *heartbeats* (`AppendEntries` vacíos) para mantener a los demás como followers. Los timeouts aleatorios evitan que todos se candidateen a la vez (evita empates perpetuos).

**RPC `RequestVote`:**
```
RequestVote(term, candidateId, lastLogIndex, lastLogTerm) -> (term, voteGranted: bool)
```

## B.5 (2) Replicación de log
- El cliente manda una escritura al **líder**. El líder la añade a su log como `entry = {term, command}` (aún **no aplicada**).
- El líder manda `AppendEntries` con las entradas nuevas. Cada follower las acepta **solo si** su log coincide en la posición previa (`prevLogIndex`/`prevLogTerm` casan) — la **Log Matching Property**: si dos logs coinciden en un índice+término, coinciden en todo lo anterior. Si no casa, el líder retrocede y reenvía hasta reconciliar.
- Cuando una entrada está replicada en **mayoría**, el líder avanza su `commitIndex`: la entrada está **comprometida** y se **aplica a la máquina de estados** (`commands.execute`). El líder comunica `leaderCommit` a los followers para que apliquen hasta ahí también.

**RPC `AppendEntries` (también es el heartbeat, con `entries=[]`):**
```
AppendEntries(term, leaderId, prevLogIndex, prevLogTerm, entries[], leaderCommit) -> (term, success: bool)
```

## B.6 (3) Seguridad (lo que hace a Raft correcto, no solo vivo)
- **Restricción de elección:** un candidato solo gana si su log es **al menos tan completo** como el de la mayoría → una entrada ya comprometida **nunca se pierde** al cambiar de líder.
- **Un líder solo compromete entradas de su propio término** (no "cuenta réplicas" de entradas de términos anteriores para comprometerlas). Esto cierra un caso sutil en el que una entrada replicada en mayoría podría, sin esta regla, ser sobrescrita.
- Juntas dan **State Machine Safety:** si un nodo aplicó una entrada en un índice, ningún otro aplicará una **distinta** en ese índice. Todos ejecutan la misma secuencia de comandos.

## B.7 (4) Cambios de membresía
Añadir/quitar nodos sin parar el clúster se hace con **joint consensus** (una configuración de transición que requiere mayoría en la vieja **y** la nueva a la vez), para no abrir una ventana con dos mayorías disjuntas. (Diséñalo al final; es el extra.)

## B.8 Dónde viviría en myredis (si lo implementaras)
- `raft.py` — `RaftNode`: estado (`FOLLOWER/CANDIDATE/LEADER`), `currentTerm`, `votedFor`, `log[]`, `commitIndex`, `lastApplied`, y los timers (election + heartbeat). Es una **máquina de estados dirigida por eventos** (timeouts + RPCs entrantes).
- `rpc.py` — la forma de los mensajes (`RequestVote`/`AppendEntries` + respuestas) y el transporte. **Reutiliza tu framing** (RESP o length-prefixed JSON como en el mini-Kafka) para mandarlos por socket.
- **La máquina de estados = tu `Storage`.** "Aplicar una entrada comprometida" = `commands.execute(cmd, args)`. Tu clon entero se convierte en el *state machine* replicado por Raft — la Parte A (máster→réplica) se sustituye por: escrituras al **líder**, comprometidas por el **log** y aplicadas por todos.
- La **persistencia** de F6 se reusa para lo que Raft exige guardar **antes de responder** un RPC: `currentTerm`, `votedFor` y el `log[]` (si un nodo reinicia, no puede "olvidar" que votó).

## B.9 Cómo se testea Raft (la parte que la mayoría ignora)
Raft es un algoritmo concurrente y con fallos → los tests normales no bastan. La técnica seria es **simulación determinista**:
- Un **reloj virtual** y una **red en memoria** que puedes **particionar, retrasar, duplicar y perder** mensajes a voluntad, con una **semilla** fija → reproduces el bug exacto.
- **Propiedades a verificar** (property-based): *Election Safety* (≤ 1 líder por término); *Leader Completeness* (una entrada comprometida está en todos los líderes futuros); *State Machine Safety* (todos aplican la misma secuencia); **linealizabilidad** de las escrituras comprometidas.
- **Escenarios**: matar al líder → se elige otro < X ms; particionar 3-2 → la minoría **no** puede comprometer; sanar la partición → los logs se reconcilian sin perder lo comprometido.

## B.10 Lecturas
- **In Search of an Understandable Consensus Algorithm (Raft)** — Ongaro & Ousterhout. El paper *es* legible; léelo con la web `raft.github.io` (visualización interactiva).
- **Designing Data-Intensive Applications** (Kleppmann), cap. 5 (Replication) y 9 (Consistency & Consensus).
- Tu [[catalogo-byox-infra]] — Raft como mini-proyecto propio; y [[MOC_CS_Fundamentos]] (sistemas distribuidos).

## Cuando termines
- Parte A: cierra F9-1…F9-4 en Huly. Post-mortem: ¿qué ve un cliente que lee de la réplica justo tras escribir en el máster (read-your-writes)?
- Parte B: una nota en la bitácora con **por qué el split-brain obliga a consenso** y el mapa de Raft. Eso es el puente al catálogo BYOX.

## Conexiones
- `docs/fase-6-persistencia.md` (RDB reusado en el resync y en el estado durable de Raft) · `docs/fase-8-pulido.md` (INFO) · `PHASES.md` · `issues/fase-9.md` · [[disenar-funciones-y-programas]] (modos de fallo) · [[catalogo-byox-infra]] (Raft) · [[MOC_CS_Fundamentos]]
