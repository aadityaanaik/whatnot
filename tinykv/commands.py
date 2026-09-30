"""The text protocol.

A ``Session`` takes one command line at a time and returns the response as a
string. Arguments are split shell-style, so values containing spaces can be
quoted: ``SET greeting "hello world"``.

    SET key value [EX seconds]   -> OK
    GET key                      -> value, or (nil)
    DEL key [key ...]            -> number of keys that existed
    INCR key [amount]            -> new value
    TTL key                      -> seconds remaining, -1 if no expiry, -2 if missing
    SCAN [prefix]                -> one "key=value" per line, or (empty)
    COUNT                        -> number of live keys
    BEGIN                        -> OK; transactions nest
    COMMIT                       -> OK; merges into the parent, or applies to the store
    ROLLBACK                     -> OK; discards the innermost transaction

While a transaction is open, writes are buffered in the session and reads see
the store with every open transaction layered on top. ``SET ... EX n`` inside
a transaction starts its clock at the outermost COMMIT; until then ``TTL``
reports the full n seconds.

Errors come back as a single line starting with ``ERR``.
"""

import shlex
from collections.abc import Callable
from dataclasses import dataclass, replace

from .store import Entry, Store, parse_int


class CommandError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Pending:
    """A value written inside a transaction and not yet committed."""

    value: str
    ttl: float | None = None  # relative; the clock starts at the outermost COMMIT
    expires_at: float | None = None  # absolute; inherited from a committed key by INCR


type Layer = dict[str, Pending | None]  # None marks a delete


class Session:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._txns: list[Layer] = []

    def execute(self, line: str) -> str:
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            return f"ERR could not parse command: {exc}"
        if not parts:
            return ""
        name, *args = parts
        handler = COMMANDS.get(name.upper())
        if handler is None:
            return f"ERR unknown command {name!r}"
        try:
            return handler(self, args)
        except CommandError as exc:
            return f"ERR {exc}"
        except ValueError as exc:  # raised by Store for bad values
            return f"ERR {exc}"

    # -- transactions ------------------------------------------------------

    def begin(self) -> None:
        self._txns.append({})

    def commit(self) -> None:
        if not self._txns:
            raise CommandError("no transaction")
        top = self._txns.pop()
        if self._txns:
            self._txns[-1].update(top)
            return
        now = self.store.clock.now()
        changes: dict[str, Entry | None] = {}
        for key, pending in top.items():
            if pending is None:
                changes[key] = None
            elif pending.ttl is not None:
                changes[key] = Entry(pending.value, now + pending.ttl)
            else:
                changes[key] = Entry(pending.value, pending.expires_at)
        self.store.apply_batch(changes)

    def rollback(self) -> None:
        if not self._txns:
            raise CommandError("no transaction")
        self._txns.pop()

    # -- the view that commands read and write -----------------------------

    def get(self, key: str) -> Pending | None:
        for layer in reversed(self._txns):
            if key in layer:
                pending = layer[key]
                return None if pending is None or self._expired(pending) else pending
        entry = self.store.lookup(key)
        return None if entry is None else Pending(entry.value, expires_at=entry.expires_at)

    def set(self, key: str, value: str, ttl: float | None = None) -> None:
        if not self._txns:
            self.store.set(key, value, ttl=ttl)
            return
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive")
        self._txns[-1][key] = Pending(value, ttl=ttl)

    def delete(self, key: str) -> bool:
        if not self._txns:
            return self.store.delete(key)
        existed = self.get(key) is not None
        self._txns[-1][key] = None
        return existed

    def incr(self, key: str, amount: int) -> int:
        if not self._txns:
            return self.store.incr(key, amount)
        current = self.get(key)
        new_value = amount if current is None else parse_int(key, current.value) + amount
        if current is None:
            self._txns[-1][key] = Pending(str(new_value))
        else:
            self._txns[-1][key] = replace(current, value=str(new_value))
        return new_value

    def ttl(self, key: str) -> float | None:
        """Like ``Store.ttl``: KeyError if missing, None if no expiry."""
        pending = self.get(key)
        if pending is None:
            raise KeyError(key)
        if pending.ttl is not None:
            return pending.ttl
        if pending.expires_at is not None:
            return pending.expires_at - self.store.clock.now()
        return None

    def scan(self, prefix: str) -> list[tuple[str, str]]:
        view = dict(self.store.scan(prefix))
        for layer in self._txns:
            for key, pending in layer.items():
                if not key.startswith(prefix):
                    continue
                if pending is None or self._expired(pending):
                    view.pop(key, None)
                else:
                    view[key] = pending.value
        return sorted(view.items())

    def _expired(self, pending: Pending) -> bool:
        return pending.expires_at is not None and self.store.clock.now() >= pending.expires_at


def _arity(args: list[str], low: int, high: int | None, usage: str) -> None:
    if len(args) < low or (high is not None and len(args) > high):
        raise CommandError(f"usage: {usage}")


def _int(text: str, what: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise CommandError(f"{what} must be an integer") from None


def cmd_set(session: Session, args: list[str]) -> str:
    _arity(args, 2, 4, "SET key value [EX seconds]")
    key, value, *options = args
    ttl: int | None = None
    if options:
        if len(options) != 2 or options[0].upper() != "EX":
            raise CommandError("usage: SET key value [EX seconds]")
        ttl = _int(options[1], "EX")
    session.set(key, value, ttl=ttl)
    return "OK"


def cmd_get(session: Session, args: list[str]) -> str:
    _arity(args, 1, 1, "GET key")
    pending = session.get(args[0])
    return "(nil)" if pending is None else pending.value


def cmd_del(session: Session, args: list[str]) -> str:
    _arity(args, 1, None, "DEL key [key ...]")
    return str(sum(session.delete(key) for key in args))


def cmd_incr(session: Session, args: list[str]) -> str:
    _arity(args, 1, 2, "INCR key [amount]")
    amount = _int(args[1], "amount") if len(args) == 2 else 1
    return str(session.incr(args[0], amount))


def cmd_ttl(session: Session, args: list[str]) -> str:
    _arity(args, 1, 1, "TTL key")
    try:
        remaining = session.ttl(args[0])
    except KeyError:
        return "-2"
    return "-1" if remaining is None else f"{remaining:g}"


def cmd_scan(session: Session, args: list[str]) -> str:
    _arity(args, 0, 1, "SCAN [prefix]")
    pairs = session.scan(args[0] if args else "")
    if not pairs:
        return "(empty)"
    return "\n".join(f"{key}={value}" for key, value in pairs)


def cmd_count(session: Session, args: list[str]) -> str:
    _arity(args, 0, 0, "COUNT")
    return str(len(session.scan("")))


def cmd_begin(session: Session, args: list[str]) -> str:
    _arity(args, 0, 0, "BEGIN")
    session.begin()
    return "OK"


def cmd_commit(session: Session, args: list[str]) -> str:
    _arity(args, 0, 0, "COMMIT")
    session.commit()
    return "OK"


def cmd_rollback(session: Session, args: list[str]) -> str:
    _arity(args, 0, 0, "ROLLBACK")
    session.rollback()
    return "OK"


COMMANDS: dict[str, Callable[[Session, list[str]], str]] = {
    "SET": cmd_set,
    "GET": cmd_get,
    "DEL": cmd_del,
    "INCR": cmd_incr,
    "TTL": cmd_ttl,
    "SCAN": cmd_scan,
    "COUNT": cmd_count,
    "BEGIN": cmd_begin,
    "COMMIT": cmd_commit,
    "ROLLBACK": cmd_rollback,
}
