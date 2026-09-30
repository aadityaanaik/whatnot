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

Errors come back as a single line starting with ``ERR``.
"""

import shlex
from collections.abc import Callable

from .store import Store


class CommandError(Exception):
    pass


class Session:
    def __init__(self, store: Store) -> None:
        self.store = store

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
    session.store.set(key, value, ttl=ttl)
    return "OK"


def cmd_get(session: Session, args: list[str]) -> str:
    _arity(args, 1, 1, "GET key")
    value = session.store.get(args[0])
    return "(nil)" if value is None else value


def cmd_del(session: Session, args: list[str]) -> str:
    _arity(args, 1, None, "DEL key [key ...]")
    return str(sum(session.store.delete(key) for key in args))


def cmd_incr(session: Session, args: list[str]) -> str:
    _arity(args, 1, 2, "INCR key [amount]")
    amount = _int(args[1], "amount") if len(args) == 2 else 1
    return str(session.store.incr(args[0], amount))


def cmd_ttl(session: Session, args: list[str]) -> str:
    _arity(args, 1, 1, "TTL key")
    try:
        remaining = session.store.ttl(args[0])
    except KeyError:
        return "-2"
    return "-1" if remaining is None else f"{remaining:g}"


def cmd_scan(session: Session, args: list[str]) -> str:
    _arity(args, 0, 1, "SCAN [prefix]")
    pairs = session.store.scan(args[0] if args else "")
    if not pairs:
        return "(empty)"
    return "\n".join(f"{key}={value}" for key, value in pairs)


def cmd_count(session: Session, args: list[str]) -> str:
    _arity(args, 0, 0, "COUNT")
    return str(len(session.store))


COMMANDS: dict[str, Callable[[Session, list[str]], str]] = {
    "SET": cmd_set,
    "GET": cmd_get,
    "DEL": cmd_del,
    "INCR": cmd_incr,
    "TTL": cmd_ttl,
    "SCAN": cmd_scan,
    "COUNT": cmd_count,
}
