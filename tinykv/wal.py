"""Write-ahead log.

Each mutation is serialised as one JSON object per line and appended to the
log *before* it is applied in memory. Replaying the log from the start
rebuilds the store.

Record shapes:
    {"op": "set", "key": str, "value": str, "expires_at": float | null}
    {"op": "del", "key": str}
    {"op": "batch", "records": [<set or del record>, ...]}

``expires_at`` is an absolute timestamp (seconds since the epoch), so a key
set with a TTL before a restart still expires at the right moment after it.

A record is only complete once its trailing newline is on disk: ``append``
writes the record and its newline in one call, so a crash mid-append leaves a
final line with no newline. ``replay`` discards such a torn tail and truncates
it away. Any other unreadable line is real corruption and raises
``CorruptLogError``.
"""

import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

type Record = dict[str, Any]


class CorruptLogError(Exception):
    pass


class WriteAheadLog:
    def __init__(self, path: str | Path, *, fsync: bool = True) -> None:
        self.path = Path(path)
        self._fsync = fsync
        # Records currently in the file. Accurate once replay() has run
        # (Store.open always replays before writing).
        self.record_count = 0

    def append(self, record: Record) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(_encode(record))
            f.flush()
            if self._fsync:
                os.fsync(f.fileno())
        self.record_count += 1

    def replay(self) -> Iterator[Record]:
        self.record_count = 0
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        *lines, tail = data.split(b"\n")  # tail is b"" when the file ends cleanly
        for line_no, raw in enumerate(lines, start=1):
            try:
                record = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise CorruptLogError(f"{self.path}: line {line_no} is corrupt: {exc}") from exc
            if not isinstance(record, dict):
                raise CorruptLogError(f"{self.path}: line {line_no} is not a record")
            self.record_count += 1
            yield record
        if tail:
            # Torn final write. Cut it off so the next append starts on a clean line.
            with self.path.open("r+b") as f:
                f.truncate(len(data) - len(tail))
                f.flush()
                if self._fsync:
                    os.fsync(f.fileno())

    def rewrite(self, records: Iterable[Record]) -> None:
        """Atomically replace the whole log with ``records``.

        The new log is written to a temporary file, flushed to disk, then
        renamed over the old one. ``os.replace`` is atomic, so a crash at any
        point leaves either the complete old log or the complete new one.
        """
        tmp = self.path.with_name(self.path.name + ".compact.tmp")
        count = 0
        try:
            with tmp.open("w", encoding="utf-8") as f:
                for record in records:
                    f.write(_encode(record))
                    count += 1
                f.flush()
                if self._fsync:
                    os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        if self._fsync:
            _fsync_dir(self.path.parent)  # make the rename itself durable
        self.record_count = count


def _encode(record: Record) -> str:
    return json.dumps(record, separators=(",", ":")) + "\n"


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
