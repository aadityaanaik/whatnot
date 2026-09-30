"""The in-memory store."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .clock import Clock, SystemClock
from .wal import Record, WriteAheadLog


@dataclass(frozen=True, slots=True)
class Entry:
    value: str
    expires_at: float | None = None  # absolute time, see wal.py


class Store:
    """A ``str -> str`` map with optional per-key expiry.

    A key set with ``ttl=N`` is readable for N seconds and gone from then on:
    set at t=100 with ttl=10 means visible at t=109.9, missing at t=110.

    If a write-ahead log is attached, every mutation is appended to it before
    being applied, and ``Store.open`` rebuilds the store from that log.

    With ``compact_threshold`` set, the log is compacted automatically once it
    holds more than that many records and more than twice as many records as
    there are live keys.
    """

    def __init__(
        self,
        clock: Clock | None = None,
        wal: WriteAheadLog | None = None,
        compact_threshold: int | None = None,
    ) -> None:
        self._clock = clock if clock is not None else SystemClock()
        self._wal = wal
        self._compact_threshold = compact_threshold
        self._data: dict[str, Entry] = {}

    @classmethod
    def open(
        cls,
        path: str | Path,
        clock: Clock | None = None,
        compact_threshold: int | None = None,
    ) -> "Store":
        """Load a store from the log at ``path`` (created on first write)."""
        wal = WriteAheadLog(path)
        store = cls(clock=clock, compact_threshold=compact_threshold)
        for record in wal.replay():
            store._apply(record)
        store._wal = wal
        return store

    @property
    def clock(self) -> Clock:
        return self._clock

    # -- reads -------------------------------------------------------------

    def get(self, key: str) -> str | None:
        entry = self._live_entry(key)
        return None if entry is None else entry.value

    def lookup(self, key: str) -> Entry | None:
        """The live entry for ``key`` (value and absolute expiry), if any."""
        return self._live_entry(key)

    def ttl(self, key: str) -> float | None:
        """Seconds until ``key`` expires, or None if it never expires.

        Raises KeyError if the key does not exist.
        """
        entry = self._live_entry(key)
        if entry is None:
            raise KeyError(key)
        if entry.expires_at is None:
            return None
        return entry.expires_at - self._clock.now()

    def scan(self, prefix: str = "") -> list[tuple[str, str]]:
        """All live ``(key, value)`` pairs whose key starts with ``prefix``, sorted by key."""
        self._purge_expired()
        return sorted((k, e.value) for k, e in self._data.items() if k.startswith(prefix))

    def __contains__(self, key: str) -> bool:
        return self._live_entry(key) is not None

    def __len__(self) -> int:
        """Number of live keys."""
        self._purge_expired()
        return len(self._data)

    # -- writes ------------------------------------------------------------

    def set(self, key: str, value: str, ttl: float | None = None) -> None:
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive")
        expires_at = None if ttl is None else self._clock.now() + ttl
        self._write(_set_record(key, Entry(value, expires_at)))

    def delete(self, key: str) -> bool:
        """Remove ``key``. Returns whether it existed."""
        if self._live_entry(key) is None:
            return False
        self._write(_del_record(key))
        return True

    def incr(self, key: str, amount: int = 1) -> int:
        """Add ``amount`` to an integer value (missing keys count as 0).

        The key keeps its existing expiry, if any.
        """
        entry = self._live_entry(key)
        current = 0 if entry is None else parse_int(key, entry.value)
        new_value = current + amount
        expires_at = None if entry is None else entry.expires_at
        self._write(_set_record(key, Entry(str(new_value), expires_at)))
        return new_value

    def apply_batch(self, changes: Mapping[str, Entry | None]) -> None:
        """Apply several changes as one log record (all or nothing on replay).

        Each key maps to its new entry, or to None to delete it.
        """
        records = [
            _del_record(key) if entry is None else _set_record(key, entry)
            for key, entry in changes.items()
        ]
        if records:
            self._write({"op": "batch", "records": records})

    def compact(self) -> None:
        """Rewrite the log to one record per live key. No-op without a log."""
        if self._wal is None:
            return
        self._purge_expired()
        self._wal.rewrite(_set_record(k, e) for k, e in sorted(self._data.items()))

    # -- internals ---------------------------------------------------------

    def _live_entry(self, key: str) -> Entry | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            # Expiry is absolute, so dropping it here needs no log record:
            # replay would recreate it already expired.
            del self._data[key]
            return None
        return entry

    def _is_expired(self, entry: Entry) -> bool:
        return entry.expires_at is not None and self._clock.now() >= entry.expires_at

    def _purge_expired(self) -> None:
        for key in [k for k, e in self._data.items() if self._is_expired(e)]:
            del self._data[key]

    def _write(self, record: Record) -> None:
        if self._wal is not None:
            self._wal.append(record)
        self._apply(record)
        self._maybe_compact()

    def _maybe_compact(self) -> None:
        if self._wal is None or self._compact_threshold is None:
            return
        records = self._wal.record_count
        if records > self._compact_threshold and records > 2 * len(self):
            self.compact()

    def _apply(self, record: Record) -> None:
        match record:
            case {"op": "set", "key": str(key), "value": str(value), "expires_at": expires_at}:
                self._data[key] = Entry(value, expires_at)
            case {"op": "del", "key": str(key)}:
                self._data.pop(key, None)
            case {"op": "batch", "records": list(records)}:
                for inner in records:
                    self._apply(inner)
            case _:
                raise ValueError(f"unrecognised log record: {record!r}")


def parse_int(key: str, value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"value at {key!r} is not an integer") from None


def _set_record(key: str, entry: Entry) -> Record:
    return {"op": "set", "key": key, "value": entry.value, "expires_at": entry.expires_at}


def _del_record(key: str) -> Record:
    return {"op": "del", "key": key}
