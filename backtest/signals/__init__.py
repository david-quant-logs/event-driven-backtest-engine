"""Signal generation modules (no same-bar fill; signals use close-of-T info only)."""

from __future__ import annotations

from backtest.signals.dual_ma import DualMAConfig, generate_dual_ma_signals
from backtest.signals.base import SignalFrame, shift_for_execution

__all__ = [
    "DualMAConfig",
    "SignalFrame",
    "generate_dual_ma_signals",
    "shift_for_execution",
]
