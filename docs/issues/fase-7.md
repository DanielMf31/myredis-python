# Issues de Huly — Fase 7 (Eviction LRU)

> Título → Título de Huly; debajo → Descripción. Labels: `byox-redis`, `fase-7`. Doc: `docs/fase-7-eviction.md`.

---

### F7-1 · storage: tracking de memoria + evict_lru

**Título:** F7-1 · storage.py: memoria + evict_lru (OrderedDict)

**Contrato:**
- `maxmemory` + `_bytes` (estimación) actualizados en set/delete
- `needs_eviction()` → True si se supera el límite
- `evict_lru()` → `popitem(last=False)` (el más viejo), O(1)
- get/set hacen `move_to_end` (mantienen el orden LRU)

**Cobertura / edge cases:**
- maxmemory=0 → sin límite (nunca evicta)
- evict sobre almacén vacío → False

**Criterio PASS:** unit: tras superar el límite, evict_lru saca la clave más antigua

---

### F7-2 · eviction.py + disparo tras escrituras + config

**Título:** F7-2 · eviction.py: maybe_evict + límite por config

**Contrato:**
- `EvictionManager.maybe_evict()`: echa claves mientras `needs_eviction()`
- se llama tras cada escritura (SET/LPUSH/HSET/INCR...)
- límite desde `MYREDIS_MAXMEMORY` (acepta `100mb`, `5kb`...)

**Cobertura / edge cases:**
- un GET refresca la clave y la salva del desalojo (corazón del LRU)
- las claves menos usadas caen primero

**Criterio PASS (Fase 7 COMPLETA):**
- `test_evicta_los_viejos` y `test_get_refresca_lru` en verde
- con `MYREDIS_MAXMEMORY=5kb`, DBSIZE se estabiliza al meter muchas claves
