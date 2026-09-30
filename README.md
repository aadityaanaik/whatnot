# tinykv

A tiny key-value store: string keys and values, optional per-key expiry, a
write-ahead log for durability, and a Redis-flavoured text protocol.

```
tinykv/
  clock.py      Clock protocol; SystemClock and FakeClock (for tests)
  store.py      Store: get/set/delete/incr/ttl/scan, expiry, log replay
  wal.py        WriteAheadLog: append-only JSON-lines log
  commands.py   Session: parses one command line and runs it on a Store
  cli.py        Interactive shell
tests/          pytest suite (all passing at the start)
problems/       The practice exercises. Start with INTERVIEW.md.
```

## Setup

Requires Python 3.14. No runtime dependencies.

```sh
python3.14 -m venv .venv
source .venv/bin/activate
pip install pytest
pytest -q
```

(or `uv venv -p 3.14 && uv pip install pytest && uv run pytest -q`)

## Try it

```sh
python -m tinykv --data /tmp/demo.log
tinykv> SET user:1 "Ada Lovelace"
OK
tinykv> SET session:abc token EX 60
OK
tinykv> SCAN user:
user:1=Ada Lovelace
tinykv> INCR visits
1
```

Restart with the same `--data` path and your keys are still there.
