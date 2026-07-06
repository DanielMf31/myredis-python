# Fase 0 — Walking skeleton (PING)

> **Meta:** el mínimo de punta a punta. Un servidor TCP asyncio que entiende **un** comando (`PING`) hablando **RESP2**, probado con el **`redis-cli` oficial**. Cuando `redis-cli -p 6380 PING` te responda `PONG`, tienes la tubería entera montada y todo lo demás son comandos que se cuelgan de ella.
>
> **Cómo usar este doc:** para cada pieza doy el **contrato + edge cases + el código comentado + los tests que debe pasar**. **Tecléalo tú** en `server/myredis/`. Lo ideal: lee el contrato y los tests, **intenta escribir la pieza tú**, y solo entonces compara con mi código. No copies-pegues: el valor está en teclearlo entendiéndolo.

---

## 1. Conceptos (qué tienes que entender antes de teclear)

### 1.1 RESP2 — el protocolo

RESP = REdis Serialization Protocol. Formato **binario, simple, terminado en `\r\n` (CRLF)**. **5 tipos**, cada uno identificado por su **primer byte**:

| Byte | Tipo | Ejemplo | Uso |
|---|---|---|---|
| `+` | Simple string | `+OK\r\n`, `+PONG\r\n` | respuestas de estado (NO puede llevar `\r`/`\n`) |
| `-` | Error | `-ERR unknown command\r\n` | errores (palabra en mayúscula al inicio: `ERR`, `WRONGTYPE`) |
| `:` | Integer | `:1000\r\n` | counts, tamaños, booleanos (1/0) |
| `$` | Bulk string | `$5\r\nhello\r\n` | datos binarios (length-prefixed → binary-safe). **Null = `$-1\r\n`** |
| `*` | Array | `*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n` | listas de valores |

**Lo clave:** el **cliente SIEMPRE manda los comandos como un array de bulk strings.** `SET foo bar` llega como `*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n` y se parsea a `[b"SET", b"foo", b"bar"]`. Tu server: parsea el array → mira `[0]` (el comando) → ejecuta → codifica la respuesta en RESP.

**Por qué length-prefixed** (`$5\r\n...`) y no delimitado como HTTP: es **binary-safe** (el contenido puede tener `\r\n`), rápido (sabes cuántos bytes leer) y eficiente en memoria. Misma idea que protobuf/gRPC.

### 1.2 El framing incremental (la parte difícil, y la interesante)

**TCP NO te entrega un mensaje por `read()`.** Un `read()` puede darte: medio mensaje, un mensaje justo, o **varios pegados** (pipelining). Por eso el parser es **incremental**:
- `feed(data)` → añade bytes a un buffer interno.
- `parse()` → devuelve **un** mensaje completo y lo consume del buffer, **o `None`** si aún no hay suficiente (esperas más `read`).
- El server, tras cada `read`, hace `feed` y luego **drena todos los mensajes completos** en un bucle `while parse() is not None` (si no, pierdes los pipelined).

> Este es el edge case central de Fase 0. Provócalo: manda `b"$5\r\nhel"` → `parse()` debe devolver `None`; luego `b"lo\r\n"` → `b"hello"`.

### 1.3 El servidor TCP asyncio

- `asyncio.start_server(handle, host, port)` → escucha y **lanza una corrutina `handle_client(reader, writer)` por cada conexión**. Un solo hilo + event loop atiende a miles de clientes (como el Redis real).
- Dentro del handler: `data = await reader.read(4096)`; **`if not data: break`** (`b""` = el cliente cerró — si no lo manejas, bucle infinito).
- Responder: `writer.write(bytes)` + **`await writer.drain()`** (back-pressure; sin drain, un cliente lento te infla la memoria).
- **Sin locks:** las ops en memoria son atómicas entre `await`s (single-thread event loop).

### 1.4 El flujo completo de Fase 0

```
redis-cli PING
   │  *1\r\n$4\r\nPING\r\n   (array de 1 bulk string)
   ▼
server._handle_client:  reader.read() → parser.feed() → parser.parse() → [b"PING"]
   ▼
server._dispatch:  cmd_name="PING", args=[]
   ▼
CommandRegistry.execute("PING", []) → cmd_ping([]) → "PONG"   (str = simple string)
   ▼
protocol.encode("PONG") → b"+PONG\r\n"
   ▼
writer.write(b"+PONG\r\n") + drain
   ▼
redis-cli imprime: PONG
```

---

## 2. `protocol.py` — encoder + parser (Issues F0-2 y F0-3)

