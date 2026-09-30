from pathlib import Path

from tinykv import FakeClock, Store, WriteAheadLog


def test_reopen_restores_state(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    store = Store.open(path, clock=clock)
    store.set("a", "1")
    store.set("b", "2")
    store.delete("a")
    store.incr("n", 3)

    reopened = Store.open(path, clock=clock)
    assert reopened.get("a") is None
    assert reopened.get("b") == "2"
    assert reopened.get("n") == "3"


def test_missing_log_is_empty_store(tmp_path: Path, clock: FakeClock) -> None:
    store = Store.open(tmp_path / "nope.log", clock=clock)
    assert len(store) == 0


def test_expiry_survives_restart(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    Store.open(path, clock=clock).set("tmp", "x", ttl=30)

    clock.advance(20)
    assert Store.open(path, clock=clock).get("tmp") == "x"

    clock.advance(20)
    assert Store.open(path, clock=clock).get("tmp") is None


def test_every_mutation_is_logged(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    store = Store.open(path, clock=clock)
    store.set("a", "1")
    store.delete("a")
    store.delete("a")  # no-op, not logged

    records = list(WriteAheadLog(path).replay())
    assert [r["op"] for r in records] == ["set", "del"]
