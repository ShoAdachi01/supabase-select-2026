"""Bounded tabular experiments with a separate final holdout."""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.datasets import load_wine
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

MAX_ROWS = 25000
MAX_COLUMNS = 50


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean_json(v) for v in value]
    if isinstance(value, np.generic):
        return clean_json(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if pd.isna(value):
        return None
    return value


def sample_dataset(kind: str) -> tuple[pd.DataFrame, str, str, str]:
    if kind == "wine":
        wine = load_wine(as_frame=True)
        frame = wine.data.round(3)
        frame["cultivar"] = wine.target.map({0: "cultivar_1", 1: "cultivar_2", 2: "cultivar_3"})
        return (
            frame,
            "Wine cultivars",
            "UCI Wine recognition dataset, distributed with scikit-learn. 178 real observations.",
            "cultivar",
        )
    rng = np.random.default_rng(42)
    if kind == "energy":
        n = 1200
        frame = pd.DataFrame(
            {
                "temperature_c": rng.uniform(5, 38, n).round(1),
                "occupancy": rng.integers(5, 130, n),
                "floor_area_m2": rng.integers(200, 2500, n),
                "building_type": rng.choice(["office", "retail", "warehouse"], n),
                "hour": rng.integers(6, 23, n),
            }
        )
        frame["energy_kwh"] = (
            20
            + frame.occupancy * 0.65
            + frame.floor_area_m2 * 0.035
            + np.maximum(frame.temperature_c - 22, 0) * 3
            + (frame.building_type == "retail") * 25
            + rng.normal(0, 7, n)
        ).round(1)
        return (
            frame,
            "Building energy",
            "Simulated operational data, generated with a fixed seed. Not evidence of real-world performance.",
            "energy_kwh",
        )
    if kind != "shipments":
        raise ValueError("Unknown sample dataset.")
    n = 1600
    frame = pd.DataFrame(
        {
            "distance_km": rng.integers(20, 1800, n),
            "warehouse_load": rng.uniform(0.1, 1, n).round(2),
            "weather": rng.choice(["clear", "rain", "storm"], n, p=[0.6, 0.3, 0.1]),
            "carrier": rng.choice(["standard", "express", "economy"], n),
            "priority": rng.choice(["normal", "urgent"], n, p=[0.8, 0.2]),
            "items": rng.integers(1, 20, n),
        }
    )
    score = (
        (frame.distance_km > 1000) * 1.2
        + frame.warehouse_load * 2.5
        + (frame.weather == "storm") * 2
        + (frame.weather == "rain") * 0.6
        + (frame.carrier == "economy") * 0.8
        - (frame.carrier == "express") * 0.8
        - (frame.priority == "urgent") * 0.5
        + rng.normal(0, 0.35, n)
    )
    frame["delayed"] = np.where(score > 2.5, "delayed", "on_time")
    # Deliberately include a post-outcome field so the demo can catch leakage.
    frame["actual_delivery_days"] = np.where(
        frame.delayed == "delayed", rng.integers(5, 9, n), rng.integers(1, 5, n)
    )
    frame.loc[rng.choice(n, 38, replace=False), "warehouse_load"] = np.nan
    return (
        frame,
        "Shipment delays",
        "Simulated operational data, generated with a fixed seed. Not evidence of real-world performance.",
        "delayed",
    )


def inspect_frame(frame: pd.DataFrame) -> dict:
    if not 50 <= len(frame) <= MAX_ROWS:
        raise ValueError(f"Use between 50 and {MAX_ROWS:,} rows for this demo.")
    if not 2 <= len(frame.columns) <= MAX_COLUMNS:
        raise ValueError(f"Use between 2 and {MAX_COLUMNS} columns.")
    if frame.columns.duplicated().any() or any(not str(c).strip() for c in frame.columns):
        raise ValueError("Column names must be unique and non-empty.")
    columns = []
    issues = []
    for name in frame.columns:
        series = frame[name]
        numeric = pd.api.types.is_numeric_dtype(series)
        unique = int(series.nunique())
        missing = int(series.isna().sum())
        excluded = False
        reason = None
        if unique <= 1:
            excluded, reason = True, "Constant or empty column"
        elif missing / len(frame) > 0.6:
            excluded, reason = True, "More than 60% missing"
        elif name.lower().endswith(("_id", "_uuid")) or name.lower() in ("id", "uuid"):
            excluded, reason = True, "Identifier, not a predictive feature"
        elif name.lower().startswith(("actual_", "final_", "outcome_")) or name.lower() in (
            "delivered_at",
            "resolved_at",
            "closed_at",
        ):
            excluded, reason = True, "Post-outcome field: possible target leakage"
        elif not numeric and unique > min(100, len(frame) * 0.5):
            excluded, reason = True, "High-cardinality text: needs a dedicated representation"
        if reason:
            issues.append({"column": str(name), "severity": "warning", "message": reason})
        elif missing:
            issues.append(
                {
                    "column": str(name),
                    "severity": "info",
                    "message": f"{missing} missing values; impute using training data only",
                }
            )
        columns.append(
            {
                "name": str(name),
                "type": "number" if numeric else "category",
                "unique": unique,
                "missing": missing,
                "excluded": excluded,
                "reason": reason,
                "examples": clean_json(series.dropna().unique()[:6]),
                "min": clean_json(series.min()) if numeric else None,
                "max": clean_json(series.max()) if numeric else None,
            }
        )
    duplicate_count = int(frame.duplicated().sum())
    if duplicate_count:
        issues.append(
            {
                "column": "*",
                "severity": "info",
                "message": f"{duplicate_count} exact duplicate rows; remove before splitting",
            }
        )
    return {
        "rows": len(frame),
        "columns": columns,
        "preview": clean_json(frame.head(8).to_dict("records")),
        "issues": issues,
        "missing_cells": int(frame.isna().sum().sum()),
        "duplicates": duplicate_count,
    }


def task_type(frame: pd.DataFrame, target: str) -> str:
    series = frame[target].dropna()
    return (
        "classification"
        if not pd.api.types.is_numeric_dtype(series) or series.nunique() <= 10
        else "regression"
    )


def train_experiment(
    frame: pd.DataFrame,
    target: str,
    features: list[str],
    task: str,
    emit: Callable,
    split: str = "random",
    time_column: str | None = None,
) -> tuple[Pipeline, dict]:
    started = time.perf_counter()
    if (
        target not in frame
        or not features
        or target in features
        or len(features) != len(set(features))
    ):
        raise ValueError(
            "Choose an existing target and distinct input features that exclude the target."
        )
    if any(f not in frame for f in features):
        raise ValueError("An input feature does not exist in this dataset.")
    if task not in ("classification", "regression"):
        raise ValueError("Choose classification or regression.")
    used = list(dict.fromkeys(features + [target] + ([time_column] if time_column else [])))
    if time_column and (
        time_column not in frame or time_column in features or time_column == target
    ):
        raise ValueError("The time column must exist and be separate from features and target.")
    data = frame[used].dropna(subset=[target]).replace([np.inf, -np.inf], np.nan).drop_duplicates()
    if len(data) < 50:
        raise ValueError("At least 50 distinct labeled rows are needed.")
    if any(data[f].isna().all() for f in features):
        raise ValueError("An input feature has no usable values.")
    y = data[target]
    if task == "classification":
        y = y.astype(str)
        counts = y.value_counts()
        if not 2 <= len(counts) <= 20 or counts.min() < 5:
            raise ValueError(
                "Classification needs 2–20 classes, each with at least 5 labeled examples."
            )
    else:
        y = pd.to_numeric(y, errors="coerce")
        if y.isna().any() or y.nunique() < 2:
            raise ValueError("Regression needs a numeric, non-constant target with finite values.")
    X = data[features].copy()
    numeric = X.select_dtypes(include="number").columns.tolist()
    categorical = [f for f in features if f not in numeric]
    for f in categorical:
        X[f] = X[f].map(lambda v: str(v) if pd.notna(v) else np.nan)
    if split == "temporal":
        if not time_column:
            raise ValueError("Choose a date column for a chronological split.")
        dates = pd.to_datetime(data[time_column], errors="coerce", utc=True)
        if dates.isna().any():
            raise ValueError("All dates must be parseable for a chronological split.")
        order = dates.sort_values(kind="stable").index
        X, y = X.loc[order], y.loc[order]
        a, b = int(len(X) * 0.6), int(len(X) * 0.8)
        # Keep identical timestamps on one side of each boundary.
        sorted_dates = dates.loc[order]
        while a < len(X) and sorted_dates.iloc[a] == sorted_dates.iloc[a - 1]:
            a += 1
        b = max(a + 1, b)
        while b < len(X) and sorted_dates.iloc[b] == sorted_dates.iloc[b - 1]:
            b += 1
        if min(a, b - a, len(X) - b) < 5:
            raise ValueError(
                "Too few distinct time periods to create three usable chronological partitions."
            )
        X_train, X_val, X_test = X.iloc[:a], X.iloc[a:b], X.iloc[b:]
        y_train, y_val, y_test = y.iloc[:a], y.iloc[a:b], y.iloc[b:]
    elif split == "random":
        stratify = y if task == "classification" else None
        X_dev, X_test, y_dev, y_test = train_test_split(
            X, y, test_size=0.2, random_state=17, stratify=stratify
        )
        X_train, X_val, y_train, y_val = train_test_split(
            X_dev,
            y_dev,
            test_size=0.25,
            random_state=18,
            stratify=y_dev if task == "classification" else None,
        )
    else:
        raise ValueError("Unknown split strategy.")
    if task == "classification" and len(set(y_train)) < 2:
        raise ValueError("The training partition needs at least two outcome classes.")
    emit(
        "Data prepared",
        f"{len(X_train):,} train / {len(X_val):,} validation / {len(X_test):,} untouched test rows.",
    )
    emit(
        "Leakage controls applied",
        "Target excluded; preprocessing learns from training rows only. Confirm that every feature is available at prediction time.",
    )

    def pipeline(estimator):
        transformers = []
        if numeric:
            transformers.append(
                (
                    "numeric",
                    Pipeline(
                        [
                            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                            ("scale", StandardScaler()),
                        ]
                    ),
                    numeric,
                )
            )
        if categorical:
            transformers.append(
                (
                    "category",
                    Pipeline(
                        [
                            ("impute", SimpleImputer(strategy="most_frequent")),
                            (
                                "encode",
                                OneHotEncoder(
                                    handle_unknown="ignore", sparse_output=False, max_categories=30
                                ),
                            ),
                        ]
                    ),
                    categorical,
                )
            )
        return Pipeline([("prepare", ColumnTransformer(transformers)), ("model", estimator)])

    if task == "classification":
        candidates = [
            ("Majority baseline", DummyClassifier(strategy="most_frequent")),
            (
                "Logistic regression",
                LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
            ),
            (
                "Random forest",
                RandomForestClassifier(
                    n_estimators=100,
                    max_depth=12,
                    min_samples_leaf=3,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=2,
                ),
            ),
        ]
        metric = "Balanced accuracy"
        score_fn = balanced_accuracy_score
        higher_better = True
    else:
        candidates = [
            ("Median baseline", DummyRegressor(strategy="median")),
            ("Ridge regression", Ridge(alpha=1)),
            (
                "Random forest",
                RandomForestRegressor(
                    n_estimators=100, max_depth=12, min_samples_leaf=3, random_state=42, n_jobs=2
                ),
            ),
        ]
        metric = "Mean absolute error"
        score_fn = mean_absolute_error
        higher_better = False
    leaderboard, fitted = [], {}
    for name, estimator in candidates:
        tick = time.perf_counter()
        emit(
            f"Training {name.lower()}",
            "Compare on validation data; final test data stays separate.",
        )
        model = pipeline(estimator)
        model.fit(X_train, y_train)
        score = float(score_fn(y_val, model.predict(X_val)))
        leaderboard.append(
            {
                "name": name,
                "score": score,
                "seconds": round(time.perf_counter() - tick, 3),
                "baseline": "baseline" in name,
            }
        )
        fitted[name] = model
    leaderboard.sort(key=lambda m: m["score"], reverse=higher_better)
    selected = leaderboard[0]
    best = fitted[selected["name"]]
    baseline_name = candidates[0][0]
    pred = best.predict(X_test)
    test_score = float(score_fn(y_test, pred))
    baseline_score = float(score_fn(y_test, fitted[baseline_name].predict(X_test)))
    emit(
        "Final holdout evaluated",
        f"{selected['name']} selected on validation; now evaluated once on {len(X_test):,} test rows.",
    )
    importance = []
    if not selected["baseline"]:
        perm = permutation_importance(
            best,
            X_val,
            y_val,
            n_repeats=3,
            random_state=42,
            scoring="balanced_accuracy" if higher_better else "neg_mean_absolute_error",
            n_jobs=2,
        )
        importance = sorted(
            [
                {"feature": f, "value": max(0, float(v))}
                for f, v in zip(features, perm.importances_mean, strict=True)
            ],
            key=lambda x: -x["value"],
        )
    model_schema = inspect_frame(frame)["columns"]
    input_schema = [c for c in model_schema if c["name"] in features]
    result = {
        "selected_model": selected["name"],
        "task": task,
        "metric": metric,
        "higher_better": higher_better,
        "test_score": test_score,
        "baseline_score": baseline_score,
        "leaderboard": leaderboard,
        "splits": {
            "train": len(X_train),
            "validation": len(X_val),
            "test": len(X_test),
            "strategy": split,
        },
        "training_seconds": round(time.perf_counter() - started, 3),
        "importance": importance,
        "input_schema": input_schema,
        "example_input": clean_json(X_test.iloc[0].to_dict()),
        "baseline_only": selected["baseline"],
        "target": target,
        "features": features,
        "test_examples": clean_json(
            [
                {"actual": actual, "predicted": p}
                for actual, p in zip(y_test.iloc[:30], pred[:30], strict=True)
            ]
        ),
        "labels": sorted(y.unique().tolist()) if task == "classification" else [],
        "confusion_matrix": confusion_matrix(y_test, pred, labels=sorted(y.unique())).tolist()
        if task == "classification"
        else [],
        "metrics": {
            "accuracy": float(accuracy_score(y_test, pred)),
            "f1_weighted": float(f1_score(y_test, pred, average="weighted")),
        }
        if task == "classification"
        else {"mae": test_score, "r2": float(r2_score(y_test, pred))},
        "notes": [
            "Final holdout was not used to fit preprocessing or select the model.",
            "Feature importance measures validation score drop under permutation; it is not a causal explanation.",
            "Model probabilities are not independently calibrated.",
            "A random split does not establish performance on future time periods; use chronological splitting for temporal tasks.",
        ],
    }
    return best, clean_json(result)


def predict(model: Pipeline, result: dict, records: list[dict]) -> dict:
    if not 1 <= len(records) <= 1000:
        raise ValueError("Send between 1 and 1,000 records.")
    warnings = []
    schema = result["input_schema"]
    cleaned = []
    for index, record in enumerate(records):
        missing = [field["name"] for field in schema if field["name"] not in record]
        if missing:
            raise ValueError(f"Row {index + 1}: missing required fields: {', '.join(missing)}.")
        row = {}
        for field in schema:
            name, value = field["name"], record[field["name"]]
            if isinstance(value, (dict, list)):
                raise ValueError(f"Row {index + 1}: {name} must be a scalar value.")
            if value is None:
                row[name] = np.nan
                warnings.append(f"{name}: missing value imputed from training data.")
            elif field["type"] == "number":
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    raise ValueError(f"{name} must be numeric.") from None
                if not np.isfinite(value):
                    raise ValueError(f"{name} must be finite.")
                row[name] = value
                if value < field["min"] or value > field["max"]:
                    warnings.append(f"{name}: outside the observed dataset range.")
            else:
                row[name] = str(value)
        cleaned.append(row)
    frame = pd.DataFrame(cleaned)[result["features"]]
    tick = time.perf_counter()
    predictions = model.predict(frame)
    probabilities = model.predict_proba(frame) if result["task"] == "classification" else None
    elapsed = (time.perf_counter() - tick) * 1000
    return clean_json(
        {
            "predictions": [
                {
                    "value": value,
                    "probabilities": dict(zip(model.classes_, probabilities[i], strict=True))
                    if probabilities is not None
                    else None,
                }
                for i, value in enumerate(predictions)
            ],
            "inference_ms": round(elapsed, 2),
            "model": result["selected_model"],
            "warnings": list(dict.fromkeys(warnings)),
            "tokens_used_for_prediction": 0,
        }
    )
