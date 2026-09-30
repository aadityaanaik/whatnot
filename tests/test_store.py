import pytest

from tinykv import FakeClock, Store


def test_set_and_get(store: Store) -> None:
    store.set("a", "1")
    assert store.get("a") == "1"
    assert store.get("missing") is None


def test_overwrite(store: Store) -> None:
    store.set("a", "1")
    store.set("a", "2")
    assert store.get("a") == "2"


def test_delete(store: Store) -> None:
    store.set("a", "1")
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert store.get("a") is None


def test_contains(store: Store) -> None:
    store.set("a", "1")
    assert "a" in store
    assert "b" not in store


def test_key_readable_before_ttl(store: Store, clock: FakeClock) -> None:
    store.set("session", "abc", ttl=10)
    clock.advance(5)
    assert store.get("session") == "abc"
    assert store.ttl("session") == pytest.approx(5)


def test_key_gone_well_after_ttl(store: Store, clock: FakeClock) -> None:
    store.set("session", "abc", ttl=10)
    clock.advance(60)
    assert store.get("session") is None
    with pytest.raises(KeyError):
        store.ttl("session")


def test_ttl_none_without_expiry(store: Store) -> None:
    store.set("a", "1")
    assert store.ttl("a") is None


def test_ttl_must_be_positive(store: Store) -> None:
    with pytest.raises(ValueError):
        store.set("a", "1", ttl=0)


def test_incr(store: Store) -> None:
    assert store.incr("hits") == 1
    assert store.incr("hits", 5) == 6
    assert store.get("hits") == "6"


def test_incr_non_integer(store: Store) -> None:
    store.set("name", "bob")
    with pytest.raises(ValueError):
        store.incr("name")


def test_scan_prefix_sorted(store: Store) -> None:
    for key in ["user:2", "user:1", "order:1", "user:10"]:
        store.set(key, key.upper())
    assert store.scan("user:") == [
        ("user:1", "USER:1"),
        ("user:10", "USER:10"),
        ("user:2", "USER:2"),
    ]
    assert len(store.scan()) == 4


def test_len(store: Store) -> None:
    store.set("a", "1")
    store.set("b", "2")
    store.delete("a")
    assert len(store) == 1
