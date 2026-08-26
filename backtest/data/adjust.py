"""
Price adjustment policy for signal generation.

Choice (documented for auditability)
------------------------------------
We use **前复权 (forward adjustment / qfq)** prices for strategy signals and
backtest marks, while always retaining a separate ``adj_factor`` column.

Why 前复权, not 后复权 / 不复权?
- Dual-MA crossovers depend on relative levels over a rolling window. 前复权
  keeps historical bars on a scale continuous with the latest close, matching
  what discretionary charts show.
- 后复权 (hfq) preserves early absolute prices but drifts far from live quotes;
  crossover *dates* are similar for pure ratio signals, but position sizing and
  human audit against brokers become harder.
- 不复权 introduces artificial gaps on dividend / split days and creates false
  MA crosses.

Execution note: fills use the same adjusted series for consistency inside the
engine. Live trading would map signals to the unadjusted book; for ETF examples
here, corporate actions are infrequent enough that qfq is the practical default.
"""

from __future__ import annotations

import pandas as pd

ADJUSTMENT_CHOICE = "qfq"
ADJUSTMENT_RATIONALE = __doc__


def choose_adjustment() -> str:
    """Return the project's canonical adjustment mode."""
    return ADJUSTMENT_CHOICE


def apply_adjustment(
    df: pd.DataFrame,
    *,
    mode: str = "qfq",
    adj_factor_col: str = "adj_factor",
) -> pd.DataFrame:
    """
    Ensure OHLCV are on the requested adjustment basis.

    If ``adj_factor`` is present and prices look unadjusted (factor not ~1 on
    the last row), rescale OHLC by factor / last_factor for qfq, or by factor
    for hfq. When the vendor already returned adjusted bars and factor is 1.0,
    the frame is left unchanged aside from ensuring the column exists.
    """
    out = df.copy()
    if adj_factor_col not in out.columns:
        out[adj_factor_col] = 1.0
    out[adj_factor_col] = pd.to_numeric(out[adj_factor_col], errors="coerce").fillna(1.0)

    mode = (mode or "qfq").lower()
    if mode in ("none", "raw", ""):
        out.attrs["adjustment"] = "none"
        return out

    # Vendor-adjusted feeds (AkShare adjust=qfq) already match live scale; keep.
    last_factor = float(out[adj_factor_col].iloc[-1])
    if abs(last_factor - 1.0) < 1e-9 and out[adj_factor_col].nunique() == 1:
        out.attrs["adjustment"] = mode
        return out

    factor = out[adj_factor_col].astype(float)
    if mode == "qfq":
        scale = factor / last_factor
    elif mode == "hfq":
        scale = factor
    else:
        raise ValueError(f"Unsupported adjustment mode: {mode}")

    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[col] = out[col].astype(float) * scale
    out.attrs["adjustment"] = mode
    return out
