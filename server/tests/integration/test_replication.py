"""Fase 9 — replicación master-réplica (integración). Levanta dos servers y
apunta la réplica al máster. Se SALTA hasta que crees replication.py."""
import time

import pytest
import redis

pytest.importorskip("myredis.replication")


def _wait(fn, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


def test_replica_hace_full_resync_y_sigue_al_master(myredis_server):
    with myredis_server() as master, myredis_server() as replica:
        master.set("antes", "1")                                 # dato previo al sync
        replica.execute_command("REPLICAOF", master.myredis_host, master.myredis_port)
        assert _wait(lambda: replica.get("antes") == b"1")       # full resync
        master.set("despues", "2")                               # propagación en vivo
        assert _wait(lambda: replica.get("despues") == b"2")


def test_replica_es_readonly(myredis_server):
    with myredis_server() as master, myredis_server() as replica:
        replica.execute_command("REPLICAOF", master.myredis_host, master.myredis_port)
        _wait(lambda: b"role:slave" in replica.execute_command("INFO"))
        with pytest.raises(redis.ResponseError):
            replica.set("x", "1")                                # READONLY


def test_info_replication_roles(myredis_server):
    with myredis_server() as master, myredis_server() as replica:
        replica.execute_command("REPLICAOF", master.myredis_host, master.myredis_port)
        assert _wait(lambda: b"role:slave" in replica.execute_command("INFO"))
        assert b"role:master" in master.execute_command("INFO")
