"""
Exploratory Data Analysis service.

Computes a dataset profile entirely server-side and returns JSON that the
frontend renders as charts. Keeping the computation here (rather than shipping
the raw dataframe to the browser) is what lets this scale to larger files later.
"""

import numpy as np
import pandas as pd


def _py(value):
    """Convert numpy scalars to plain Python types so FastAPI can serialize them."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else round(float(value), 4)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def profile_columns(df: pd.DataFrame) -> list[dict]:
    """Per-column summary: dtype, missing count, unique count, basic stats."""
    out = []
    total = len(df)
    for col in df.columns:
        s = df[col]
        missing = int(s.isna().sum())
        info = {
            "name": str(col),
            "dtype": str(s.dtype),
            "is_numeric": bool(pd.api.types.is_numeric_dtype(s)),
            "missing": missing,
            "missing_pct": round((missing / total) * 100, 2) if total else 0.0,
            "unique": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            info.update(
                {
                    "mean": _py(s.mean()),
                    "std": _py(s.std()),
                    "min": _py(s.min()),
                    "max": _py(s.max()),
                    "median": _py(s.median()),
                }
            )
        else:
            top = s.value_counts(dropna=True).head(1)
            info["top_value"] = str(top.index[0]) if len(top) else None
            info["top_count"] = int(top.iloc[0]) if len(top) else 0
        out.append(info)
    return out


def missing_summary(df: pd.DataFrame) -> list[dict]:
    """Columns that have missing values, sorted worst-first — drives the missing-data bar chart."""
    total = len(df)
    rows = []
    for col in df.columns:
        missing = int(df[col].isna().sum())
        if missing > 0:
            rows.append(
                {
                    "column": str(col),
                    "missing": missing,
                    "missing_pct": round((missing / total) * 100, 2) if total else 0.0,
                }
            )
    return sorted(rows, key=lambda r: r["missing"], reverse=True)


def correlation_matrix(df: pd.DataFrame, max_cols: int = 12) -> dict:
    """Pearson correlation between numeric columns — drives the heatmap."""
    numeric = df.select_dtypes(include=[np.number])
    if numeric.shape[1] < 2:
        return {"columns": [], "matrix": []}
    numeric = numeric.iloc[:, :max_cols]
    corr = numeric.corr(numeric_only=True).fillna(0)
    return {
        "columns": [str(c) for c in corr.columns],
        "matrix": [[round(float(v), 3) for v in row] for row in corr.values],
    }


def histograms(df: pd.DataFrame, bins: int = 10, max_cols: int = 6) -> list[dict]:
    """Binned distributions for numeric columns — drives the distribution charts."""
    numeric = df.select_dtypes(include=[np.number]).iloc[:, :max_cols]
    out = []
    for col in numeric.columns:
        s = numeric[col].dropna()
        if s.empty:
            continue
        counts, edges = np.histogram(s, bins=min(bins, max(1, s.nunique())))
        out.append(
            {
                "column": str(col),
                "bins": [
                    {
                        "label": f"{round(float(edges[i]), 2)}\u2013{round(float(edges[i + 1]), 2)}",
                        "count": int(counts[i]),
                    }
                    for i in range(len(counts))
                ],
            }
        )
    return out


def build_eda(df: pd.DataFrame) -> dict:
    """Full EDA payload for one dataset."""
    return {
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()),
        "total_missing": int(df.isna().sum().sum()),
        "numeric_columns": int(df.select_dtypes(include=[np.number]).shape[1]),
        "categorical_columns": int(df.select_dtypes(exclude=[np.number]).shape[1]),
        "columns": profile_columns(df),
        "missing_summary": missing_summary(df),
        "correlation": correlation_matrix(df),
        "histograms": histograms(df),
        "preview": df.head(10).fillna("").astype(str).to_dict(orient="records"),
    }
