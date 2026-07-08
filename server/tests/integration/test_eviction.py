"""Fase 7 — eviction LRU (integración). Requiere MYREDIS_MAXMEMORY + el hook de
eviction en execute(). Se SALTA hasta que crees eviction.py."""
import pytest

pytest.importorskip("myredis.eviction")


def test_evicta_los_viejos(myredis_server):
    with myredis_server(MYREDIS_MAXMEMORY="5kb") as c:
        for i in range(500):
            c.set(f"k{i}", "x" * 100)
        assert c.get("k0") is None                 # la primera (más vieja) fue evictada
        assert c.get("k499") == b"x" * 100         # la última sigue viva


def test_get_salva_de_eviction(myredis_server):
    with myredis_server(MYREDIS_MAXMEMORY="5kb") as c:
        c.set("importante", "x" * 100)
        for i in range(500):
            c.get("importante")                    # tocarla la mantiene reciente
            c.set(f"k{i}", "x" * 100)
        assert c.get("importante") == b"x" * 100   # sobrevivió por ser MRU
