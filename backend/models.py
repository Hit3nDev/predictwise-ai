"""
SQLAlchemy models — implements the User, Dataset and CleaningLog entities
from the ER diagram in the synopsis. Experiment/Model/Prediction follow as
those modules get built.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    datasets = relationship("Dataset", back_populates="owner")


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    file_name = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    cleaned_path = Column(String, nullable=True)   # set once cleaning has run
    row_count = Column(Integer)
    column_count = Column(Integer)
    columns_json = Column(Text)                     # JSON list of column names
    uploaded_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="datasets")
    cleaning_logs = relationship(
        "CleaningLog", back_populates="dataset", cascade="all, delete-orphan"
    )


class CleaningLog(Base):
    """One row per preprocessing operation applied — makes the pipeline auditable."""

    __tablename__ = "cleaning_logs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    operation = Column(String, nullable=False)
    detail = Column(Text)
    rows_affected = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

    dataset = relationship("Dataset", back_populates="cleaning_logs")
