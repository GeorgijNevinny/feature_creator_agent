"""Вычисление признаков для превью (OHLCV / Tesla и похожие датасеты)."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

_EPS = 1e-9


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def _pick_col(columns: list[str], *needles: str) -> str | None:
    for col in columns:
        nn = _norm(col)
        for needle in needles:
            if needle in nn:
                return col
    return None


def ohlcv_column_map(df: pd.DataFrame) -> dict[str, str] | None:
    cols = [str(c) for c in df.columns]
    close = _pick_col(cols, "close", "adj_close", "adjclose")
    if not close:
        return None
    mapping = {
        "close": close,
        "open": _pick_col(cols, "open") or close,
        "high": _pick_col(cols, "high") or close,
        "low": _pick_col(cols, "low") or close,
        "volume": _pick_col(cols, "volume", "vol") or "",
        "date": _pick_col(cols, "date", "time", "timestamp", "dt") or "",
    }
    return mapping


def compute_ohlcv_features(df: pd.DataFrame, names: list[str] | None = None) -> pd.DataFrame:
    """
  Добавляет типовые OHLCV-признаки. Если ``names`` задан — только перечисленные.
  Датасет сортируется по date при наличии колонки даты.
  """
    work = df.copy()
    cmap = ohlcv_column_map(work)
    if not cmap:
        return work

    if cmap.get("date"):
        work = work.sort_values(cmap["date"]).reset_index(drop=True)

    c = pd.to_numeric(work[cmap["close"]], errors="coerce")
    o = pd.to_numeric(work[cmap["open"]], errors="coerce")
    h = pd.to_numeric(work[cmap["high"]], errors="coerce")
    l = pd.to_numeric(work[cmap["low"]], errors="coerce")

    recipes: dict[str, pd.Series] = {
        "gap_from_prev_close_pct": (o - c.shift(1)) / (c.shift(1) + _EPS),
        "vwap_proxy_dev": (c - (h + l + c) / 3) / (((h + l + c) / 3) + _EPS),
        "volatility_20d": c.pct_change().rolling(20).std(),
        "intraday_range_pct": (h - l) / (c + _EPS),
    }

    if cmap.get("volume"):
        v = pd.to_numeric(work[cmap["volume"]], errors="coerce")
        roll_mean = v.rolling(20).mean()
        roll_std = v.rolling(20).std()
        recipes["volume_zscore_20"] = (v - roll_mean) / (roll_std + _EPS)

    wanted = set(names) if names else set(recipes)
    for fname, series in recipes.items():
        if fname in wanted:
            work[fname] = series

    return work


def enriched_preview_rows(
    df: pd.DataFrame,
    feature_names: list[str],
    *,
    max_rows: int = 12,
    base_cols: int = 6,
) -> list[dict[str, Any]]:
    enriched = compute_ohlcv_features(df, names=feature_names)
    preview_cols = list(df.columns[: min(base_cols, len(df.columns))])
    for name in feature_names:
        if name in enriched.columns and name not in preview_cols:
            preview_cols.append(name)
    preview_cols = [c for c in preview_cols if c in enriched.columns]
    tail = enriched[preview_cols].tail(max_rows)
    for col in preview_cols:
        if pd.api.types.is_numeric_dtype(tail[col]):
            tail[col] = tail[col].round(6)
    return tail.to_dict(orient="records")
