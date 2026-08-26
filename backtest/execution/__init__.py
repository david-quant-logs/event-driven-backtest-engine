"""Order execution: fill timing, slippage, suspension skip."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Fill:
    """A single simulated fill."""

    datetime: pd.Timestamp
    symbol: str
    side: str  # buy | sell
    qty: float
    price: float
    gross_price: float
    slippage: float
    commission: float
    reason: str = ""


@dataclass
class ExecutionConfig:
    """Broker-style execution knobs."""

    fill_on: str = "next_open"  # next_open | next_close
    slippage_type: str = "percent"  # percent | ticks
    slippage_value: float = 0.001
    tick_size: float = 0.001
    commission_rate: float = 0.0
    lot_size: int = 100  # 0 => fractional allowed


def apply_slippage(
    price: float,
    *,
    side: str,
    slippage_type: str,
    slippage_value: float,
    tick_size: float,
) -> tuple[float, float]:
    """
    Return (fill_price, slippage_per_unit).

    Buys pay up; sells receive less.
    """
    direction = 1.0 if side == "buy" else -1.0
    if slippage_type == "percent":
        slip = price * float(slippage_value)
    elif slippage_type == "ticks":
        slip = float(slippage_value) * float(tick_size)
    else:
        raise ValueError(f"Unknown slippage_type: {slippage_type}")
    fill = price + direction * slip
    return fill, slip


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
