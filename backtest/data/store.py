"""CSV / Parquet persistence for market data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def save_frame(df: pd.DataFrame, stem: Path, formats: list[str] | None = None) -> list[Path]:
    """Write a frame to csv and/or parquet under stem (without suffix)."""
    formats = formats or ["csv", "parquet"]
    stem.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if "csv" in formats:
        path = stem.with_suffix(".csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        written.append(path)
    if "parquet" in formats:
        path = stem.with_suffix(".parquet")
        df.to_parquet(path, index=False)
        written.append(path)
    return written


def load_frame(stem: Path) -> pd.DataFrame | None:
    """Load parquet preferentially, else csv. Returns None if missing."""
    parquet = stem.with_suffix(".parquet")
    csv = stem.with_suffix(".csv")
    if parquet.exists():
        return pd.read_parquet(parquet)
    if csv.exists():
        return pd.read_csv(csv, parse_dates=["datetime"])
    return None
