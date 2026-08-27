"""Frozen week-3 canonical strategy parameters.

QC Lean and JoinQuant copies must match these constants. Change only after
the IS grid in ``examples/run_dma_vol_research.py`` has been run; then update
this file and ``docs/STRATEGY_SPEC.md`` together.
"""

from __future__ import annotations

from backtest.signals.dual_ma_vol import DualMAVolConfig

SYMBOL = "510300"
START = "2019-01-01"
IS_END = "2022-12-31"
OOS_START = "2023-01-01"
INITIAL_CAPITAL = 1_000_000.0
FILL_ON = "next_open"
LOT_SIZE = 100
FEE_PROFILE = "ashare_etf"
SLIPPAGE_BPS = 5  # 5 bps = 0.0005
WEIGHT_MODE = "target"
MA_TYPE = "sma"
FAST = 30
SLOW = 120
ATR_WINDOW = 20
TREND_K = 1.0
VOL_LOOKBACK = 20
VOL_TARGET = 0.12
MAX_WEIGHT = 1.0
WEIGHT_STEP = 0.10
VOL_PERIODS_PER_YEAR = 252
CUSTOM_DATA_URL = (
    "https://raw.githubusercontent.com/david-quant-logs/"
    "event-driven-backtest-engine/main/platforms/quantconnect/data/510300.csv"
)


def signal_config(*, delay_bars: int = 0) -> DualMAVolConfig:
    """Canonical signal config (T close → T+1 via ``delay_bars``)."""
    return DualMAVolConfig(
        fast=FAST,
        slow=SLOW,
        ma_type=MA_TYPE,
        atr_window=ATR_WINDOW,
        trend_k=TREND_K,
        vol_lookback=VOL_LOOKBACK,
        vol_target=VOL_TARGET,
        vol_periods_per_year=VOL_PERIODS_PER_YEAR,
        max_weight=MAX_WEIGHT,
        weight_step=WEIGHT_STEP,
        delay_bars=delay_bars,
    )
