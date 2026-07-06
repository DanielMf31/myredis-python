import os, socket, subprocess, sys, time
import pytest
import redis

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture
def redis_client():
    port = _free_port()
    server_dir = os.path.join(os.path.dirname(__file__), "..")
    env = {**os.environ, "PYTHONPATH": server_dir, "MYREDIS_HOST": "127.0.0.1", "MYREDIS_PORT": str(port)}
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
    
    yield client
    client.close()
    proc.terminate()

    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    