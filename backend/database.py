"""
Database connection setup.

SQLite locally, so there is zero setup friction. In the cloud DATABASE_URL
points at Amazon RDS for PostgreSQL (cloud.py builds it from Secrets Manager):
    postgresql+psycopg2://user:password@host:5432/predictwise
Nothing else in the codebase changes.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL") or "sqlite:///./predictwise.db"

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # pool_pre_ping drops connections RDS closed while idle instead of failing a request.
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema(bind=None):
    """
    Create missing tables AND add missing columns to existing ones.

    `Base.metadata.create_all` only creates tables that don't exist; it never
    touches a table that does. So a database file from an older version of the
    app crashes with "no such column" the moment a model gains a field. This
    compares each model against the live file and runs ALTER TABLE ADD COLUMN
    for anything missing, so upgrading never means deleting your data.
    (A production deployment would use Alembic migrations for the same job.)
    """
    from sqlalchemy import inspect, text

    eng = bind or engine
    Base.metadata.create_all(bind=eng)
    inspector = inspect(eng)
    added = []
    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                coltype = col.type.compile(dialect=eng.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'))
                added.append(f"{table.name}.{col.name}")
    if added:
        print(f"[database] upgraded old schema, added: {', '.join(added)}", flush=True)
    return added
