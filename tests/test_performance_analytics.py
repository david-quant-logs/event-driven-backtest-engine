"""Tests for slippage models and metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from performance_analytics.metrics import bootstrap_metrics, compute_full_metrics, rolling_sharpe
from performance_analytics.slippage import SlippageModel, apply_slippage_model
from performance_analytics.distribution import analyze_return_distribution


def test_percent_and_volume_slippage():
    pct = apply_slippage_model(100.0, side="buy", model=SlippageModel(mode="percent", value=0.001))
    assert abs(pct.fill_price - 100.1) < 1e-9
    vol = apply_slippage_model(
        100.0,
        side="sell",
        model=SlippageModel(mode="volume", impact_coef=0.1, impact_power=0.5),
        trade_qty=100,
        bar_volume=10_000,
    )
    assert vol.fill_price < 100.0
    assert vol.slippage_per_unit > 0


def test_vol_adjusted_increases_with_vol():
    quiet = pd.Series(np.linspace(100, 101, 40))
    wild = pd.Series(100 * np.cumprod(1 + np.random.default_rng(0).normal(0, 0.03, 40)))
    model = SlippageModel(mode="vol_adjusted", base_bps=5.0, ref_vol=0.15, vol_lookback=20)
    s_quiet = apply_slippage_model(100.0, side="buy", model=model, recent_closes=quiet)
    s_wild = apply_slippage_model(100.0, side="buy", model=model, recent_closes=wild)
    assert s_wild.slippage_per_unit >= s_quiet.slippage_per_unit


def test_full_metrics_and_bootstrap():
    rng = np.random.default_rng(1)
    rets = pd.Series(rng.normal(0.0004, 0.01, 600))
    equity = (1 + rets).cumprod() * 100_000
    equity.index = pd.bdate_range("2020-01-01", periods=len(equity))
    stats = compute_full_metrics(equity, bootstrap_n=200, rolling_window=60, total_fees=100.0)
    assert "sharpe" in stats.basic
    assert "sortino" in stats.advanced
    assert stats.rolling_sharpe is not None
    assert "sharpe_p2_5" in stats.bootstrap
    assert stats.costs["total_fees"] == 100.0


def test_distribution_flags_fat_tails():
    rng = np.random.default_rng(2)
    # Mixture with fat tails
    core = rng.normal(0, 0.01, 800)
    jumps = rng.choice([-0.08, 0.08, 0.0], size=800, p=[0.02, 0.02, 0.96])
    r = pd.Series(core + jumps)
    out = analyze_return_distribution(r)
    assert out["n"] == 800
    assert "discussion" in out
