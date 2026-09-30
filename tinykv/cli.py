"""Interactive shell: ``python -m tinykv [--data PATH]``."""

import argparse
import sys

from .commands import Session
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tinykv", description=__doc__)
    parser.add_argument("--data", help="write-ahead log path; in-memory only if omitted")
    args = parser.parse_args(argv)

    store = Store.open(args.data) if args.data else Store()
    session = Session(store)
    interactive = sys.stdin.isatty()

    while True:
        if interactive:
            print("tinykv> ", end="", flush=True)
        line = sys.stdin.readline()
        if not line:
            break
        if line.strip().upper() in {"QUIT", "EXIT"}:
            break
        response = session.execute(line)
        if response:
            print(response)
    return 0
