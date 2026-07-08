"""Fase 6 — persistencia (unit): snapshot/restore + guardado atómico."""
import asyncio

from myredis.storage import Storage
from myredis.persistence import Persistence


def test_snapshot_restore_roundtrip():
    s = Storage()
    s.set(b"a", b"1")
    s.set(b"b", b"2")
    snap = s.snapshot()
    s2 = Storage()
    s2.restore(snap)
    assert s2.get(b"a") == b"1"
    assert s2.get(b"b") == b"2"


def test_load_sin_fichero_no_peta(tmp_path):
    # cargar cuando el fichero no existe (primer arranque) no debe lanzar
    Persistence(Storage(), path=str(tmp_path / "nope.rdb")).load()


def test_save_crea_fichero_y_recarga(tmp_path):
    path = str(tmp_path / "dump.rdb")
    s = Storage()
    s.set(b"k", b"v")
    asyncio.run(Persistence(s, path=path).save())
    assert (tmp_path / "dump.rdb").exists()

    s2 = Storage()
    Persistence(s2, path=path).load()
    assert s2.get(b"k") == b"v"
