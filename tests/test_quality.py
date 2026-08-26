"""Tests for data quality and suspension handling."""

from __future__ import annotations

import pandas as pd

from backtest.data.quality import check_data_quality
from backtest.data.prepare import prepare_symbol_frame
from backtest.data.adjust import choose_adjustment


def test_choose_adjustment_is_qfq():
    assert choose_adjustment() == "qfq"


def test_quality_flags_bad_prices_and_gaps():
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-20"]),
            "open": [10, 10, 10],
            "high": [9, 11, 11],  # first row high < low
            "low": [10, 9, 9],
            "close": [10, 10.5, 10.2],
            "volume": [100, 0, 100],
            "symbol": ["X"] * 3,
        }
    )
    report = check_data_quality(df, max_gap_calendar_days=5)
    assert report.abnormal_prices >= 1
    assert report.date_gaps >= 1
    assert not report.ok


def test_prepare_marks_suspension():
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]),
            "open": [10.0, 10.0, 10.5],
            "high": [10.5, 10.0, 11.0],
            "low": [9.5, 10.0, 10.0],
            "close": [10.0, 10.0, 10.8],
            "volume": [1000.0, 0.0, 800.0],
            "amount": [10000, 0, 8000],
            "adj_factor": [1.0, 1.0, 1.0],
            "symbol": ["Y"] * 3,
        }
    )
    out, report = prepare_symbol_frame(df)
    assert bool(out.loc[1, "suspended"])
    assert out.loc[1, "volume"] == 0.0
    assert report.suspended_days == 1
    assert report.ok
