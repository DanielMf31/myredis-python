"""Fase 6 — persistencia (integración): los datos sobreviven a un reinicio.

Requiere que el server lea MYREDIS_DBFILENAME (ver docs/fase-6). Hasta que lo
implementes, este test queda en rojo (TDD)."""


def test_persiste_tras_reinicio(myredis_server, tmp_path):
    dbfile = str(tmp_path / "dump.rdb")

    # 1er arranque: escribe y guarda un snapshot
    with myredis_server(MYREDIS_DBFILENAME=dbfile) as c:
        c.set("curso", "systems")
        c.save()

    # 2º arranque sobre el MISMO dump.rdb: el dato sigue ahí
    with myredis_server(MYREDIS_DBFILENAME=dbfile) as c:
        assert c.get("curso") == b"systems"


def test_bgsave_responde(myredis_server, tmp_path):
    with myredis_server(MYREDIS_DBFILENAME=str(tmp_path / "dump.rdb")) as c:
        c.set("k", "v")
        # redis-py normaliza la respuesta de BGSAVE; basta con que no lance y sea truthy
        assert c.execute_command("BGSAVE")
