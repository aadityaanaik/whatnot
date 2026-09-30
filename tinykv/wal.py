"""Write-ahead log.

Each mutation is serialised as one JSON object per line and appended to the
log *before* it is applied in memory. Replaying the log from the start
rebuilds the store.

Record shapes:
    {"op": "set", "key": str, "value": str, "expires_at": float | null}
    {"op": "del", "key": str}

``expires_at`` is an absolute timestamp (seconds since the epoch), so a key
set with a TTL before a restart still expires at the right moment after it.
"""

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

type Record = dict[str, Any]


class WriteAheadLog:
    def __init__(self, path: str | Path, *, fsync: bool = True) -> None:
        self.path = Path(path)
        self._fsync = fsync

    def append(self, record: Record) -> None:
        line = json.dumps(record, separators=(",", ":")) + "\n"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            if self._fsync:
                os.fsync(f.fileno())

    def replay(self) -> Iterator[Record]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                yield json.loads(line)
