# 沪深300ETF 双均线 + 波动率标的（可移植版）
# 粘贴到聚宽「策略研究」新建策略。规格见仓库 docs/STRATEGY_SPEC.md
#
# 必须覆盖的平台默认值（不覆盖就不是同一策略）：
#   1. use_real_price + avoid_future_data
#   2. 基金费率 type='fund'（不要用股票印花税）
#   3. 09:31 用【昨日及以前】收盘算仓位，市价单吃当天开盘
#   4. skip_paused=False：停牌日留在均线窗口里，但 volume=0 时不下单

from jqdata import *
import numpy as np
import pandas as pd

FAST = 30
SLOW = 120
ATR_WINDOW = 20
TREND_K = 1.0
VOL_LOOKBACK = 20
VOL_TARGET = 0.12
MAX_WEIGHT = 1.0
WEIGHT_STEP = 0.10
LOT_SIZE = 100
LOOKBACK = SLOW + VOL_LOOKBACK + 5


def initialize(context):
    set_benchmark("510300.XSHG")
    set_option("use_real_price", True)
    set_option("avoid_future_data", True)
    set_option("order_volume_ratio", 1.0)
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0,
            open_commission=0.0001,
            close_commission=0.0001,
            close_today_commission=0,
            min_commission=0.1,
        ),
        type="fund",
    )
    set_slippage(PriceRelatedSlippage(0.0005), type="fund")
    g.security = "510300.XSHG"
    g.last_weight = None
    run_daily(rebalance, time="09:31", reference_security=g.security)
    log.info("DMA+vol 510300 SMA {}/{} k={} vol*={}".format(FAST, SLOW, TREND_K, VOL_TARGET))


def rebalance(context):
    hist = attribute_history(
        g.security,
        LOOKBACK,
        "1d",
        ["open", "high", "low", "close", "volume"],
        skip_paused=False,
        fq="pre",
        df=True,
    )
    if hist is None or len(hist) < SLOW:
        return
    # 09:31：history 不含今日，最后一行是昨日收盘 → 对应本地引擎的 T close 信号、T+1 开盘成交
    weight = _target_weight(hist)
    current = hist.iloc[-1]
    if float(current["volume"]) <= 0:
        log.info("skip suspended {}".format(context.current_dt))
        return
    qty = context.portfolio.positions[g.security].total_amount
    # 空仓且目标为 0 时聚宽会报「下单数量为 0」；规格也要求权重不变不调仓
    if abs(weight) < 1e-12 and qty == 0:
        g.last_weight = 0.0
        return
    if g.last_weight is not None and abs(weight - g.last_weight) < 1e-12:
        return
    target_value = weight * context.portfolio.total_value
    order_target_value(g.security, target_value)
    g.last_weight = weight
    log.info("rebalance w={:.2f} value={:.0f}".format(weight, target_value))


def _target_weight(hist):
    close = hist["close"].astype(float)
    high = hist["high"].astype(float)
    low = hist["low"].astype(float)
    fast = close.rolling(FAST, min_periods=FAST).mean().iloc[-1]
    slow = close.rolling(SLOW, min_periods=SLOW).mean().iloc[-1]
    if np.isnan(fast) or np.isnan(slow):
        return 0.0
    prev_c = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_c).abs(), (low - prev_c).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(ATR_WINDOW, min_periods=ATR_WINDOW).mean().iloc[-1]
    if not atr or atr <= 0 or np.isnan(atr):
        return 0.0
    strength = (fast - slow) / atr
    if not (fast > slow and strength > TREND_K):
        return 0.0
    rets = close.pct_change()
    rvol = rets.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK).std(ddof=0).iloc[-1]
    if rvol is None or np.isnan(rvol) or rvol <= 0:
        return 0.0
    rvol *= np.sqrt(252.0)
    w = min(MAX_WEIGHT, VOL_TARGET / float(rvol))
    w = round(w / WEIGHT_STEP) * WEIGHT_STEP
    return float(max(0.0, min(MAX_WEIGHT, w)))
