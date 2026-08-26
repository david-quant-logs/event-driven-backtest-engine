"""Execution + engine tests: fill modes, slippage, suspension skip."""

from __future__ import annotations

import pandas as pd

from backtest.engine import PortfolioEngine
from backtest.execution import ExecutionConfig, apply_slippage, fill_price_for_bar


def _bars() -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=8)
    closes = [10, 11, 12, 11, 10, 10, 11, 12]
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": [c - 0.1 for c in closes],
            "high": [c + 0.2 for c in closes],
            "low": [c - 0.2 for c in closes],
            "close": closes,
            "volume": [1000, 1000, 0, 1000, 1000, 1000, 1000, 1000],
            "suspended": [False, False, True, False, False, False, False, False],
            "symbol": ["Z"] * 8,
            "adj_factor": 1.0,
        }
    )


def test_slippage_percent_and_ticks():
    buy_pct, slip = apply_slippage(100.0, side="buy", slippage_type="percent", slippage_value=0.001, tick_size=0.01)
    assert abs(buy_pct - 100.1) < 1e-9
    sell_tick, _ = apply_slippage(100.0, side="sell", slippage_type="ticks", slippage_value=2, tick_size=0.01)
    assert abs(sell_tick - 99.98) < 1e-9


def test_fill_modes():
    row = pd.Series({"open": 10.0, "close": 11.0})
    assert fill_price_for_bar(row, "next_open") == 10.0
    assert fill_price_for_bar(row, "next_close") == 11.0


def test_engine_skips_suspended_and_respects_targets():
    df = _bars()
    # Flat, then want long from bar index 1 onward (already delayed series).
    sig = pd.DataFrame(
        {
            "datetime": df["datetime"],
            "target_position": [0, 1, 1, 1, 0, 0, 1, 1],
        }
    )
    engine = PortfolioEngine(
        initial_capital=100_000,
        execution=ExecutionConfig(
            fill_on="next_open",
            slippage_type="percent",
            slippage_value=0.0,
            lot_size=0,
        ),
    )
    result = engine.run({"Z": df}, {"Z": sig})
    assert not result.trades.empty
    # No trade should occur on the suspended bar (index 2).
    suspended_day = df.loc[2, "datetime"]
    traded_on_halt = result.trades["datetime"].eq(suspended_day).any()
    assert not traded_on_halt
    assert result.metrics["final_equity"] > 0
