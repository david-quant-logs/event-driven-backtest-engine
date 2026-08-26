"""Order execution: fill timing, fee matrix, slippage models, suspension skip."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from performance_analytics.fees import FeeMatrix, FeeResult, default_fee_matrix
from performance_analytics.slippage import SlippageModel, apply_slippage_model


@dataclass
class Fill:
    """A single simulated fill with full cost audit trail."""

    datetime: pd.Timestamp
    symbol: str
    side: str  # buy | sell
    qty: float
    price: float
    gross_price: float
    slippage: float
    commission: float
    stamp_tax: float = 0.0
    transfer_fee: float = 0.0
    taker_or_maker: float = 0.0
    funding: float = 0.0
    fees_total: float = 0.0
    reason: str = ""


@dataclass
class ExecutionConfig:
    """Broker-style execution knobs (week-1 compatible + week-2 models)."""

    fill_on: str = "next_open"  # next_open | next_close
    # Legacy simple knobs (still honored when slippage_model is None)
    slippage_type: str = "percent"  # percent | ticks
    slippage_value: float = 0.001
    tick_size: float = 0.001
    commission_rate: float = 0.0
    lot_size: int = 100  # 0 => fractional allowed
    # Week-2
    slippage_model: SlippageModel | None = None
    fee_matrix: FeeMatrix = field(default_factory=FeeMatrix)
    fee_profile: str | None = None  # default from matrix
    symbol_fee_profiles: dict[str, str] = field(default_factory=dict)
    is_taker: bool = True


def apply_slippage(
    price: float,
    *,
    side: str,
    slippage_type: str,
    slippage_value: float,
    tick_size: float,
) -> tuple[float, float]:
    """Legacy percent/ticks helper kept for unit tests and simple paths."""
    model = SlippageModel(mode=slippage_type, value=slippage_value, tick_size=tick_size)
    result = apply_slippage_model(price, side=side, model=model)
    return result.fill_price, result.slippage_per_unit


def fill_price_for_bar(row: pd.Series | dict, fill_on: str) -> float:
    """Select the executable price for a bar given fill mode."""
    if fill_on == "next_open":
        return float(row["open"])
    if fill_on == "next_close":
        return float(row["close"])
    raise ValueError(f"Unknown fill_on: {fill_on}")


def round_qty(qty: float, lot_size: int) -> float:
    """Round toward zero to lot size; lot_size<=0 keeps fractional qty."""
    if lot_size is None or lot_size <= 0:
        return float(qty)
    lots = int(qty // lot_size)
    return float(lots * lot_size)


def is_tradable(row: pd.Series | dict) -> bool:
    """False on suspended / zero-volume bars — engine must skip fills."""
    keys = row.index if hasattr(row, "index") else row.keys()
    if "suspended" in keys and bool(row["suspended"]):
        return False
    if "volume" in keys and float(row.get("volume") or 0) <= 0:
        return False
    return True


def resolve_slippage_model(cfg: ExecutionConfig) -> SlippageModel:
    if cfg.slippage_model is not None:
        return cfg.slippage_model
    return SlippageModel(mode=cfg.slippage_type, value=cfg.slippage_value, tick_size=cfg.tick_size)
