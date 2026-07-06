"""
Archivo que se encarga de implementar el Parser de RESP

Cuenta con un encoder y un decoder de RESP, por lo que traduce
RESP -> bytes y bytes -> RESP
"""
from typing import Any

CRLF = b"\r\n"


# -- Encoder: valor Python -> bytes RESP
def encode(value: Any) -> bytes:
    if value is None:
        return b"$-1\r\n"
    if isinstance(value, bool):
        return b":1\r\n" if value else b":0\r\n"
    if isinstance(value, int):
        return b":" + str(value).encode() + CRLF
    if isinstance(value, str):
        return b"+" + str(value).encode() + CRLF
    if isinstance(value, bytes):
        return b"$" + str(len(value)).encode() + CRLF + value + CRLF
    if isinstance(value, (list, tuple)):
        out = b"*" + str(len(value)).encode() +   CRLF
        for item in value:
            out += encode(item)
        return out
    if isinstance(value, Exception):
        return b"-ERR " + str(value).encode() + CRLF
    raise TypeError(f"Cannot encode {type(value).__name__} to RESP")

class ProtocolError(Exception):
    """El byte stream no es RESP válido"""

class RESPParser:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> None:
        self.buffer.extend(data)
    
    def parse(self) -> Any | None:
        """Un mensaje completo (y lo consume), o None si falta data"""

        if not self.buffer:
            return None
        try: 
            value, consumed = self._parse_at(0)
            del self.buffer[:consumed]
            return value
        except IndexError:
            return None
        
    def _parse_at(self, pos: int) -> tuple[Any, int]:
        """Parsea el valor que empieza en buffer[pos:]. Devuelve
        (valor, bytes_consumidos)"""
        if pos >= len(self.buffer):
            raise IndexError("need more data")
        t = self.buffer[pos]
        if t == ord("+"):
            return self._line(pos + 1, decode=True)
        if t == ord("-"):
            v, c = self._line(pos + 1, decode=True)
            return Exception(v), c
        if t == ord(":"):
            v, c = self._line(pos + 1, decode=True)
            return int(v), c
        if t == ord("$"):
            return self._bulk(pos + 1)
        if t == ord("*"):
            return self._array(pos + 1)
        raise ProtocolError(f"Unknow RESP type byte {chr(t)!r}")
    
        
    ## Terminar funcion _parse_at, primero vamos a mirar las funciones auxilares
    
    def _find_crlf(self, start: int) -> int:
        for i in range(start, len(self.buffer) - 1):
            if self.buffer[i] == 0x0D and self.buffer[i + 1] == 0x0A:
                return i
        raise IndexError("no CRLF yet")
    
    def _line(self, pos: int, decode: bool = False) -> tuple[Any, int]:
        end = self._find_crlf(pos)
        raw = bytes(self.buffer[pos:end])
        consumed = end + 2
        return (raw.decode("utf-8"), consumed) if decode else (raw, consumed)
    
    def _bulk(self, pos: int) -> tuple[bytes | None, int]:
        length_str, after = self._line(pos, decode=True)
        length = int(length_str)
        if length == -1:
            return None, after
        
        end = after + length
        if end + 2 > len(self.buffer):
            raise IndexError("need more data for bulk")
        data = bytes(self.buffer[after:end])
        if self.buffer[end:end + 2] != b"\r\n":
            raise ProtocolError("expected CRLF after bulk data")
        return data, end + 2
    
    def _array(self, pos: int) -> tuple[list | None, int]:
        length_str, after = self._line(pos, decode=True)
        length = int(length_str)
        if length == -1:
            return None, after
        items, cursor = [], after
        for _ in range(length):
            item, cursor = self._parse_at(cursor)
            items.append(item)
        return items, cursor
    

    
    
    

