"""Example 1: dual-MA on 沪深300ETF + 中证500ETF (multi-asset portfolio)."""

from __future__ import annotations

import argparse
from pathlib import Path

from backtest.config import load_config
from backtest.data import load_or_fetch_panel
from backtest.engine import PortfolioEngine
from backtest.execution import ExecutionConfig
from backtest.report import write_backtest_outputs
from backtest.signals import DualMAConfig, generate_dual_ma_signals

ROOT = Path(__file__).resolve().parents[1]


def run(refresh: bool = False) -> dict:
    """Fetch ≥5y ETF history, run dual-MA portfolio backtest, write reports."""
    cfg = load_config(ROOT / "config.yaml")
    panel = load_or_fetch_panel(
        cfg.etf.symbols,
        start=cfg.etf.start,
        end=cfg.etf.end,
        data_dir=ROOT / cfg.data_dir,
        kind="etf",
        refresh=refresh,
    )
    for sym, df in panel.items():
        span = df.attrs.get("span_days", 0)
        print(f"  {sym}: {len(df)} bars, span≈{span}d, source={df['source'].iloc[0]}")

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

    engine = PortfolioEngine(
        initial_capital=cfg.engine.initial_capital,
        execution=ExecutionConfig(
            fill_on=cfg.engine.fill_on,
            slippage_type=cfg.engine.slippage_type,
            slippage_value=cfg.engine.slippage_value,
            tick_size=cfg.engine.tick_size,
            commission_rate=cfg.engine.commission_rate,
            lot_size=cfg.engine.lot_size,
        ),
    )
    result = engine.run(panel, signals)
    paths = write_backtest_outputs(result, ROOT / cfg.output_dir, run_name="etf_dual_ma")
    print("Portfolio metrics:", result.metrics)
    print("Per symbol:", result.per_symbol_metrics)
    print("Wrote:", {k: str(v) for k, v in paths.items()})
    return {"result": result, "paths": paths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Re-download market data")
    args = parser.parse_args()
    print("=== ETF dual-MA portfolio ===")
    run(refresh=args.refresh)


if __name__ == "__main__":
    main()
