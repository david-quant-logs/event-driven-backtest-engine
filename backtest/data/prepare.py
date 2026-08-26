"""Prepare audit-ready market panels for the backtest engine."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backtest.data.adjust import apply_adjustment, choose_adjustment
from backtest.data.fetch_crypto import fetch_crypto_daily
from backtest.data.fetch_etf import fetch_etf_daily
from backtest.data.quality import DataQualityReport, check_data_quality
from backtest.data.store import load_frame, save_frame


def prepare_symbol_frame(
    df: pd.DataFrame,
    *,
    adjustment: str | None = None,
) -> tuple[pd.DataFrame, DataQualityReport]:
    """
    Apply adjustment policy, mark suspensions, and run quality checks.

    Suspended bars keep last prices but ``volume == 0`` and ``suspended=True``.
    The engine skips fills on those bars.
    """
    mode = adjustment or choose_adjustment()
    out = apply_adjustment(df, mode=mode)
    if "volume" in out.columns:
        suspended = out["volume"].fillna(0) <= 0
        out["suspended"] = suspended
        # Keep OHLC as-is on halt days; force volume to 0 for audit clarity.
        out.loc[suspended, "volume"] = 0.0
    else:
        out["suspended"] = False

    report = check_data_quality(out)
    out.attrs["quality"] = report.to_dict()
    out.attrs["adjustment"] = mode
    return out, report


def load_or_fetch_panel(
    symbols: list[str],
    *,
    start: str,
    end: str | None = None,
    data_dir: Path | str = "data",
    kind: str = "etf",
    refresh: bool = False,
    crypto_interval: str = "1d",
) -> dict[str, pd.DataFrame]:
    """
    Load processed bars from disk or fetch + cache them.

    Parameters
    ----------
    kind:
        ``etf`` uses AkShare/Eastmoney path; ``crypto`` uses Gate/Binance.
    """
    data_dir = Path(data_dir)
    processed = data_dir / "processed" / kind
    raw_dir = data_dir / "raw" / kind
    panel: dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        stem = processed / symbol.replace("/", "_")
        cached = None if refresh else load_frame(stem)
        if cached is not None and not cached.empty:
            frame = cached
        else:
            if kind == "crypto":
                frame = fetch_crypto_daily(symbol, start=start, end=end, interval=crypto_interval)
            else:
                frame = fetch_etf_daily(symbol, start=start, end=end, adjust=choose_adjustment())
            save_frame(frame, raw_dir / symbol.replace("/", "_"), ["csv"])
            frame, _ = prepare_symbol_frame(frame)
            save_frame(frame, stem)
        frame, report = prepare_symbol_frame(frame)
        if not report.ok:
            raise ValueError(f"Data quality failed for {symbol}: {report.issues}")
        # Span check for course requirement (>= 5 years for ETF examples).
        span_days = (pd.to_datetime(frame["datetime"].iloc[-1]) - pd.to_datetime(frame["datetime"].iloc[0])).days
        frame.attrs["span_days"] = int(span_days)
        panel[symbol] = frame.reset_index(drop=True)
    return panel
