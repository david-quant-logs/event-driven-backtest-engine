"""Data quality checks: missing values, bad prices, calendar gaps, suspensions."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class DataQualityReport:
    """Structured audit result for one symbol's OHLCV series."""

    symbol: str
    n_rows: int
    start: str | None
    end: str | None
    missing_ohlc: int = 0
    abnormal_prices: int = 0
    date_gaps: int = 0
    gap_dates: list[str] = field(default_factory=list)
    suspended_days: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no hard failures (gaps are warnings for A-share calendars)."""
        return self.missing_ohlc == 0 and self.abnormal_prices == 0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "n_rows": self.n_rows,
            "start": self.start,
            "end": self.end,
            "missing_ohlc": self.missing_ohlc,
            "abnormal_prices": self.abnormal_prices,
            "date_gaps": self.date_gaps,
            "gap_dates_sample": self.gap_dates[:10],
            "suspended_days": self.suspended_days,
            "ok": self.ok,
            "issues": self.issues,
        }


def check_data_quality(
    df: pd.DataFrame,
    *,
    symbol: str | None = None,
    max_gap_calendar_days: int = 5,
    price_jump_threshold: float = 0.25,
) -> DataQualityReport:
    """
    Validate a daily bar frame.

    Checks:
    - missing OHLC / non-positive prices
    - high < low or close outside [low, high]
    - calendar gaps larger than ``max_gap_calendar_days`` (weekends/holidays OK)
    - extreme close-to-close jumps (flagged, not auto-dropped)
    - suspended bars (volume == 0)
    """
    sym = symbol or (str(df["symbol"].iloc[0]) if "symbol" in df.columns and len(df) else "unknown")
    report = DataQualityReport(
        symbol=sym,
        n_rows=len(df),
        start=str(pd.to_datetime(df["datetime"].iloc[0]).date()) if len(df) else None,
        end=str(pd.to_datetime(df["datetime"].iloc[-1]).date()) if len(df) else None,
    )
    if df.empty:
        report.issues.append("empty frame")
        return report

    out = df.copy()
    out["datetime"] = pd.to_datetime(out["datetime"])

    ohlc = ["open", "high", "low", "close"]
    missing = out[ohlc].isna().any(axis=1).sum()
    report.missing_ohlc = int(missing)
    if missing:
        report.issues.append(f"{missing} rows with missing OHLC")

    bad_price = (
        (out["open"] <= 0)
        | (out["high"] <= 0)
        | (out["low"] <= 0)
        | (out["close"] <= 0)
        | (out["high"] < out["low"])
        | (out["close"] > out["high"] * 1.0001)
        | (out["close"] < out["low"] * 0.9999)
    )
    report.abnormal_prices = int(bad_price.sum())
    if report.abnormal_prices:
        report.issues.append(f"{report.abnormal_prices} rows with abnormal prices")

    rets = out["close"].pct_change().abs()
    jumps = int((rets > price_jump_threshold).sum())
    if jumps:
        report.issues.append(f"{jumps} close jumps > {price_jump_threshold:.0%}")

    dates = out["datetime"].sort_values()
    deltas = dates.diff().dt.days
    gap_mask = deltas > max_gap_calendar_days
    report.date_gaps = int(gap_mask.sum())
    if report.date_gaps:
        gap_idx = np.where(gap_mask.to_numpy())[0]
        report.gap_dates = [str(dates.iloc[i].date()) for i in gap_idx[:20]]
        report.issues.append(
            f"{report.date_gaps} calendar gaps > {max_gap_calendar_days}d "
            f"(sample: {', '.join(report.gap_dates[:5])})"
        )

    if "suspended" in out.columns:
        report.suspended_days = int(out["suspended"].fillna(False).astype(bool).sum())
    elif "volume" in out.columns:
        report.suspended_days = int((out["volume"].fillna(0) <= 0).sum())

    if report.suspended_days:
        report.issues.append(f"{report.suspended_days} suspended / zero-volume bars")

    return report
