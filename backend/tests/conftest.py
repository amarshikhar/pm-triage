import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PM_TRIAGE_DB_URL"] = "sqlite:///:memory:"
os.environ["LLM_MODE"] = "mock"
os.environ["SIM_ENABLED"] = "0"
os.environ["CMMS_RETRY_BACKOFF_S"] = "0"  # no backoff sleeps in tests

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.db import Base
from app.seed import seed_if_empty


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    # route the app's module-level SessionLocal (used by audit/simulator) to the test engine
    db_module.SessionLocal.configure(bind=engine)
    session = TestSession()
    seed_if_empty(session)
    yield session
    session.close()
