"""Week-2: full dual-MA performance report (fees + slippage + analytics).

Writes a draft Markdown report under docs/. Confirm with the user before
pushing to GitHub.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from backtest.config import load_config
from backtest.data import load_or_fetch_panel
from backtest.engine import PortfolioEngine
from backtest.execution import ExecutionConfig
from backtest.signals import DualMAConfig, generate_dual_ma_signals
from performance_analytics.fees import FeeMatrix, default_fee_matrix
from performance_analytics.report import generate_performance_report
from performance_analytics.sensitivity import run_slippage_sensitivity, sensitivity_markdown
from performance_analytics.slippage import SlippageModel


def _build_signals(panel: dict[str, pd.DataFrame], cfg) -> dict[str, pd.DataFrame]:
    signals = {}
    for sym, df in panel.items():
        sf = generate_dual_ma_signals(
            df,
            DualMAConfig(
                fast=cfg.etf.fast,
                slow=cfg.etf.slow,
                ma_type=cfg.etf.ma_type,
                side=cfg.etf.side,
                delay_bars=cfg.engine.delay_bars,
            ),
        )
        signals[sym] = sf.signals
    return signals


def _benchmark_returns(panel: dict[str, pd.DataFrame], symbol: str = "510300") -> pd.Series:
    df = panel[symbol].copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    s = df.set_index("datetime")["close"].astype(float).sort_index()
    return s.pct_change().fillna(0.0)


def run_once(
    panel: dict[str, pd.DataFrame],
    signals: dict[str, pd.DataFrame],
    *,
    slip: SlippageModel,
    initial_capital: float,
    fill_on: str,
    lot_size: int,
) -> object:
    matrix = FeeMatrix(
        profiles=default_fee_matrix(),
        default_profile="ashare_etf",
        symbol_map={s: "ashare_etf" for s in panel},
    )
    engine = PortfolioEngine(
        initial_capital=initial_capital,
        execution=ExecutionConfig(
            fill_on=fill_on,
            lot_size=lot_size,
            slippage_model=slip,
            fee_matrix=matrix,
            fee_profile="ashare_etf",
            symbol_fee_profiles={s: "ashare_etf" for s in panel},
        ),
    )
    return engine.run(panel, signals)


def run(refresh: bool = False) -> dict:
    cfg = load_config(ROOT / "config.yaml")
    panel = load_or_fetch_panel(
        cfg.etf.symbols,
        start=cfg.etf.start,
        end=cfg.etf.end,
        data_dir=ROOT / cfg.data_dir,
        kind="etf",
        refresh=refresh,
    )
    signals = _build_signals(panel, cfg)
    base_slip = SlippageModel(mode="percent", value=0.0005)  # 5 bps baseline

    print("Running baseline (ETF fees + 5bps slippage)...")
    result = run_once(
        panel,
        signals,
        slip=base_slip,
        initial_capital=cfg.engine.initial_capital,
        fill_on=cfg.engine.fill_on,
        lot_size=cfg.engine.lot_size,
    )
    print("Baseline metrics:", result.metrics)
    print(f"Total fees: {result.total_fees:,.2f}")

    print("Running slippage sensitivity grid...")

    def _runner(model: SlippageModel):
        return run_once(
            panel,
            signals,
            slip=model,
            initial_capital=cfg.engine.initial_capital,
            fill_on=cfg.engine.fill_on,
            lot_size=cfg.engine.lot_size,
        )

    sens = run_slippage_sensitivity(_runner)
    sens_path = ROOT / "output" / "reports" / "slippage_sensitivity.csv"
    sens_path.parent.mkdir(parents=True, exist_ok=True)
    sens.to_csv(sens_path, index=False, encoding="utf-8-sig")
    print(sensitivity_markdown(sens))

    equity = result.equity_curve.set_index(pd.to_datetime(result.equity_curve["datetime"]))["equity"]
    bench = _benchmark_returns(panel, cfg.etf.symbols[0])

    out_dir = ROOT / "output" / "reports" / "etf_dual_ma_performance"
    paths = generate_performance_report(
        equity,
        title="ETF Dual-MA Performance (510300+510500)",
        trades=result.trades,
        benchmark_returns=bench,
        initial_capital=cfg.engine.initial_capital,
        total_fees=result.total_fees,
        sensitivity_table=sens,
        out_dir=out_dir,
        report_name="etf_dual_ma_performance",
        extra_sections=[
            "## 费率假设",
            "",
            "- 品种：A 股 ETF（`ashare_etf`）",
            "- 佣金：万 1，最低 0.1 元；过户费万 0.1；**无印花税**",
            "- 基线滑点：成交价 5 bps（固定比例）",
            "- 成交：T+1 开盘（`next_open`）",
            "",
            "## 滑点敏感性表（CSV）",
            "",
            f"机器可读副本：`{sens_path.as_posix()}`",
            "",
        ],
    )

    # Draft copy for GitHub docs — do NOT push until user confirms.
    docs_report = ROOT / "docs" / "DUAL_MA_PERFORMANCE_REPORT.md"
    docs_charts = ROOT / "docs" / "charts"
    docs_charts.mkdir(parents=True, exist_ok=True)
    text = paths["report"].read_text(encoding="utf-8")
    # Point image links to docs/charts/
    for key in ("equity_chart", "drawdown_chart", "heatmap_chart", "rolling_sharpe_chart"):
        src = paths[key]
        dst = docs_charts / src.name
        shutil.copy2(src, dst)
        text = text.replace(f"charts/{src.name}", f"charts/{src.name}")
    docs_report.write_text(text, encoding="utf-8")
    sens.to_csv(ROOT / "docs" / "slippage_sensitivity.csv", index=False, encoding="utf-8-sig")

    print(f"Draft report: {docs_report}")
    print("Confirm before pushing to GitHub.")
    return {"result": result, "paths": paths, "sensitivity": sens, "docs_report": docs_report}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    print("=== Week-2 performance analytics ===")
    run(refresh=args.refresh)


if __name__ == "__main__":
    main()
