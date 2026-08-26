"""Tests for fee matrix and fee erosion."""

from __future__ import annotations

from performance_analytics.fees import FeeMatrix, default_fee_matrix


def test_stock_sell_includes_stamp_tax():
    m = FeeMatrix(profiles=default_fee_matrix(), default_profile="ashare_stock")
    buy = m.compute_fill_fees(symbol="600000", side="buy", notional=100_000, profile="ashare_stock")
    sell = m.compute_fill_fees(symbol="600000", side="sell", notional=100_000, profile="ashare_stock")
    assert buy.stamp_tax == 0.0
    assert abs(sell.stamp_tax - 100.0) < 1e-9  # 千1
    assert buy.commission >= 5.0
    assert sell.total > buy.total


def test_etf_no_stamp_tax():
    m = FeeMatrix(profiles=default_fee_matrix(), default_profile="ashare_etf")
    sell = m.compute_fill_fees(symbol="510300", side="sell", notional=100_000, profile="ashare_etf")
    assert sell.stamp_tax == 0.0
    assert sell.commission == max(100_000 * 0.0001, 0.1)


def test_crypto_taker_and_funding():
    m = FeeMatrix(profiles=default_fee_matrix(), default_profile="gate_perp")
    fill = m.compute_fill_fees(
        symbol="BTC_USDT",
        side="buy",
        notional=10_000,
        profile="gate_perp",
        is_taker=True,
        holding_notional_for_funding=10_000,
        apply_funding=True,
    )
    assert abs(fill.taker_or_maker - 5.0) < 1e-9
    assert abs(fill.funding - 1.0) < 1e-9


def test_fee_erosion_ratio():
    m = FeeMatrix()
    stats = m.fee_erosion(total_fees=100, gross_pnl=1000, initial_capital=10_000)
    assert abs(stats["erosion_vs_gross"] - 0.1) < 1e-9
    assert abs(stats["net_pnl"] - 900) < 1e-9
