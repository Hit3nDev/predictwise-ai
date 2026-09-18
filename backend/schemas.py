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