Es el corazón. Dos partes: `encode` (valor Python → bytes RESP) y `RESPParser` (bytes → valor Python, incremental).

**Contrato `encode(value) -> bytes`:** `None`→`$-1\r\n`; `bool`→`:1/:0` (¡antes que int!); `int`→`:N`; `str`→`+S` (simple, respuestas tipo "OK"/"PONG"); `bytes`→`$N\r\n...` (bulk); `list/tuple`→`*N...` (recursivo); `Exception`→`-ERR msg`. Tipo no soportado → `TypeError`.

**Contrato `RESPParser`:** `feed(data)` acumula; `parse()` devuelve un mensaje completo (y lo consume) o `None` si falta data; `ProtocolError` si el formato es inválido.

**Edge cases que cazan los tests:** null bulk (`$-1`), array vacío (`*0`), array anidado/mixto, **partial data** (medio mensaje → `None`), **varios mensajes en el buffer**, roundtrip (`encode`→`feed`→`parse` == original).

```python
"""RESP2 protocol: parser incremental + encoder. Solo stdlib."""
from typing import Any

CRLF = b"\r\n"


# ── ENCODER: valor Python → bytes RESP ──────────────────────────────────────
def encode(value: Any) -> bytes:
    if value is None:
        return b"$-1\r\n"                       # null bulk string (nil)
    if isinstance(value, bool):
        # bool ANTES que int (bool es subtipo de int en Python)
        return b":1\r\n" if value else b":0\r\n"
    if isinstance(value, int):
        return b":" + str(value).encode() + CRLF
    if isinstance(value, str):
        return b"+" + value.encode() + CRLF     # simple string (no \r/\n dentro)
    if isinstance(value, bytes):
        return b"$" + str(len(value)).encode() + CRLF + value + CRLF   # bulk
    if isinstance(value, (list, tuple)):
        out = b"*" + str(len(value)).encode() + CRLF
        for item in value:
            out += encode(item)                 # recursivo
        return out
    if isinstance(value, Exception):
        return b"-ERR " + str(value).encode() + CRLF
    raise TypeError(f"Cannot encode {type(value).__name__} to RESP")


# ── PARSER: bytes → valor Python (incremental) ──────────────────────────────
class ProtocolError(Exception):
    """El byte stream no es RESP válido."""


class RESPParser:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> None:
        self.buffer.extend(data)

    def parse(self) -> Any | None:
        """Un mensaje completo (y lo consume), o None si falta data."""
        if not self.buffer:
            return None
        try:
            value, consumed = self._parse_at(0)
            del self.buffer[:consumed]          # avanza el cursor
            return value
        except IndexError:
            return None                         # aún no hay bytes suficientes

    def _parse_at(self, pos: int) -> tuple[Any, int]:
        """Parsea el valor que empieza en buffer[pos:]. Devuelve (valor, bytes_consumidos)."""
        if pos >= len(self.buffer):
            raise IndexError("need more data")
        t = self.buffer[pos]
        if t == ord("+"):
            return self._line(pos + 1, decode=True)
        if t == ord("-"):
            v, c = self._line(pos + 1, decode=True); return Exception(v), c
        if t == ord(":"):
            v, c = self._line(pos + 1, decode=True); return int(v), c
        if t == ord("$"):
            return self._bulk(pos + 1)
        if t == ord("*"):
            return self._array(pos + 1)
        raise ProtocolError(f"Unknown RESP type byte: {chr(t)!r}")

    def _find_crlf(self, start: int) -> int:
        for i in range(start, len(self.buffer) - 1):
            if self.buffer[i] == 0x0D and self.buffer[i + 1] == 0x0A:  # \r \n
                return i
        raise IndexError("no CRLF yet")

    def _line(self, pos: int, decode: bool = False) -> tuple[Any, int]:
        end = self._find_crlf(pos)
        raw = bytes(self.buffer[pos:end])
        consumed = end + 2                       # incluye \r\n
        return (raw.decode("utf-8"), consumed) if decode else (raw, consumed)

    def _bulk(self, pos: int) -> tuple[bytes | None, int]:
        length_str, after = self._line(pos, decode=True)
        length = int(length_str)
        if length == -1:
            return None, after                   # null bulk
        end = after + length
        if end + 2 > len(self.buffer):
            raise IndexError("need more data for bulk")
        data = bytes(self.buffer[after:end])
        if self.buffer[end:end + 2] != b"\r\n":
            raise ProtocolError("expected CRLF after bulk data")
        return data, end + 2

    def _array(self, pos: int) -> tuple[list | None, int]:
        length_str, after = self._line(pos, decode=True)
        length = int(length_str)
        if length == -1:
            return None, after
        items, cursor = [], after
        for _ in range(length):
            item, cursor = self._parse_at(cursor)
            items.append(item)
        return items, cursor
```

