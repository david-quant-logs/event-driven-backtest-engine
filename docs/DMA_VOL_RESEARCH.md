# 510300 Dual-MA + Volatility Targeting — Research Note

In-sample window **2019-01-01 – 2022-12-31** is the only place parameters
were chosen. Out-of-sample **2023-01-01 onward** is reported, not tuned.

## Frozen parameters

- SMA `30` / `120`
- ATR window `20`, trend strength threshold `k = 1.0`
- Vol lookback `20`, target vol `12%`, leverage cap 1.0, **weight step 10%**
- Selection rule: `max IS Sharpe among max_dd >= -40% (else unconstrained max Sharpe)`
- Winning IS Sharpe `0.356`, IS max DD `-11.73%`

Full spec: [STRATEGY_SPEC.md](STRATEGY_SPEC.md).

## Equity vs buy & hold

![equity](charts/dma_vol_equity_vs_buyhold.png)

## IS Sharpe heatmap (winner vol* and k)

![heatmap](charts/dma_vol_is_sharpe_heatmap.png)

### In sample (2019–2022)

| | Strategy | Buy & hold |
| --- | ---: | ---: |
| Total return | 11.32% | 49.41% |
| Annualized | 2.82% | 10.98% |
| Sharpe | 0.356 | 0.566 |
| Max DD | -11.73% | -40.22% |
| Trades | 91 | 1 |
| Fees | 1605 | 110 |

### Out of sample (2023– )

| | Strategy | Buy & hold |
| --- | ---: | ---: |
| Total return | 9.02% | 28.00% |
| Annualized | 2.50% | 7.31% |
| Sharpe | 0.339 | 0.472 |
| Max DD | -10.27% | -24.15% |
| Trades | 66 | 1 |
| Fees | 1497 | 110 |

### Full sample

| | Strategy | Buy & hold |
| --- | ---: | ---: |
| Total return | 15.09% | 91.89% |
| Annualized | 1.93% | 9.26% |
| Sharpe | 0.258 | 0.525 |
| Max DD | -17.38% | -44.75% |
| Trades | 173 | 1 |
| Fees | 3607 | 110 |

## Interpretation

Volatility targeting and the ATR trend filter are not a promise of higher
compounded return versus sitting in 510300. They exist to cut exposure in
choppy, high-vol regimes and to make the sleeve portable across platforms
with a single weight series. If OOS Sharpe is weak, that is left in the
table — the parameter tuple is not reopened.
