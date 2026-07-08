# Fase 6 — Persistencia RDB: SAVE / BGSAVE (snapshots)

> **Meta:** que los datos **sobrevivan a un reinicio**. Guardas un *snapshot* del almacén a disco y lo cargas al arrancar. Aparece la **escritura atómica** (temp + rename) — el mismo edge case que viste en el organizador de descargas y en el mini-Kafka.
>
> **Prerrequisito:** F1 (más datos si tienes F4/F5). **Archivo nuevo:** `persistence.py`. Tocas `storage.py` y `server.py`.

## 1. Concepto
- **RDB = snapshot:** una foto de todo el almacén en un fichero binario. Redis real usa un formato propio; nosotros usamos **`pickle`** (serializa cualquier objeto Python: bytes, deque, dict).
- **Escritura atómica (clave):** escribes a un fichero **temporal** y luego haces **`os.replace(temp, destino)`** — que en POSIX es **atómico**. Así, si el server muere a mitad de escribir, el `dump.rdb` **antiguo queda intacto** (nunca corrupto).
- **No bloquear el event loop:** guardar puede tardar; lo ejecutas en un hilo con **`asyncio.to_thread`** para no congelar el server.

## 2. `storage.py` — snapshot / restore
```python
def snapshot(self) -> dict:
    """Foto del estado para persistir."""
    return {"data": dict(self._data), "expirations": dict(self._expirations)}

def restore(self, snap: dict) -> None:
    """Recarga el estado desde una foto."""
    from collections import OrderedDict
    self._data = OrderedDict(snap.get("data", {}))
    self._expirations = dict(snap.get("expirations", {}))
```

## 3. `persistence.py` — el guardado atómico (NUEVO)
```python
"""Persistencia RDB: snapshot con pickle + escritura atómica (temp + rename)."""
import os
import pickle
import tempfile
from pathlib import Path


class Persistence:
    def __init__(self, storage, path: str = "dump.rdb") -> None:
        self.storage = storage
        self.path = Path(path)

    def _save_sync(self) -> None:
        snap = self.storage.snapshot()
        # temp en la MISMA carpeta que el destino (para que os.replace sea atómico)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent or "."), suffix=".rdb.tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump(snap, f)
                f.flush()
                os.fsync(f.fileno())          # asegura que llega a disco
            os.replace(tmp, self.path)         # ← atómico
        except BaseException:
            os.unlink(tmp)                     # si algo falla, no dejes el temp
            raise

    async def save(self) -> None:
        await asyncio.to_thread(self._save_sync)   # en un hilo, no bloquea el loop

    def load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("rb") as f:
            self.storage.restore(pickle.load(f))
```
> ⚠️ Necesitas `import asyncio` arriba. Y `os.replace` es atómico **solo si temp y destino están en el mismo sistema de ficheros** — por eso el temp se crea en la carpeta del destino.

## 4. Comandos + server

**Comandos:**
- `SAVE` → guarda **sincrónicamente** (bloquea), devuelve "OK".
- `BGSAVE` → dispara el guardado en background, devuelve "Background saving started".

```python
async def cmd_save(self, args):
    await self.persistence.save()
    return "OK"

async def cmd_bgsave(self, args):
    asyncio.create_task(self.persistence.save())   # no espera
    return "Background saving started"
```
(El registry recibe también `persistence`.)

**server.py:**
```python
from myredis.persistence import Persistence

# __init__:
self.persistence = Persistence(self.storage, path="dump.rdb")

# start(): cargar ANTES de aceptar conexiones
self.persistence.load()
# ... start_server ...
self._spawn(self._snapshot_loop())

# bucle de snapshot periódico:
async def _snapshot_loop(self):
    while True:
        await asyncio.sleep(60)      # cada 60s
        await self.persistence.save()

# shutdown: un save final (al recibir SIGINT/SIGTERM)
```

## 5. Tests
```python
def test_save_crea_fichero(redis_client, tmp_path):
    redis_client.set("k", "v")
    redis_client.save()
    # (el conftest debe apuntar MYREDIS_DBFILENAME a tmp_path para verificar el fichero)

def test_persiste_tras_reinicio(...):
    # produce datos, SAVE, reinicia el server sobre el mismo dump.rdb, GET devuelve el dato
    ...
```
> El test de persistencia real (reiniciar y recuperar) necesita relanzar el server sobre el mismo `dump.rdb` — igual que el `test_persists_after_restart` del mini-Kafka. Reusa ese patrón del `conftest`.

## 6. Verificación
```bash
redis-cli -p 6380 SET k persistente
redis-cli -p 6380 SAVE
# mata el server (Ctrl+C) y relánzalo:
python -m myredis
redis-cli -p 6380 GET k    # -> "persistente"  (¡sobrevivió!)
```

## Siguiente
F6 → **Fase 7 (LRU eviction)**: cuando la memoria se llena, echar las claves menos usadas.

## El edge case para tu bitácora
La **escritura atómica** (temp + `os.replace`) es el patrón que ya has visto 3 veces (organizador, Kafka, aquí). Grábatelo: *"para no corromper un fichero ante un crash, escribe a temp y renombra atómicamente."*

## Conexiones
- `docs/fase-1-strings.md` · `PHASES.md` · `issues/fase-6.md` · [[disenar-funciones-y-programas]] (atomicidad)
