"""Exploratory data analysis for data_after_EDA.csv."""

from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).parent / "data_after_EDA.csv"


def load_data(path: Path = DATA_PATH) -> pd.DataFrame:
    """Load multi-level header stock panel (metrics × tickers)."""
    raw = pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True)
    raw.index.name = "date"
    # Drop empty spacer row if present
    raw = raw[raw.notna().any(axis=1)]
    return raw


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to metric_ticker (e.g. close_TSLA)."""
    out = df.copy()
    out.columns = [
        f"{metric}_{ticker}" if ticker and str(ticker) != "nan" else str(metric)
        for metric, ticker in out.columns
    ]
    return out


def summarize(df: pd.DataFrame) -> None:
    print("=" * 60)
    print("DATA OVERVIEW")
    print("=" * 60)
    print(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
    print(f"Date range: {df.index.min().date()} → {df.index.max().date()}")
    print(f"Trading days: {df.shape[0]}")
    print()

    tickers = sorted({c.rsplit("_", 1)[-1] for c in df.columns if "_" in c})
    metrics = sorted({c.rsplit("_", 1)[0] for c in df.columns if "_" in c})
    print(f"Tickers: {', '.join(tickers)}")
    print(f"Metrics: {', '.join(metrics)}")
    print()

    print("=" * 60)
    print("MISSING VALUES")
    print("=" * 60)
    missing = df.isna().sum()
    if missing.sum() == 0:
        print("No missing values.")
    else:
        print(missing[missing > 0].to_string())
    print()

    print("=" * 60)
    print("DESCRIPTIVE STATISTICS (numeric)")
    print("=" * 60)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print(df.describe().T.round(4).to_string())
    print()

    print("=" * 60)
    print("CORRELATION — close prices between tickers")
    print("=" * 60)
    close_cols = [c for c in df.columns if c.startswith("close_")]
    print(df[close_cols].corr().round(3).to_string())
    print()

    print("=" * 60)
    print("RETURNS (daily % change on close)")
    print("=" * 60)
    returns = df[close_cols].pct_change().dropna()
    print(returns.describe().T[["mean", "std", "min", "max"]].round(6).to_string())
    print()

    print("=" * 60)
    print("VOLUME SUMMARY")
    print("=" * 60)
    vol_cols = [c for c in df.columns if c.startswith("volume_")]
    print(df[vol_cols].describe().T[["mean", "std", "min", "max"]].round(0).to_string())
    print()

    print("=" * 60)
    print("PRICE RANGE (close) — min / max / last")
    print("=" * 60)
    for col in close_cols:
        s = df[col]
        print(
            f"  {col.split('_')[1]:5s}: "
            f"min={s.min():8.2f}  max={s.max():8.2f}  last={s.iloc[-1]:8.2f}"
        )
    print()

    print("=" * 60)
    print("DUPLICATE DATES")
    print("=" * 60)
    dupes = df.index.duplicated().sum()
    print(f"Duplicate index entries: {dupes}")
    print()

    print("=" * 60)
    print("SAMPLE (first 3 & last 3 rows, close only)")
    print("=" * 60)
    print(df[close_cols].head(3).to_string())
    print("...")
    print(df[close_cols].tail(3).to_string())


if __name__ == "__main__":
    panel = load_data()
    flat = flatten_columns(panel)
    summarize(flat)
