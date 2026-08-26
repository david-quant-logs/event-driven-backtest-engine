"""Automated Markdown performance report with charts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from performance_analytics.distribution import analyze_return_distribution, distribution_markdown
from performance_analytics.metrics import (
    PerformanceStats,
    compute_drawdown_series,
    compute_full_metrics,
    equity_to_returns,
)
from performance_analytics.sensitivity import sensitivity_markdown


def generate_performance_report(
    equity: pd.Series,
    *,
    title: str = "Strategy Performance Report",
    trades: pd.DataFrame | None = None,
    benchmark_returns: pd.Series | None = None,
    initial_capital: float | None = None,
    total_fees: float = 0.0,
    sensitivity_table: pd.DataFrame | None = None,
    out_dir: Path | str = "output/reports/performance",
    report_name: str = "performance_report",
    extra_sections: list[str] | None = None,
    bootstrap_n: int = 1000,
) -> dict[str, Path]:
    """
    Build a full Markdown performance report + PNG charts.

    Returns paths to the markdown file and generated images.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    equity = _ensure_datetime_index(equity)
    returns = equity_to_returns(equity)
    stats = compute_full_metrics(
        equity,
        returns=returns,
        trades=trades,
        benchmark_returns=benchmark_returns,
        initial_capital=initial_capital,
        total_fees=total_fees,
        bootstrap_n=bootstrap_n,
    )
    dist = analyze_return_distribution(returns)

    equity_png = chart_dir / f"{report_name}_equity.png"
    dd_png = chart_dir / f"{report_name}_drawdown.png"
    heat_png = chart_dir / f"{report_name}_monthly_heatmap.png"
    roll_png = chart_dir / f"{report_name}_rolling_sharpe.png"

    _plot_equity(equity, equity_png, title=f"{title} — Equity")
    _plot_drawdown(equity, dd_png, title=f"{title} — Drawdown")
    _plot_monthly_heatmap(returns, heat_png, title=f"{title} — Monthly Returns")
    if stats.rolling_sharpe is not None:
        _plot_rolling_sharpe(stats.rolling_sharpe, roll_png, title=f"{title} — Rolling Sharpe (12m)")

    md = _build_markdown(
        title=title,
        stats=stats,
        dist=dist,
        sensitivity_table=sensitivity_table,
        chart_names={
            "equity": equity_png.name,
            "drawdown": dd_png.name,
            "heatmap": heat_png.name,
            "rolling": roll_png.name,
        },
        extra_sections=extra_sections or [],
    )
    md_path = out_dir / f"{report_name}.md"
    # Charts referenced relatively from report folder
    md_body = md.replace(equity_png.name, f"charts/{equity_png.name}")
    md_body = md_body.replace(dd_png.name, f"charts/{dd_png.name}")
    md_body = md_body.replace(heat_png.name, f"charts/{heat_png.name}")
    md_body = md_body.replace(roll_png.name, f"charts/{roll_png.name}")
    md_path.write_text(md_body, encoding="utf-8")

    return {
        "report": md_path,
        "equity_chart": equity_png,
        "drawdown_chart": dd_png,
        "heatmap_chart": heat_png,
        "rolling_sharpe_chart": roll_png,
    }


def _ensure_datetime_index(equity: pd.Series) -> pd.Series:
    s = equity.copy()
    if not isinstance(s.index, pd.DatetimeIndex):
        s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    s.name = s.name or "equity"
    return s


def _fmt_pct(x: float) -> str:
    if x != x:
        return "n/a"
    return f"{x:.2%}"


def _fmt_num(x: float, digits: int = 3) -> str:
    if x != x:
        return "n/a"
    return f"{x:.{digits}f}"


