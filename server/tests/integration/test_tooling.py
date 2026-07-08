"""Fase 8 — tooling (integración): DBSIZE / FLUSHDB / KEYS / TYPE / INFO.
Se SALTA hasta que implementes la fase 8 (marcador: Storage.type_of)."""
import pytest

from myredis.storage import Storage

pytestmark = pytest.mark.skipif(
    not hasattr(Storage, "type_of"), reason="fase 8 (tooling) no implementada"
)


def _norm(t):
    return t if isinstance(t, bytes) else t.encode()


def test_dbsize_flushdb(myredis_server):
    with myredis_server() as c:
        c.set("a", "1")
        c.set("b", "2")
        assert c.dbsize() == 2
        c.flushdb()
        assert c.dbsize() == 0


def test_keys_pattern(myredis_server):
    with myredis_server() as c:
        c.set("user:1", "a")
        c.set("user:2", "b")
        c.set("post:1", "c")
        assert set(c.keys("user:*")) == {b"user:1", b"user:2"}
        assert c.keys("nada:*") == []


def test_type(myredis_server):
    with myredis_server() as c:
        c.set("s", "v")
        c.rpush("l", "a")
        c.hset("h", mapping={"f": "v"})
        assert _norm(c.execute_command("TYPE", "s")) == b"string"
        assert _norm(c.execute_command("TYPE", "l")) == b"list"
        assert _norm(c.execute_command("TYPE", "h")) == b"hash"
        assert _norm(c.execute_command("TYPE", "nope")) == b"none"


def test_info(myredis_server):
    with myredis_server() as c:
        raw = c.execute_command("INFO")
        assert b"role:master" in raw
        assert b"redis_version" in raw
