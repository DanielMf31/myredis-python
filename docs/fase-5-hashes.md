# Fase 5 — Hashes: HSET / HGET / HDEL / HKEYS / HGETALL

> **Meta:** el **tercer tipo de dato**. Una clave puede guardar un **hash** (un `dict` de campo→valor), como un objeto. Mismo patrón que las listas (F4): helper de tipo + WRONGTYPE + auto-borrado.>
> **Prerrequisito:** Fase 4 (reusas el patrón). Tocas `commands.py`.

## 1. Concepto
El valor de una clave puede ser ahora un **`dict[bytes, bytes]`** (campo → valor). Es el "objeto" de Redis: `user:1 → {name: "Ana", age: "30"}`. Todo O(1) por campo. Reglas iguales que en listas: **WRONGTYPE** si el tipo no cuadra, y si el hash queda **vacío** tras borrar campos, la clave se **borra**.

## 2. Helper de tipo
```python
def _get_hash(self, key: bytes, create: bool = False):
    self.expiration.check_and_expire(key)
    value = self.storage.get(key)
    if value is None:
        if create:
            h = {}; self.storage.set(key, h); return h
        return None
    if not isinstance(value, dict):
        raise ValueError("WRONGTYPE Operation against a key holding the wrong kind of value")
    return value
```

## 3. Los comandos

**Contratos:**
- `HSET key field value [field value ...]` → guarda campos, devuelve **cuántos campos NUEVOS** se crearon.
- `HGET key field` → valor del campo (nil si no existe).
- `HDEL key field [field ...]` → borra campos, devuelve cuántos borró (y auto-borra la clave si el hash queda vacío).
- `HKEYS key` → lista de campos.
- `HGETALL key` → lista plana `[field1, value1, field2, value2, ...]` (así lo manda RESP; redis-py lo reconvierte a dict).

```python
async def cmd_hset(self, args):
    self._check_argc_min(args, 3, "hset")
    key = _to_bytes(args[0]); h = self._get_hash(key, create=True)
    pares = args[1:]
    nuevos = 0
    for i in range(0, len(pares) - 1, 2):
        field, value = _to_bytes(pares[i]), _to_bytes(pares[i + 1])
        if field not in h:
            nuevos += 1
        h[field] = value
    return nuevos

async def cmd_hget(self, args):
    self._check_argc(args, 2, "hget")
    h = self._get_hash(_to_bytes(args[0]))
    if h is None:
        return None
    return h.get(_to_bytes(args[1]))

async def cmd_hdel(self, args):
    self._check_argc_min(args, 2, "hdel")
    key = _to_bytes(args[0]); h = self._get_hash(key)
    if h is None:
        return 0
    borrados = 0
    for f in args[1:]:
        if h.pop(_to_bytes(f), None) is not None:
            borrados += 1
    if len(h) == 0:
        self.storage.delete(key)
    return borrados

async def cmd_hkeys(self, args):
    self._check_argc(args, 1, "hkeys")
    h = self._get_hash(_to_bytes(args[0]))
    return list(h.keys()) if h is not None else []

async def cmd_hgetall(self, args):
    self._check_argc(args, 1, "hgetall")
    h = self._get_hash(_to_bytes(args[0]))
    if h is None:
        return []
    out = []
    for f, v in h.items():
        out.append(f); out.append(v)     # plano: [f1, v1, f2, v2, ...]
    return out
```
Regístralos.

> Edge case: `HGETALL` devuelve una lista **plana** (no un dict) porque RESP2 no tiene tipo mapa; el cliente la empareja. `HSET` cuenta solo los campos **nuevos**, no los que solo actualizas.

## 4. Tests
```python
def test_hset_hget(redis_client):
    redis_client.hset("u", mapping={"name": "Ana", "age": "30"})
    assert redis_client.hget("u", "name") == b"Ana"
    assert redis_client.hlen("u") == 2 if hasattr(redis_client, "hlen") else True

def test_hgetall(redis_client):
    redis_client.hset("u", mapping={"a": "1", "b": "2"})
    assert redis_client.hgetall("u") == {b"a": b"1", b"b": b"2"}

def test_hdel(redis_client):
    redis_client.hset("u", mapping={"a": "1", "b": "2"})
    assert redis_client.hdel("u", "a") == 1
    assert redis_client.hkeys("u") == [b"b"]
```

## 5. Verificación
```bash
pytest tests/ -v
redis-cli -p 6380 HSET user:1 name Ana age 30
redis-cli -p 6380 HGETALL user:1
```

## Siguiente
F5 → **Fase 6 (Persistencia RDB)**: por fin los datos **sobreviven a un reinicio**. Aparece `persistence.py`.

## Conexiones
- `docs/fase-4-listas.md` · `PHASES.md` · `HULY_fase-5-issues.md`
