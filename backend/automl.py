"""
AutoML engine.

Given a cleaned dataframe and a target column, this:
  1. infers whether the task is classification or regression,
  2. builds a preprocessing pipeline (impute + scale numeric, one-hot categorical),
  3. trains several candidate algorithms with cross-validation,
  4. ranks them on a leaderboard and returns the best,
  5. computes permutation feature importance for the winner.

Everything is wrapped in a single sklearn Pipeline so that preprocessing is
fitted on training folds only — this is what prevents the data leakage that
naive "fit the scaler on everything first" implementations suffer from.
"""

import time

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

MAX_CLASSES_FOR_CLASSIFICATION = 20


class TrainingError(Exception):
    """Raised when a dataset can't be trained on, with a user-facing reason."""


# ---------------------------------------------------------------------------
# Task inference
# ---------------------------------------------------------------------------

def infer_task(y: pd.Series) -> str:
    """Decide classification vs regression from the target column itself."""
    if not pd.api.types.is_numeric_dtype(y):
        return "classification"
    clean = y.dropna()
    if clean.empty:
        return "regression"
    unique = clean.nunique()
    # Whole numbers with few distinct values read as classes, not quantities
    # (e.g. a 0/1 "purchased" flag stored as an integer).
    is_whole = bool((clean % 1 == 0).all())
    if is_whole and unique <= MAX_CLASSES_FOR_CLASSIFICATION:
        return "classification"
    return "regression"


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def build_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    numeric_cols = X.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = [c for c in X.columns if c not in numeric_cols]

    numeric_pipe = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    categorical_pipe = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore", max_categories=20)),
        ]
    )

    transformers = []
    if numeric_cols:
        transformers.append(("num", numeric_pipe, numeric_cols))
    if categorical_cols:
        transformers.append(("cat", categorical_pipe, categorical_cols))

    if not transformers:
        raise TrainingError("No usable feature columns found.")

    return ColumnTransformer(transformers, remainder="drop")


# ---------------------------------------------------------------------------
# Candidate models
# ---------------------------------------------------------------------------