> **Cuidado con el bug del modelo** (que ya te señalé): usar `IndexError` como "necesito más datos" conflacia con un `IndexError` de bug real → el server esperaría para siempre. Para Fase 0 lo dejamos así (es lo que hace el modelo), pero anótalo: en una versión seria, usa una excepción propia `NeedMoreData` distinta de `IndexError`.

**Tests que debe pasar** — `server/tests/unit/test_protocol.py`:

```python
from myredis.protocol import RESPParser, encode


# ── encoder ──
def test_encode_simple_string(): assert encode("OK") == b"+OK\r\n"
def test_encode_integer():       assert encode(42) == b":42\r\n"; assert encode(-7) == b":-7\r\n"
def test_encode_bulk():          assert encode(b"hello") == b"$5\r\nhello\r\n"
def test_encode_null():          assert encode(None) == b"$-1\r\n"
def test_encode_array():         assert encode([b"foo", b"bar"]) == b"*2\r\n$3\r\nfoo\r\n$3\r\nbar\r\n"
def test_encode_empty_array():   assert encode([]) == b"*0\r\n"
def test_encode_nested_mixed():  assert encode([1, b"x", None]) == b"*3\r\n:1\r\n$1\r\nx\r\n$-1\r\n"
def test_encode_error():         assert encode(Exception("bad command")) == b"-ERR bad command\r\n"
def test_encode_bool():          assert encode(True) == b":1\r\n"; assert encode(False) == b":0\r\n"


# ── parser ──
def _one(data):
    p = RESPParser(); p.feed(data); return p.parse()

def test_parse_simple():   assert _one(b"+PONG\r\n") == "PONG"
def test_parse_integer():  assert _one(b":1000\r\n") == 1000
def test_parse_bulk():     assert _one(b"$5\r\nhello\r\n") == b"hello"
def test_parse_null_bulk():assert _one(b"$-1\r\n") is None
def test_parse_command():  assert _one(b"*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n") == [b"SET", b"foo", b"bar"]


# ── framing (lo importante) ──
def test_partial_data():
    p = RESPParser(); p.feed(b"$5\r\nhel")
    assert p.parse() is None
    p.feed(b"lo\r\n"); assert p.parse() == b"hello"

def test_multiple_in_buffer():
    p = RESPParser(); p.feed(b"+PONG\r\n+OK\r\n")
    assert p.parse() == "PONG"; assert p.parse() == "OK"; assert p.parse() is None

def test_roundtrip():
    p = RESPParser(); p.feed(encode(b"hello")); assert p.parse() == b"hello"
```

---

## 3. `commands.py` — registry + PING (Issue F0-5)

**Contrato:** un registry `{nombre_mayus: handler}`. `execute(name, args)` busca el handler; si no existe, **devuelve** (no lanza) `Exception("unknown command")` → se codifica como error RESP. Cada handler recibe **un solo `args: list`** (bytes crudos) y devuelve un valor Python que `encode` traduce.

```python
"""Registro y ejecución de comandos. Fase 0: solo PING."""
from typing import Any, Awaitable, Callable

CommandHandler = Callable[[list], Awaitable[Any]]


class CommandRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}
        self._register_all()

    def register(self, name: str, handler: CommandHandler) -> None:
        self._handlers[name.upper()] = handler

    def _register_all(self) -> None:
        self.register("PING", self.cmd_ping)        # ← aquí crecerá la lista

    async def execute(self, name: str, args: list) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            return Exception(f"ERR unknown command '{name}'")   # devolver, no lanzar
        return await handler(args)

    async def cmd_ping(self, args: list) -> Any:
        if not args:
            return "PONG"           # simple string
        return args[0]              # PING con arg = eco (bulk string)
```

---

## 4. `server.py` — el servidor TCP (Issues F0-4 y F0-5)

**Contrato `_handle_client`:** bucle read→feed→(drenar mensajes)→dispatch→write; sale si `read()` devuelve `b""`. **Edge cases:** desconexión (`b""`), buffer incompleto (`parse()` → `None`, esperar), varios mensajes pegados (drenar en bucle), `ProtocolError` (responder error, no matar la conexión).

