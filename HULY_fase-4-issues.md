# Issues de Huly — Fase 4 (Listas)

> Título → Título de Huly; debajo → Descripción. Labels: `byox-redis`, `fase-4`. Doc: `docs/fase-4-listas.md`.

---

### F4-1 · helper de tipo lista + WRONGTYPE

**Título:** F4-1 · commands: helper `_get_list` + WRONGTYPE

**Contexto:** el valor de una clave puede ser ahora un `collections.deque`. Un helper devuelve la deque (o error si la clave guarda otro tipo).

**Contrato:**
- `_get_list(key, create=False)`: deque, None, o WRONGTYPE si no es deque
- `_drop_if_empty(key, d)`: borra la clave si la lista quedó vacía
- deque (no list) por O(1) en ambos extremos

**Criterio PASS:**
- LPUSH sobre una clave string da WRONGTYPE (no crash)

---

### F4-2 · LPUSH / RPUSH / LPOP / RPOP / LLEN / LRANGE

**Título:** F4-2 · commands: comandos de lista

**Contexto:** los seis comandos de lista sobre la deque.

**Contrato:**
- `LPUSH/RPUSH` → añaden, devuelven longitud; LPUSH invierte el orden
- `LPOP/RPOP` → sacan un extremo (nil si vacía); auto-borran la clave si queda vacía
- `LLEN` → longitud (0 si no existe)
- `LRANGE start stop` → sublista; índices negativos desde el final; **stop INCLUSIVO** (`items[start:stop+1]`)

**Cobertura / edge cases:**
- LPUSH a b c → [c, b, a]
- LRANGE 0 -1 = lista entera
- pop que vacía la lista borra la clave
- WRONGTYPE

**Criterio PASS (Fase 4 COMPLETA):**
- `test_rpush_lrange`, `test_lpush_invierte`, `test_pop_y_llen`, `test_wrongtype` en verde
