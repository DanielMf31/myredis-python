"""Fase 8 — Config.from_env (unit). Se SALTA hasta que crees config.py."""
import pytest

pytest.importorskip("myredis.config")

from myredis.config import Config


def test_from_env(monkeypatch):
    monkeypatch.setenv("MYREDIS_PORT", "7000")
    monkeypatch.setenv("MYREDIS_MAXMEMORY", "5kb")
    cfg = Config.from_env()
    assert cfg.port == 7000
    assert cfg.maxmemory == 5120


def test_defaults(monkeypatch):
    for v in ("MYREDIS_HOST", "MYREDIS_PORT", "MYREDIS_MAXMEMORY", "MYREDIS_DBFILENAME"):
        monkeypatch.delenv(v, raising=False)
    cfg = Config.from_env()
    assert cfg.port == 6380
    assert cfg.maxmemory == 0
    assert cfg.host == "0.0.0.0"
