"""Persistencia RDB: snapshot con pickle + escritura atómica (temp + rename)"""

import os
import pickle
import tempfile
from pathlib import Path
from myredis.storage import Storage
import asyncio

class Persistence:
    def __init__(self, storage: Storage, path: str = "dump.rdb") -> None:
        self.storage = storage
        self.path = Path(path)

    def _save_sync(self) -> None:
        snap = self.storage.snapshot()
        
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent or "."), suffix=".rdb.tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump(snap, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            os.unlink(tmp)
            raise

    async def save(self) -> None:
        await asyncio.to_thread(self._save_sync)

    def load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("rb") as f:
            self.storage.restore(pickle.load(f))
        
                