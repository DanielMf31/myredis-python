# Fase 4 — Listas: LPUSH / RPUSH / LPOP / RPOP / LLEN / LRANGE

> **Meta:** un **segundo tipo de dato**. Hasta ahora los valores eran `bytes` (strings); ahora una clave puede guardar una **lista** (`collections.deque`). Aparece el error **WRONGTYPE**.
>
> **Prerrequisito:** Fase 1. Tocas `commands.py` (los valores ya se guardan tal cual en `storage`).

## 1. Concepto
- El valor de una clave puede ser ahora un **`collections.deque`** (cola doblemente enlazada). ¿Por qué deque y no `list`? Porque **`deque` hace push/pop en AMBOS extremos en O(1)**; una `list` es O(n) por la izquierda.
- **WRONGTYPE:** si haces una op de lista sobre una clave que guarda un string (bytes), error. Y al revés. Cada comando comprueba el tipo.
- **Auto-borrado:** si una lista se queda **vacía** tras un pop, la clave se **borra** (convención Redis).
- **LPUSH invierte:** `LPUSH k a b c` mete a, luego b, luego c **por la izquierda** → la lista queda `[c, b, a]`.

## 2. Un helper para el tipo
Casi todos los comandos necesitan "dame la deque de esta clave (o error si no es lista)":

```python
from collections import deque

def _get_list(self, key: bytes, create: bool = False):
    self.expiration.check_and_expire(key)
    value = self.storage.get(key)
    if value is None:
        if create:
            d = deque(); self.storage.set(key, d); return d
        return None
    if not isinstance(value, deque):
        raise ValueError("WRONGTYPE Operation against a key holding the wrong kind of value")
    return value

def _drop_if_empty(self, key: bytes, d) -> None:
    if len(d) == 0:
        self.storage.delete(key)
```

## 3. Los comandos

**Contratos:**
- `LPUSH/RPUSH key v [v...]` → añade por izquierda/derecha, devuelve la **longitud** resultante.
- `LPOP/RPOP key` → saca uno de izquierda/derecha, lo devuelve (o nil si vacía).
- `LLEN key` → longitud (0 si no existe).
- `LRANGE key start stop` → sublista; índices negativos cuentan desde el final (`-1` = último).

```python
async def cmd_rpush(self, args):
    self._check_argc_min(args, 2, "rpush")
    key = _to_bytes(args[0]); d = self._get_list(key, create=True)
    for v in args[1:]:
        d.append(_to_bytes(v))
    return len(d)

async def cmd_lpush(self, args):
    self._check_argc_min(args, 2, "lpush")
    key = _to_bytes(args[0]); d = self._get_list(key, create=True)
    for v in args[1:]:
        d.appendleft(_to_bytes(v))     # cada uno por la izquierda -> invierte el orden
    return len(d)

async def cmd_lpop(self, args):
    self._check_argc(args, 1, "lpop")
    key = _to_bytes(args[0]); d = self._get_list(key)
    if d is None or len(d) == 0:
        return None
    v = d.popleft(); self._drop_if_empty(key, d); return v

async def cmd_rpop(self, args):
    self._check_argc(args, 1, "rpop")
    key = _to_bytes(args[0]); d = self._get_list(key)
    if d is None or len(d) == 0:
        return None
    v = d.pop(); self._drop_if_empty(key, d); return v

async def cmd_llen(self, args):
    self._check_argc(args, 1, "llen")
    d = self._get_list(_to_bytes(args[0]))
    return len(d) if d is not None else 0

async def cmd_lrange(self, args):
    self._check_argc(args, 3, "lrange")
    d = self._get_list(_to_bytes(args[0]))
    if d is None:
        return []
    items = list(d)
    start, stop = int(args[1]), int(args[2])
    n = len(items)
    if start < 0: start = max(0, n + start)
    if stop < 0: stop = n + stop
    return items[start:stop + 1]        # RESP: stop es INCLUSIVO (¡ojo!)
```
Regístralos. Y **añade la comprobación WRONGTYPE en `cmd_get`**: si el valor no es bytes, ya lanzabas WRONGTYPE en Fase 1 — perfecto, ahora tiene sentido (puede ser una deque).

> Edge case fino: en `LRANGE`, **`stop` es inclusivo** (`0 -1` = toda la lista). En Python el slice es exclusivo, por eso `items[start:stop+1]`.

## 4. Tests
```python
def test_rpush_lrange(redis_client):
    redis_client.rpush("l", "a", "b", "c")
    assert redis_client.lrange("l", 0, -1) == [b"a", b"b", b"c"]

def test_lpush_invierte(redis_client):
    redis_client.lpush("l", "a", "b", "c")
    assert redis_client.lrange("l", 0, -1) == [b"c", b"b", b"a"]

def test_pop_y_llen(redis_client):
    redis_client.rpush("l", "a", "b")
    assert redis_client.lpop("l") == b"a"
    assert redis_client.llen("l") == 1

def test_wrongtype(redis_client):
    redis_client.set("s", "soy string")
    import redis
    try:
        redis_client.lpush("s", "x"); assert False
    except redis.ResponseError:
        pass
```

## 5. Verificación
```bash
pytest tests/ -v
redis-cli -p 6380 RPUSH cola a b c
redis-cli -p 6380 LRANGE cola 0 -1   # 1) "a" 2) "b" 3) "c"
```

## Siguiente
F4 → **Fase 5 (Hashes)**: mismo patrón pero el valor es un `dict` anidado.

## Conexiones
- `docs/fase-1-strings.md` · `PHASES.md` · `issues/fase-4.md`
