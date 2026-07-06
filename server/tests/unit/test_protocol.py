from myredis.protocol import RESPParser, encode

# 1. Tests encoder

def test_encode_simple_string(): assert encode("OK") == b"+OK\r\n"
def test_encode_integer(): assert encode(42) == b":42\r\n"
def test_encode_bulk(): assert encode(b"hello") == b"$5\r\nhello\r\n"
def test_encode_null(): assert encode(None) == b"$-1\r\n"
def test_encode_array(): assert encode([b"foo", b"bar"]) == b"*2\r\n$3\r\nfoo\r\n$3\r\nbar\r\n"
def test_encode_empty_array(): assert encode([]) == b"*0\r\n"
def test_encode_nested_mixed(): assert encode([1, b"x", None]) == b"*3\r\n:1\r\n$1\r\nx\r\n$-1\r\n"
def test_encode_error(): assert encode(Exception("bad command")) == b"-ERR bad command\r\n"
def test_encode_bool(): assert encode(True) == b":1\r\n"; assert encode(False) == b":0\r\n"

# 2. Tests parser

def _one(data):
    p = RESPParser()
    p.feed(data)
    return p.parse()

def test_parse_simple(): assert _one(b"+PONG\r\n") == "PONG"
def test_parse_integer(): assert _one(b":1000\r\n") == 1000
def test_parse_bulk(): assert _one(b"$5\r\nhello\r\n") == b"hello"
def test_parse_null_bulk(): assert _one(b"$-1\r\n") is None
def test_parse_command(): assert _one(b"*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n") == [b"SET", b"foo", b"bar"]

# 3. Tests framing 

def test_partial_data():
    p = RESPParser()
    p.feed(b"$5\r\nhel")
    assert p.parse() is None
    p.feed(b"lo\r\n"); 
    assert p.parse() == b"hello"

def test_multiple_in_buffer():
    p = RESPParser()
    p.feed(b"+PONG\r\n+OK\r\n")
    assert p.parse() == "PONG"
    assert p.parse() == "OK"
    assert p.parse() is None

def test_roundtrip():
    p = RESPParser()
    p.feed(encode(b"hello"))
    assert p.parse() == b"hello"


