import contextlib
import os
import socket
import subprocess
import sys
import time

import pytest
import redis


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _spawn_server(**env_overrides):
    """Arranca un myredis real en un puerto libre con env arbitrario.
    Devuelve (proc, client). El cliente lleva .myredis_host / .myredis_port
    para poder apuntar una réplica a un máster."""
    port = _free_port()
    server_dir = os.path.join(os.path.dirname(__file__), "..")
    env = {
        **os.environ,
        "PYTHONPATH": server_dir,
        "MYREDIS_HOST": "127.0.0.1",
        "MYREDIS_PORT": str(port),
        **{k: str(v) for k, v in env_overrides.items()},
    }
    proc = subprocess.Popen([sys.executable, "-m", "myredis"], env=env)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("myredis no arranco")
    client = redis.Redis(host="127.0.0.1", port=port, decode_responses=False)
    client.myredis_host = "127.0.0.1"
    client.myredis_port = port
    return proc, client


def _stop(proc, client):
    try:
        client.close()
    except Exception:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def myredis_server():
    """Fábrica de servers como context manager. Permite arrancar varios (p.ej.
    máster + réplica) o simular un reinicio con dos `with` seguidos sobre el
    mismo MYREDIS_DBFILENAME.

        with myredis_server(MYREDIS_MAXMEMORY="5kb") as c:
            c.set("k", "v")
    """
    started = []

    @contextlib.contextmanager
    def factory(**env):
        proc, client = _spawn_server(**env)
        started.append((proc, client))
        try:
            yield client
        finally:
            _stop(proc, client)
            if (proc, client) in started:
                started.remove((proc, client))

    yield factory
    for proc, client in started:
        _stop(proc, client)


@pytest.fixture
def redis_client(myredis_server):
    """Un único server con config por defecto (lo que usan los tests de F0–F5)."""
    with myredis_server() as client:
        yield client
