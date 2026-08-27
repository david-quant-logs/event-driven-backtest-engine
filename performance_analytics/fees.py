"""
Configurable fee matrix for stocks, ETFs, and crypto perpetuals.

Profiles encode exchange / venue defaults. The engine looks up a profile by
name (or asset-class fallback) and charges commissions, stamp tax, transfer
fees, maker/taker, and a simplified daily funding rate for perps.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FeeSpec:
    """Single venue / asset-class fee schedule."""

    name: str
    asset_class: str  # stock | etf | crypto_perp
    # Cash equities / ETF
    commission_rate: float = 0.0
    commission_min: float = 0.0
    stamp_tax_rate: float = 0.0  # charged on sells only (A-share stock)
    transfer_fee_rate: float = 0.0
    # Crypto perpetual
    maker_rate: float = 0.0
    taker_rate: float = 0.0
    # Simplified overnight funding (fraction of notional per calendar day)
    funding_rate_per_day: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FeeResult:
    """Breakdown of fees for one fill."""

    commission: float = 0.0
    stamp_tax: float = 0.0
    transfer_fee: float = 0.0
    taker_or_maker: float = 0.0
    funding: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.commission
            + self.stamp_tax
            + self.transfer_fee
            + self.taker_or_maker
            + self.funding
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "commission": self.commission,
            "stamp_tax": self.stamp_tax,
            "transfer_fee": self.transfer_fee,
            "taker_or_maker": self.taker_or_maker,
            "funding": self.funding,
            "total": self.total,
        }


def default_fee_matrix() -> dict[str, FeeSpec]:
    """
    Built-in fee matrix (China retail + Gate-like perp defaults).

    - A-share stock: commission 万2.5 (min ¥5), stamp tax 千1 on sell, transfer 万0.1
    - A-share ETF: commission 万1 (min ¥0.1), no stamp tax, transfer 万0.1
    - Crypto perp (Gate-style): taker 0.05%, maker 0.015%, funding ~0.01%/day proxy
    """
    return {
        "ashare_stock": FeeSpec(
            name="ashare_stock",
            asset_class="stock",
            commission_rate=0.00025,
            commission_min=5.0,
            stamp_tax_rate=0.001,
            transfer_fee_rate=0.00001,
            notes="佣金万2.5最低5元；印花税卖出千1；过户费万0.1",
        ),
        "ashare_etf": FeeSpec(
            name="ashare_etf",
            asset_class="etf",
            commission_rate=0.0001,
            commission_min=0.1,
            stamp_tax_rate=0.0,
            transfer_fee_rate=0.00001,
            notes="ETF佣金更低（万1）、无印花税",
        ),
        "gate_perp": FeeSpec(
            name="gate_perp",
            asset_class="crypto_perp",
            maker_rate=0.00015,
            taker_rate=0.0005,
            funding_rate_per_day=0.0001,
            notes="Maker/Taker + 简化日度资金费率代理",
        ),
        "zero": FeeSpec(name="zero", asset_class="etf", notes="zero-cost baseline"),
        "jq_stock_default": FeeSpec(
            name="jq_stock_default",
            asset_class="stock",
            commission_rate=0.0003,
            commission_min=5.0,
            stamp_tax_rate=0.001,
            transfer_fee_rate=0.00001,
            notes="聚宽股票默认近似：佣金万3最低5元 + 卖出印花税千1（未覆盖 type=fund）",
        ),
        "qc_ib_like": FeeSpec(
            name="qc_ib_like",
            asset_class="etf",
            commission_rate=0.00125,
            commission_min=1.0,
            stamp_tax_rate=0.0,
            transfer_fee_rate=0.0,
            notes="IB 美股约 $0.005/股在 510300≈4 元时约 12.5bps 的费率代理",
        ),
    }


@dataclass
class FeeMatrix:
    """Lookup table: profile name or symbol → FeeSpec."""

    profiles: dict[str, FeeSpec] = field(default_factory=default_fee_matrix)
    symbol_map: dict[str, str] = field(default_factory=dict)
    default_profile: str = "zero"

    def resolve(self, symbol: str, profile: str | None = None) -> FeeSpec:
        """Resolve fee schedule for a symbol."""
        key = profile or self.symbol_map.get(symbol) or self.default_profile
        if key not in self.profiles:
            raise KeyError(f"Unknown fee profile: {key}")
        return self.profiles[key]

    def compute_fill_fees(
        self,
        *,
        symbol: str,
        side: str,
        notional: float,
        profile: str | None = None,
        is_taker: bool = True,
        holding_notional_for_funding: float = 0.0,
        apply_funding: bool = False,
    ) -> FeeResult:
        """
        Compute fee breakdown for one trade.

        ``holding_notional_for_funding`` is the absolute overnight exposure used
        when ``apply_funding`` is True (crypto perps).
        """
        spec = self.resolve(symbol, profile)
        out = FeeResult()
        notional = abs(float(notional))

        if spec.asset_class == "crypto_perp":
            rate = spec.taker_rate if is_taker else spec.maker_rate
            out.taker_or_maker = notional * rate
            if apply_funding and holding_notional_for_funding:
                out.funding = abs(holding_notional_for_funding) * spec.funding_rate_per_day
            return out

        commission = notional * spec.commission_rate
        if spec.commission_min > 0:
            commission = max(commission, spec.commission_min)
        out.commission = commission
        out.transfer_fee = notional * spec.transfer_fee_rate
        if side == "sell" and spec.stamp_tax_rate > 0:
            out.stamp_tax = notional * spec.stamp_tax_rate
        return out

    def fee_erosion(
        self,
        *,
        total_fees: float,
        gross_pnl: float,
        initial_capital: float,
    ) -> dict[str, float]:
        """
        Quantify how much fees eat into strategy P&L.

        - ``erosion_vs_gross``: fees / |gross_pnl| when gross ≠ 0
        - ``erosion_vs_capital``: fees / initial_capital
        """
        total_fees = float(total_fees)
        gross_pnl = float(gross_pnl)
        initial_capital = float(initial_capital)
        vs_gross = abs(total_fees / gross_pnl) if abs(gross_pnl) > 1e-9 else float("nan")
        return {
            "total_fees": total_fees,
            "gross_pnl": gross_pnl,
            "net_pnl": gross_pnl - total_fees,
            "erosion_vs_gross": vs_gross,
            "erosion_vs_capital": total_fees / initial_capital if initial_capital else float("nan"),
        }
