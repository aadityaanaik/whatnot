"""Acceptance tests for problem 1. They use only the public API."""

from pathlib import Path

from tinykv import FakeClock, Session, Store


def test_101_key_gone_exactly_at_ttl(store: Store, clock: FakeClock) -> None:
    store.set("otp", "123456", ttl=30)
    clock.advance(29.999)
    assert store.get("otp") == "123456"
    clock.advance(0.001)
    assert store.get("otp") is None
    assert "otp" not in store


def test_102_scan_and_count_hide_expired(session: Session, clock: FakeClock) -> None:
    session.execute("SET session:a 1 EX 10")
    session.execute("SET session:b 2 EX 20")
    session.execute("SET session:c 3")
    clock.advance(10)
    assert session.execute("SCAN session:") == "session:b=2\nsession:c=3"
    assert session.execute("COUNT") == "2"
    clock.advance(10)
    assert session.execute("SCAN") == "session:c=3"
    assert session.execute("COUNT") == "1"


def test_102_len_does_not_trigger_on_get_only(store: Store, clock: FakeClock) -> None:
    store.set("a", "1", ttl=5)
    clock.advance(5)
    # No GET has touched "a"; len and scan must still exclude it.
    assert len(store) == 0
    assert store.scan() == []


def test_103_incr_keeps_expiry(session: Session, clock: FakeClock) -> None:
    session.execute("SET rl:alice 0 EX 60")
    clock.advance(10)
    assert session.execute("INCR rl:alice") == "1"
    assert session.execute("TTL rl:alice") == "50"
    clock.advance(50)
    assert session.execute("GET rl:alice") == "(nil)"
    assert session.execute("INCR rl:alice") == "1"  # fresh counter, no expiry
    assert session.execute("TTL rl:alice") == "-1"


def test_103_incr_expiry_survives_restart(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    store = Store.open(path, clock=clock)
    store.set("rl", "0", ttl=60)
    store.incr("rl")
    clock.advance(59)
    assert Store.open(path, clock=clock).get("rl") == "1"
    clock.advance(1)
    assert Store.open(path, clock=clock).get("rl") is None
