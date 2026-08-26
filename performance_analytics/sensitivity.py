"""Slippage sensitivity: re-run strategy under multiple slippage assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from performance_analytics.slippage import SlippageModel


@dataclass
class SensitivityRow:
    label: str
    mode: str
    param: float
    total_return: float
    annual_return: float
    sharpe: float
    max_drawdown: float
    final_equity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "mode": self.mode,
            "param": self.param,
            "total_return": self.total_return,
            "annual_return": self.annual_return,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "final_equity": self.final_equity,
        }


def default_slippage_grid() -> list[tuple[str, SlippageModel]]:
    """Preset grid for sensitivity tables."""
    return [
        ("zero", SlippageModel(mode="percent", value=0.0)),
        ("1bps", SlippageModel(mode="percent", value=0.0001)),
        ("5bps", SlippageModel(mode="percent", value=0.0005)),
        ("10bps", SlippageModel(mode="percent", value=0.001)),
        ("20bps", SlippageModel(mode="percent", value=0.002)),
        ("volume_k0.05", SlippageModel(mode="volume", impact_coef=0.05, impact_power=0.5, value=0.0005)),
        ("volume_k0.10", SlippageModel(mode="volume", impact_coef=0.10, impact_power=0.5, value=0.0005)),
        ("vol_adj_5bps", SlippageModel(mode="vol_adjusted", base_bps=5.0)),
        ("vol_adj_15bps", SlippageModel(mode="vol_adjusted", base_bps=15.0)),
    ]


def run_slippage_sensitivity(
    runner: Callable[[SlippageModel], Any],
    grid: list[tuple[str, SlippageModel]] | None = None,
) -> pd.DataFrame:
    """
    Call ``runner(model)`` for each slippage assumption.

    ``runner`` must return an object with ``.metrics`` dict containing at least
    total_return / annual_return / sharpe / max_drawdown / final_equity
    (as produced by PortfolioEngine / compute_full_metrics basic block),
    **or** a ``PerformanceStats`` / dict with those keys.
    """
    grid = grid or default_slippage_grid()
    rows: list[dict[str, Any]] = []
    for label, model in grid:
        result = runner(model)
        metrics = _extract_metrics(result)
        param = model.value if model.mode == "percent" else (
            model.impact_coef if model.mode == "volume" else model.base_bps
        )
        rows.append(
            SensitivityRow(
                label=label,
                mode=model.mode,
                param=float(param),
                total_return=float(metrics.get("total_return", float("nan"))),
                annual_return=float(metrics.get("annual_return", float("nan"))),
                sharpe=float(metrics.get("sharpe", float("nan"))),
                max_drawdown=float(metrics.get("max_drawdown", float("nan"))),
                final_equity=float(metrics.get("final_equity", float("nan"))),
            ).to_dict()
        )
    return pd.DataFrame(rows)


def _extract_metrics(result: Any) -> dict[str, float]:
    if result is None:
        return {}
    if isinstance(result, dict):
        if "basic" in result:
            return dict(result["basic"])
        return result
    if hasattr(result, "basic") and isinstance(result.basic, dict):
        return dict(result.basic)
    if hasattr(result, "metrics") and isinstance(result.metrics, dict):
        m = result.metrics
        if "basic" in m:
            return dict(m["basic"])
        return dict(m)
    return {}


def sensitivity_markdown(table: pd.DataFrame) -> str:
    """Render sensitivity DataFrame as a Markdown table."""
    lines = [
        "## 滑点敏感性分析",
        "",
        "| 情景 | 模式 | 参数 | 总收益 | 年化 | 夏普 | 最大回撤 | 期末权益 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in table.iterrows():
        lines.append(
            f"| {r['label']} | {r['mode']} | {r['param']:.4g} | "
            f"{r['total_return']:.2%} | {r['annual_return']:.2%} | {r['sharpe']:.3f} | "
            f"{r['max_drawdown']:.2%} | {r['final_equity']:,.0f} |"
        )
    lines.append("")
    return "\n".join(lines)
