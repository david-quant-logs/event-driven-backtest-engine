"""Event-driven portfolio backtest engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backtest.execution import (
    ExecutionConfig,
    Fill,
    fill_price_for_bar,
    is_tradable,
    resolve_slippage_model,
    round_qty,
)
from performance_analytics.fees import FeeMatrix
from performance_analytics.slippage import apply_slippage_model


@dataclass
class BacktestResult:
    """Auditable outputs of one engine run."""

    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    positions: pd.DataFrame
    metrics: dict[str, Any]
    per_symbol_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    total_fees: float = 0.0


class PortfolioEngine:
    """
    Multi-symbol event loop.

    Timing contract
    ---------------
    ``target_position`` on bar i is the desired exposure *for that bar's fill*,
    already shifted by the signal module (T close → T+1 actionable). On each
    bar the engine:
    1. Marks existing positions at close for equity.
    2. Rebalances only when target changes (no daily drift rebalance).
    3. Applies configurable slippage + fee matrix on each fill.
    4. Optionally accrues crypto funding on held notional each bar.
    """

    def __init__(
        self,
        *,
        initial_capital: float = 1_000_000.0,
        execution: ExecutionConfig | None = None,
        weight_mode: str = "equal",
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.execution = execution or ExecutionConfig()
        self.weight_mode = weight_mode

    def run(
        self,
        panel: dict[str, pd.DataFrame],
        signals: dict[str, pd.DataFrame],
    ) -> BacktestResult:
        if not panel:
            raise ValueError("empty panel")

        aligned = _align_panel(panel, signals)
        dates = aligned["dates"]
        symbols = aligned["symbols"]
        market = aligned["market"]
        target = aligned["target"]
        close_hist: dict[str, list[float]] = {s: [] for s in symbols}

        cash = self.initial_capital
        qty: dict[str, float] = {s: 0.0 for s in symbols}
        avg_cost: dict[str, float] = {s: 0.0 for s in symbols}
        prev_target: dict[str, float] = {s: 0.0 for s in symbols}
        fills: list[Fill] = []
        equity_rows: list[dict] = []
        position_rows: list[dict] = []
        total_fees = 0.0
        slip_model = resolve_slippage_model(self.execution)
        fee_matrix: FeeMatrix = self.execution.fee_matrix

        for dt in dates:
            # Accrue funding on crypto perps for overnight holdings (bar open).
            for sym in symbols:
                row = market[dt].get(sym)
                if row is None or abs(qty[sym]) < 1e-12:
                    continue
                profile = self.execution.symbol_fee_profiles.get(sym, self.execution.fee_profile)
                spec = fee_matrix.resolve(sym, profile)
                if spec.asset_class != "crypto_perp" or spec.funding_rate_per_day <= 0:
                    continue
                notional = abs(qty[sym] * float(row["close"]))
                funding = notional * spec.funding_rate_per_day
                cash -= funding
                total_fees += funding

            active = [s for s in symbols if abs(target[dt].get(s, 0.0)) > 1e-12]
            n_active = max(len(active), 1)

            for sym in symbols:
                row = market[dt].get(sym)
                desired = float(target[dt].get(sym, 0.0))
                if row is None:
                    continue

                close_hist[sym].append(float(row["close"]))
                target_changed = abs(desired - prev_target[sym]) > 1e-12
                prev_target[sym] = desired

                if not is_tradable(row):
                    position_rows.append(
                        {
                            "datetime": dt,
                            "symbol": sym,
                            "qty": qty[sym],
                            "target": desired,
                            "skipped_suspended": True,
                        }
                    )
                    continue

                if not target_changed:
                    position_rows.append(
                        {
                            "datetime": dt,
                            "symbol": sym,
                            "qty": qty[sym],
                            "target": desired,
                            "skipped_suspended": False,
                        }
                    )
                    continue

                if abs(desired) < 1e-12 and abs(qty[sym]) < 1e-12:
                    position_rows.append(
                        {
                            "datetime": dt,
                            "symbol": sym,
                            "qty": qty[sym],
                            "target": desired,
                            "skipped_suspended": False,
                        }
                    )
                    continue

                port_value = cash + sum(
                    qty[s] * float(market[dt][s]["close"])
                    for s in symbols
                    if s in market[dt]
                )
                if abs(desired) < 1e-12:
                    target_dollar = 0.0
                elif self.weight_mode == "equal":
                    weight = 1.0 / n_active
                    target_dollar = port_value * weight * np.sign(desired)
                else:
                    weight = abs(desired) / sum(abs(target[dt].get(s, 0.0)) for s in active)
                    target_dollar = port_value * weight * np.sign(desired)

                px_ref = fill_price_for_bar(row, self.execution.fill_on)
                if px_ref <= 0:
                    continue
                desired_qty = target_dollar / px_ref if px_ref else 0.0
                desired_qty = round_qty(desired_qty, self.execution.lot_size)
                delta = desired_qty - qty[sym]
                if abs(delta) < 1e-12:
                    position_rows.append(
                        {
                            "datetime": dt,
                            "symbol": sym,
                            "qty": qty[sym],
                            "target": desired,
                            "skipped_suspended": False,
                        }
                    )
                    continue

                side = "buy" if delta > 0 else "sell"
                trade_qty = abs(delta)
                recent = pd.Series(close_hist[sym])
                slip = apply_slippage_model(
                    px_ref,
                    side=side,
                    model=slip_model,
                    trade_qty=trade_qty,
                    bar_volume=float(row.get("volume") or 0.0),
                    recent_closes=recent,
                )
                fill_px = slip.fill_price

                profile = self.execution.symbol_fee_profiles.get(sym, self.execution.fee_profile)
                spec = fee_matrix.resolve(sym, profile)

                if side == "buy":
                    # Cap qty so notional + fees fit in cash (respect commission floor).
                    if spec.asset_class == "crypto_perp":
                        rate = spec.taker_rate if self.execution.is_taker else spec.maker_rate
                        max_notional = cash / (1.0 + rate) if rate < 1 else 0.0
                    else:
                        rate = spec.commission_rate + spec.transfer_fee_rate
                        max_notional = max(cash - spec.commission_min, 0.0) / (1.0 + rate)
                    max_qty = round_qty(max_notional / fill_px, self.execution.lot_size) if fill_px > 0 else 0.0
                    trade_qty = min(trade_qty, max_qty)
                    if trade_qty <= 0:
                        position_rows.append(
                            {
                                "datetime": dt,
                                "symbol": sym,
                                "qty": qty[sym],
                                "target": desired,
                                "skipped_suspended": False,
                            }
                        )
                        continue
                    notional = trade_qty * fill_px
                    fee_res = fee_matrix.compute_fill_fees(
                        symbol=sym,
                        side=side,
                        notional=notional,
                        profile=profile,
                        is_taker=self.execution.is_taker,
                    )
                    if self.execution.commission_rate > 0 and fee_res.total == 0:
                        fee_res.commission = notional * self.execution.commission_rate
                    if notional + fee_res.total > cash + 1e-6:
                        position_rows.append(
                            {
                                "datetime": dt,
                                "symbol": sym,
                                "qty": qty[sym],
                                "target": desired,
                                "skipped_suspended": False,
                            }
                        )
                        continue
                    new_qty = qty[sym] + trade_qty
                    if new_qty > 0:
                        avg_cost[sym] = (avg_cost[sym] * qty[sym] + fill_px * trade_qty) / new_qty
                    qty[sym] = new_qty
                    cash -= notional + fee_res.total
                else:
                    if qty[sym] >= 0:
                        sell_qty = min(trade_qty, qty[sym])
                        if sell_qty <= 0:
                            position_rows.append(
                                {
                                    "datetime": dt,
                                    "symbol": sym,
                                    "qty": qty[sym],
                                    "target": desired,
                                    "skipped_suspended": False,
                                }
                            )
                            continue
                        trade_qty = sell_qty
                        notional = trade_qty * fill_px
                        fee_res = fee_matrix.compute_fill_fees(
                            symbol=sym,
                            side=side,
                            notional=notional,
                            profile=profile,
                            is_taker=self.execution.is_taker,
                        )
                        if self.execution.commission_rate > 0 and fee_res.total == 0:
                            fee_res.commission = notional * self.execution.commission_rate
                        cash += notional - fee_res.total
                        qty[sym] -= sell_qty
                        if qty[sym] <= 1e-12:
                            qty[sym] = 0.0
                            avg_cost[sym] = 0.0
                    else:
                        notional = trade_qty * fill_px
                        fee_res = fee_matrix.compute_fill_fees(
                            symbol=sym,
                            side=side,
                            notional=notional,
                            profile=profile,
                            is_taker=self.execution.is_taker,
                        )
                        cash += notional - fee_res.total
                        qty[sym] -= trade_qty

                total_fees += fee_res.total
                fills.append(
                    Fill(
                        datetime=pd.Timestamp(dt),
                        symbol=sym,
                        side=side,
                        qty=trade_qty,
                        price=fill_px,
                        gross_price=px_ref,
                        slippage=slip.slippage_per_unit,
                        commission=fee_res.commission,
                        stamp_tax=fee_res.stamp_tax,
                        transfer_fee=fee_res.transfer_fee,
                        taker_or_maker=fee_res.taker_or_maker,
                        funding=fee_res.funding,
                        fees_total=fee_res.total,
                        reason=f"rebalance target={desired}",
                    )
                )
                position_rows.append(
                    {
                        "datetime": dt,
                        "symbol": sym,
                        "qty": qty[sym],
                        "target": desired,
                        "skipped_suspended": False,
                    }
                )

            equity = cash + sum(
                qty[s] * float(market[dt][s]["close"])
                for s in symbols
                if s in market[dt]
            )
            row_eq: dict[str, Any] = {
                "datetime": dt,
                "cash": cash,
                "equity": equity,
                "cumulative_fees": total_fees,
            }
            for s in symbols:
                row_eq[f"pos_{s}"] = qty[s]
                if s in market[dt]:
                    row_eq[f"close_{s}"] = float(market[dt][s]["close"])
            equity_rows.append(row_eq)

        equity_curve = pd.DataFrame(equity_rows)
        trades = pd.DataFrame([f.__dict__ for f in fills])
        positions = pd.DataFrame(position_rows)
        from backtest.metrics import compute_metrics, compute_per_symbol_metrics

        metrics = compute_metrics(equity_curve, trades, initial_capital=self.initial_capital)
        metrics["total_fees"] = float(total_fees)
        gross_pnl = float(equity_curve["equity"].iloc[-1] - self.initial_capital + total_fees) if len(equity_curve) else 0.0
        metrics["fee_erosion_vs_gross"] = (
            float(total_fees / abs(gross_pnl)) if abs(gross_pnl) > 1e-9 else float("nan")
        )
        metrics["fee_erosion_vs_capital"] = float(total_fees / self.initial_capital)
        per_sym = compute_per_symbol_metrics(equity_curve, trades, symbols, self.initial_capital)
        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            positions=positions,
            metrics=metrics,
            per_symbol_metrics=per_sym,
            total_fees=float(total_fees),
            config={
                "initial_capital": self.initial_capital,
                "fill_on": self.execution.fill_on,
                "slippage": resolve_slippage_model(self.execution).to_dict(),
                "fee_profile": self.execution.fee_profile,
                "symbol_fee_profiles": self.execution.symbol_fee_profiles,
                "delay_note": "signals must be pre-shifted (T close -> T+1 fill)",
            },
        )


def _align_panel(
    panel: dict[str, pd.DataFrame],
    signals: dict[str, pd.DataFrame],
) -> dict:
    symbols = sorted(panel.keys())
    frames = []
    for sym in symbols:
        m = panel[sym].copy()
        m["datetime"] = pd.to_datetime(m["datetime"])
        s = signals[sym].copy()
        s["datetime"] = pd.to_datetime(s["datetime"])
        cols = ["datetime", "target_position"]
        if "signal" in s.columns and "target_position" not in s.columns:
            s = s.rename(columns={"signal": "target_position"})
        merged = m.merge(s[cols], on="datetime", how="left")
        merged["target_position"] = merged["target_position"].fillna(0.0)
        merged["symbol"] = sym
        frames.append(merged)

    all_dates = sorted(set().union(*[set(f["datetime"]) for f in frames]))
    market: dict = {d: {} for d in all_dates}
    target: dict = {d: {} for d in all_dates}
    for f in frames:
        sym = f["symbol"].iloc[0]
        for _, row in f.iterrows():
            dt = row["datetime"]
            market[dt][sym] = row.to_dict()
            target[dt][sym] = float(row["target_position"])
    return {"dates": all_dates, "symbols": symbols, "market": market, "target": target}
