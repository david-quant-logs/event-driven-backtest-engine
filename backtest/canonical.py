"""Shared runner for the week-3 canonical dual-MA + vol-target strategy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from backtest.engine import BacktestResult, PortfolioEngine
from backtest.execution import ExecutionConfig
from backtest.signals.dual_ma_vol import DualMAVolConfig, generate_dual_ma_vol_signals
from backtest.strategy_spec import (
    FEE_PROFILE,
    FILL_ON,
    INITIAL_CAPITAL,
    LOT_SIZE,
    SLIPPAGE_BPS,
    WEIGHT_MODE,
    signal_config,
)
from performance_analytics.fees import FeeMatrix, default_fee_matrix
from performance_analytics.slippage import SlippageModel


def slice_frame(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    """Inclusive date slice on the ``datetime`` column."""
    out = df.copy()
    out["datetime"] = pd.to_datetime(out["datetime"])
    if start:
        out = out.loc[out["datetime"] >= pd.Timestamp(start)]
    if end:
        out = out.loc[out["datetime"] <= pd.Timestamp(end)]
    return out.reset_index(drop=True)


def buy_and_hold_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Fully invested from the first bar (still shifted +1 for T+1 fill)."""
    from backtest.signals.base import shift_for_execution

    w = pd.Series(1.0, index=df.index, dtype=float)
    out = df[["datetime"]].copy()
    out["target_at_close"] = w
    out["target_position"] = shift_for_execution(w, delay_bars=0)
    out["signal"] = out["target_position"]
    return out


def make_execution(
    *,
    fill_on: str = FILL_ON,
    lot_size: int = LOT_SIZE,
    fee_profile: str = FEE_PROFILE,
    slippage_value: float | None = None,
    skip_suspended: bool = True,
    commission_rate: float = 0.0,
) -> ExecutionConfig:
    slip = SlippageModel(
        mode="percent",
        value=SLIPPAGE_BPS / 10_000.0 if slippage_value is None else slippage_value,
    )
    matrix = FeeMatrix(profiles=default_fee_matrix(), default_profile=fee_profile)
    return ExecutionConfig(
        fill_on=fill_on,
        skip_suspended=skip_suspended,
        lot_size=lot_size,
        slippage_model=slip,
        fee_matrix=matrix,
        fee_profile=fee_profile,
        commission_rate=commission_rate,
    )


def run_dma_vol(
    df: pd.DataFrame,
    *,
    config: DualMAVolConfig | None = None,
    initial_capital: float = INITIAL_CAPITAL,
    execution: ExecutionConfig | None = None,
    weight_mode: str = WEIGHT_MODE,
    shift: bool = True,
) -> BacktestResult:
    """Run one symbol through the vol-targeted dual-MA strategy."""
    cfg = config or signal_config()
    if not shift:
        cfg = DualMAVolConfig(**{**cfg.__dict__, "delay_bars": 0})
        sf = generate_dual_ma_vol_signals(df, cfg)
        sig = sf.signals.copy()
        sig["target_position"] = sig["target_at_close"]
        sig["signal"] = sig["target_position"]
    else:
        sf = generate_dual_ma_vol_signals(df, cfg)
        sig = sf.signals
    engine = PortfolioEngine(
        initial_capital=initial_capital,
        execution=execution or make_execution(),
        weight_mode=weight_mode,
    )
    symbol = str(df["symbol"].iloc[0]) if "symbol" in df.columns else "unknown"
    return engine.run({symbol: df}, {symbol: sig})


def export_canonical_csv(df: pd.DataFrame, path: Path) -> Path:
    """Write QuantConnect custom-data CSV (Date,OHLCV)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(
        {
            "Date": pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m-%d"),
            "Open": df["open"].astype(float),
            "High": df["high"].astype(float),
            "Low": df["low"].astype(float),
            "Close": df["close"].astype(float),
            "Volume": df["volume"].astype(float),
        }
    )
    out.to_csv(path, index=False)
    return path


def metrics_row(name: str, result: BacktestResult) -> dict[str, Any]:
    m = dict(result.metrics)
    m["run"] = name
    m["total_fees"] = float(result.total_fees)
    return m
