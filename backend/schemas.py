from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class DatasetOut(BaseModel):
    id: int
    file_name: str
    row_count: int
    column_count: int
    columns: list[str]
    uploaded_at: datetime
    is_cleaned: bool = False

    class Config:
        from_attributes = True


class CleaningOptions(BaseModel):
    drop_duplicates: bool = True
    numeric_strategy: str = "median"        # median | mean | zero | drop
    categorical_strategy: str = "mode"      # mode | constant | drop
    outlier_method: str = "none"            # none | iqr_clip


class CleaningLogOut(BaseModel):
    operation: str
    detail: Optional[str] = None
    rows_affected: int = 0


class CleaningResult(BaseModel):
    dataset_id: int
    rows_before: int
    rows_after: int
    columns: int
    operations: list[CleaningLogOut]


class EDAResult(BaseModel):
    dataset_id: int
    source: str          # "raw" or "cleaned"
    row_count: int
    column_count: int
    duplicate_rows: int
    total_missing: int
    numeric_columns: int
    categorical_columns: int
    columns: list[dict[str, Any]]
    missing_summary: list[dict[str, Any]]
    correlation: dict[str, Any]
    histograms: list[dict[str, Any]]
    preview: list[dict[str, Any]]


# --- AutoML -----------------------------------------------------------------

class TrainRequest(BaseModel):
    target: str
    test_size: float = 0.2
    cv_folds: int = 5


class LeaderboardEntry(BaseModel):
    model_config = {"protected_namespaces": ()}

    rank: Optional[int] = None
    algorithm: str
    cv_mean: Optional[float] = None
    cv_std: Optional[float] = None
    train_seconds: Optional[float] = None
    metrics: dict[str, Any] = {}
    status: str = "ok"
    is_best: bool = False
    model_id: Optional[int] = None


class FeatureImportance(BaseModel):
    feature: str
    importance: float
    std: float = 0.0


class ExperimentResult(BaseModel):
    experiment_id: int
    dataset_id: int
    task: str
    target: str
    features: list[str]
    dropped_columns: list[str] = []
    n_train: int
    n_test: int
    cv_folds: int
    primary_metric: str
    best_algorithm: str
    best_metrics: dict[str, Any]
    best_model_id: int
    leaderboard: list[LeaderboardEntry]
    feature_importance: list[FeatureImportance] = []


class PredictRequest(BaseModel):
    rows: list[dict[str, Any]]


class PredictionOut(BaseModel):
    row: dict[str, Any]
    prediction: Any
    confidence: Optional[float] = None
    probabilities: Optional[dict[str, float]] = None


class PredictResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_id: int
    algorithm: str
    task: str
    target: str
    results: list[PredictionOut]


# --- Simple Mode --------------------------------------------------------

class TemplateAvailability(BaseModel):
    id: str
    label: str
    hint: str
    available: bool
    reason: Optional[str] = None


class AskRequest(BaseModel):
    question: Optional[str] = None
    template_id: Optional[str] = None


class FieldSpec(BaseModel):
    name: str
    label: str
    type: str                    # "number" | "select"
    options: Optional[list[str]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    typical: Optional[float] = None


class AskResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    matched_template: str
    matched_label: str
    kind: str                     # "profile" | "ranking" | "predictable"
    narrative: list[str]
    target: Optional[str] = None
    experiment_id: Optional[int] = None
    model_id: Optional[int] = None
    fields: list[FieldSpec] = []
    ranking: Optional[list[dict]] = None
