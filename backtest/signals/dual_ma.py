"""Configurable dual moving-average crossover strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backtest.signals.base import SignalFrame, shift_for_execution


@dataclass
class DualMAConfig:
    """Parameters for the dual-MA signal generator."""

    fast: int = 20
    slow: int = 60
    ma_type: str = "sma"  # sma | ema
    side: str = "long_only"  # long_only | long_short
    delay_bars: int = 0
    price_col: str = "close"


def _moving_average(series: pd.Series, window: int, ma_type: str) -> pd.Series:
    ma_type = ma_type.lower()
    if ma_type == "sma":
        return series.rolling(window=window, min_periods=window).mean()
    if ma_type == "ema":
        return series.ewm(span=window, adjust=False, min_periods=window).mean()
    raise ValueError(f"Unsupported ma_type: {ma_type}")


def generate_dual_ma_signals(df: pd.DataFrame, config: DualMAConfig | None = None) -> SignalFrame:
    """
    Generate dual-MA target positions.

    Rules
    -----
    - After both MAs are valid: target +1 while fast > slow.
    - While fast < slow: target 0 (``long_only``) or -1 (``long_short``).
    - Cross-up / cross-down events are recorded for audit.
    - MAs use ``close`` of day T only; ``target_position`` is shifted so the
      earliest fill is T+1 open/close (see ``shift_for_execution``).
    """
    cfg = config or DualMAConfig()
    if cfg.fast >= cfg.slow:
        raise ValueError("fast window must be < slow window")
    if cfg.price_col not in df.columns:
        raise ValueError(f"missing price column: {cfg.price_col}")

    out = df[["datetime", cfg.price_col]].copy()
    symbol = str(df["symbol"].iloc[0]) if "symbol" in df.columns else "unknown"

    price = out[cfg.price_col].astype(float)
    fast = _moving_average(price, cfg.fast, cfg.ma_type)
    slow = _moving_average(price, cfg.slow, cfg.ma_type)
    out["fast_ma"] = fast
    out["slow_ma"] = slow

    valid = fast.notna() & slow.notna()
    position = pd.Series(0.0, index=out.index, dtype=float)
    long_mask = valid & (fast > slow)
    short_mask = valid & (fast < slow)
    position.loc[long_mask] = 1.0
    if cfg.side == "long_short":
        position.loc[short_mask] = -1.0
    else:
        position.loc[short_mask] = 0.0

    cross_up = long_mask & ~long_mask.shift(1, fill_value=False)
    cross_down = short_mask & ~short_mask.shift(1, fill_value=False)
    event = pd.Series(0.0, index=out.index, dtype=float)
    event.loc[cross_up] = 1.0
    event.loc[cross_down] = -1.0

    out["signal_event"] = event
    out["target_at_close"] = position  # known after T close — not yet actionable
    out["target_position"] = shift_for_execution(position, delay_bars=cfg.delay_bars)
    out["signal"] = out["target_position"]
    return SignalFrame(symbol=symbol, signals=out)
