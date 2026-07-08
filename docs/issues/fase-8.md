# Issues de Huly — Fase 8 (Pulido)

> Título → Título de Huly; debajo → Descripción. Labels: `byox-redis`, `fase-8`. Doc: `docs/fase-8-pulido.md`.

---

### F8-1 · comandos de servidor/keyspace

**Título:** F8-1 · commands: DBSIZE, FLUSHDB, KEYS, ECHO, INFO, COMMAND

**Contrato:**
- `DBSIZE` → nº claves · `FLUSHDB` → borra todo, "OK"
- `KEYS pattern` → glob con `fnmatch` · `ECHO` → eco
- `INFO` → bloque de texto con estadísticas
- `COMMAND` → respuesta trivial (que redis-cli no proteste)

**Criterio PASS:** `test_dbsize_flushdb`, `test_keys_pattern` en verde; `redis-cli INFO` funciona

---

### F8-2 · config.py centralizado

**Título:** F8-2 · config.py: Config.from_env (dataclass)

**Contrato:**
- dataclass `Config` con host/port/maxmemory/dbfilename/snapshot_interval
- `from_env()` lee las MYREDIS_*
- `__main__` usa `RedisServer(Config.from_env())`

**Criterio PASS:** el server arranca leyendo la config del entorno; los tests siguen verdes

---

### F8-3 · benchmark vs Redis real

**Título:** F8-3 · benchmarks: comparar con Redis oficial

**Contrato:**
- script que mide ops/s de tu server (6380) vs Redis real (6379) en SET/GET/LPUSH...
- imprime el ratio

**Criterio PASS (Fase 8 = clon básico COMPLETO):**
- benchmark corre y muestra ~10-20× más lento (esperado); número documentado en el README
- (opcional) ADRs de decisiones + README de portfolio + vídeo-walkthrough
