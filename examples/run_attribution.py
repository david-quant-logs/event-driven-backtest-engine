"""Controlled ablations for cross-platform return attribution.

One 510300 panel, one frozen signal spec, one change per run. Writes CSV + a
Markdown table consumed by docs/CROSS_PLATFORM_ATTRIBUTION.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from backtest.canonical import make_execution, run_dma_vol, slice_frame
from backtest.data import load_or_fetch_panel
from backtest.engine import BacktestResult
from backtest.signals.dual_ma_vol import generate_dual_ma_vol_signals
from backtest.strategy_spec import INITIAL_CAPITAL, START, SYMBOL, signal_config

PERIODS = 252


def _load(refresh: bool) -> pd.DataFrame:
    panel = load_or_fetch_panel(
        [SYMBOL],
        start=START,
        end=None,
        data_dir=ROOT / "data",
        kind="etf",
        refresh=refresh,
    )
    return slice_frame(panel[SYMBOL], START, None)


def _metrics(equity: pd.Series, trades: pd.DataFrame, fees: float) -> dict:
    eq = equity.astype(float)
    rets = eq.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    total = float(eq.iloc[-1] / INITIAL_CAPITAL - 1.0)
    n = max(len(eq) - 1, 1)
    cagr = float((1.0 + total) ** (PERIODS / n) - 1.0) if total > -1 else float("nan")
    arith = float(rets.mean() * PERIODS)
    vol = float(rets.std(ddof=0) * np.sqrt(PERIODS))
    sharpe0 = float(rets.mean() / rets.std(ddof=0) * np.sqrt(PERIODS)) if rets.std(ddof=0) else 0.0
    dd = float((eq / eq.cummax() - 1.0).min())
    return {
        "total_return": total,
        "annual_return": cagr,
        "arith_annual": arith,
        "sharpe": sharpe0,
        "max_drawdown": dd,
        "n_trades": int(len(trades)) if trades is not None and not trades.empty else 0,
        "total_fees": float(fees),
        "n_bars": int(len(eq)),
        "final_equity": float(eq.iloc[-1]),
    }


def _from_result(result: BacktestResult) -> dict:
    eq = result.equity_curve.set_index(pd.to_datetime(result.equity_curve["datetime"]))["equity"]
    return _metrics(eq, result.trades, result.total_fees)


def _alt_sharpe(eq: pd.Series) -> dict:
    rets = eq.astype(float).pct_change().fillna(0.0)
    std0 = float(rets.std(ddof=0))
    std1 = float(rets.std(ddof=1))
    mu = float(rets.mean())
    rf2 = 0.02 / PERIODS
    rf4 = 0.04 / PERIODS
    cal_days = max((eq.index[-1] - eq.index[0]).days, 1)
    total = float(eq.iloc[-1] / eq.iloc[0] - 1.0)
    cagr_365 = float((1.0 + total) ** (365.0 / cal_days) - 1.0) if total > -1 else float("nan")
    return {
        "sharpe_rf0_ddof0_252": float(mu / std0 * np.sqrt(PERIODS)) if std0 else 0.0,
        "sharpe_rf0_ddof1_252": float(mu / std1 * np.sqrt(PERIODS)) if std1 else 0.0,
        "sharpe_rf2pct_ddof0_252": float((mu - rf2) / std0 * np.sqrt(PERIODS)) if std0 else 0.0,
        "sharpe_rf4pct_ddof0_252": float((mu - rf4) / std0 * np.sqrt(PERIODS)) if std0 else 0.0,
        "sharpe_rf0_ddof0_365": float(mu / std0 * np.sqrt(365.0)) if std0 else 0.0,
        "cagr_252": float((1.0 + total) ** (PERIODS / max(len(eq) - 1, 1)) - 1.0),
        "cagr_365": cagr_365,
        "arith_252": float(mu * PERIODS),
        "sample_start": str(eq.index[0].date()),
        "sample_end": str(eq.index[-1].date()),
    }


def _signal_flip_dates(df: pd.DataFrame, shifted: bool) -> pd.DatetimeIndex:
    sig = generate_dual_ma_vol_signals(df, signal_config()).signals
    col = "target_position" if shifted else "target_at_close"
    pos = (sig[col] > 0).astype(int)
    flips = sig.loc[pos.ne(pos.shift(1).fillna(0)), "datetime"]
    return pd.to_datetime(flips)


def run(refresh: bool = False) -> dict:
    df = _load(refresh)
    n_halt = int((df["volume"].fillna(0) <= 0).sum())
    print(f"{SYMBOL}: {len(df)} bars, halted={n_halt}")

    baseline = run_dma_vol(df)
    base_m = _from_result(baseline)
    runs = {"baseline_local": {**base_m, "note": "qfq, T+1 open, ETF fees, 5bps, skip halt"}}

    runs["fill_next_close"] = {
        **_from_result(run_dma_vol(df, execution=make_execution(fill_on="next_close"))),
        "note": "same signal, fill T+1 close instead of open",
    }
    runs["fill_same_bar_close"] = {
        **_from_result(
            run_dma_vol(df, shift=False, execution=make_execution(fill_on="next_close"))
        ),
        "note": "T close signal filled at T close (look-ahead)",
    }
    runs["signal_one_day_early"] = {
        **_from_result(
            run_dma_vol(df, shift=False, execution=make_execution(fill_on="next_open"))
        ),
        "note": "T close used to trade T open (1-day early vs spec)",
    }
    runs["fee_zero"] = {
        **_from_result(run_dma_vol(df, execution=make_execution(fee_profile="zero", slippage_value=0.0))),
        "note": "zero commission, zero slippage",
    }
    runs["fee_jq_stock_default"] = {
        **_from_result(run_dma_vol(df, execution=make_execution(fee_profile="jq_stock_default"))),
        "note": "JoinQuant stock default proxy: 3bp + stamp 10bp on sells",
    }
    runs["fee_qc_ib_like"] = {
        **_from_result(run_dma_vol(df, execution=make_execution(fee_profile="qc_ib_like"))),
        "note": "IB-like ~12.5bp on a ~4 CNY ETF price",
    }
    runs["trade_on_halts"] = {
        **_from_result(run_dma_vol(df, execution=make_execution(skip_suspended=False))),
        "note": "fills allowed on volume=0 bars",
    }

    dropped = df.loc[df["volume"].fillna(0) > 0].reset_index(drop=True)
    runs["drop_halt_bars_from_ma"] = {
        **_from_result(run_dma_vol(dropped)),
        "note": "skip_paused=True analog: halt days removed from MA window",
    }

    # Sample-end alignment with the public cloud backtests (same signal, same fees).
    qc_end = slice_frame(df, START, "2026-05-29")
    jq_end = slice_frame(df, START, "2026-06-26")
    runs["sample_end_qc"] = {
        **_from_result(run_dma_vol(qc_end)),
        "note": "truncate local book to QC cloud end 2026-05-29",
    }
    runs["sample_end_jq"] = {
        **_from_result(run_dma_vol(jq_end)),
        "note": "truncate local book to JoinQuant end 2026-06-26",
    }

    eq = baseline.equity_curve.set_index(pd.to_datetime(baseline.equity_curve["datetime"]))["equity"]
    metric_conventions = _alt_sharpe(eq)

    flipped_actionable = _signal_flip_dates(df, shifted=True)
    flipped_close = _signal_flip_dates(df, shifted=False)
    # How many close-time flips move by exactly one session versus the actionable series.
    close_set = set(flipped_close.dt.normalize())
    act_set = set(flipped_actionable.dt.normalize())
    # actionable is close shifted +1 trading day — mismatch vs an unshifted engine.
    n_close_flips = int(len(flipped_close))
    n_act_flips = int(len(flipped_actionable))

    rows = []
    for name, m in runs.items():
        delta_ann = m["annual_return"] - base_m["annual_return"]
        delta_sh = m["sharpe"] - base_m["sharpe"]
        rows.append(
            {
                "run": name,
                "total_return": m["total_return"],
                "annual_return": m["annual_return"],
                "sharpe": m["sharpe"],
                "max_drawdown": m["max_drawdown"],
                "n_trades": m["n_trades"],
                "total_fees": m["total_fees"],
                "final_equity": m["final_equity"],
                "n_bars": m["n_bars"],
                "delta_ann_vs_baseline": delta_ann,
                "delta_sharpe_vs_baseline": delta_sh,
                "note": m["note"],
            }
        )
    table = pd.DataFrame(rows)

    out_dir = ROOT / "output" / "reports" / "attribution"
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / "ablation.csv", index=False, encoding="utf-8-sig")
    docs_csv = ROOT / "docs" / "attribution_ablation.csv"
    table.to_csv(docs_csv, index=False, encoding="utf-8-sig")
    payload = {
        "baseline": base_m,
        "metric_conventions": metric_conventions,
        "n_bars": int(len(df)),
        "n_halt_bars": n_halt,
        "n_close_flips": n_close_flips,
        "n_actionable_flips": n_act_flips,
        "adj_factor_unique": int(df["adj_factor"].nunique()) if "adj_factor" in df.columns else 1,
        "source": str(df["source"].iloc[0]) if "source" in df.columns else "",
    }
    (out_dir / "ablation_meta.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    md = _markdown(table, payload)
    (out_dir / "ablation_table.md").write_text(md, encoding="utf-8")
    print(table.to_string(index=False))
    print("Metric conventions:", json.dumps(metric_conventions, indent=2))
    return {"table": table, "meta": payload, "md": md}


def _pp(x: float) -> str:
    return f"{100.0 * float(x):+.2f} pp"


def _markdown(table: pd.DataFrame, meta: dict) -> str:
    lines = [
        "| 差异来源 | 机制 | 年化 | Δ年化 vs 本地基线 | 夏普 | Δ夏普 | 最大回撤 | 成交笔数 | 费用 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in table.iterrows():
        ann = f"{100.0 * r['annual_return']:.2f}%"
        dann = "—" if r["run"] == "baseline_local" else _pp(r["delta_ann_vs_baseline"])
        lines.append(
            "| `{run}` | {note} | {ann} | {dann} | {sh:.3f} | {dsh:+.3f} | {dd} | {nt} | {fee:,.0f} |".format(
                run=r["run"],
                note=r["note"],
                ann=ann,
                dann=dann,
                sh=r["sharpe"],
                dsh=r["delta_sharpe_vs_baseline"],
                dd=f"{100.0 * r['max_drawdown']:.2f}%",
                nt=int(r["n_trades"]),
                fee=r["total_fees"],
            )
        )
    mc = meta["metric_conventions"]
    extra = [
        "",
        "Same equity curve, different performance conventions:",
        "",
        "| 口径 | 数值 |",
        "| --- | ---: |",
        f"| CAGR 252 (baseline) | {100.0 * mc['cagr_252']:.2f}% |",
        f"| CAGR 365 calendar | {100.0 * mc['cagr_365']:.2f}% |",
        f"| Arithmetic × 252 | {100.0 * mc['arith_252']:.2f}% |",
        f"| Sharpe rf=0 ddof=0 252 | {mc['sharpe_rf0_ddof0_252']:.3f} |",
        f"| Sharpe rf=0 ddof=1 252 | {mc['sharpe_rf0_ddof1_252']:.3f} |",
        f"| Sharpe rf=2% ddof=0 252 | {mc['sharpe_rf2pct_ddof0_252']:.3f} |",
        f"| Sharpe rf=4% ddof=0 252 (JoinQuant-like) | {mc['sharpe_rf4pct_ddof0_252']:.3f} |",
        f"| Sharpe rf=0 ddof=0 365 | {mc['sharpe_rf0_ddof0_365']:.3f} |",
        "",
        f"Halt bars in panel: **{meta['n_halt_bars']}** / {meta['n_bars']}. "
        f"Close-time weight flips: {meta['n_close_flips']}; "
        f"T+1 actionable flips: {meta['n_actionable_flips']}. "
        f"Vendor `adj_factor` unique values: {meta['adj_factor_unique']} "
        f"(source={meta['source']}).",
        "",
    ]
    return "\n".join(lines + extra)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    print("=== Week-3 attribution ablations ===")
    run(refresh=args.refresh)


if __name__ == "__main__":
    main()