def candidate_models(task: str) -> dict:
    if task == "classification":
        return {
            "Logistic Regression": LogisticRegression(max_iter=1000),
            "Decision Tree": DecisionTreeClassifier(max_depth=8, random_state=42),
            "Random Forest": RandomForestClassifier(
                n_estimators=200, random_state=42, n_jobs=-1
            ),
            "Gradient Boosting": GradientBoostingClassifier(random_state=42),
        }
    return {
        "Linear Regression": LinearRegression(),
        "Ridge Regression": Ridge(alpha=1.0),
        "Decision Tree": DecisionTreeRegressor(max_depth=8, random_state=42),
        "Random Forest": RandomForestRegressor(
            n_estimators=200, random_state=42, n_jobs=-1
        ),
        "Gradient Boosting": GradientBoostingRegressor(random_state=42),
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def score_model(task: str, model, X_test, y_test) -> dict:
    preds = model.predict(X_test)
    if task == "classification":
        metrics = {
            "accuracy": round(float(accuracy_score(y_test, preds)), 4),
            "f1": round(
                float(f1_score(y_test, preds, average="weighted", zero_division=0)), 4
            ),
        }
        # ROC-AUC only defined for binary targets with probability output.
        try:
            if len(np.unique(y_test)) == 2 and hasattr(model, "predict_proba"):
                proba = model.predict_proba(X_test)[:, 1]
                metrics["roc_auc"] = round(float(roc_auc_score(y_test, proba)), 4)
        except Exception:
            pass
        return metrics

    rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
    return {
        "r2": round(float(r2_score(y_test, preds)), 4),
        "rmse": round(rmse, 4),
        "mae": round(float(mean_absolute_error(y_test, preds)), 4),
    }


def primary_metric(task: str) -> str:
    return "accuracy" if task == "classification" else "r2"


# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

def feature_importance(pipeline, X_test, y_test, top_n: int = 12) -> list[dict]:
    """
    Permutation importance: shuffle one column at a time and measure how much
    the score drops. Model-agnostic, so it works for linear models and trees
    alike — this is the groundwork the SHAP module builds on later.
    """
    try:
        result = permutation_importance(
            pipeline, X_test, y_test, n_repeats=5, random_state=42, n_jobs=1
        )
    except Exception:
        return []

    rows = [
        {
            "feature": str(col),
            "importance": round(float(result.importances_mean[i]), 4),
            "std": round(float(result.importances_std[i]), 4),
        }
        for i, col in enumerate(X_test.columns)
    ]
    rows.sort(key=lambda r: abs(r["importance"]), reverse=True)
    return rows[:top_n]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_automl(
    df: pd.DataFrame,
    target: str,
    test_size: float = 0.2,
    cv_folds: int = 5,
) -> dict:
    if target not in df.columns:
        raise TrainingError(f"Target column '{target}' is not in the dataset.")

    data = df.dropna(subset=[target])
    if len(data) < 10:
        raise TrainingError(
            f"Need at least 10 rows with a value in '{target}' to train; got {len(data)}."
        )

    y = data[target]
    X = data.drop(columns=[target])

    # Drop columns that are almost certainly identifiers rather than features.
    def _looks_like_id(series: pd.Series, name: str) -> bool:
        lname = name.lower()
        if lname == "id" or lname.endswith("_id") or lname.endswith("id") or lname == "index":
            return True
        if pd.api.types.is_integer_dtype(series):
            s = series.dropna()
            if len(s) > 1 and s.nunique() == len(s):
                ordered = s.sort_values().reset_index(drop=True)
                if (ordered.diff().dropna() == 1).all():
                    return True
        return False

    id_like = [c for c in X.columns if _looks_like_id(X[c], c)]
    if id_like:
        X = X.drop(columns=id_like)
    if X.empty:
        raise TrainingError("No feature columns left after removing identifier columns.")

    task = infer_task(y)

    if task == "classification":
        counts = y.value_counts()
        if len(counts) < 2:
            raise TrainingError(f"Target '{target}' has only one class — nothing to predict.")
        if counts.min() < 2:
            raise TrainingError(
                f"Every class in '{target}' needs at least 2 rows; "
                f"class '{counts.idxmin()}' has {int(counts.min())}."
            )

    stratify = y if (task == "classification" and y.value_counts().min() >= 2) else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=stratify
    )

    # Cross-validation folds can't exceed the smallest class size.
    folds = cv_folds
    if task == "classification":
        folds = int(min(cv_folds, max(2, y_train.value_counts().min())))
    folds = int(min(folds, max(2, len(X_train) // 2)))

    preprocessor = build_preprocessor(X)
    scoring = "accuracy" if task == "classification" else "r2"

    leaderboard = []
    fitted = {}

    for name, estimator in candidate_models(task).items():
        pipe = Pipeline([("prep", preprocessor), ("model", estimator)])
        started = time.perf_counter()
        try:
            cv_scores = cross_val_score(
                pipe, X_train, y_train, cv=folds, scoring=scoring, n_jobs=1
            )
            pipe.fit(X_train, y_train)
            metrics = score_model(task, pipe, X_test, y_test)
            entry = {
                "algorithm": name,
                "cv_mean": round(float(np.mean(cv_scores)), 4),
                "cv_std": round(float(np.std(cv_scores)), 4),
                "train_seconds": round(time.perf_counter() - started, 3),
                "metrics": metrics,
                "status": "ok",
            }
            fitted[name] = pipe
        except Exception as exc:
            entry = {
                "algorithm": name,
                "cv_mean": None,
                "cv_std": None,
                "train_seconds": round(time.perf_counter() - started, 3),
                "metrics": {},
                "status": f"failed: {type(exc).__name__}",
            }
        leaderboard.append(entry)

    ok = [e for e in leaderboard if e["status"] == "ok"]
    if not ok:
        raise TrainingError("Every candidate model failed to train on this dataset.")

    key = primary_metric(task)
    # Rank by cross-validated score on the TRAINING data, not by the test score.
    # Selecting on the test set would leak it into model choice and inflate the
    # metric we then report as an unbiased held-out estimate.
    ok.sort(key=lambda e: (e["cv_mean"] is None, -(e["cv_mean"] or 0)))
    leaderboard = ok + [e for e in leaderboard if e["status"] != "ok"]
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1 if entry["status"] == "ok" else None

    best_name = ok[0]["algorithm"]
    best_pipeline = fitted[best_name]

    return {
        "task": task,
        "target": target,
        "features": list(X.columns),
        "dropped_columns": id_like,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "cv_folds": folds,
        "primary_metric": key,
        "leaderboard": leaderboard,
        "best_algorithm": best_name,
        "best_metrics": ok[0]["metrics"],
        "feature_importance": feature_importance(best_pipeline, X_test, y_test),
        "_pipeline": best_pipeline,
        "_classes": (
            [str(c) for c in best_pipeline.named_steps["model"].classes_]
            if task == "classification"
            else None
        ),
    }
