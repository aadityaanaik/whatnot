"""Acceptance tests for problem 3. Parts C and D are skipped if not attempted."""

import inspect
import os
from pathlib import Path

import pytest

from tinykv import FakeClock, Session, Store


def lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


# -- Part A ----------------------------------------------------------------


def test_torn_tail_is_discarded(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    store = Store.open(path, clock=clock)
    store.set("a", "1")
    store.set("b", "2")
    with path.open("a") as f:
        f.write('{"op":"set","key":"user:42","val')

    reopened = Store.open(path, clock=clock)
    assert reopened.scan() == [("a", "1"), ("b", "2")]

    # The next append must start on a clean line and survive another reopen.
    reopened.set("c", "3")
    assert Store.open(path, clock=clock).scan() == [("a", "1"), ("b", "2"), ("c", "3")]


def test_torn_tail_only_record(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    path.write_text('{"op":"set"')
    store = Store.open(path, clock=clock)
    assert len(store) == 0
    store.set("a", "1")
    assert Store.open(path, clock=clock).get("a") == "1"


def test_corruption_in_middle_raises(tmp_path: Path, clock: FakeClock) -> None:
    from tinykv.wal import CorruptLogError

    path = tmp_path / "data.log"
    store = Store.open(path, clock=clock)
    store.set("a", "1")
    store.set("b", "2")
    store.set("c", "3")
    content = lines(path)
    content[1] = content[1][:10] + "#garbage#"
    path.write_text("\n".join(content) + "\n")

    with pytest.raises(CorruptLogError, match="2"):
        Store.open(path, clock=clock)


# -- Part B ----------------------------------------------------------------


def build_history(path: Path, clock: FakeClock) -> Store:
    store = Store.open(path, clock=clock)
    for i in range(100):
        store.incr("hot")
    store.set("keep", "v", ttl=100)
    store.set("gone", "v", ttl=5)
    store.set("deleted", "v")
    store.delete("deleted")
    clock.advance(10)
    return store


def test_compact_preserves_state_and_shrinks(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    store = build_history(path, clock)
    before = path.stat().st_size

    store.compact()

    assert path.stat().st_size < before
    assert len(lines(path)) == 2  # hot and keep
    reopened = Store.open(path, clock=clock)
    assert reopened.scan() == [("hot", "100"), ("keep", "v")]
    assert reopened.ttl("keep") == pytest.approx(90)


def test_writes_after_compact_persist(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    store = build_history(path, clock)
    store.compact()
    store.set("new", "1")
    store.delete("hot")
    assert Store.open(path, clock=clock).scan() == [("keep", "v"), ("new", "1")]


def test_crash_during_compact_keeps_old_log(
    tmp_path: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "data.log"
    store = build_history(path, clock)
    original = path.read_bytes()

    def crash(*args: object, **kwargs: object) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", crash)
    monkeypatch.setattr(os, "rename", crash)
    with pytest.raises(OSError):
        store.compact()
    monkeypatch.undo()

    assert path.read_bytes() == original
    assert Store.open(path, clock=clock).scan() == [("hot", "100"), ("keep", "v")]


# -- Part C (stretch) ------------------------------------------------------


@pytest.mark.skipif(
    "compact_threshold" not in inspect.signature(Store.open).parameters,
    reason="part C not attempted",
)
def test_auto_compaction(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    store = Store.open(path, clock=clock, compact_threshold=50)
    for i in range(1_000):
        store.set("counter", str(i))
    assert len(lines(path)) <= 51
    assert Store.open(path, clock=clock).get("counter") == "999"

    # Lots of live keys: the log is not mostly garbage, so no compaction.
    for i in range(200):
        store.set(f"k{i}", "v")
    assert len(lines(path)) >= 200


# -- Part D (stretch) ------------------------------------------------------


def test_commit_is_atomic_in_log(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    session = Session(Store.open(path, clock=clock))
    if session.execute("BEGIN") != "OK":
        pytest.skip("problem 2 not attempted")
    session.execute("SET a 1")
    session.execute("SET b 2")
    session.execute("SET c 3")
    session.execute("COMMIT")
    if len(lines(path)) != 1:
        pytest.skip("part D not attempted")

    # Tear the single commit record: none of it may be applied.
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    assert len(Store.open(path, clock=clock)) == 0
