# Fase 6 — Persistencia RDB: SAVE / BGSAVE (snapshots)

> **Meta:** que los datos **sobrevivan a un reinicio**. Guardas un *snapshot* de todo el almacén a disco y lo cargas al arrancar. Aparecen tres ideas de sistemas: **serialización**, **escritura atómica** (temp + rename) y **no bloquear el event loop**.
>
> **Prerrequisito:** F1 (más rico si tienes F4 listas / F5 hashes). **Archivo nuevo:** `persistence.py`. Tocas `storage.py`, `commands.py`, `server.py` y `__main__.py`.
>
> **Cómo usarlo:** contrato + edge cases + código comentado + los tests que debe pasar. Tecléalo tú en `server/myredis/`; intenta cada pieza antes de mirar mi versión. No copies-pegues.

---

## 1. Conceptos (qué entender antes de teclear)

### 1.1 RDB = snapshot
Un **snapshot** es una foto de *todo* el almacén en un fichero. Redis real usa un formato binario propio; nosotros usamos **`pickle`**, que serializa cualquier objeto Python (bytes, `deque` de las listas, `dict` de los hashes) sin que tengamos que escribir un serializador a mano. El fichero se llama `dump.rdb` por convención.

> Trade-off honesto: `pickle` es cómodo pero **inseguro si cargas un fichero de origen no confiable** (puede ejecutar código al deserializar). Aquí solo cargamos ficheros que nosotros escribimos, así que es aceptable — pero anótalo, es justo el tipo de decisión que un ingeniero verbaliza.

### 1.2 Escritura atómica (el edge case central de la fase)
Si escribieras directamente sobre `dump.rdb` y el proceso muriera a mitad, te quedarías con un fichero **corrupto** y perderías *todo*. La solución es el patrón que ya viste en el organizador de descargas y en el mini-Kafka:

```
escribe a  dump.rdb.tmp   →   fsync   →   os.replace(tmp, dump.rdb)
```

`os.replace` es **atómico** en POSIX: o ves el fichero viejo entero, o el nuevo entero, nunca a medias. Si el crash ocurre antes del `replace`, el `dump.rdb` **antiguo queda intacto**.

### 1.3 No congelar el server
Serializar + `fsync` puede tardar. Si lo haces en el hilo del event loop, **ningún cliente responde** mientras guardas. Por eso `save()` delega el trabajo pesado a un hilo con **`asyncio.to_thread`**.

---

## 2. `storage.py` — snapshot / restore (Issue F6-1)

**Contrato:** `snapshot()` devuelve un `dict` serializable con todo el estado (datos + expiraciones); `restore(snap)` reconstruye el almacén desde esa foto. Deben ser **inversos**: `restore(snapshot())` no cambia nada.

**Edge cases:** un `snapshot` recién arrancado es `{"data": {}, "expirations": {}}`; `restore` de un dict sin las claves (`.get(..., {})`) no revienta.

Añade estos dos métodos a tu `Storage`:

```python
def snapshot(self) -> dict:
    """Foto del estado para persistir (todo lo que hay que recuperar tras reiniciar)."""
    return {"data": dict(self._data), "expirations": dict(self._expirations)}

def restore(self, snap: dict) -> None:
    """Recarga el estado desde una foto."""
    from collections import OrderedDict
    self._data = OrderedDict(snap.get("data", {}))     # .get -> tolerante a fotos incompletas
    self._expirations = dict(snap.get("expirations", {}))
```

> Nota: `snapshot` convierte el `OrderedDict` a `dict` plano (pierde el orden LRU). Para la fase 6 da igual; si en el futuro quieres persistir el orden de acceso, guarda `list(self._data.items())` en su lugar.

---

## 3. `persistence.py` — el guardado atómico (NUEVO, Issue F6-2)

**Contrato:**
- `save()` (async) → escribe un snapshot a `path` de forma **atómica** y **sin bloquear** el loop.
- `load()` (sync) → si el fichero existe, restaura el almacén; si no, **no hace nada** (arranque en frío).

**Edge cases que cazan los tests:**
- Fichero inexistente → `load()` retorna sin error (primer arranque).
- Crash a mitad de escribir → el `dump.rdb` viejo sobrevive (gracias a temp+replace).
- El temp se crea **en la misma carpeta** que el destino (si no, `os.replace` no sería atómico entre sistemas de ficheros distintos).

