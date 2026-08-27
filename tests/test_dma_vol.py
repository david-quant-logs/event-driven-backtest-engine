"""Tests for dual-MA + vol-target signals and target-weight execution."""

from __future__ import annotations

import pandas as pd

from backtest.canonical import run_dma_vol
from backtest.engine import PortfolioEngine
from backtest.execution import ExecutionConfig
from backtest.signals.dual_ma_vol import DualMAVolConfig, generate_dual_ma_vol_signals
from performance_analytics.slippage import SlippageModel


def _bars(*, n: int = 80, start_px: float = 10.0, trend: float = 0.02) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=n)
    close = [start_px * ((1.0 + trend) ** i) for i in range(n)]
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": [c * 0.999 for c in close],
            "high": [c * 1.01 for c in close],
            "low": [c * 0.99 for c in close],
            "close": close,
            "volume": [10_000] * n,
            "symbol": ["510300"] * n,
        }
    )


def test_vol_signal_is_shifted_and_bounded():
    df = _bars()
    sf = generate_dual_ma_vol_signals(
        df, DualMAVolConfig(fast=5, slow=15, atr_window=5, vol_lookback=5, trend_k=0.0)
    )
    sig = sf.signals
    assert sig["target_position"].iloc[0] == 0.0
    assert (sig["target_at_close"] >= 0).all()
    assert (sig["target_at_close"] <= 1.0 + 1e-12).all()
    steps = (sig["target_at_close"] / 0.10).round()
    assert ((sig["target_at_close"] - steps * 0.10).abs() < 1e-12).all()
    at_close = sig["target_at_close"].tolist()
    actionable = sig["target_position"].tolist()
    for i in range(len(at_close) - 1):
        assert actionable[i + 1] == at_close[i]


def test_huge_trend_k_stays_in_cash():
    df = _bars(trend=0.001)
    sf = generate_dual_ma_vol_signals(
        df, DualMAVolConfig(fast=5, slow=15, atr_window=5, vol_lookback=5, trend_k=1e6)
    )
    assert (sf.signals["target_at_close"] == 0.0).all()


def test_weight_mode_target_holds_half_book():
    dates = pd.bdate_range("2020-01-01", periods=5)
    px = 10.0
    df = pd.DataFrame(
        {
            "datetime": dates,
            "open": [px] * 5,
            "high": [px] * 5,
            "low": [px] * 5,
            "close": [px] * 5,
            "volume": [10_000] * 5,
            "symbol": ["Z"] * 5,
        }
    )
    sig = pd.DataFrame({"datetime": dates, "target_position": [0.0, 0.5, 0.5, 0.5, 0.0]})
    engine = PortfolioEngine(
        initial_capital=100_000,
        execution=ExecutionConfig(
            fill_on="next_open",
            slippage_model=SlippageModel(mode="percent", value=0.0),
            lot_size=0,
            fee_profile="zero",
        ),
        weight_mode="target",
    )
    result = engine.run({"Z": df}, {"Z": sig})
    # After the 0.5 fill, qty * price ≈ 50k (half the book).
    filled = result.trades[result.trades["side"] == "buy"]
    assert not filled.empty
    qty = float(filled.iloc[0]["qty"])
    assert abs(qty * px - 50_000) < 1.0


def test_equal_weight_ignores_fractional_target():
    """Regression: equal mode must NOT treat 0.5 as 50% — it is full sleeve."""
    dates = pd.bdate_range("2020-01-01", periods=4)
    px = 10.0
    df = pd.DataFrame(
        {
            "datetime": dates,
            "open": [px] * 4,
            "high": [px] * 4,
            "low": [px] * 4,
            "close": [px] * 4,
            "volume": [10_000] * 4,
            "symbol": ["Z"] * 4,
        }
    )
    sig = pd.DataFrame({"datetime": dates, "target_position": [0.0, 0.5, 0.5, 0.5]})
    engine = PortfolioEngine(
        initial_capital=100_000,
        execution=ExecutionConfig(
            fill_on="next_open",
            slippage_model=SlippageModel(mode="percent", value=0.0),
            lot_size=0,
            fee_profile="zero",
        ),
        weight_mode="equal",
    )
    result = engine.run({"Z": df}, {"Z": sig})
    qty = float(result.trades.iloc[0]["qty"])
    assert abs(qty * px - 100_000) < 1.0


def test_skip_suspended_false_allows_halt_fill():
    dates = pd.bdate_range("2020-01-01", periods=4)
    df = pd.DataFrame(
        {
            "datetime": dates,
            "open": [10, 10, 10, 10],
            "high": [10] * 4,
            "low": [10] * 4,
            "close": [10] * 4,
            "volume": [1000, 0, 1000, 1000],
            "suspended": [False, True, False, False],
            "symbol": ["Z"] * 4,
        }
    )
    sig = pd.DataFrame({"datetime": dates, "target_position": [0.0, 1.0, 1.0, 0.0]})
    engine = PortfolioEngine(
        initial_capital=10_000,
        execution=ExecutionConfig(
            fill_on="next_open",
            skip_suspended=False,
            slippage_model=SlippageModel(mode="percent", value=0.0),
            lot_size=0,
            fee_profile="zero",
        ),
        weight_mode="target",
    )
    result = engine.run({"Z": df}, {"Z": sig})
    halted = df.loc[1, "datetime"]
    assert result.trades["datetime"].eq(halted).any()


def test_run_dma_vol_helper_no_lookahead_on_first_bar():
    df = _bars()
    result = run_dma_vol(
        df,
        config=DualMAVolConfig(fast=5, slow=15, atr_window=5, vol_lookback=5, trend_k=0.0),
        initial_capital=100_000,
        execution=ExecutionConfig(
            fill_on="next_open",
            slippage_model=SlippageModel(mode="percent", value=0.0),
            lot_size=0,
            fee_profile="zero",
        ),
    )
    if not result.trades.empty:
        first_trade_day = pd.Timestamp(result.trades["datetime"].iloc[0])
        assert first_trade_day > pd.Timestamp(df["datetime"].iloc[0])
