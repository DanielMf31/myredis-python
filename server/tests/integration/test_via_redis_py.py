def test_ping(redis_client):
    assert redis_client.ping() is True

def test_set_get(redis_client):
    assert redis_client.set("foo", "bar") is True
    assert redis_client.get("foo") == b"bar"

def test_get_noexistent(redis_client):
    assert redis_client.get("nope") is None

def test_delete(redis_client):
    redis_client.set("a", "1")
    redis_client.set("b", "2")
    assert redis_client.delete("a", "b", "c") == 2

def test_exists(redis_client):
    redis_client.set("foo", "bar")
    assert redis_client.exists("foo") == 1
    assert redis_client.exists("nope") == 0

def test_ttl_sin_expiracion(redis_client):
    redis_client.set("k", "v")
    assert redis_client.ttl("k") == -1

def test_expire_y_ttl(redis_client):
    redis_client.set("k", "v")
    assert redis_client.expire("k", 100) is True
    assert 0 < redis_client.ttl("k") <= 100

def test_persist(redis_client):
    redis_client.set("k", "v", ex=100)
    assert redis_client.persist("k") is True
    assert redis_client.ttl("k") == -1

def test_set_ex(redis_client):
    redis_client.set("k", "v", ex=100)
    assert 0 < redis_client.ttl("k") <= 100



    