"""
Performance analytics: fees, slippage, full metrics, reports.

Week-2 module that upgrades the backtest from toy numbers to auditable
net-of-cost performance.
"""

from performance_analytics.fees import FeeMatrix, FeeResult, FeeSpec, default_fee_matrix
from performance_analytics.slippage import SlippageModel, SlippageResult, apply_slippage_model
from performance_analytics.metrics import PerformanceStats, compute_full_metrics
from performance_analytics.report import generate_performance_report
from performance_analytics.sensitivity import run_slippage_sensitivity
from performance_analytics.distribution import analyze_return_distribution

__all__ = [
    "FeeMatrix",
    "FeeResult",
    "FeeSpec",
    "SlippageModel",
    "SlippageResult",
    "PerformanceStats",
    "analyze_return_distribution",
    "apply_slippage_model",
    "compute_full_metrics",
    "default_fee_matrix",
    "generate_performance_report",
    "run_slippage_sensitivity",
]
