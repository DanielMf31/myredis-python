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

def test_incr_desde_cero(redis_client):
    assert redis_client.incr("c") == 1
    assert redis_client.incr("c") == 2

def test_incrby_decrby(redis_client):
    redis_client.set("c", "10")
    assert redis_client.incrby("c", 5) == 15
    assert redis_client.decrby("c", 3) == 12

def test_incr_no_entero(redis_client):
    redis_client.set("c", "hola")
    import redis
    try:
        redis_client.incr("c")
        assert False
    except redis.ResponseError:
        pass

def test_rpush_lrange(redis_client):
    redis_client.rpush("l", "a", "b", "c")
    assert redis_client.lrange("l", 0, -1) == [b"a", b"b", b"c"]

def test_lpush_invierte(redis_client):
    redis_client.lpush("l", "a", "b", "c")
    assert redis_client.lrange("l", 0, -1) == [b"c", b"b", b"a"]

def test_pop_y_llen(redis_client):
    redis_client.rpush("l", "a", "b")
    assert redis_client.lpop("l") == b"a"

def test_wrongtype(redis_client):
    redis_client.set("s", "soy string")
    import redis
    try:
        redis_client.lpush("s", "x")
        assert False
    except redis.ResponseError:
        pass
