# Issues de Huly — Fase 2 (Expiración)

> Título → campo Título de Huly; lo de debajo → Descripción. Copia desde modo source (`Ctrl+E`). Labels: `byox-redis`, `fase-2`. Doc: `docs/fase-2-expiracion.md`.

---

### F2-1 · storage: TTLs

**Título:** F2-1 · storage.py: soporte de TTLs (dict de expiraciones)

**Contexto:** el almacén guarda los vencimientos en un dict aparte (la mayoría de claves no tiene TTL).

**Contrato:**
- `_expirations: dict[bytes, float]` en `__init__`
- `set_expiration`, `get_expiration`, `remove_expiration`, `keys_with_expiration`
- `delete()` limpia también el TTL de la clave

**Criterio PASS:**
- unit tests del store (set/get/remove expiration) en verde

---

### F2-2 · expiration.py (lazy + active)

**Título:** F2-2 · expiration.py: gestor lazy + active

**Contexto:** el módulo que decide y ejecuta la caducidad.

**Contrato:**
- `is_expired(key)`: True si ya pasó su timestamp
- `check_and_expire(key)`: lazy, borra si caducó, devuelve si borró
- `active_sweep(sample=20, threshold=0.25)`: muestrea claves con TTL, borra caducadas, repite si >25%

**Cobertura / edge cases:**
- clave sin TTL nunca caduca
- sweep sin claves con TTL no peta
- repetición cuando >25% caducadas

**Criterio PASS:**
- unit tests de expiration en verde (con `now` inyectado para determinismo)

---

### F2-3 · comandos EXPIRE / TTL / PERSIST + SET EX

**Título:** F2-3 · commands: EXPIRE, TTL, PERSIST y SET ... EX

**Contexto:** los comandos de caducidad. El registry ahora recibe el `expiration`; las lecturas llaman a `check_and_expire` primero (lazy).

**Contrato:**
- `EXPIRE key seconds` → 1 si existe, 0 si no
- `TTL key` → segundos; -1 sin TTL; -2 si no existe
- `PERSIST key` → 1 si tenía TTL, 0 si no
- `SET ... EX seconds` pone TTL; `SET` sin EX quita el TTL previo
- `cmd_get` llama `check_and_expire` antes de leer

**Cobertura / edge cases:**
- TTL de clave inexistente = -2 (distinto de -1)
- SET sin EX borra el TTL que hubiera
- GET de clave caducada = nil

**Criterio PASS:**
- `test_ttl_sin_expiracion`, `test_expire_y_ttl`, `test_persist`, `test_set_ex` en verde

---

### F2-4 · server: barrido activo en background

**Título:** F2-4 · server.py: bucle de expiración en segundo plano

**Contexto:** el server lanza una tarea de fondo que llama a `active_sweep` cada segundo.

**Contrato:**
- `__init__` crea `ExpirationManager` y lo pasa al registry
- helper `_spawn` que guarda la referencia de la task (o el GC la mata)
- `_expiration_loop`: `while True: await asyncio.sleep(1); active_sweep()`
- se lanza en `start()`

**Cobertura / edge cases:**
- usar `asyncio.sleep`, nunca `time.sleep`
- guardar referencia de la task

**Criterio PASS (Fase 2 COMPLETA):**
- todos los tests en verde + `redis-cli SET k v EX 100` / `TTL k` / `PERSIST k` funcionan
