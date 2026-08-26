"""Performance metrics at portfolio and single-symbol level."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    initial_capital: float,
    periods_per_year: int = 252,
) -> dict[str, Any]:
    """Compute portfolio-level performance statistics."""
    if equity_curve.empty:
        return {"error": "empty equity curve"}

    eq = equity_curve["equity"].astype(float)
    rets = eq.pct_change().fillna(0.0)
    total_return = float(eq.iloc[-1] / initial_capital - 1.0)
    n = max(len(eq) - 1, 1)
    ann_factor = periods_per_year / n
    ann_return = float((1.0 + total_return) ** ann_factor - 1.0) if total_return > -1 else float("nan")
    vol = float(rets.std(ddof=0) * np.sqrt(periods_per_year))
    sharpe = float((rets.mean() * periods_per_year) / vol) if vol > 1e-12 else 0.0
    cummax = eq.cummax()
    drawdown = eq / cummax - 1.0
    max_dd = float(drawdown.min())
    n_trades = int(len(trades)) if trades is not None and not trades.empty else 0

    return {
        "initial_capital": initial_capital,
        "final_equity": float(eq.iloc[-1]),
        "total_return": total_return,
        "annual_return": ann_return,
        "annual_volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "n_trades": n_trades,
        "n_bars": int(len(eq)),
    }


def compute_per_symbol_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    symbols: list[str],
    initial_capital: float,
) -> dict[str, dict[str, Any]]:
    """
    Approximate per-symbol contribution using trade PnL and position notionals.

    Each symbol is attributed realized PnL from its trades plus mark-to-market
    on residual qty using the last close column if present.
    """
    out: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        sym_trades = (
            trades[trades["symbol"] == sym].copy()
            if trades is not None and not trades.empty and "symbol" in trades.columns
            else pd.DataFrame()
        )
        realized = 0.0
        position = 0.0
        avg = 0.0
        for _, t in sym_trades.iterrows():
            q = float(t["qty"])
            px = float(t["price"])
            if t["side"] == "buy":
                new_pos = position + q
                avg = (avg * position + px * q) / new_pos if new_pos else 0.0
                position = new_pos
            else:
                # Sell long
                sell_q = min(q, position) if position > 0 else q
                realized += (px - avg) * sell_q
                position -= sell_q
                if position <= 1e-12:
                    position = 0.0
                    avg = 0.0

        last_close = None
        close_col = f"close_{sym}"
        pos_col = f"pos_{sym}"
        if close_col in equity_curve.columns and len(equity_curve):
            last_close = float(equity_curve[close_col].iloc[-1])
        if pos_col in equity_curve.columns and len(equity_curve):
            position = float(equity_curve[pos_col].iloc[-1])
        unrealized = (last_close - avg) * position if last_close is not None and position else 0.0
        out[sym] = {
            "n_trades": int(len(sym_trades)),
            "realized_pnl": float(realized),
            "unrealized_pnl": float(unrealized),
            "total_pnl": float(realized + unrealized),
            "pnl_vs_capital": float((realized + unrealized) / initial_capital),
            "final_qty": float(position),
        }
    return out
