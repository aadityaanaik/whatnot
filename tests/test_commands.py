from tinykv import FakeClock, Session


def test_set_get(session: Session) -> None:
    assert session.execute("SET a 1") == "OK"
    assert session.execute("GET a") == "1"
    assert session.execute("GET b") == "(nil)"


def test_commands_are_case_insensitive(session: Session) -> None:
    assert session.execute("set a 1") == "OK"
    assert session.execute("get a") == "1"


def test_quoted_values(session: Session) -> None:
    session.execute('SET greeting "hello world"')
    assert session.execute("GET greeting") == "hello world"


def test_del_counts_existing(session: Session) -> None:
    session.execute("SET a 1")
    session.execute("SET b 2")
    assert session.execute("DEL a b c") == "2"


def test_incr(session: Session) -> None:
    assert session.execute("INCR n") == "1"
    assert session.execute("INCR n 10") == "11"
    session.execute("SET s text")
    assert session.execute("INCR s").startswith("ERR")


def test_set_with_expiry(session: Session, clock: FakeClock) -> None:
    assert session.execute("SET tmp x EX 10") == "OK"
    assert session.execute("TTL tmp") == "10"
    clock.advance(30)
    assert session.execute("GET tmp") == "(nil)"
    assert session.execute("TTL tmp") == "-2"


def test_ttl_without_expiry(session: Session) -> None:
    session.execute("SET a 1")
    assert session.execute("TTL a") == "-1"


def test_scan(session: Session) -> None:
    assert session.execute("SCAN") == "(empty)"
    session.execute("SET k:b 2")
    session.execute("SET k:a 1")
    session.execute("SET other 3")
    assert session.execute("SCAN k:") == "k:a=1\nk:b=2"


def test_count(session: Session) -> None:
    session.execute("SET a 1")
    session.execute("SET b 2")
    assert session.execute("COUNT") == "2"


def test_errors(session: Session) -> None:
    assert session.execute("FLY away").startswith("ERR unknown command")
    assert session.execute("GET").startswith("ERR usage")
    assert session.execute("SET a 1 EX soon").startswith("ERR")
    assert session.execute("SET a 1 PX 5").startswith("ERR usage")
    assert session.execute('SET a "unterminated').startswith("ERR")
    assert session.execute("   ") == ""
