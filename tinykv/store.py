"""The in-memory store."""

from dataclasses import dataclass
from pathlib import Path

from .clock import Clock, SystemClock
from .wal import Record, WriteAheadLog


@dataclass(slots=True)
class Entry:
    value: str
    expires_at: float | None = None  # absolute time, see wal.py


class Store:
    """A ``str -> str`` map with optional per-key expiry.

    A key set with ``ttl=N`` is readable for N seconds and gone from then on:
    set at t=100 with ttl=10 means visible at t=109.9, missing at t=110.

    If a write-ahead log is attached, every mutation is appended to it before
    being applied, and ``Store.open`` rebuilds the store from that log.
    """

    def __init__(self, clock: Clock | None = None, wal: WriteAheadLog | None = None) -> None:
        self._clock = clock if clock is not None else SystemClock()
        self._wal = wal
        self._data: dict[str, Entry] = {}

    @classmethod
    def open(cls, path: str | Path, clock: Clock | None = None) -> "Store":
        """Load a store from the log at ``path`` (created on first write)."""
        wal = WriteAheadLog(path)
        store = cls(clock=clock)
        for record in wal.replay():
            store._apply(record)
        store._wal = wal
        return store

    # -- reads -------------------------------------------------------------

    def get(self, key: str) -> str | None:
        entry = self._live_entry(key)
        return None if entry is None else entry.value

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
        return sorted((k, e.value) for k, e in self._data.items() if k.startswith(prefix))

    def __contains__(self, key: str) -> bool:
        return self._live_entry(key) is not None

    def __len__(self) -> int:
        """Number of live keys."""
        return len(self._data)

    # -- writes ------------------------------------------------------------

    def set(self, key: str, value: str, ttl: float | None = None) -> None:
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive")
        expires_at = None if ttl is None else self._clock.now() + ttl
        self._write({"op": "set", "key": key, "value": value, "expires_at": expires_at})

    def delete(self, key: str) -> bool:
        """Remove ``key``. Returns whether it existed."""
        if self._live_entry(key) is None:
            return False
        self._write({"op": "del", "key": key})
        return True

    def incr(self, key: str, amount: int = 1) -> int:
        """Add ``amount`` to an integer value (missing keys count as 0).

        The key keeps its existing expiry, if any.
        """
        entry = self._live_entry(key)
        current = 0 if entry is None else _parse_int(key, entry.value)
        new_value = current + amount
        self._write({"op": "set", "key": key, "value": str(new_value), "expires_at": None})
        return new_value

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
        return entry.expires_at is not None and self._clock.now() > entry.expires_at

    def _write(self, record: Record) -> None:
        if self._wal is not None:
            self._wal.append(record)
        self._apply(record)

    def _apply(self, record: Record) -> None:
        match record:
            case {"op": "set", "key": str(key), "value": str(value), "expires_at": expires_at}:
                self._data[key] = Entry(value, expires_at)
            case {"op": "del", "key": str(key)}:
                self._data.pop(key, None)
            case _:
                raise ValueError(f"unrecognised log record: {record!r}")


def _parse_int(key: str, value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"value at {key!r} is not an integer") from None
