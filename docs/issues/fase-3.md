# Issues de Huly — Fase 3 (Contadores)

> Título → Título de Huly; debajo → Descripción. Labels: `byox-redis`, `fase-3`. Doc: `docs/fase-3-contadores.md`.

---

### F3-1 · INCR / DECR / INCRBY / DECRBY

**Título:** F3-1 · commands: contadores atómicos

**Contexto:** operaciones sobre números guardados como string. Un helper `_incr_by(key, delta)` y cuatro comandos que lo usan.

**Contrato:**
- `INCR`/`DECR` → ±1; `INCRBY`/`DECRBY key n` → ±n
- clave inexistente empieza en 0
- valor no entero → error `ERR value is not an integer or out of range`
- el resultado se guarda como string (`str(v).encode()`)

**Cobertura / edge cases:**
- INCR desde cero (clave nueva)
- INCR sobre valor no numérico → error, no crash
- respeta TTL (llama a check_and_expire si tienes F2)

**Criterio PASS (Fase 3 COMPLETA):**
- `test_incr_desde_cero`, `test_incrby_decrby`, `test_incr_no_entero` en verde
- `redis-cli INCR / INCRBY` funcionan
