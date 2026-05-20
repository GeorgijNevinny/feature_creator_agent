#!/usr/bin/env python3
"""Проверка кандидатов признаков на eda/tesla.csv (time-series CV)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from src.feature_compute import compute_ohlcv_features  # noqa: E402

TESLA_PATH = Path(__file__).resolve().parents[2] / "eda" / "tesla.csv"
TOP5 = [
    "gap_from_prev_close_pct",
    "vwap_proxy_dev",
    "volatility_20d",
    "intraday_range_pct",
    "volume_zscore_20",
]


def main() -> None:
    df = pd.read_csv(TESLA_PATH, parse_dates=["date"]).sort_values("date")
    enriched = compute_ohlcv_features(df, names=TOP5)
    c = pd.to_numeric(df["close"], errors="coerce")
    y = (c.shift(-1) > c).astype(int)
    base_cols = ["open", "high", "low", "close", "volume"]
    data = enriched[base_cols + TOP5].copy()
    data["target"] = y
    data = data.dropna()
    yv = data["target"].values
    Xb = data[base_cols].values
    tscv = TimeSeriesSplit(n_splits=5)
    clf = GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42)

    def cv_auc(X: np.ndarray) -> float:
        scores = []
        for tr, te in tscv.split(X):
            pipe = Pipeline([("sc", StandardScaler()), ("clf", clf)])
            pipe.fit(X[tr], yv[tr])
            proba = pipe.predict_proba(X[te])[:, 1]
            if len(np.unique(yv[te])) >= 2:
                scores.append(roc_auc_score(yv[te], proba))
        return float(np.mean(scores)) if scores else 0.5

    baseline = cv_auc(Xb)
    print(f"Baseline ROC-AUC: {baseline:.4f}\n")
    ranked = []
    for fname in TOP5:
        X = np.column_stack([Xb, data[fname].values.reshape(-1, 1)])
        auc = cv_auc(X)
        ranked.append((fname, auc, auc - baseline))
    ranked.sort(key=lambda x: x[2], reverse=True)
    for i, (fname, auc, delta) in enumerate(ranked, 1):
        print(f"{i}. {fname}: AUC={auc:.4f}  delta={delta:+.4f}")


if __name__ == "__main__":
    main()
