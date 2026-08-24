"""
SQLAlchemy models — the initial slice of the ER diagram from the synopsis.
Only User and Dataset are implemented today; Experiment/Model/Prediction etc.
get added as those modules are built.
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
    row_count = Column(Integer)
    column_count = Column(Integer)
    columns_json = Column(Text)  # JSON-encoded list of column names/dtypes
    uploaded_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="datasets")
