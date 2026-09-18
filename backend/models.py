"""
SQLAlchemy models — implements User, Dataset, CleaningLog, Experiment,
MLModel and Prediction from the ER diagram in the synopsis.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Text
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
    cleaned_path = Column(String, nullable=True)
    row_count = Column(Integer)
    column_count = Column(Integer)
    columns_json = Column(Text)
    uploaded_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="datasets")
    cleaning_logs = relationship(
        "CleaningLog", back_populates="dataset", cascade="all, delete-orphan"
    )
    experiments = relationship(
        "Experiment", back_populates="dataset", cascade="all, delete-orphan"
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


class Experiment(Base):
    """One AutoML run against one dataset and target column."""

    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    target_column = Column(String, nullable=False)
    task_type = Column(String, nullable=False)          # classification | regression
    status = Column(String, default="completed")        # completed | failed
    primary_metric = Column(String)
    n_train = Column(Integer)
    n_test = Column(Integer)
    cv_folds = Column(Integer)
    features_json = Column(Text)
    error_message = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    dataset = relationship("Dataset", back_populates="experiments")
    ml_models = relationship(
        "MLModel", back_populates="experiment", cascade="all, delete-orphan"
    )


class MLModel(Base):
    """One trained candidate. The winner has is_best=1 and a saved artifact."""

    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True, index=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    algorithm = Column(String, nullable=False)
    rank = Column(Integer)
    is_best = Column(Integer, default=0)
    cv_mean = Column(Float)
    cv_std = Column(Float)
    train_seconds = Column(Float)
    metrics_json = Column(Text)
    importance_json = Column(Text)
    classes_json = Column(Text)
    artifact_path = Column(String)
    status = Column(String, default="ok")
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=utcnow)

    experiment = relationship("Experiment", back_populates="ml_models")
    predictions = relationship(
        "Prediction", back_populates="ml_model", cascade="all, delete-orphan"
    )


class Prediction(Base):
    """A prediction served from a saved model, kept for auditing and monitoring."""

    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("ml_models.id"), nullable=False)
    input_json = Column(Text)
    output_json = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    ml_model = relationship("MLModel", back_populates="predictions")
