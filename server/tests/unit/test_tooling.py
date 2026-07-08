"""Fase 8 — tooling (unit): Storage.keys / flush / type_of. Se SALTA hasta que
implementes esos métodos en Storage."""
from collections import deque

import pytest

from myredis.storage import Storage

pytestmark = pytest.mark.skipif(
    not hasattr(Storage, "type_of"), reason="fase 8 (tooling) no implementada"
)


def test_keys_y_flush():
    s = Storage()
    s.set(b"a", b"1")
    s.set(b"b", b"2")
    assert set(s.keys()) == {b"a", b"b"}
    s.flush()
    assert s.keys() == []
    assert s.dbsize() == 0


def test_type_of():
    s = Storage()
    s.set(b"s", b"v")
    s.set(b"l", deque([b"a"]))
    s.set(b"h", {b"f": b"v"})
    assert s.type_of(b"s") == "string"
    assert s.type_of(b"l") == "list"
    assert s.type_of(b"h") == "hash"
    assert s.type_of(b"nope") == "none"
