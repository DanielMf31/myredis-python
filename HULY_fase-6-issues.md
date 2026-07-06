# Issues de Huly — Fase 6 (Persistencia RDB)

> Título → Título de Huly; debajo → Descripción. Labels: `byox-redis`, `fase-6`. Doc: `docs/fase-6-persistencia.md`.

---

### F6-1 · storage: snapshot / restore

**Título:** F6-1 · storage.py: snapshot y restore

**Contrato:**
- `snapshot()` → dict con data + expirations
- `restore(snap)` → recarga el estado

**Criterio PASS:** unit: snapshot y restore preservan los datos

---

### F6-2 · persistence.py (escritura atómica)

**Título:** F6-2 · persistence.py: snapshot RDB con escritura atómica

**Contexto:** guarda el snapshot a disco con pickle, de forma atómica (temp + os.replace), sin bloquear el event loop.

**Contrato:**
- `_save_sync`: pickle a un temp EN LA MISMA carpeta → fsync → `os.replace(temp, destino)` (atómico)
- `save()`: `asyncio.to_thread(_save_sync)`
- `load()`: si existe el fichero, restaura
- ante fallo, borra el temp (no dejes basura)

**Cobertura / edge cases:**
- crash a mitad → el dump.rdb antiguo queda intacto (atomicidad)
- temp en la misma carpeta que el destino (os.replace solo es atómico en el mismo FS)
- fichero inexistente → load no peta

**Criterio PASS:** unit: save+load hace roundtrip del estado

---

### F6-3 · comandos SAVE / BGSAVE + server (load + loop + shutdown)

**Título:** F6-3 · SAVE/BGSAVE + carga al arrancar + snapshot periódico

**Contrato:**
- `SAVE` → save síncrono, "OK"; `BGSAVE` → `create_task(save())`, "Background saving started"
- server: `persistence.load()` ANTES de aceptar conexiones
- `_snapshot_loop`: save cada 60s
- shutdown: un save final

**Criterio PASS (Fase 6 COMPLETA):**
- `redis-cli SET k v; SAVE` → matar server → relanzar → `GET k` devuelve el dato (persistió)
