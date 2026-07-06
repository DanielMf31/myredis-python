# Issues de Huly — Fase 1 (Strings: SET/GET/DEL/EXISTS)

> **Cómo usarlo:** la línea Título va al campo Título de Huly; lo de debajo va a la Descripción. Copia desde el modo código/source de Obsidian (`Ctrl+E`) para que pegue limpio. Labels: `byox-redis`, `fase-1`. Orden F1-1 → F1-4, 1 "In Progress" a la vez. Doc de referencia: `docs/fase-1-strings.md`.

---

### F1-1 · storage.py

**Título:** F1-1 · storage.py: almacén clave-valor en memoria

**Contexto:** el KV en memoria sobre el que se apoyan todos los comandos de datos. Fase 1: básico, sin TTL/LRU/persistencia.

**Contrato:**
- `set(key, value)`: guarda (sobrescribe si existe)
- `get(key)`: devuelve el valor o `None` si no existe
- `delete(key)`: devuelve `True` si existía y se borró, `False` si no
- `exists(key)`: `True`/`False`
- claves y valores son `bytes`

**Cobertura / edge cases:**
- get de clave inexistente da None
- set sobrescribe
- delete de clave inexistente da False
- exists distingue existe / no existe

**Criterio PASS:**
- Los tests de `tests/unit/test_storage.py` en verde

---

### F1-2 · SET + GET

**Título:** F1-2 · commands: SET y GET (+ helpers de validación)

**Contexto:** los dos primeros comandos de datos. El registry pasa a recibir el `storage`.

**Contrato:**
- `SET key value` da "OK" (simple string); mínimo 2 args
- `GET key` da bytes o `None` (nil); exactamente 1 arg; WRONGTYPE si el valor no es bytes
- helpers: `_to_bytes`, `_check_argc`, `_check_argc_min`
- el registry: `CommandRegistry(storage)`; `server.__init__` crea `Storage()` y lo pasa

**Cobertura / edge cases:**
- SET con menos de 2 args da error RESP (no crash)
- GET de clave inexistente da nil
- case-insensitive (set / SET)

**Criterio PASS:**
- `redis-cli -p 6380 SET foo bar` da OK y `GET foo` da "bar"
- `test_set_get` y `test_get_nonexistent` en verde

---

### F1-3 · DEL + EXISTS

**Título:** F1-3 · commands: DEL y EXISTS (cuentan)

**Contexto:** borrado y comprobación de existencia. Ambos aceptan varias claves y devuelven un contador.

**Contrato:**
- `DEL key [key...]` da int = cuántas existentes se borraron
- `EXISTS key [key...]` da int = cuántas existen (cuenta duplicados)
- mínimo 1 arg cada uno

**Cobertura / edge cases:**
- DEL de mezcla existentes/inexistentes cuenta solo las existentes
- EXISTS de la misma clave dos veces cuenta 2
- borrar deja la clave inexistente después

**Criterio PASS:**
- `test_delete` (da 2 sobre 3 args) y `test_exists` (1 / 0) en verde

---

### F1-4 · Verificación E2E (+ bonus)

**Título:** F1-4 · Verificación end-to-end de la Fase 1

**Contexto:** cerrar la fase con el cliente oficial y, opcional, ampliar con DBSIZE/FLUSHDB/KEYS.

**Tareas:**
- `pytest tests/unit -v` (storage + protocol) en verde
- Comprobar a mano con `redis-cli`: SET, GET, GET nil, DEL, EXISTS
- `pytest tests/integration -k "set or get or delete or exists" -v` en verde

**Bonus opcional:**
- DBSIZE (len del storage) y FLUSHDB (flush + "OK") → test_dbsize_flushdb
- KEYS pattern con glob (fnmatch) → test_keys_pattern

**Criterio PASS (Fase 1 COMPLETA):**
- unit verde + los 5 comandos funcionan con redis-cli + integración string/keyspace en verde

---

## Siguiente

Al cerrar F1 → **Fase 2: EXPIRE / TTL / PERSIST** (expiración lazy + active sweep). Se detalla al llegar.
