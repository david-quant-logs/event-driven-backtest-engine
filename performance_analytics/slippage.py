"""
Slippage models: fixed percent/ticks, volume participation, vol-adjusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class SlippageModel:
    """
    Slippage configuration.

    Modes
    -----
    - ``percent``: fixed fraction of price (e.g. 0.0005 = 5 bps)
    - ``ticks``: N * tick_size
    - ``volume``: Almgren-style proxy ``k * (q / V)^alpha * price``
    - ``vol_adjusted``: ``base_bps * (sigma / sigma_ref) * price``
    """

    mode: str = "percent"
    value: float = 0.0005
    tick_size: float = 0.001
    # volume participation
    impact_coef: float = 0.1
    impact_power: float = 0.5
    # vol-adjusted
    base_bps: float = 5.0  # 5 bps at reference vol
    vol_lookback: int = 20
    ref_vol: float = 0.15  # annualized reference
    periods_per_year: int = 252

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "value": self.value,
            "tick_size": self.tick_size,
            "impact_coef": self.impact_coef,
            "impact_power": self.impact_power,
            "base_bps": self.base_bps,
            "vol_lookback": self.vol_lookback,
            "ref_vol": self.ref_vol,
        }


@dataclass
class SlippageResult:
    fill_price: float
    slippage_per_unit: float
    mode: str


def realized_vol(closes: pd.Series, lookback: int, periods_per_year: int = 252) -> float:
    """Annualized realized vol from the last ``lookback`` close-to-close returns."""
    if len(closes) < 3:
        return float("nan")
    rets = closes.astype(float).pct_change().dropna().iloc[-lookback:]
    if len(rets) < 2:
        return float("nan")
    return float(rets.std(ddof=0) * np.sqrt(periods_per_year))


def apply_slippage_model(
    price: float,
    *,
    side: str,
    model: SlippageModel,
    trade_qty: float = 0.0,
    bar_volume: float | None = None,
    recent_closes: pd.Series | None = None,
) -> SlippageResult:
    """
    Return adverse fill price. Buys pay up; sells receive less.
    """
    direction = 1.0 if side == "buy" else -1.0
    mode = model.mode.lower()
    slip = 0.0

    if mode == "percent":
        slip = price * float(model.value)
    elif mode == "ticks":
        slip = float(model.value) * float(model.tick_size)
    elif mode == "volume":
        vol = float(bar_volume or 0.0)
        if vol <= 0:
            slip = price * float(model.value)  # fallback to percent value
        else:
            participation = min(abs(trade_qty) / vol, 1.0)
            slip = price * model.impact_coef * (participation ** model.impact_power)
    elif mode == "vol_adjusted":
        sigma = (
            realized_vol(recent_closes, model.vol_lookback, model.periods_per_year)
            if recent_closes is not None
            else float("nan")
        )
        if not np.isfinite(sigma) or sigma <= 0:
            scale = 1.0
        else:
            scale = max(sigma / model.ref_vol, 0.25)
        slip = price * (model.base_bps / 10_000.0) * scale
    else:
        raise ValueError(f"Unknown slippage mode: {mode}")

    fill = price + direction * slip
    return SlippageResult(fill_price=fill, slippage_per_unit=slip, mode=mode)
