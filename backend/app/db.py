import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# DATABASE_URL is the hosting-platform convention (Render/Heroku/Supabase);
# PM_TRIAGE_DB_URL is the app-specific override. SQLite remains the zero-infra
# default for local dev and the test suite.
DB_URL = os.getenv("DATABASE_URL") or os.getenv("PM_TRIAGE_DB_URL", "sqlite:///./pm_triage.db")

# Platforms hand out postgres:// URLs; SQLAlchemy 2.x needs an explicit driver.
if DB_URL.startswith("postgres://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgres://"):]
elif DB_URL.startswith("postgresql://"):
    DB_URL = "postgresql+psycopg://" + DB_URL[len("postgresql://"):]

IS_SQLITE = DB_URL.startswith("sqlite")

# On a shared Postgres instance the app lives in its own schema so it never
# collides with other tenants of the database.
DB_SCHEMA = os.getenv("PM_TRIAGE_DB_SCHEMA", "" if IS_SQLITE else "pm_triage")

if IS_SQLITE:
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
else:
    connect_args = {}
    if DB_SCHEMA:
        connect_args["options"] = f"-csearch_path={DB_SCHEMA},public"
    engine = create_engine(
        DB_URL,
        connect_args=connect_args,
        pool_pre_ping=True,   # free-tier poolers drop idle connections
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create the schema (Postgres) and all tables. Idempotent."""
    if not IS_SQLITE and DB_SCHEMA:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"'))
    Base.metadata.create_all(engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
