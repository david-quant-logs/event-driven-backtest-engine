"""Look-ahead detector must PASS on a correct engine."""

from __future__ import annotations

from backtest.lookahead import run_lookahead_detection, synthesize_trending_ohlcv


def test_lookahead_detector_passes_on_safe_engine():
    df = synthesize_trending_ohlcv(500, seed=7)
    report = run_lookahead_detection(df)
    assert report.passed, report.message
    assert report.leaky_metrics["total_return"] > report.safe_metrics["total_return"]
