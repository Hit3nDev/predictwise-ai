"""
Database connection setup.

Using SQLite for local development so there is zero setup friction on day one.
To move to PostgreSQL later, just change SQLALCHEMY_DATABASE_URL to something like:
    postgresql://user:password@localhost:5432/predictwise
and add `psycopg2-binary` to requirements.txt. Nothing else in the codebase changes.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = "sqlite:///./predictwise.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
