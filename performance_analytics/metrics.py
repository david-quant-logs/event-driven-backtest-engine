"""Full performance metric suite (basic + advanced + rolling + bootstrap)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class PerformanceStats:
    """Structured performance output for reports."""

    basic: dict[str, float] = field(default_factory=dict)
    advanced: dict[str, float] = field(default_factory=dict)
    rolling_sharpe: pd.Series | None = None
    bootstrap: dict[str, Any] = field(default_factory=dict)
    benchmark: dict[str, float] = field(default_factory=dict)
    costs: dict[str, float] = field(default_factory=dict)

    def to_flat_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        out.update({f"basic.{k}": v for k, v in self.basic.items()})
        out.update({f"advanced.{k}": v for k, v in self.advanced.items()})
        out.update({f"bootstrap.{k}": v for k, v in self.bootstrap.items()})
        out.update({f"benchmark.{k}": v for k, v in self.benchmark.items()})
        out.update({f"costs.{k}": v for k, v in self.costs.items()})
        return out


def equity_to_returns(equity: pd.Series) -> pd.Series:
    eq = equity.astype(float)
    return eq.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)


def compute_drawdown_series(equity: pd.Series) -> pd.Series:
    eq = equity.astype(float)
    peak = eq.cummax()
    return eq / peak - 1.0


def max_drawdown_stats(equity: pd.Series) -> dict[str, float]:
    """Max DD, longest DD duration (bars), and recovery bars after trough."""
    dd = compute_drawdown_series(equity)
    max_dd = float(dd.min()) if len(dd) else 0.0
    under = (dd < -1e-12).to_numpy()
    longest = 0
    cur = 0
    for flag in under:
        if flag:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0

    recovery = float("nan")
    if len(dd):
        trough_i = int(dd.to_numpy().argmin())
        after = dd.to_numpy()[trough_i:]
        recovered = np.where(after >= -1e-12)[0]
        if len(recovered):
            recovery = float(recovered[0])

    return {
        "max_drawdown": max_dd,
        "longest_drawdown_bars": float(longest),
        "drawdown_recovery_bars": recovery,
    }


def compute_full_metrics(
    equity: pd.Series,
    *,
    returns: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    benchmark_returns: pd.Series | None = None,
    initial_capital: float | None = None,
    periods_per_year: int = 252,
    rolling_window: int = 252,
    bootstrap_n: int = 1000,
    bootstrap_seed: int = 42,
    risk_free: float = 0.0,
    total_fees: float = 0.0,
    omega_threshold: float = 0.0,
) -> PerformanceStats:
    """
    Compute basic + advanced metrics, rolling Sharpe, bootstrap CIs, benchmark.
    """
    equity = equity.astype(float).dropna()
    if returns is None:
        returns = equity_to_returns(equity)
    returns = returns.astype(float).reindex(equity.index).fillna(0.0)

    if initial_capital is None:
        initial_capital = float(equity.iloc[0])

    total_return = float(equity.iloc[-1] / initial_capital - 1.0)
    n = max(len(returns), 1)
    ann_return = float((1.0 + total_return) ** (periods_per_year / max(n - 1, 1)) - 1.0) if total_return > -1 else float("nan")
    # Also mean-based annualized return (common in Sharpe context)
    mu = float(returns.mean())
    vol = float(returns.std(ddof=0) * np.sqrt(periods_per_year))
    rf_daily = risk_free / periods_per_year
    excess = returns - rf_daily
    sharpe = float(excess.mean() / returns.std(ddof=0) * np.sqrt(periods_per_year)) if returns.std(ddof=0) > 1e-12 else 0.0

    dd_stats = max_drawdown_stats(equity)
    calmar = float(ann_return / abs(dd_stats["max_drawdown"])) if abs(dd_stats["max_drawdown"]) > 1e-12 else float("nan")

    basic = {
        "initial_capital": float(initial_capital),
        "final_equity": float(equity.iloc[-1]),
        "total_return": total_return,
        "annual_return": ann_return,
        "annual_volatility": vol,
        "sharpe": sharpe,
        "max_drawdown": dd_stats["max_drawdown"],
        "calmar": calmar,
        "n_bars": float(len(equity)),
        "n_trades": float(len(trades)) if trades is not None and not trades.empty else 0.0,
    }

    # Sortino
    downside = returns[returns < rf_daily] - rf_daily
    downside_std = float(np.sqrt((downside**2).mean())) if len(downside) else 0.0
    sortino = (
        float((mu - rf_daily) / downside_std * np.sqrt(periods_per_year))
        if downside_std > 1e-12
        else float("nan")
    )

    # Omega ratio
    gains = (returns - omega_threshold).clip(lower=0).sum()
    losses = (omega_threshold - returns).clip(lower=0).sum()
    omega = float(gains / losses) if losses > 1e-12 else float("nan")

    # Monthly win rate
    idx = pd.to_datetime(equity.index) if not isinstance(equity.index, pd.DatetimeIndex) else equity.index
    ret_by_date = pd.Series(returns.values, index=idx)
    monthly = (1.0 + ret_by_date).resample("ME").prod() - 1.0
    month_win = float((monthly > 0).mean()) if len(monthly) else float("nan")

    # Daily win/loss payoff
    wins = returns[returns > 0]
    losses_s = returns[returns < 0]
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses_s.mean()) if len(losses_s) else 0.0
    payoff = float(avg_win / abs(avg_loss)) if avg_loss < 0 else float("nan")
    win_rate_daily = float((returns > 0).mean())

    advanced = {
        "sortino": sortino,
        "omega": omega,
        "longest_drawdown_bars": dd_stats["longest_drawdown_bars"],
        "drawdown_recovery_bars": dd_stats["drawdown_recovery_bars"],
        "monthly_win_rate": month_win,
        "daily_win_rate": win_rate_daily,
        "payoff_ratio": payoff,
        "skewness": float(ret_by_date.skew()),
        "excess_kurtosis": float(ret_by_date.kurt()),  # pandas kurtosis is excess
    }

    rolling = rolling_sharpe(ret_by_date, window=rolling_window, periods_per_year=periods_per_year)
    boot = bootstrap_metrics(ret_by_date, n_boot=bootstrap_n, seed=bootstrap_seed, periods_per_year=periods_per_year)

    bench: dict[str, float] = {}
    if benchmark_returns is not None and len(benchmark_returns):
        bench = benchmark_relative(ret_by_date, benchmark_returns, periods_per_year=periods_per_year)

    gross_pnl = float(equity.iloc[-1] - initial_capital + total_fees)
    costs = {
        "total_fees": float(total_fees),
        "gross_pnl": gross_pnl,
        "net_pnl": float(equity.iloc[-1] - initial_capital),
        "erosion_vs_gross": float(total_fees / abs(gross_pnl)) if abs(gross_pnl) > 1e-9 else float("nan"),
        "erosion_vs_capital": float(total_fees / initial_capital) if initial_capital else float("nan"),
    }

    return PerformanceStats(
        basic=basic,
        advanced=advanced,
        rolling_sharpe=rolling,
        bootstrap=boot,
        benchmark=bench,
        costs=costs,
    )


def rolling_sharpe(
    returns: pd.Series,
    *,
    window: int = 252,
    periods_per_year: int = 252,
) -> pd.Series:
    """Trailing Sharpe over ``window`` bars (≈12 months when window=252)."""
    r = returns.astype(float)
    mean = r.rolling(window).mean()
    std = r.rolling(window).std(ddof=0)
    out = (mean / std) * np.sqrt(periods_per_year)
    out.name = "rolling_sharpe"
    return out


def bootstrap_metrics(
    returns: pd.Series,
    *,
    n_boot: int = 1000,
    seed: int = 42,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """Block-free i.i.d. bootstrap of annualized return and Sharpe (95% CI)."""
    rng = np.random.default_rng(seed)
    arr = returns.astype(float).to_numpy()
    n = len(arr)
    if n < 10:
        return {"n_boot": float(n_boot), "error": 1.0}

    ann_rets = np.empty(n_boot)
    sharpes = np.empty(n_boot)
    for i in range(n_boot):
        sample = rng.choice(arr, size=n, replace=True)
        mu = sample.mean()
        sd = sample.std(ddof=0)
        # Compounded annualized from mean daily
        ann_rets[i] = (1.0 + mu) ** periods_per_year - 1.0
        sharpes[i] = (mu / sd * np.sqrt(periods_per_year)) if sd > 1e-12 else 0.0

    return {
        "n_boot": float(n_boot),
        "ann_return_mean": float(ann_rets.mean()),
        "ann_return_p2_5": float(np.percentile(ann_rets, 2.5)),
        "ann_return_p97_5": float(np.percentile(ann_rets, 97.5)),
        "sharpe_mean": float(sharpes.mean()),
        "sharpe_p2_5": float(np.percentile(sharpes, 2.5)),
        "sharpe_p97_5": float(np.percentile(sharpes, 97.5)),
    }


def benchmark_relative(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """Excess return, information ratio, and beta vs benchmark."""
    s = strategy_returns.astype(float)
    b = benchmark_returns.astype(float)
    aligned = pd.concat([s, b], axis=1, join="inner").dropna()
    if aligned.empty or len(aligned) < 5:
        return {}
    aligned.columns = ["s", "b"]
    excess = aligned["s"] - aligned["b"]
    te = float(excess.std(ddof=0) * np.sqrt(periods_per_year))
    ir = float(excess.mean() / excess.std(ddof=0) * np.sqrt(periods_per_year)) if excess.std(ddof=0) > 1e-12 else 0.0
    # Beta via covariance
    cov = np.cov(aligned["s"], aligned["b"], ddof=0)
    var_b = float(cov[1, 1])
    beta = float(cov[0, 1] / var_b) if var_b > 1e-18 else float("nan")
    ann_excess = float(excess.mean() * periods_per_year)
    return {
        "ann_excess_return": ann_excess,
        "tracking_error": te,
        "information_ratio": ir,
        "beta": beta,
        "corr": float(aligned["s"].corr(aligned["b"])),
    }
