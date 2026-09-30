"""Acceptance tests for problem 2. They use only the text protocol."""

from pathlib import Path

from tinykv import FakeClock, Session, Store, WriteAheadLog


def run(session: Session, *lines: str) -> list[str]:
    return [session.execute(line) for line in lines]


def test_example_from_problem(session: Session) -> None:
    assert run(
        session,
        "SET balance:alice 100",
        "BEGIN",
        "INCR balance:alice -30",
        "INCR balance:bob 30",
        "GET balance:alice",
        "ROLLBACK",
        "GET balance:alice",
        "GET balance:bob",
    ) == ["OK", "OK", "70", "30", "70", "OK", "100", "(nil)"]


def test_commit_applies(session: Session, store: Store) -> None:
    run(session, "SET a 1", "BEGIN", "SET a 2", "SET b 3", "DEL a")
    assert store.get("b") is None  # nothing reaches the store before COMMIT
    assert session.execute("COMMIT") == "OK"
    assert store.get("a") is None
    assert store.get("b") == "3"


def test_nested_rollback_only_discards_inner(session: Session) -> None:
    assert run(
        session,
        "BEGIN",
        "SET a outer",
        "BEGIN",
        "SET a inner",
        "SET b inner",
        "GET a",
        "ROLLBACK",
        "GET a",
        "GET b",
        "COMMIT",
        "GET a",
    ) == ["OK", "OK", "OK", "OK", "OK", "inner", "OK", "outer", "(nil)", "OK", "outer"]


def test_nested_commit_merges_into_parent(session: Session, store: Store) -> None:
    run(session, "BEGIN", "BEGIN", "SET a 1", "COMMIT")
    assert store.get("a") is None
    assert session.execute("GET a") == "1"
    run(session, "ROLLBACK")
    assert session.execute("GET a") == "(nil)"


def test_no_transaction_errors(session: Session) -> None:
    assert session.execute("COMMIT") == "ERR no transaction"
    assert session.execute("ROLLBACK") == "ERR no transaction"
    run(session, "BEGIN", "COMMIT")
    assert session.execute("COMMIT") == "ERR no transaction"


def test_scan_and_count_see_pending(session: Session) -> None:
    run(session, "SET k:a 1", "SET k:b 2", "SET k:c 3")
    run(session, "BEGIN", "DEL k:b", "SET k:aa 9", "SET k:c 33", "SET other 0")
    assert session.execute("SCAN k:") == "k:a=1\nk:aa=9\nk:c=33"
    assert session.execute("COUNT") == "4"
    run(session, "BEGIN", "DEL k:a", "SET k:b back")
    assert session.execute("SCAN k:") == "k:aa=9\nk:b=back\nk:c=33"
    run(session, "ROLLBACK", "ROLLBACK")
    assert session.execute("SCAN k:") == "k:a=1\nk:b=2\nk:c=3"
    assert session.execute("COUNT") == "3"


def test_del_counts_against_view(session: Session) -> None:
    run(session, "SET a 1", "BEGIN", "SET b 2", "DEL c")
    assert session.execute("DEL a b c") == "2"
    assert session.execute("DEL a b") == "0"
    run(session, "ROLLBACK")
    assert session.execute("GET a") == "1"


def test_error_leaves_transaction_intact(session: Session) -> None:
    run(session, "BEGIN", "SET n 5", "SET s text")
    assert session.execute("INCR s").startswith("ERR")
    assert session.execute("GET n") == "5"
    assert session.execute("INCR n") == "6"
    assert session.execute("COMMIT") == "OK"
    assert session.execute("GET n") == "6"


def test_ttl_starts_at_commit(session: Session, clock: FakeClock) -> None:
    run(session, "BEGIN", "SET tmp x EX 10")
    clock.advance(100)
    assert session.execute("GET tmp") == "x"
    run(session, "COMMIT")
    clock.advance(9)
    assert session.execute("GET tmp") == "x"
    clock.advance(1)
    assert session.execute("GET tmp") == "(nil)"


def test_incr_in_transaction_keeps_expiry(session: Session, clock: FakeClock) -> None:
    run(session, "SET rl 0 EX 60", "BEGIN", "INCR rl", "COMMIT")
    assert session.execute("TTL rl") == "60"
    clock.advance(60)
    assert session.execute("GET rl") == "(nil)"


def test_sessions_are_isolated(store: Store) -> None:
    alice, bob = Session(store), Session(store)
    run(alice, "BEGIN", "SET shared alice")
    assert bob.execute("GET shared") == "(nil)"
    run(alice, "COMMIT")
    assert bob.execute("GET shared") == "alice"


def test_nothing_logged_until_commit(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    session = Session(Store.open(path, clock=clock))
    run(session, "BEGIN", "SET a 1", "INCR n", "DEL a")
    assert list(WriteAheadLog(path).replay()) == []
    run(session, "COMMIT")
    reopened = Store.open(path, clock=clock)
    assert reopened.get("a") is None
    assert reopened.get("n") == "1"


def test_rolled_back_writes_never_logged(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "data.log"
    session = Session(Store.open(path, clock=clock))
    run(session, "BEGIN", "SET a 1", "ROLLBACK")
    assert Store.open(path, clock=clock).get("a") is None
