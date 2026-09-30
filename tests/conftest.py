import pytest

from tinykv import FakeClock, Session, Store


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(start=1_000.0)


@pytest.fixture
def store(clock: FakeClock) -> Store:
    return Store(clock=clock)


@pytest.fixture
def session(store: Store) -> Session:
    return Session(store)
