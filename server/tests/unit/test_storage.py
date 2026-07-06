from myredis.storage import Storage

def test_set_get():
    s = Storage()
    s.set(b"k", b"v")
    assert s.get(b"k") == b"v"

def test_get_missing():
    assert Storage().get(b"nope") is None

def test_set_overwrite():
    s = Storage()
    s.set(b"k", b"v1")
    s.set(b"k", b"v2")
    assert s.get(b"k") == b"v2"

def test_delete():
    s = Storage()
    s.set(b"k", b"v")
    assert s.delete(b"k") is True
    assert s.delete(b"k") is False

def test_exists():
    s = Storage()
    s.set(b"k", b"v")
    assert s.exists(b"k") is True
    assert s.exists(b"k2") is False 

