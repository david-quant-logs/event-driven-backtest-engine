"""Signal timing helpers to prevent look-ahead fills."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class SignalFrame:
    """Target position series aligned to the bar index used for generation."""

    symbol: str
    signals: pd.DataFrame  # columns: datetime, signal, target_position, ...


def shift_for_execution(
    signal: pd.Series,
    *,
    delay_bars: int = 0,
) -> pd.Series:
    """
    Map T-close signals to the first actionable bar.

    Convention
    ----------
    Signal is computed after bar T's close using only data available at T.
    The earliest fill is on bar T+1 (``shift(1)``). Extra ``delay_bars`` model
    ops lag between signal calc and order submission.
    """
    total = 1 + max(0, int(delay_bars))
    return signal.shift(total).fillna(0.0)
