"""Dual moving-average trend with ATR filter and volatility targeting.

Canonical week-3 strategy. Signals use T-close information only; the
actionable series is shifted so the earliest fill is T+1 (see
``shift_for_execution``). Target weights are in ``[0, max_weight]``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backtest.signals.base import SignalFrame, shift_for_execution


@dataclass
class DualMAVolConfig:
    """Parameters for the dual-MA + vol-target signal generator."""

    fast: int = 20
    slow: int = 60
    ma_type: str = "sma"  # sma | ema
    atr_window: int = 20
    trend_k: float = 0.5
    vol_lookback: int = 20
    vol_target: float = 0.10
    vol_periods_per_year: int = 252
    max_weight: float = 1.0
    weight_step: float = 0.10
    delay_bars: int = 0
    price_col: str = "close"


def _moving_average(series: pd.Series, window: int, ma_type: str) -> pd.Series:
    ma_type = ma_type.lower()
    if ma_type == "sma":
        return series.rolling(window=window, min_periods=window).mean()
    if ma_type == "ema":
        return series.ewm(span=window, adjust=False, min_periods=window).mean()
    raise ValueError(f"Unsupported ma_type: {ma_type}")


def true_range(df: pd.DataFrame, price_col: str = "close") -> pd.Series:
    """Wilder true range from high/low/close; falls back to |Δclose|."""
    close = df[price_col].astype(float)
    if "high" in df.columns and "low" in df.columns:
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        prev_close = close.shift(1)
        return pd.concat(
            [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
    return close.diff().abs()


def realized_vol(
    close: pd.Series,
    *,
    lookback: int,
    periods_per_year: int = 252,
) -> pd.Series:
    """Annualized close-to-close volatility (population std)."""
    rets = close.astype(float).pct_change()
    return rets.rolling(window=lookback, min_periods=lookback).std(ddof=0) * np.sqrt(
        periods_per_year
    )


def generate_dual_ma_vol_signals(
    df: pd.DataFrame,
    config: DualMAVolConfig | None = None,
) -> SignalFrame:
    """
    Generate volatility-targeted dual-MA weights.

    Rules
    -----
    - Long only when ``fast_ma > slow_ma`` and ``(fast-slow)/ATR > trend_k``.
    - Weight ``min(max_weight, vol_target / realized_vol)``; cash otherwise.
    - Leverage is capped at ``max_weight`` (1.0 = fully invested, no borrow).
    - ``target_at_close`` is known after T close; ``target_position`` is the
      T+1 actionable weight.
    """
    cfg = config or DualMAVolConfig()
    if cfg.fast >= cfg.slow:
        raise ValueError("fast window must be < slow window")
    if cfg.price_col not in df.columns:
        raise ValueError(f"missing price column: {cfg.price_col}")
    if cfg.vol_target <= 0 or cfg.max_weight <= 0:
        raise ValueError("vol_target and max_weight must be positive")

    out = df[["datetime"]].copy()
    symbol = str(df["symbol"].iloc[0]) if "symbol" in df.columns else "unknown"
    price = df[cfg.price_col].astype(float)
    fast = _moving_average(price, cfg.fast, cfg.ma_type)
    slow = _moving_average(price, cfg.slow, cfg.ma_type)
    atr = true_range(df, cfg.price_col).rolling(
        window=cfg.atr_window, min_periods=cfg.atr_window
    ).mean()
    rvol = realized_vol(
        price, lookback=cfg.vol_lookback, periods_per_year=cfg.vol_periods_per_year
    )

    out["fast_ma"] = fast
    out["slow_ma"] = slow
    out["atr"] = atr
    out["realized_vol"] = rvol
    trend_gap = fast - slow
    strength = trend_gap / atr.replace(0.0, np.nan)
    out["trend_strength"] = strength

    valid = fast.notna() & slow.notna() & atr.notna() & rvol.notna() & (atr > 0) & (rvol > 0)
    in_trend = valid & (fast > slow) & (strength > cfg.trend_k)
    raw_w = pd.Series(0.0, index=out.index, dtype=float)
    sized = cfg.vol_target / rvol
    raw_w.loc[in_trend] = sized.loc[in_trend].clip(upper=cfg.max_weight)
    if cfg.weight_step and cfg.weight_step > 0:
        raw_w = ((raw_w / cfg.weight_step).round() * cfg.weight_step).clip(0.0, cfg.max_weight)

    out["in_trend"] = in_trend.astype(float)
    out["target_at_close"] = raw_w
    out["target_position"] = shift_for_execution(raw_w, delay_bars=cfg.delay_bars)
    out["signal"] = out["target_position"]
    return SignalFrame(symbol=symbol, signals=out)