def _build_markdown(
    *,
    title: str,
    stats: PerformanceStats,
    dist: dict[str, Any],
    sensitivity_table: pd.DataFrame | None,
    chart_names: dict[str, str],
    extra_sections: list[str],
) -> str:
    b, a, boot, bench, costs = stats.basic, stats.advanced, stats.bootstrap, stats.benchmark, stats.costs
    lines = [
        f"# {title}",
        "",
        "> 自动生成的绩效报告（含费率侵蚀、滑点敏感性、滚动夏普、Bootstrap 与收益分布检验）。",
        "",
        "## 资金曲线与回撤",
        "",
        f"![equity]({chart_names['equity']})",
        "",
        f"![drawdown]({chart_names['drawdown']})",
        "",
        "## 基础指标",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 初始资金 | {b.get('initial_capital', float('nan')):,.0f} |",
        f"| 期末权益 | {b.get('final_equity', float('nan')):,.0f} |",
        f"| 总收益率 | {_fmt_pct(b.get('total_return', float('nan')))} |",
        f"| 年化收益率 | {_fmt_pct(b.get('annual_return', float('nan')))} |",
        f"| 年化波动率 | {_fmt_pct(b.get('annual_volatility', float('nan')))} |",
        f"| 夏普比率 | {_fmt_num(b.get('sharpe', float('nan')))} |",
        f"| 最大回撤 | {_fmt_pct(b.get('max_drawdown', float('nan')))} |",
        f"| Calmar | {_fmt_num(b.get('calmar', float('nan')))} |",
        f"| 成交笔数 | {int(b.get('n_trades', 0))} |",
        "",
        "## 进阶指标",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| Sortino | {_fmt_num(a.get('sortino', float('nan')))} |",
        f"| Omega | {_fmt_num(a.get('omega', float('nan')))} |",
        f"| 最长回撤持续（交易日） | {_fmt_num(a.get('longest_drawdown_bars', float('nan')), 0)} |",
        f"| 回撤恢复时间（交易日） | {_fmt_num(a.get('drawdown_recovery_bars', float('nan')), 0)} |",
        f"| 月胜率 | {_fmt_pct(a.get('monthly_win_rate', float('nan')))} |",
        f"| 日胜率 | {_fmt_pct(a.get('daily_win_rate', float('nan')))} |",
        f"| 盈亏比（日均） | {_fmt_num(a.get('payoff_ratio', float('nan')))} |",
        "",
        "## 成本与费率侵蚀",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 累计费用 | {costs.get('total_fees', 0):,.2f} |",
        f"| 毛收益（净收益+费用） | {costs.get('gross_pnl', float('nan')):,.2f} |",
        f"| 净收益 | {costs.get('net_pnl', float('nan')):,.2f} |",
        f"| 费用/毛收益绝对值 侵蚀比例 | {_fmt_pct(costs.get('erosion_vs_gross', float('nan')))} |",
        f"| 费用/初始资金 | {_fmt_pct(costs.get('erosion_vs_capital', float('nan')))} |",
        "",
        "## Bootstrap 95% 置信区间（1000 次重采样）",
        "",
        "| 指标 | 均值 | 2.5% | 97.5% |",
        "| --- | ---: | ---: | ---: |",
        f"| 年化收益 | {_fmt_pct(boot.get('ann_return_mean', float('nan')))} | "
        f"{_fmt_pct(boot.get('ann_return_p2_5', float('nan')))} | "
        f"{_fmt_pct(boot.get('ann_return_p97_5', float('nan')))} |",
        f"| 夏普 | {_fmt_num(boot.get('sharpe_mean', float('nan')))} | "
        f"{_fmt_num(boot.get('sharpe_p2_5', float('nan')))} | "
        f"{_fmt_num(boot.get('sharpe_p97_5', float('nan')))} |",
        "",
    ]
    if bench:
        lines += [
            "## 与基准对比",
            "",
            "| 指标 | 数值 |",
            "| --- | ---: |",
            f"| 年化超额收益 | {_fmt_pct(bench.get('ann_excess_return', float('nan')))} |",
            f"| 跟踪误差 | {_fmt_pct(bench.get('tracking_error', float('nan')))} |",
            f"| 信息比率 IR | {_fmt_num(bench.get('information_ratio', float('nan')))} |",
            f"| Beta | {_fmt_num(bench.get('beta', float('nan')))} |",
            f"| 相关 | {_fmt_num(bench.get('corr', float('nan')))} |",
            "",
        ]

    lines += [
        "## 滚动夏普（约 12 个月 = 252 交易日）",
        "",
        f"![rolling sharpe]({chart_names['rolling']})",
        "",
        "## 月度收益热力图",
        "",
        f"![monthly heatmap]({chart_names['heatmap']})",
        "",
        distribution_markdown(dist),
    ]
    if sensitivity_table is not None and not sensitivity_table.empty:
        lines.append(sensitivity_markdown(sensitivity_table))
    for sec in extra_sections:
        lines.append(sec)
        if not sec.endswith("\n"):
            lines.append("")
    return "\n".join(lines)


def _plot_equity(equity: pd.Series, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(equity.index, equity.values, color="#1f4e79", lw=1.4)
    ax.set_title(title)
    ax.set_ylabel("Equity")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_drawdown(equity: pd.Series, path: Path, title: str) -> None:
    dd = compute_drawdown_series(equity)
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.fill_between(dd.index, dd.values, 0, color="#b22222", alpha=0.45)
    ax.set_title(title)
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_rolling_sharpe(series: pd.Series, path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.plot(series.index, series.values, color="#2e7d32", lw=1.2)
    ax.axhline(0.0, color="#666", lw=0.8)
    ax.set_title(title)
    ax.set_ylabel("Sharpe")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_monthly_heatmap(returns: pd.Series, path: Path, title: str) -> None:
    r = returns.copy()
    r.index = pd.to_datetime(r.index)
    monthly = (1.0 + r).resample("ME").prod() - 1.0
    if monthly.empty:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.set_title(title + " (empty)")
        fig.savefig(path, dpi=120)
        plt.close(fig)
        return
    df = pd.DataFrame({"ret": monthly, "year": monthly.index.year, "month": monthly.index.month})
    pivot = df.pivot(index="year", columns="month", values="ret")
    pivot = pivot.reindex(columns=range(1, 13))
    fig, ax = plt.subplots(figsize=(10, max(3, 0.35 * len(pivot) + 1)))
    data = pivot.to_numpy(dtype=float)
    vmax = np.nanmax(np.abs(data)) if np.isfinite(data).any() else 0.01
    vmax = max(vmax, 1e-6)
    im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(12))
    ax.set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(y) for y in pivot.index])
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
