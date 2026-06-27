import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://condodata_test:test_password@localhost:5432/condodata_test",
)


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    with Session(db_engine) as session:
        yield session
        session.rollback()
