"""Unit tests for dual-MA signal timing and crossover logic."""

from __future__ import annotations

import pandas as pd

from backtest.signals.dual_ma import DualMAConfig, generate_dual_ma_signals
from backtest.signals.base import shift_for_execution


def _synth_cross() -> pd.DataFrame:
    """
    Construct prices so SMA(2) crosses SMA(4) at a known index.

    Sequence designed for easy mental arithmetic.
    """
    # Flat then ramp up then down.
    closes = [10, 10, 10, 10, 11, 12, 13, 14, 15, 14, 12, 10, 9, 8, 7]
    dates = pd.bdate_range("2020-01-01", periods=len(closes))
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000] * len(closes),
            "symbol": "T",
        }
    )


def test_dual_ma_sma_regime_and_shift():
    df = _synth_cross()
    sf = generate_dual_ma_signals(df, DualMAConfig(fast=2, slow=4, ma_type="sma", delay_bars=0))
    sig = sf.signals
    # target_at_close may be long when fast>slow; target_position is shifted +1.
    assert "target_at_close" in sig.columns
    assert "target_position" in sig.columns
    # First actionable bar cannot use same-day close: shift means index 0 is 0.
    assert sig["target_position"].iloc[0] == 0.0
    # Wherever target_at_close turns 1, target_position becomes 1 on the next bar.
    at_close = sig["target_at_close"].tolist()
    actionable = sig["target_position"].tolist()
    for i in range(len(at_close) - 1):
        assert actionable[i + 1] == at_close[i]


def test_ema_supported():
    df = _synth_cross()
    sf = generate_dual_ma_signals(df, DualMAConfig(fast=2, slow=4, ma_type="ema"))
    assert sf.signals["fast_ma"].notna().sum() > 0


def test_long_short_goes_negative():
    df = _synth_cross()
    sf = generate_dual_ma_signals(
        df, DualMAConfig(fast=2, slow=4, ma_type="sma", side="long_short")
    )
    assert (sf.signals["target_at_close"] < 0).any()


def test_extra_delay_bars():
    s = pd.Series([0, 1, 1, 0, 0], dtype=float)
    delayed = shift_for_execution(s, delay_bars=1)
    # total shift = 2
    assert delayed.tolist() == [0.0, 0.0, 0.0, 1.0, 1.0]


def test_signal_uses_only_close_column():
    df = _synth_cross()
    # Corrupt open/high/low — signal must still work from close.
    df["open"] = 999
    df["high"] = 999
    df["low"] = 1
    sf = generate_dual_ma_signals(df, DualMAConfig(fast=2, slow=4))
    assert sf.signals["target_at_close"].notna().all()