```python
"""Persistencia RDB: snapshot con pickle + escritura atómica (temp + rename). Fase 6."""
import asyncio
import os
import pickle
import tempfile
from pathlib import Path

from myredis.storage import Storage


class Persistence:
    def __init__(self, storage: Storage, path: str = "dump.rdb") -> None:
        self.storage = storage
        self.path = Path(path)

    def _save_sync(self) -> None:
        snap = self.storage.snapshot()
        # temp en la MISMA carpeta que el destino → os.replace será atómico
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent or "."), suffix=".rdb.tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump(snap, f)
                f.flush()
                os.fsync(f.fileno())        # fuerza que los bytes lleguen a disco
            os.replace(tmp, self.path)      # ← atómico: el viejo nunca queda corrupto
        except BaseException:
            os.unlink(tmp)                  # si algo falla, no dejes el temp tirado
            raise

    async def save(self) -> None:
        await asyncio.to_thread(self._save_sync)   # trabajo pesado en un hilo, el loop sigue libre

    def load(self) -> None:
        if not self.path.exists():
            return                          # primer arranque: no hay nada que cargar
        with self.path.open("rb") as f:
            self.storage.restore(pickle.load(f))
```

---

## 4. `commands.py` — SAVE / BGSAVE (Issue F6-3)

**Contratos:**
- `SAVE` → guarda **sincrónicamente** (espera a que termine), devuelve `"OK"`. 0 args.
- `BGSAVE` → dispara el guardado en **background** (no espera), devuelve `"Background saving started"`. 0 args.

El registry ahora recibe también `persistence` (además de `storage` y `expiration`):

```python
def __init__(self, storage, expiration, persistence) -> None:   # ← +persistence
    self.storage = storage
    self.expiration = expiration
    self.persistence = persistence
    self._handlers = {}
    self._register_all()

# en _register_all():
self.register("SAVE", self.cmd_save)
self.register("BGSAVE", self.cmd_bgsave)

# handlers:
async def cmd_save(self, args: list) -> Any:
    await self.persistence.save()
    return "OK"

async def cmd_bgsave(self, args: list) -> Any:
    asyncio.create_task(self.persistence.save())   # no espera; corre "en segundo plano"
    return "Background saving started"
```

> ⚠️ `import asyncio` arriba de `commands.py`. `create_task` necesita un event loop corriendo — lo hay, porque `execute` se llama dentro del loop.

---

## 5. `server.py` — cargar al arrancar + snapshot loop + save en shutdown

Aquí está el `server.py` **completo** de la Fase 6 (crece sobre el de fases anteriores). Los tres cambios: `Persistence` en `__init__`, `load()` **antes** de aceptar conexiones, y un **save final** en el `finally`.

```python
"""Servidor TCP asyncio. Fase 6: + persistencia (load al arrancar, snapshot loop, save al salir)."""
import asyncio

from myredis.protocol import RESPParser, encode, ProtocolError
from myredis.commands import CommandRegistry
from myredis.storage import Storage
from myredis.expiration import ExpirationManager
from myredis.persistence import Persistence


class RedisServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 6380,
                 dbfilename: str = "dump.rdb") -> None:
        self.host = host
        self.port = port
        self.storage = Storage()
        self.persistence = Persistence(self.storage, path=dbfilename)      # ← nuevo
        self.expiration = ExpirationManager(self.storage)
        self.commands = CommandRegistry(self.storage, self.expiration, self.persistence)
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set = set()

    async def start(self) -> None:
        self.persistence.load()                       # ← cargar ANTES de servir
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        addr = self._server.sockets[0].getsockname()
        print(f"myredis escuchando en {addr}")
        self._spawn(self._expiration_loop())
        self._spawn(self._snapshot_loop())            # ← snapshot periódico
        try:
            async with self._server:
                await self._server.serve_forever()
        finally:
            await self.persistence.save()             # ← save final al apagar (Ctrl+C)

    async def _snapshot_loop(self) -> None:
        while True:
            await asyncio.sleep(60)                    # cada 60s, foto de seguridad
            await self.persistence.save()

    async def _expiration_loop(self) -> None:
        while True:
            await asyncio.sleep(1)
            self.expiration.active_sweep()

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def _handle_client(self, reader, writer) -> None:
        parser = RESPParser()
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                parser.feed(data)
                while True:
                    try:
                        message = parser.parse()
                    except ProtocolError as e:
                        writer.write(encode(Exception(str(e)))); await writer.drain(); break
                    if message is None:
                        break
                    response = await self._dispatch(message)
                    writer.write(response)
                    await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, message) -> bytes:
        if not isinstance(message, list) or not message:
            return encode(Exception("ERR protocol error"))
        cmd_name = message[0].decode("utf-8", "replace").upper()
        args = message[1:]
        result = await self.commands.execute(cmd_name, args)
        return encode(result)
```

