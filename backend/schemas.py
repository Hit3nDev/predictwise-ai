from datetime import datetime
from pydantic import BaseModel


class DatasetOut(BaseModel):
    id: int
    file_name: str
    row_count: int
    column_count: int
    columns: list[str]
    uploaded_at: datetime

    class Config:
        from_attributes = True