```python
"""Servidor TCP asyncio. Fase 0: solo el esqueleto (sin snapshot/expiración)."""
import asyncio

from myredis.protocol import RESPParser, encode, ProtocolError
from myredis.commands import CommandRegistry


class RedisServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 6380) -> None:
        self.host = host
        self.port = port
        self.commands = CommandRegistry()
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        addr = self._server.sockets[0].getsockname()
        print(f"myredis escuchando en {addr}")

    async def serve_forever(self) -> None:
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        parser = RESPParser()
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break                                   # cliente cerró
                parser.feed(data)
                while True:                                 # drenar TODOS los mensajes
                    try:
                        message = parser.parse()
                    except ProtocolError as e:
                        writer.write(encode(Exception(str(e))))
                        await writer.drain()
                        break
                    if message is None:
                        break                               # falta data → esperar más read
                    response = await self._dispatch(message)
                    writer.write(response)
                    await writer.drain()                    # back-pressure
        finally:
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, message: object) -> bytes:
        if not isinstance(message, list) or not message:
            return encode(Exception("ERR protocol error"))
        cmd_name = message[0].decode("utf-8", "replace").upper()
        args = message[1:]
        result = await self.commands.execute(cmd_name, args)
        return encode(result)
```

---

## 5. `__main__.py` — arranque (Issue F0-6)

Lee host/puerto de env vars (así los tests pueden lanzar en un puerto libre) sin necesitar `config.py`.

```python
"""Entry point: python -m myredis"""
import asyncio
import os

from myredis.server import RedisServer


async def main() -> None:
    host = os.environ.get("MYREDIS_HOST", "0.0.0.0")
    port = int(os.environ.get("MYREDIS_PORT", "6380"))
    server = RedisServer(host, port)
    await server.start()
    await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nmyredis apagado")
```

(`__init__.py` déjalo vacío — solo marca `myredis` como paquete.)

---

## 6. Test de integración con el cliente OFICIAL (Issue F0-6)

Esto es el sello: si `redis-py` (el cliente real) te hace `ping()` y funciona, tu RESP es correcto. `conftest.py` lanza tu server como **subproceso** en un puerto libre (evita choques con asyncio de los tests síncronos).

`server/tests/conftest.py`:

```python
import os, socket, subprocess, sys, time
import pytest
import redis


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    return port


@pytest.fixture
def redis_client():
    port = _free_port()
    server_dir = os.path.join(os.path.dirname(__file__), "..")   # .../server
    env = {**os.environ, "PYTHONPATH": server_dir,
           "MYREDIS_HOST": "127.0.0.1", "MYREDIS_PORT": str(port)}
    proc = subprocess.Popen([sys.executable, "-m", "myredis"], env=env)
    for _ in range(50):                                          # esperar a que acepte
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close(); break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill(); raise RuntimeError("myredis no arrancó")
    client = redis.Redis(host="127.0.0.1", port=port, decode_responses=False)
    yield client
    client.close(); proc.terminate()
    try: proc.wait(timeout=3)
    except subprocess.TimeoutExpired: proc.kill()
```

`server/tests/integration/test_via_redis_py.py`:

```python
def test_ping(redis_client):
    assert redis_client.ping() is True
```

---

## 7. Verificación de la Fase 0 (criterio de "hecho")

```bash
cd server && source ../.venv/bin/activate

pytest tests/unit/test_protocol.py -v      # (1) encoder + parser en verde

python -m myredis                          # (2) arranca en :6380
#   en otra terminal:
redis-cli -p 6380 PING                     # (3) -> PONG   ← el cliente OFICIAL habla con tu server

pytest tests/integration/ -k ping -v       # (4) ping() True
```

**Fase 0 hecha = (1) + (3) + (4) en verde.** Cuando `redis-cli PING` te devuelva `PONG`, has montado la tubería completa. Todo lo demás (SET/GET, TTL, listas…) es colgar comandos nuevos del registry.

## 8. Cuando termines

- **Post-mortem** en tu bitácora: ¿qué edge case del framing se te resistió? → tu taxonomía.
- Cierra los Issues F0-x en Huly y pasa a **Fase 1 (SET/GET/DEL)** — ahí aparece `storage.py`.

## Conexiones
- [[disenar-funciones-y-programas]] — contratos + edge cases (lo has aplicado aquí)
- `PHASES.md` — el mapa · `HULY_fase-0-issues.md` — los Issues
- Modelo: `../06_build_your_own_redis/docs/01-resp-protocol-explained.md` y `02-asyncio-tcp-server-patterns.md`
