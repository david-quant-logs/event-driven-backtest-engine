"""Write equity curves, trade logs, and metric reports to disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from backtest.engine import BacktestResult


def write_backtest_outputs(
    result: BacktestResult,
    out_dir: Path | str,
    *,
    run_name: str,
) -> dict[str, Path]:
    """
    Persist equity curve, trades, daily positions, metrics, and a simple chart.
    """
    out_dir = Path(out_dir)
    report_dir = out_dir / "reports" / run_name
    chart_dir = out_dir / "charts"
    report_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    eq_path = report_dir / "equity_curve.csv"
    result.equity_curve.to_csv(eq_path, index=False, encoding="utf-8-sig")
    paths["equity_curve"] = eq_path

    trades_path = report_dir / "trades.csv"
    result.trades.to_csv(trades_path, index=False, encoding="utf-8-sig")
    paths["trades"] = trades_path

    pos_path = report_dir / "positions.csv"
    result.positions.to_csv(pos_path, index=False, encoding="utf-8-sig")
    paths["positions"] = pos_path

    metrics_path = report_dir / "metrics.md"
    metrics_path.write_text(_metrics_markdown(run_name, result), encoding="utf-8")
    paths["metrics"] = metrics_path

    chart_path = chart_dir / f"{run_name}_equity.png"
    _plot_equity(result.equity_curve, chart_path, title=f"{run_name} equity")
    paths["chart"] = chart_path
    return paths


def _metrics_markdown(run_name: str, result: BacktestResult) -> str:
    lines = [
        f"# Metrics: {run_name}",
        "",
        "## Portfolio",
        "",
        "```",
        f"{result.metrics}",
        "```",
        "",
        "## Per symbol",
        "",
        "```",
        f"{result.per_symbol_metrics}",
        "```",
        "",
        "## Engine config",
        "",
        "```",
        f"{result.config}",
        "```",
        "",
    ]
    return "\n".join(lines)


def _plot_equity(equity_curve: pd.DataFrame, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    if not equity_curve.empty:
        ax.plot(pd.to_datetime(equity_curve["datetime"]), equity_curve["equity"], color="#1f4e79", lw=1.5)
    ax.set_title(title)
    ax.set_ylabel("Equity")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def write_text_report(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
