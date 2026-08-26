"""One-shot runner: week-1 examples + optional week-2 performance report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run backtest deliverables.")
    parser.add_argument("--refresh", action="store_true", help="Re-download market data")
    parser.add_argument("--skip-crypto", action="store_true")
    parser.add_argument("--skip-etf", action="store_true")
    parser.add_argument("--synthetic-lookahead", action="store_true")
    parser.add_argument(
        "--performance-report",
        action="store_true",
        help="Also run week-2 ETF dual-MA full performance report",
    )
    args = parser.parse_args(argv)

    print("=== event-driven-backtest-engine ===")
    if not args.skip_etf:
        from examples.run_etf_dual_ma import run as run_etf

        run_etf(refresh=args.refresh)
    if not args.skip_crypto:
        from examples.run_crypto_dual_ma import run as run_crypto

        run_crypto(refresh=args.refresh)

    from examples.run_lookahead_check import run as run_la

    run_la(use_live_etf=not args.synthetic_lookahead, refresh=args.refresh)

    if args.performance_report:
        from examples.run_performance_report import run as run_perf

        run_perf(refresh=args.refresh)

    print("All done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
