"""Run the frozen week-3 510300 dual-MA + vol-target strategy (full sample)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.canonical import export_canonical_csv, run_dma_vol, slice_frame
from backtest.data import load_or_fetch_panel
from backtest.report import write_backtest_outputs
from backtest.strategy_spec import START, SYMBOL, signal_config


def run(refresh: bool = False) -> dict:
    panel = load_or_fetch_panel(
        [SYMBOL],
        start=START,
        end=None,
        data_dir=ROOT / "data",
        kind="etf",
        refresh=refresh,
    )
    df = slice_frame(panel[SYMBOL], START, None)
    result = run_dma_vol(df, config=signal_config())
    paths = write_backtest_outputs(result, ROOT / "output", run_name="dma_vol_510300")
    csv_path = export_canonical_csv(
        df, ROOT / "platforms" / "quantconnect" / "data" / "510300.csv"
    )
    print("Frozen config:", signal_config())
    print("Metrics:", result.metrics)
    print("Wrote:", {k: str(v) for k, v in paths.items()})
    print("Canonical CSV:", csv_path)
    return {"result": result, "paths": paths, "csv": csv_path}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    print("=== Frozen 510300 dual-MA + vol target ===")
    run(refresh=args.refresh)


if __name__ == "__main__":
    main()
