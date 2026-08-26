"""
Look-ahead bias detector.

Idea
----
Inject a *perfect foresight* signal that knows the next bar's close return.
If the engine fills on the **same bar** that produced that future-dependent
signal (no mandatory delay), the strategy harvests nearly the full move and
reports absurd Sharpe / returns → the engine has a look-ahead hole.

A correct engine only allows fills on T+1 (plus optional delay), so even a
perfect signal cannot trade the bar whose close it peeked at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from backtest.engine import PortfolioEngine
from backtest.execution import ExecutionConfig
from backtest.signals.base import shift_for_execution


@dataclass
class LookaheadReport:
    """Result of the automatic look-ahead probe."""

    passed: bool
    message: str
    leaky_metrics: dict[str, Any]
    safe_metrics: dict[str, Any]
    details: dict[str, Any]

    def to_markdown(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [
            "# Look-ahead Bias Detection Report",
            "",
            f"**Status: {status}**",
            "",
            self.message,
            "",
            "## Setup",
            "",
            "- Perfect signal: long iff next close > current close (future function).",
            "- **Leaky path**: apply that signal with `shift(0)` and fill on the same bar's close.",
            "- **Safe path**: `shift(1)` so T-close foresight only becomes actionable on T+1 close.",
            "- Both paths use `fill_on=next_close`; only the signal delay differs.",
            "",
            "## Leaky engine metrics (should look 'too good')",
            "",
            "```",
            f"{self.leaky_metrics}",
            "```",
            "",
            "## Safe engine metrics (mandatory T+1 delay)",
            "",
            "```",
            f"{self.safe_metrics}",
            "```",
            "",
            "## Details",
            "",
            "```",
            f"{self.details}",
            "```",
            "",
            "## Interpretation",
            "",
            "If the safe path still matches leaky same-bar capture (Sharpe / total return",
            "within the failure threshold of the leaky run), signal→fill delay is not",
            "removing look-ahead alpha and the engine pipeline is unsafe to use as-is.",
            "",
        ]
        return "\n".join(lines)


def perfect_foresight_raw_signal(close: pd.Series) -> pd.Series:
    """+1 if tomorrow's close is higher — uses future information."""
    future_ret = close.shift(-1) / close - 1.0
    sig = (future_ret > 0).astype(float)
    sig.iloc[-1] = 0.0
    return sig


def run_lookahead_detection(
    df: pd.DataFrame,
    *,
    initial_capital: float = 100_000.0,
    sharpe_gap_min: float = 1.0,
    return_gap_min: float = 0.2,
) -> LookaheadReport:
    """
    Compare leaky vs safe execution of a perfect foresight signal.

    Both paths fill on the bar's **close** so the only difference is whether
    ``target_position`` was shifted by one bar (engine contract). The leaky
    path monetizes tomorrow's close on today's close fill; the safe path
    cannot. A PASS means delaying signals removes the future-function edge.
    """
    symbol = str(df["symbol"].iloc[0]) if "symbol" in df.columns else "TEST"
    close = df["close"].astype(float)
    raw = perfect_foresight_raw_signal(close)
    panel = {symbol: df.copy()}
    exec_cfg = ExecutionConfig(
        fill_on="next_close",
        slippage_type="percent",
        slippage_value=0.0,
        lot_size=0,
    )

    # --- Leaky: future signal actionable on the same bar (no shift) ---
    leaky_sig = df[["datetime"]].copy()
    leaky_sig["target_position"] = raw.fillna(0.0).values
    leaky_res = PortfolioEngine(initial_capital=initial_capital, execution=exec_cfg).run(
        panel, {symbol: leaky_sig}
    )

    # --- Safe: mandatory +1 bar shift (T info → T+1 fill) ---
    safe_sig = df[["datetime"]].copy()
    safe_sig["target_position"] = shift_for_execution(raw, delay_bars=0).values
    safe_res = PortfolioEngine(initial_capital=initial_capital, execution=exec_cfg).run(
        panel, {symbol: safe_sig}
    )

    leaky_r = float(leaky_res.metrics.get("total_return", 0.0))
    safe_r = float(safe_res.metrics.get("total_return", 0.0))
    leaky_s = float(leaky_res.metrics.get("sharpe", 0.0))
    safe_s = float(safe_res.metrics.get("sharpe", 0.0))

    return_ok = leaky_r - safe_r >= return_gap_min
    sharpe_ok = leaky_s - safe_s >= sharpe_gap_min
    # Delayed perfect foresight should not retain near-oracle Sharpe.
    absurd_safe = safe_s > 5.0 and (leaky_s - safe_s) < sharpe_gap_min

    passed = bool(return_ok and sharpe_ok and not absurd_safe)
    if absurd_safe:
        message = (
            "FAIL: after mandatory shift, perfect foresight still looks like an "
            "oracle — fill timing may ignore signal delay."
        )
        passed = False
    elif passed:
        message = (
            "PASS: same-bar perfect foresight earns far more than the delayed "
            "T+1 path. Enforcing shift_for_execution removes look-ahead alpha."
        )
    else:
        message = (
            "FAIL: delayed path performance is too close to the leaky path; "
            "investigate fill timing / signal shift."
        )

    details = {
        "leaky_total_return": leaky_r,
        "safe_total_return": safe_r,
        "leaky_sharpe": leaky_s,
        "safe_sharpe": safe_s,
        "return_gap": leaky_r - safe_r,
        "sharpe_gap": leaky_s - safe_s,
        "thresholds": {
            "sharpe_gap_min": sharpe_gap_min,
            "return_gap_min": return_gap_min,
        },
        "note": "Both paths use fill_on=next_close; only signal shift differs.",
    }
    return LookaheadReport(
        passed=passed,
        message=message,
        leaky_metrics=leaky_res.metrics,
        safe_metrics=safe_res.metrics,
        details=details,
    )


def synthesize_trending_ohlcv(n: int = 400, seed: int = 42) -> pd.DataFrame:
    """Synthetic bars for unit tests / detector demos (open ≠ prior close)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=n)
    rets = rng.normal(0.0005, 0.015, size=n)
    close = 100 * np.cumprod(1 + rets)
    gap = rng.normal(0.0, 0.004, size=n)
    open_ = np.empty(n)
    open_[0] = close[0] * (1 + gap[0])
    open_[1:] = close[:-1] * (1 + gap[1:])
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.005, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.005, n))
    volume = rng.integers(1_000, 10_000, size=n).astype(float)
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": volume * close,
            "adj_factor": 1.0,
            "symbol": "TEST",
            "timeframe": "1d",
            "source": "synthetic",
            "suspended": False,
        }
    )
