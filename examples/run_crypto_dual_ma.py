"""Example 2: dual-MA EMA on BTC_USDT daily (Gate / Binance)."""

from __future__ import annotations

import argparse
from pathlib import Path

from backtest.config import load_config
from backtest.data import load_or_fetch_panel
from backtest.engine import PortfolioEngine
from backtest.execution import ExecutionConfig
from backtest.report import write_backtest_outputs
from backtest.signals import DualMAConfig, generate_dual_ma_signals
from performance_analytics.fees import FeeMatrix, default_fee_matrix
from performance_analytics.slippage import SlippageModel

ROOT = Path(__file__).resolve().parents[1]


def run(refresh: bool = False) -> dict:
    """Fetch BTC daily history, run EMA dual-MA, write reports."""
    cfg = load_config(ROOT / "config.yaml")
    symbol = cfg.crypto.symbol
    panel = load_or_fetch_panel(
        [symbol],
        start=cfg.crypto.start,
        end=None,
        data_dir=ROOT / cfg.data_dir,
        kind="crypto",
        refresh=refresh,
        crypto_interval=cfg.crypto.interval,
    )
    df = panel[symbol]
    print(f"  {symbol}: {len(df)} bars, source={df['source'].iloc[0]}")

    sf = generate_dual_ma_signals(
        df,
        DualMAConfig(
            fast=cfg.crypto.fast,
            slow=cfg.crypto.slow,
            ma_type=cfg.crypto.ma_type,
            side=cfg.crypto.side,
            delay_bars=cfg.engine.delay_bars,
        ),
    )
    fee_profile = getattr(cfg.crypto, "fee_profile", None) or "gate_perp"
    engine = PortfolioEngine(
        initial_capital=cfg.crypto.initial_capital,
        execution=ExecutionConfig(
            fill_on=cfg.engine.fill_on,
            lot_size=cfg.crypto.lot_size,
            tick_size=cfg.crypto.tick_size,
            slippage_model=SlippageModel(
                mode=cfg.engine.slippage_type,
                value=cfg.engine.slippage_value,
                tick_size=cfg.crypto.tick_size,
            ),
            fee_matrix=FeeMatrix(profiles=default_fee_matrix(), default_profile=fee_profile),
            fee_profile=fee_profile,
            symbol_fee_profiles={symbol: fee_profile},
            is_taker=True,
        ),
    )
    result = engine.run(panel, {symbol: sf.signals})
    paths = write_backtest_outputs(result, ROOT / cfg.output_dir, run_name="crypto_dual_ma")
    print("Metrics:", result.metrics)
    print(f"Total fees (incl. funding): {result.total_fees:,.2f}")
    print("Wrote:", {k: str(v) for k, v in paths.items()})
    return {"result": result, "paths": paths}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    print("=== Crypto dual-MA (BTC) ===")
    run(refresh=args.refresh)


if __name__ == "__main__":
    main()
