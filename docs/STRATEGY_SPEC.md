# Strategy spec — CSI 300 ETF dual-MA + volatility targeting

Canonical week-3 strategy. Local engine, QuantConnect Lean, and JoinQuant
must implement this document, not a private variant. Parameters below are
**frozen after the IS grid** (2019-01-01 – 2022-12-31). OOS (2023-01-01 onward)
is report-only.

Python source of truth: [`backtest/strategy_spec.py`](../backtest/strategy_spec.py).

## Universe and sample

| Item | Value |
| --- | --- |
| Symbol | `510300` (沪深300ETF / CSI 300 ETF, Shanghai) |
| Adjustment (local / QC CSV) | Static **前复权 (qfq)** |
| Start | 2019-01-01 |
| IS end | 2022-12-31 |
| OOS start | 2023-01-01 |
| Calendar | Exchange trading days in the price file; `volume <= 0` → suspended |
| Initial capital | 1,000,000 CNY |

## Signal (after session close on day T)

Let \(P_t\) be the adjusted close.

1. \(\mathrm{SMA}^{fast}_t = \frac{1}{L_f}\sum_{i=0}^{L_f-1} P_{t-i}\), same for \(L_s\) (slow). SMA, not EMA.
2. True range \(\mathrm{TR}_t = \max(H_t-L_t, |H_t-P_{t-1}|, |L_t-P_{t-1}|)\); \(\mathrm{ATR}_t\) is the \(N_{atr}\)-day mean of TR.
3. Trend strength \(s_t = (\mathrm{SMA}^{fast}_t - \mathrm{SMA}^{slow}_t) / \mathrm{ATR}_t\).
4. In-trend iff \(\mathrm{SMA}^{fast}_t > \mathrm{SMA}^{slow}_t\) and \(s_t > k\).
5. Realized vol \(\sigma_t = \mathrm{std}_{ddof=0}(r_{t-N_v+1:t}) \times \sqrt{252}\) where \(r\) is close-to-close return.
6. Target weight at close, then **round to the nearest 10%** (`weight_step = 0.10`) so a 1 bp move in realized vol does not fire a ticket:

\[
w_t =
\begin{cases}
\mathrm{round}_{0.1}\!\left(\min\!\left(1,\; \sigma^\star / \sigma_t\right)\right) & \text{if in-trend and } \sigma_t > 0 \\
0 & \text{otherwise}
\end{cases}
\]

No leverage (\(w_t \le 1\)). Cash when the filter is off.

## Frozen parameters

| Name | Value |
| --- | --- |
| `fast` \(L_f\) | **30** |
| `slow` \(L_s\) | **120** |
| `ma_type` | `sma` |
| `atr_window` \(N_{atr}\) | 20 |
| `trend_k` \(k\) | **1.0** |
| `vol_lookback` \(N_v\) | 20 |
| `vol_target` \(\sigma^\star\) | **0.12** |
| `max_weight` | 1.0 |
| `weight_step` | **0.10** (round \(w_t\) to 10% so vol targeting does not trade every bar) |

## Execution

| Item | Rule |
| --- | --- |
| Timing | \(w_t\) is known after T close; first fill is **T+1 open** |
| Lot | 100 shares (A-share ETF board lot) |
| Suspension | Skip fills when `volume <= 0` / `suspended` |
| Slippage | 5 bps of fill price, buy up / sell down |
| Fees | ETF: commission 1 bp (min 0.1 CNY), transfer 0.1 bp, **no stamp tax** |
| Rebalance | Only when the target weight changes (no daily drift rebalance) |

## Performance convention (local baseline)

- Annualized return: \((1+R)^{252/n}-1\) on the equity curve (\(n\) = bars − 1).
- Sharpe: daily mean / daily std (\(ddof=0\)) × \(\sqrt{252}\), risk-free = 0.
- Max drawdown: peak-to-trough on marked-to-close equity.

## What this is not

- Not a multi-ETF equal-weight sleeve (that remains the week-1/2 example).
- Not same-bar close fills.
- Not JoinQuant’s default stock commission/stamp schedule (must override `type='fund'`).
- Not QuantConnect IB US-equity fees (must attach an explicit fee model).

## Literature

- Brock, Lakonishok, LeBaron (1992), *Journal of Finance* — moving-average crossover.
- Moskowitz, Ooi, Pedersen (2012), *JFE* — time-series momentum.
- Moreira and Muir (2017), *Journal of Finance*; Barroso and Santa-Clara (2015) — volatility targeting / scaled momentum.
