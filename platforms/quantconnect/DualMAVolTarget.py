# QuantConnect Lean algorithm (paste into qc.com → Algorithm Lab).
# Spec: docs/STRATEGY_SPEC.md  |  frozen params: backtest/strategy_spec.py
#
# Cloud has no native SSE ETF. Custom data = the same static-qfq CSV the
# local engine exported. Paper trading polls GitHub raw; that is NOT a
# Shanghai call-auction fill.
#
# Timing: OnData(T) computes weight from closes through T and stores it;
#         OnData(T+1) fills that weight at T+1 Open. Matches local T+1 open.

from AlgorithmImports import *  # noqa: F403
from collections import deque
from datetime import timedelta
from math import sqrt

FAST = 30
SLOW = 120
ATR_WINDOW = 20
TREND_K = 1.0
VOL_LOOKBACK = 20
VOL_TARGET = 0.12
MAX_WEIGHT = 1.0
WEIGHT_STEP = 0.10
LOT_SIZE = 100
SLIPPAGE = 0.0005
COMMISSION_RATE = 0.0001
TRANSFER_RATE = 0.00001
COMMISSION_MIN = 0.1
CASH_BUFFER = 0.98  # leave cash for fees; avoids QC margin rejects
CSV_URL = (
    "https://raw.githubusercontent.com/david-quant-logs/"
    "event-driven-backtest-engine/main/platforms/quantconnect/data/510300.csv"
)


class Csi300Etf(PythonData):
    def GetSource(self, config, date, isLiveMode):
        return SubscriptionDataSource(CSV_URL, SubscriptionTransportMedium.RemoteFile)

    def Reader(self, config, line, date, isLiveMode):
        if not line or line.startswith("Date"):
            return None
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            return None
        bar = Csi300Etf()
        bar.Symbol = config.Symbol
        # Naive dates in UTC so each CSV row is one calendar session (not SH noon).
        bar.Time = datetime.strptime(parts[0], "%Y-%m-%d")
        bar.EndTime = bar.Time + timedelta(hours=8)
        bar["Open"] = float(parts[1])
        bar["High"] = float(parts[2])
        bar["Low"] = float(parts[3])
        bar["Close"] = float(parts[4])
        bar["Volume"] = float(parts[5])
        bar.Value = bar["Close"]
        return bar


class AshareEtfFeeModel(FeeModel):
    """ETF: commission 1 bp (floor 0.1) + transfer 0.1 bp. No stamp tax."""

    def GetOrderFee(self, parameters):
        security = parameters.Security
        order = parameters.Order
        qty = abs(float(order.Quantity))
        price = float(security.Price or 0.0)
        if price <= 0:
            price = float(getattr(order, "Price", 0.0) or 0.0)
        notional = qty * price
        fee = max(COMMISSION_MIN, notional * COMMISSION_RATE) + notional * TRANSFER_RATE
        return OrderFee(CashAmount(fee, "USD"))


class DualMAVolTarget(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2019, 1, 1)
        self.SetCash(1000000)
        self.SetTimeZone(TimeZones.Utc)
        # Custom data defaults to 0-fee + a margin model that rejects small rebalances.
        self.Settings.FreePortfolioValuePercentage = 0.02
        self.Settings.MinimumOrderMarginPortfolioPercentage = 0
        self.SetSecurityInitializer(self._init_security)
        self.ticker = self.AddData(Csi300Etf, "510300", Resolution.Daily).Symbol
        self.SetWarmUp(SLOW + VOL_LOOKBACK + 5, Resolution.Daily)

        self._closes = deque(maxlen=SLOW + 5)
        self._highs = deque(maxlen=SLOW + 5)
        self._lows = deque(maxlen=SLOW + 5)
        self._pending = 0.0
        self._have_pending = False

    def _init_security(self, security):
        security.SetFeeModel(AshareEtfFeeModel())
        security.SetSlippageModel(ConstantSlippageModel(SLIPPAGE))
        security.SetFillModel(ImmediateFillModel())
        # Local engine is a cash book; do not let QC's margin buffer block 10% steps.
        security.SetBuyingPowerModel(NullBuyingPowerModel())

    def OnData(self, data):
        if self.ticker not in data:
            return
        bar = data[self.ticker]
        o = float(bar["Open"])
        h = float(bar["High"])
        l = float(bar["Low"])
        c = float(bar["Close"])
        v = float(bar["Volume"])

        if self._have_pending and v > 0 and not self.IsWarmingUp:
            self._rebalance(o, self._pending)

        self._highs.append(h)
        self._lows.append(l)
        self._closes.append(c)
        self._pending = self._target_weight()
        self._have_pending = True

    def _rebalance(self, fill_px, target_w):
        if fill_px <= 0:
            return
        pv = float(self.Portfolio.TotalPortfolioValue) * CASH_BUFFER
        target_qty = int((pv * float(target_w) / fill_px) // LOT_SIZE) * LOT_SIZE
        holdings = float(self.Portfolio[self.ticker].Quantity)
        delta = target_qty - holdings
        if abs(delta) < LOT_SIZE:
            return
        if delta > 0:
            cash = float(self.Portfolio.Cash)
            max_qty = int((cash * CASH_BUFFER / fill_px) // LOT_SIZE) * LOT_SIZE
            delta = min(delta, max_qty)
            if delta < LOT_SIZE:
                return
        self.MarketOrder(self.ticker, int(delta))

    def _target_weight(self):
        n = len(self._closes)
        if n < SLOW:
            return 0.0
        closes = list(self._closes)
        highs = list(self._highs)
        lows = list(self._lows)
        fast = sum(closes[-FAST:]) / FAST
        slow = sum(closes[-SLOW:]) / SLOW
        trs = []
        for i in range(1, n):
            trs.append(
                max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
            )
        if len(trs) < ATR_WINDOW:
            return 0.0
        atr = sum(trs[-ATR_WINDOW:]) / ATR_WINDOW
        if atr <= 0:
            return 0.0
        if not (fast > slow and (fast - slow) / atr > TREND_K):
            return 0.0
        rets = [
            closes[i] / closes[i - 1] - 1.0
            for i in range(1, n)
            if closes[i - 1] != 0
        ]
        if len(rets) < VOL_LOOKBACK:
            return 0.0
        window = rets[-VOL_LOOKBACK:]
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        rvol = sqrt(var) * sqrt(252.0)
        if rvol <= 0:
            return 0.0
        w = round(min(MAX_WEIGHT, VOL_TARGET / rvol) / WEIGHT_STEP) * WEIGHT_STEP
        return max(0.0, min(MAX_WEIGHT, w))
