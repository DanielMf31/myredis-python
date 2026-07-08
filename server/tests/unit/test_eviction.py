"""Fase 7 — eviction LRU (unit). Se SALTA hasta que crees eviction.py; entonces
se activa solo (TDD)."""
import pytest

pytest.importorskip("myredis.eviction")

from myredis.storage import Storage
from myredis.eviction import EvictionManager, parse_memory


def test_parse_memory():
    assert parse_memory("5kb") == 5120
    assert parse_memory("1mb") == 1024 * 1024
    assert parse_memory("0") == 0
    assert parse_memory("100") == 100


def test_evict_lru_quita_la_mas_vieja():
    s = Storage()
    for k in (b"a", b"b", b"c"):
        s.set(k, b"x")
    assert s.evict_lru() == b"a"          # la más antigua (front)
    assert s.get(b"a") is None
    assert s.get(b"b") == b"x"


def test_get_refresca_lru():
    s = Storage()
    for k in (b"a", b"b", b"c"):
        s.set(k, b"x")
    s.get(b"a")                            # 'a' pasa a MRU
    assert s.evict_lru() == b"b"           # ahora la más vieja es 'b'


def test_maybe_evict_respeta_maxmemory():
    s = Storage()
    for i in range(200):
        s.set(f"k{i}".encode(), b"x" * 50)
    em = EvictionManager(s, maxmemory=parse_memory("1kb"))
    em.maybe_evict()
    assert s.memory_usage() <= parse_memory("1kb")


def test_maxmemory_cero_no_evicta():
    s = Storage()
    for i in range(50):
        s.set(f"k{i}".encode(), b"x" * 100)
    assert EvictionManager(s, maxmemory=0).maybe_evict() == 0
