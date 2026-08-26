"""Run look-ahead bias detection and write the audit report."""

from __future__ import annotations

import argparse
from pathlib import Path

from backtest.data import load_or_fetch_panel
from backtest.lookahead import run_lookahead_detection, synthesize_trending_ohlcv
from backtest.report import write_text_report

ROOT = Path(__file__).resolve().parents[1]


def run(*, use_live_etf: bool = True, refresh: bool = False) -> Path:
    """
    Prefer real 510300 history when available; fall back to synthetic bars.
    """
    df = None
    if use_live_etf:
        try:
            panel = load_or_fetch_panel(
                ["510300"],
                start="2019-01-01",
                data_dir=ROOT / "data",
                kind="etf",
                refresh=refresh,
            )
            df = panel["510300"]
            print(f"Using live ETF 510300 ({len(df)} bars)")
        except Exception as exc:  # noqa: BLE001
            print(f"Live ETF unavailable ({exc}); using synthetic series")
    if df is None:
        df = synthesize_trending_ohlcv(500)
        print(f"Using synthetic series ({len(df)} bars)")

    report = run_lookahead_detection(df)
    out = ROOT / "output" / "reports" / "lookahead_detection.md"
    write_text_report(out, report.to_markdown())
    # Also keep a stable copy under docs/ for the GitHub deliverable.
    docs_copy = ROOT / "docs" / "LOOKAHEAD_REPORT.md"
    write_text_report(docs_copy, report.to_markdown())
    print(report.message)
    print(f"Wrote {out}")
    print(f"Wrote {docs_copy}")
    if not report.passed:
        raise SystemExit(2)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true", help="Skip live ETF fetch")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    print("=== Look-ahead detection ===")
    run(use_live_etf=not args.synthetic, refresh=args.refresh)


if __name__ == "__main__":
    main()
