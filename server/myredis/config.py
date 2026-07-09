import os
from dataclasses import dataclass

from myredis.eviction import parse_memory

@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 6380
    maxmemory: int = 0
    dbfilename: str = "dump.rdb"
    snapshot_interval: int = 60

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            host=os.environ.get("MYREDIS_HOST", "0.0.0.0"),
            port=int(os.environ.get("MYREDIS_PORT", "6380")),
            maxmemory=parse_memory(os.environ.get("MYREDIS_MAXMEMORY", "0")),
            dbfilename=os.environ.get("MYREDIS_DBFILENAME", "dump.rdb"),
            snapshot_interval=int(os.environ.get("MYREDIS_SNAPSHOT_INTERVAL", "60")),
        )