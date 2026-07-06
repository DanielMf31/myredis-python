from myredis.storage import Storage

def test_set_get_expiration():
    s = Storage()
    s.set(b"k", b"v")
    s.set_expiration(b"k", 1000)
    assert s.get(b"k") == b"v"
    assert s.get_expiration(b"k") == 1000

def test_remove_expiration():
    s = Storage()
    s.set(b"k", b"v")
    s.set_expiration(b"k", 1000)
    assert s.get(b"k") == b"v"
    s.remove_expiration(b"k")
    assert s.get_expiration(b"k") is None