> Edge case del `finally`: al hacer Ctrl+C, `asyncio.run` cancela la tarea principal → `serve_forever` lanza `CancelledError` → el `finally` corre → **un último save**. Así no pierdes lo escrito desde el último snapshot.

**`__main__.py`** — añade `MYREDIS_DBFILENAME` (lo usarán los tests para aislar el fichero):

```python
import asyncio, os
from myredis.server import RedisServer

async def main() -> None:
    host = os.environ.get("MYREDIS_HOST", "0.0.0.0")
    port = int(os.environ.get("MYREDIS_PORT", "6380"))
    dbfile = os.environ.get("MYREDIS_DBFILENAME", "dump.rdb")   # ← nuevo
    server = RedisServer(host, port, dbfilename=dbfile)
    await server.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nmyredis apagado")
```

---

## 6. Tests

**Unit** — `server/tests/unit/test_persistence.py` (prueban `Persistence` con un `Storage` directo, sin red):

```python
from myredis.storage import Storage
from myredis.persistence import Persistence


def test_snapshot_restore_roundtrip():
    s = Storage(); s.set(b"a", b"1"); s.set(b"b", b"2")
    snap = s.snapshot()
    s2 = Storage(); s2.restore(snap)
    assert s2.get(b"a") == b"1" and s2.get(b"b") == b"2"

def test_load_sin_fichero_no_peta(tmp_path):
    p = Persistence(Storage(), path=str(tmp_path / "nope.rdb"))
    p.load()                       # no existe -> no lanza

def test_save_crea_fichero_y_recarga(tmp_path):
    import asyncio
    path = str(tmp_path / "dump.rdb")
    s = Storage(); s.set(b"k", b"v")
    p = Persistence(s, path=path)
    asyncio.run(p.save())
    assert (tmp_path / "dump.rdb").exists()
    s2 = Storage(); Persistence(s2, path=path).load()
    assert s2.get(b"k") == b"v"
```

**Integración** — `server/tests/integration/test_persistence.py` (usa la fábrica `myredis_server` del `conftest`, que arranca un server real con `MYREDIS_DBFILENAME` en un `tmp_path`):

```python
def test_persiste_tras_reinicio(myredis_server, tmp_path):
    dbfile = str(tmp_path / "dump.rdb")
    # 1er arranque: escribe y guarda
    with myredis_server(MYREDIS_DBFILENAME=dbfile) as c:
        c.set("curso", "systems")
        c.save()                      # SAVE síncrono
    # 2º arranque sobre el MISMO dump.rdb: el dato sigue ahí
    with myredis_server(MYREDIS_DBFILENAME=dbfile) as c:
        assert c.get("curso") == b"systems"
```

> El `myredis_server` es un *context manager* que arranca el server, cede el cliente y lo mata al salir del `with` — así puedes simular el reinicio (dos `with` seguidos sobre el mismo fichero). Está en el `conftest.py` (ver Fase 6 de tests).

---

## 7. Verificación de la Fase 6

```bash
cd server && source ../.venv/bin/activate

pytest tests/unit/test_persistence.py -v                 # roundtrip + atomicidad
pytest tests/integration/test_persistence.py -v          # sobrevive al reinicio

# a mano:
MYREDIS_DBFILENAME=/tmp/dump.rdb python -m myredis        # arranca
redis-cli -p 6380 SET k persistente                      # -> OK
redis-cli -p 6380 SAVE                                    # -> OK
#   Ctrl+C y relánzalo con el MISMO fichero:
MYREDIS_DBFILENAME=/tmp/dump.rdb python -m myredis
redis-cli -p 6380 GET k                                   # -> "persistente"  (¡sobrevivió!)
```

**Fase 6 hecha** = unit verde + `test_persiste_tras_reinicio` verde + el dato sobrevive a Ctrl+C con `redis-cli`.

## 8. Cuando termines
- Post-mortem en la bitácora: ¿por qué temp+rename y no escribir directo? ¿qué pasa si `MYREDIS_DBFILENAME` apunta a otro sistema de ficheros?
- Cierra F6-1…F6-3 en Huly → **Fase 7 (LRU eviction)**: cuando la memoria se llena, echar las claves menos usadas. Aparece `eviction.py`.

## El edge case para tu bitácora
La **escritura atómica** (temp + `os.replace` + `fsync`) es el patrón que ya has visto en el organizador, el mini-Kafka y ahora aquí. Grábatelo: *"para no corromper un fichero ante un crash: escribe a un temporal en la misma carpeta, fsync, y renombra atómicamente."*

## Conexiones
- `docs/fase-1-strings.md` · `PHASES.md` · `issues/fase-6.md` · [[disenar-funciones-y-programas]] (atomicidad, contratos)
