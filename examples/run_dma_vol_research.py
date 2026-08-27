"""Week-3 IS/OOS research: dual-MA + vol targeting on 510300.

Select parameters on 2019–2022 only. Report 2023+ out of sample without
refitting. Exports the canonical CSV used by QuantConnect custom data.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import pandas as pd

from backtest.canonical import (
    buy_and_hold_signals,
    export_canonical_csv,
    make_execution,
    run_dma_vol,
    slice_frame,
)
from backtest.data import load_or_fetch_panel
from backtest.engine import PortfolioEngine
from backtest.signals.dual_ma_vol import DualMAVolConfig
from backtest.strategy_spec import (
    INITIAL_CAPITAL,
    IS_END,
    OOS_START,
    START,
    SYMBOL,
)

FAST_GRID = (10, 20, 30)
SLOW_GRID = (60, 90, 120)
VOL_GRID = (0.08, 0.10, 0.12)
K_GRID = (0.0, 0.5, 1.0)
MAX_DD_FLOOR = -0.40  # reject IS configs worse than -40% drawdown if any survive


def _load_panel(refresh: bool) -> pd.DataFrame:
    panel = load_or_fetch_panel(
        [SYMBOL],
        start=START,
        end=None,
        data_dir=ROOT / "data",
        kind="etf",
        refresh=refresh,
    )
    return panel[SYMBOL]


def _run_bh(df: pd.DataFrame) -> object:
    engine = PortfolioEngine(
        initial_capital=INITIAL_CAPITAL,
        execution=make_execution(),
        weight_mode="target",
    )
    return engine.run({SYMBOL: df}, {SYMBOL: buy_and_hold_signals(df)})


def _row(tag: str, cfg: DualMAVolConfig, result) -> dict:
    m = dict(result.metrics)
    m.update(
        {
            "tag": tag,
            "fast": cfg.fast,
            "slow": cfg.slow,
            "vol_target": cfg.vol_target,
            "trend_k": cfg.trend_k,
            "atr_window": cfg.atr_window,
            "total_fees": float(result.total_fees),
        }
    )
    return m


def select_winner(grid: pd.DataFrame) -> pd.Series:
    """Highest IS Sharpe among configs with max DD above the floor."""
    is_part = grid[grid["tag"] == "IS"].copy()
    eligible = is_part[is_part["max_drawdown"] >= MAX_DD_FLOOR]
    pool = eligible if not eligible.empty else is_part
    pool = pool.sort_values(
        ["sharpe", "annual_return", "max_drawdown"],
        ascending=[False, False, False],
    )
    return pool.iloc[0]


def _heatmap(is_df: pd.DataFrame, path: Path, vol_target: float, trend_k: float) -> None:
    sub = is_df[(is_df["vol_target"] == vol_target) & (is_df["trend_k"] == trend_k)]
    if sub.empty:
        return
    pivot = sub.pivot_table(index="fast", columns="slow", values="sharpe", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(pivot.to_numpy(), cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(list(pivot.columns))
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(list(pivot.index))
    ax.set_xlabel("slow SMA")
    ax.set_ylabel("fast SMA")
    ax.set_title(f"IS Sharpe  vol*={vol_target:.0%}  k={trend_k}")
    for i, fast in enumerate(pivot.index):
        for j, slow in enumerate(pivot.columns):
            val = pivot.iloc[i, j]
            ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_equity(frames: dict[str, pd.Series], path: Path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for name, s in frames.items():
        s = s.copy()
        s.index = pd.to_datetime(s.index)
        ax.plot(s.index, s / s.iloc[0], label=name, lw=1.4)
    ax.axvline(pd.Timestamp(OOS_START), color="#666", ls="--", lw=1, label="OOS start")
    ax.set_ylabel("Growth of 1 CNY")
    ax.set_title(title)
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)


def run(refresh: bool = False) -> dict:
    df = _load_panel(refresh)
    print(f"  {SYMBOL}: {len(df)} bars  {df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]}")
    is_df = slice_frame(df, START, IS_END)
    oos_df = slice_frame(df, OOS_START, None)
    full_df = slice_frame(df, START, None)

    rows: list[dict] = []
    combos = list(product(FAST_GRID, SLOW_GRID, VOL_GRID, K_GRID))
    print(f"Grid size: {len(combos)} (IS only for selection)")
    for i, (fast, slow, vol, k) in enumerate(combos, 1):
        cfg = DualMAVolConfig(
            fast=fast,
            slow=slow,
            vol_target=vol,
            trend_k=k,
            atr_window=20,
            vol_lookback=20,
        )
        is_res = run_dma_vol(is_df, config=cfg)
        rows.append(_row("IS", cfg, is_res))
        if i % 20 == 0 or i == len(combos):
            print(f"  {i}/{len(combos)}")

    grid = pd.DataFrame(rows)
    winner = select_winner(grid)
    frozen = DualMAVolConfig(
        fast=int(winner["fast"]),
        slow=int(winner["slow"]),
        vol_target=float(winner["vol_target"]),
        trend_k=float(winner["trend_k"]),
        atr_window=20,
        vol_lookback=20,
    )
    print("Frozen (IS-selected):", frozen)

    oos_res = run_dma_vol(oos_df, config=frozen)
    full_res = run_dma_vol(full_df, config=frozen)
    bh_is = _run_bh(is_df)
    bh_oos = _run_bh(oos_df)
    bh_full = _run_bh(full_df)

    summary = pd.DataFrame(
        [
            _row("IS_strategy", frozen, run_dma_vol(is_df, config=frozen)),
            _row("IS_buyhold", frozen, bh_is),
            _row("OOS_strategy", frozen, oos_res),
            _row("OOS_buyhold", frozen, bh_oos),
            _row("FULL_strategy", frozen, full_res),
            _row("FULL_buyhold", frozen, bh_full),
        ]
    )

    out_dir = ROOT / "output" / "reports" / "dma_vol_research"
    out_dir.mkdir(parents=True, exist_ok=True)
    docs_charts = ROOT / "docs" / "charts"
    docs_charts.mkdir(parents=True, exist_ok=True)

    grid.to_csv(out_dir / "is_grid.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out_dir / "is_oos_summary.csv", index=False, encoding="utf-8-sig")

    heat_path = docs_charts / "dma_vol_is_sharpe_heatmap.png"
    _heatmap(grid, heat_path, float(frozen.vol_target), float(frozen.trend_k))

    eq_full = full_res.equity_curve.set_index(pd.to_datetime(full_res.equity_curve["datetime"]))["equity"]
    eq_bh = bh_full.equity_curve.set_index(pd.to_datetime(bh_full.equity_curve["datetime"]))["equity"]
    eq_path = docs_charts / "dma_vol_equity_vs_buyhold.png"
    _plot_equity(
        {"Strategy": eq_full, "Buy & hold 510300": eq_bh},
        eq_path,
        "510300 dual-MA + vol target vs buy & hold",
    )

    csv_path = export_canonical_csv(
        full_df, ROOT / "platforms" / "quantconnect" / "data" / "510300.csv"
    )

    freeze = {
        "fast": frozen.fast,
        "slow": frozen.slow,
        "vol_target": frozen.vol_target,
        "trend_k": frozen.trend_k,
        "atr_window": frozen.atr_window,
        "vol_lookback": frozen.vol_lookback,
        "weight_step": frozen.weight_step,
        "ma_type": "sma",
        "symbol": SYMBOL,
        "is_end": IS_END,
        "oos_start": OOS_START,
        "selection": "max IS Sharpe among max_dd >= -40% (else unconstrained max Sharpe)",
        "csv": str(csv_path.as_posix()),
    }
    (out_dir / "frozen_params.json").write_text(
        json.dumps(freeze, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md = _research_markdown(freeze, summary, winner)
    (out_dir / "research_summary.md").write_text(md, encoding="utf-8")
    (ROOT / "docs" / "DMA_VOL_RESEARCH.md").write_text(md, encoding="utf-8")

    print(summary.to_string(index=False))
    print("Wrote", out_dir)
    print("Canonical CSV", csv_path)
    return {
        "frozen": freeze,
        "summary": summary,
        "grid": grid,
        "csv": csv_path,
        "full_result": full_res,
        "bh_full": bh_full,
    }


def _fmt_pct(x: float) -> str:
    return f"{100.0 * float(x):.2f}%"


def _research_markdown(freeze: dict, summary: pd.DataFrame, winner: pd.Series) -> str:
    def grab(tag: str) -> pd.Series:
        return summary.loc[summary["tag"] == tag].iloc[0]

    s_is = grab("IS_strategy")
    b_is = grab("IS_buyhold")
    s_oos = grab("OOS_strategy")
    b_oos = grab("OOS_buyhold")
    s_full = grab("FULL_strategy")
    b_full = grab("FULL_buyhold")

    def block(title: str, s: pd.Series, b: pd.Series) -> str:
        return "\n".join(
            [
                f"### {title}",
                "",
                "| | Strategy | Buy & hold |",
                "| --- | ---: | ---: |",
                f"| Total return | {_fmt_pct(s['total_return'])} | {_fmt_pct(b['total_return'])} |",
                f"| Annualized | {_fmt_pct(s['annual_return'])} | {_fmt_pct(b['annual_return'])} |",
                f"| Sharpe | {s['sharpe']:.3f} | {b['sharpe']:.3f} |",
                f"| Max DD | {_fmt_pct(s['max_drawdown'])} | {_fmt_pct(b['max_drawdown'])} |",
                f"| Trades | {int(s['n_trades'])} | {int(b['n_trades'])} |",
                f"| Fees | {s['total_fees']:.0f} | {b['total_fees']:.0f} |",
                "",
            ]
        )

    return "\n".join(
        [
            "# 510300 Dual-MA + Volatility Targeting — Research Note",
            "",
            "In-sample window **2019-01-01 – 2022-12-31** is the only place parameters",
            "were chosen. Out-of-sample **2023-01-01 onward** is reported, not tuned.",
            "",
            "## Frozen parameters",
            "",
            f"- SMA `{freeze['fast']}` / `{freeze['slow']}`",
            f"- ATR window `{freeze['atr_window']}`, trend strength threshold `k = {freeze['trend_k']}`",
            f"- Vol lookback `{freeze['vol_lookback']}`, target vol `{freeze['vol_target']:.0%}`, leverage cap 1.0",
            f"- Selection rule: `{freeze['selection']}`",
            f"- Winning IS Sharpe `{winner['sharpe']:.3f}`, IS max DD `{_fmt_pct(winner['max_drawdown'])}`",
            "",
            "Full spec: [STRATEGY_SPEC.md](STRATEGY_SPEC.md).",
            "",
            "## Equity vs buy & hold",
            "",
            "![equity](charts/dma_vol_equity_vs_buyhold.png)",
            "",
            "## IS Sharpe heatmap (winner vol* and k)",
            "",
            "![heatmap](charts/dma_vol_is_sharpe_heatmap.png)",
            "",
            block("In sample (2019–2022)", s_is, b_is),
            block("Out of sample (2023– )", s_oos, b_oos),
            block("Full sample", s_full, b_full),
            "## Interpretation",
            "",
            "Volatility targeting and the ATR trend filter are not a promise of higher",
            "compounded return versus sitting in 510300. They exist to cut exposure in",
            "choppy, high-vol regimes and to make the sleeve portable across platforms",
            "with a single weight series. If OOS Sharpe is weak, that is left in the",
            "table — the parameter tuple is not reopened.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    print("=== Week-3 dual-MA vol-target research ===")
    run(refresh=args.refresh)


if __name__ == "__main__":
    main()
