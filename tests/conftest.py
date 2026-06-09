import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.base import Base


@pytest.fixture()
def db_session():
    """Fresh SQLite in-memory DB per test — no external MySQL required."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
