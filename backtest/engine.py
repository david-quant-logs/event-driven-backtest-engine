"""Event-driven portfolio backtest engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backtest.execution import (
    ExecutionConfig,
    Fill,
    apply_slippage,
    fill_price_for_bar,
    is_tradable,
    round_qty,
)


@dataclass
class BacktestResult:
    """Auditable outputs of one engine run."""

    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    positions: pd.DataFrame
    metrics: dict[str, Any]
    per_symbol_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


class PortfolioEngine:
    """
    Multi-symbol event loop.

    Timing contract
    ---------------
    ``target_position`` on bar i is the desired exposure *for that bar's fill*,
    already shifted by the signal module (T close → T+1 actionable). On each
    bar the engine:
    1. Marks existing positions to the fill reference price (open or close).
    2. Rebalances toward target weights / unit positions if the bar is tradable.
    3. Records end-of-bar equity using close.
    """

    def __init__(
        self,
        *,
        initial_capital: float = 1_000_000.0,
        execution: ExecutionConfig | None = None,
        weight_mode: str = "equal",  # equal | signal (abs signal share of capital)
    ) -> None:
        self.initial_capital = float(initial_capital)
        self.execution = execution or ExecutionConfig()
        self.weight_mode = weight_mode

    def run(
        self,
        panel: dict[str, pd.DataFrame],
        signals: dict[str, pd.DataFrame],
    ) -> BacktestResult:
        """
        Run the backtest.

        Parameters
        ----------
        panel:
            symbol -> OHLCV frame with datetime, open, high, low, close, volume,
            suspended.
        signals:
            symbol -> frame with datetime and target_position (already delayed).
        """
        if not panel:
            raise ValueError("empty panel")

        aligned = _align_panel(panel, signals)
        dates = aligned["dates"]
        symbols = aligned["symbols"]
        market = aligned["market"]  # date -> symbol -> row dict
        target = aligned["target"]  # date -> symbol -> float

        cash = self.initial_capital
        qty: dict[str, float] = {s: 0.0 for s in symbols}
        avg_cost: dict[str, float] = {s: 0.0 for s in symbols}
        prev_target: dict[str, float] = {s: 0.0 for s in symbols}
        fills: list[Fill] = []
        equity_rows: list[dict] = []
        position_rows: list[dict] = []

        for dt in dates:
            # Mark-to-market at close for equity; fills use configured price.
            port_value = cash
            for sym in symbols:
                row = market[dt].get(sym)
                if row is None:
                    continue
                port_value += qty[sym] * float(row["close"])

            # Desired dollar allocation — trade only when target changes (no daily rebalance).
            active = [s for s in symbols if abs(target[dt].get(s, 0.0)) > 1e-12]
            n_active = max(len(active), 1)
            for sym in symbols:
                row = market[dt].get(sym)
                desired = float(target[dt].get(sym, 0.0))
                if row is None:
                    continue

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

                # Hold existing shares while target unchanged.
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

                # Refresh portfolio value before sizing this symbol.
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
                fill_px, slip = apply_slippage(
                    px_ref,
                    side=side,
                    slippage_type=self.execution.slippage_type,
                    slippage_value=self.execution.slippage_value,
                    tick_size=self.execution.tick_size,
                )
                trade_qty = abs(delta)
                notional = trade_qty * fill_px
                commission = notional * self.execution.commission_rate

                if side == "buy":
                    cost = notional + commission
                    if cost > cash + 1e-6:
                        # Scale down to available cash.
                        affordable = max(cash - commission, 0.0) / fill_px
                        trade_qty = round_qty(affordable, self.execution.lot_size)
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
                        commission = notional * self.execution.commission_rate
                        cost = notional + commission
                        delta = trade_qty
                    # Update avg cost
                    new_qty = qty[sym] + trade_qty
                    if new_qty > 0:
                        avg_cost[sym] = (avg_cost[sym] * qty[sym] + fill_px * trade_qty) / new_qty
                    qty[sym] = new_qty
                    cash -= cost
                else:
                    sell_qty = min(trade_qty, abs(qty[sym]) if qty[sym] > 0 else trade_qty)
                    # Allow reducing long; for short, extend when long_short.
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
                        proceeds = sell_qty * fill_px - commission
                        cash += proceeds
                        qty[sym] -= sell_qty
                        if qty[sym] <= 1e-12:
                            qty[sym] = 0.0
                            avg_cost[sym] = 0.0
                        delta = -sell_qty
                        trade_qty = sell_qty
                    else:
                        # Cover/increase short — simplified: cash += proceeds of short sell
                        proceeds = trade_qty * fill_px - commission
                        cash += proceeds
                        qty[sym] -= trade_qty

                fills.append(
                    Fill(
                        datetime=pd.Timestamp(dt),
                        symbol=sym,
                        side=side,
                        qty=trade_qty,
                        price=fill_px,
                        gross_price=px_ref,
                        slippage=slip,
                        commission=commission,
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
            row_eq: dict[str, Any] = {"datetime": dt, "cash": cash, "equity": equity}
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
        per_sym = compute_per_symbol_metrics(equity_curve, trades, symbols, self.initial_capital)
        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            positions=positions,
            metrics=metrics,
            per_symbol_metrics=per_sym,
            config={
                "initial_capital": self.initial_capital,
                "fill_on": self.execution.fill_on,
                "slippage_type": self.execution.slippage_type,
                "slippage_value": self.execution.slippage_value,
                "delay_note": "signals must be pre-shifted (T close -> T+1 fill)",
            },
        )


def _sign(x: float) -> float:
    if x > 0:
        return 1.0
    if x < 0:
        return -1.0
    return 0.0


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
