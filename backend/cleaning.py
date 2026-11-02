"""
Data cleaning / preprocessing service.

Every operation applied is recorded and returned so the pipeline is
reproducible and auditable — that log is what gets persisted to CleaningLog.
"""

import numpy as np
import pandas as pd


def clean_dataframe(
    df: pd.DataFrame,
    drop_duplicates: bool = True,
    numeric_strategy: str = "median",      # median | mean | zero | drop
    categorical_strategy: str = "mode",    # mode | constant | drop
    outlier_method: str = "none",          # none | iqr_clip
) -> tuple[pd.DataFrame, list[dict]]:
    """Return the cleaned dataframe plus a log of every operation performed."""
    log: list[dict] = []
    out = df.copy()
    start_rows = len(out)

    # --- 1. Normalize text: strip whitespace ------------------------------
    # Done FIRST so that values differing only by padding (" Delhi" vs "Delhi")
    # are recognised as duplicates in the next step.
    for col in out.select_dtypes(include=["object"]).columns:
        # .str.strip() leaves NaN as NaN, unlike .astype(str) which would turn
        # missing values into the literal string "nan" and hide them from imputation.
        before = out[col]
        after = before.str.strip()
        changed = int((before != after).sum())
        if changed:
            out[col] = after
            log.append(
                {
                    "operation": "strip_whitespace",
                    "detail": f"Trimmed whitespace in {changed} value(s) of '{col}'",
                    "rows_affected": changed,
                }
            )

    # --- 2. Duplicate rows -------------------------------------------------
    if drop_duplicates:
        dupes = int(out.duplicated().sum())
        if dupes:
            out = out.drop_duplicates()
            log.append(
                {
                    "operation": "drop_duplicates",
                    "detail": f"Removed {dupes} duplicate row(s)",
                    "rows_affected": dupes,
                }
            )

    # --- 3. Missing values: numeric ---------------------------------------
    numeric_cols = out.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        missing = int(out[col].isna().sum())
        if not missing:
            continue
        if numeric_strategy == "median":
            fill = out[col].median()
        elif numeric_strategy == "mean":
            fill = out[col].mean()
        elif numeric_strategy == "zero":
            fill = 0
        elif numeric_strategy == "drop":
            out = out[out[col].notna()]
            log.append(
                {
                    "operation": "drop_missing_rows",
                    "detail": f"Dropped {missing} row(s) with missing '{col}'",
                    "rows_affected": missing,
                }
            )
            continue
        else:
            fill = out[col].median()
        out[col] = out[col].fillna(fill)
        log.append(
            {
                "operation": "impute_numeric",
                "detail": f"Filled {missing} missing value(s) in '{col}' with {numeric_strategy} ({round(float(fill), 3)})",
                "rows_affected": missing,
            }
        )

    # --- 4. Missing values: categorical -----------------------------------
    cat_cols = out.select_dtypes(exclude=[np.number]).columns
    for col in cat_cols:
        missing = int(out[col].isna().sum())
        if not missing:
            continue
        if categorical_strategy == "drop":
            out = out[out[col].notna()]
            log.append(
                {
                    "operation": "drop_missing_rows",
                    "detail": f"Dropped {missing} row(s) with missing '{col}'",
                    "rows_affected": missing,
                }
            )
            continue
        if categorical_strategy == "mode":
            modes = out[col].mode(dropna=True)
            fill = modes.iloc[0] if len(modes) else "Unknown"
        else:
            fill = "Unknown"
        out[col] = out[col].fillna(fill)
        log.append(
            {
                "operation": "impute_categorical",
                "detail": f"Filled {missing} missing value(s) in '{col}' with '{fill}'",
                "rows_affected": missing,
            }
        )

    # --- 5. Outlier handling ----------------------------------------------
    if outlier_method == "iqr_clip":
        for col in out.select_dtypes(include=[np.number]).columns:
            q1, q3 = out[col].quantile(0.25), out[col].quantile(0.75)
            iqr = q3 - q1
            if iqr == 0 or pd.isna(iqr):
                continue
            low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            affected = int(((out[col] < low) | (out[col] > high)).sum())
            if affected:
                out[col] = out[col].clip(low, high)
                log.append(
                    {
                        "operation": "clip_outliers_iqr",
                        "detail": f"Clipped {affected} outlier(s) in '{col}' to [{round(float(low), 2)}, {round(float(high), 2)}]",
                        "rows_affected": affected,
                    }
                )

    if not log:
        log.append(
            {
                "operation": "no_op",
                "detail": "Dataset was already clean — no changes required",
                "rows_affected": 0,
            }
        )

    return out, log
