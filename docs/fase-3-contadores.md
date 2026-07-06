# Fase 3 — Contadores: INCR / DECR / INCRBY / DECRBY

> **Meta:** operaciones atómicas sobre números guardados como string. Es la fase **más corta** (solo handlers), buena para coger ritmo.
>
> **Prerrequisito:** Fase 1. Solo tocas `commands.py`.

## 1. Concepto
En Redis los números se guardan como **bulk strings** (`b"42"`), no como int. `INCR` = leer, parsear a int, sumar 1, volver a guardar como string, devolver el nuevo valor. Es **atómico** porque el server es single-thread (entre `await`s nadie se cuela). Si la clave no existe, se trata como **0**. Si el valor no es un entero, **error**.

## 2. `commands.py` — los 4 handlers

**Contratos:**
- `INCR key` → +1, devuelve el nuevo int. Clave inexistente = empieza en 0.
- `DECR key` → -1.
- `INCRBY key n` / `DECRBY key n` → ±n.
- Si el valor guardado **no es un entero** → error `ERR value is not an integer or out of range`.

Un solo helper hace el trabajo; los cuatro comandos lo llaman:

```python
async def _incr_by(self, key: bytes, delta: int) -> int:
    self.expiration.check_and_expire(key)         # respeta TTL (si tienes F2)
    current = self.storage.get(key)
    if current is None:
        value = 0
    else:
        if not isinstance(current, bytes):
            raise ValueError("WRONGTYPE Operation against a key holding the wrong kind of value")
        try:
            value = int(current)
        except ValueError:
            raise ValueError("ERR value is not an integer or out of range")
    value += delta
    self.storage.set(key, str(value).encode())     # se guarda como string
    return value

async def cmd_incr(self, args):
    self._check_argc(args, 1, "incr")
    return await self._incr_by(_to_bytes(args[0]), 1)

async def cmd_decr(self, args):
    self._check_argc(args, 1, "decr")
    return await self._incr_by(_to_bytes(args[0]), -1)

async def cmd_incrby(self, args):
    self._check_argc(args, 2, "incrby")
    return await self._incr_by(_to_bytes(args[0]), int(args[1]))

async def cmd_decrby(self, args):
    self._check_argc(args, 2, "decrby")
    return await self._incr_by(_to_bytes(args[0]), -int(args[1]))
```
Regístralos: `INCR`, `DECR`, `INCRBY`, `DECRBY`.

> Fíjate en el patrón que ya conoces: guardas el número como `str(value).encode()` (número → texto → bytes). El mismo que te costó en el encoder.

## 3. Tests
```python
def test_incr_desde_cero(redis_client):
    assert redis_client.incr("c") == 1
    assert redis_client.incr("c") == 2

def test_incrby_decrby(redis_client):
    redis_client.set("c", "10")
    assert redis_client.incrby("c", 5) == 15
    assert redis_client.decrby("c", 3) == 12

def test_incr_no_entero(redis_client):
    redis_client.set("c", "hola")
    import redis
    try:
        redis_client.incr("c"); assert False
    except redis.ResponseError:
        pass
```

## 4. Verificación
```bash
pytest tests/ -
redis-cli -p 6380 INCR visitas     # -> (integer) 1
redis-cli -p 6380 INCRBY visitas 9 # -> (integer) 10
```

## Siguiente
F3 hecha → **Fase 4 (Listas)**, donde el valor deja de ser bytes y aparece un `deque`.

## Conexiones
- `docs/fase-1-strings.md` · `PHASES.md` · `HULY_fase-3-issues.md`
