# Issues de Huly — Fase 5 (Hashes)

> Título → Título de Huly; debajo → Descripción. Labels: `byox-redis`, `fase-5`. Doc: `docs/fase-5-hashes.md`.

---

### F5-1 · helper de tipo hash

**Título:** F5-1 · commands: helper `_get_hash` + WRONGTYPE

**Contexto:** el valor puede ser ahora un `dict[bytes, bytes]`. Mismo patrón que la lista.

**Contrato:**
- `_get_hash(key, create=False)`: dict, None, o WRONGTYPE
- auto-borrado de la clave si el hash queda vacío

**Criterio PASS:**
- HSET sobre una clave string da WRONGTYPE

---

### F5-2 · HSET / HGET / HDEL / HKEYS / HGETALL

**Título:** F5-2 · commands: comandos de hash

**Contrato:**
- `HSET` → cuenta solo campos NUEVOS
- `HGET` → valor o nil
- `HDEL` → cuenta borrados; auto-borra la clave si queda vacía
- `HKEYS` → lista de campos
- `HGETALL` → lista PLANA [f1, v1, f2, v2, ...] (RESP2 no tiene tipo mapa)

**Cobertura / edge cases:**
- HSET que actualiza un campo existente no lo cuenta como nuevo
- HGETALL devuelve plano; el cliente lo empareja
- HDEL de todos los campos borra la clave

**Criterio PASS (Fase 5 COMPLETA):**
- `test_hset_hget`, `test_hgetall`, `test_hdel` en verde
