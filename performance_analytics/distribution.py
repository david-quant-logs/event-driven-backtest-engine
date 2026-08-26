"""Return-distribution diagnostics and Sharpe applicability discussion."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def analyze_return_distribution(returns: pd.Series) -> dict[str, Any]:
    """
    Test how far daily returns are from normality and discuss Sharpe.

    Computes skewness, excess kurtosis, Jarque–Bera statistic, and a plain-
    language assessment of Sharpe interpretability under fat tails / skew.
    """
    r = returns.astype(float).dropna()
    n = len(r)
    if n < 20:
        return {"n": n, "error": "insufficient observations"}

    mu = float(r.mean())
    sigma = float(r.std(ddof=1))
    skew = float(r.skew())
    # pandas Series.kurt is excess kurtosis (Fisher)
    excess_kurt = float(r.kurt())
    # Jarque-Bera
    jb = n / 6.0 * (skew**2 + (excess_kurt**2) / 4.0)
    # Chi-square(2) critical value ~5.99 at 5%
    jb_reject_5pct = jb > 5.991

    # Empirical vs normal: fraction of |z|>3
    if sigma > 1e-12:
        z = (r - mu) / sigma
        tail3 = float((z.abs() > 3).mean())
        normal_tail3 = 0.0027
    else:
        tail3 = float("nan")
        normal_tail3 = 0.0027

    if abs(skew) < 0.5 and excess_kurt < 1.0 and not jb_reject_5pct:
        verdict = (
            "接近正态：夏普作为均值/波动权衡指标较稳健。"
        )
        severity = "low"
    elif abs(skew) < 1.0 and excess_kurt < 3.0:
        verdict = (
            "轻度偏态/厚尾：夏普仍可排序策略，但置信区间应加宽；"
            "建议同时看 Sortino / Omega / 最大回撤。"
        )
        severity = "medium"
    else:
        verdict = (
            "明显非正态（偏度或峰度偏高，JB 拒绝正态）："
            "夏普把尾部风险压缩成一个方差数字，解释力偏弱——"
            "同等夏普下，左偏厚尾策略的真实破产风险更高。"
            "应以回撤、Sortino、Omega 与 bootstrap 区间为主。"
        )
        severity = "high"

    return {
        "n": n,
        "mean": mu,
        "std": sigma,
        "skewness": skew,
        "excess_kurtosis": excess_kurt,
        "jarque_bera": float(jb),
        "jb_reject_normal_5pct": bool(jb_reject_5pct),
        "empirical_tail_gt3sigma": tail3,
        "normal_tail_gt3sigma": normal_tail3,
        "severity": severity,
        "discussion": verdict,
    }


def distribution_markdown(stats: dict[str, Any]) -> str:
    """Render distribution challenge section as Markdown."""
    if stats.get("error"):
        return f"## 收益分布与夏普适用性\n\n数据不足：{stats['error']}\n"
    lines = [
        "## 收益分布与夏普适用性（高难度挑战）",
        "",
        "问题：若日收益不服从正态分布，夏普比率的解释力有多弱？",
        "",
        "| 统计量 | 数值 |",
        "| --- | ---: |",
        f"| 样本数 | {stats['n']} |",
        f"| 偏度 skewness | {stats['skewness']:.4f} |",
        f"| 超额峰度 excess kurtosis | {stats['excess_kurtosis']:.4f} |",
        f"| Jarque–Bera | {stats['jarque_bera']:.2f} |",
        f"| 5% 水平拒绝正态 | {stats['jb_reject_normal_5pct']} |",
        f"| abs(z)>3 经验频率 | {stats['empirical_tail_gt3sigma']:.4%} |",
        f"| abs(z)>3 正态基准 | {stats['normal_tail_gt3sigma']:.4%} |",
        "",
        f"**严重程度：** `{stats['severity']}`",
        "",
        stats["discussion"],
        "",
    ]
    return "\n".join(lines)
