# Public strategy links (week 3)

Fill after you share the QuantConnect backtest and the JoinQuant post/sim.
Do not commit API keys. Screenshots go in [`docs/screenshots/`](screenshots/).

| Platform | What to publish | URL | Backtest span | Runtime | Total return | Fees | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Local engine | this repo | https://github.com/david-quant-logs/event-driven-backtest-engine | 2019-01-02 – 2026-08-25 | n/a | 15.09% (CAGR 1.93%) | 3,607 | Frozen SMA 30/120, k=1, vol*=12%; Sharpe 0.258; max DD −17.38% |
| QuantConnect | Shared backtest **Determined Orange Jaguar** | https://www.quantconnect.cloud/backtest/97782a6933f5ad26546e921833bcb2e3/?theme=darkly | 2019-01-01 – 2026-05-29 | 17.0s | 15.62% | 3,847 | Custom data CSV; paper ≠ SSE auction; equity 1,156,225 |
| QuantConnect | Research post | https://www.quantconnect.com/research/21289/dual-ma-trend-with-volatility-targeting-on-csi-300-etf-portability-not-alpha/p1 | same | n/a | — | — | Pending 3 community upvotes to leave review |
| JoinQuant | Community post | https://www.joinquant.com/view/community/detail/78746 | 2019-01-01 – 2026-06-26 | n/a | 20.97% (ann. 2.60%) | — | Headline Sharpe −0.153 is rf≈4%; max DD 16.82%; Beta 0.304 |
| JoinQuant | 模拟盘 | https://www.joinquant.com/algorithm/live/index?backtestId=55e474b188c8afb46a66d4dcd5ddf5d7 | live from same backtest | n/a | — | — | `type='fund'` + 09:31; paper ≠ 可成交保证 |

## QuantConnect checklist

1. Push `platforms/quantconnect/data/510300.csv` to `main` so `CSV_URL` resolves.
2. New Python algorithm → paste [`platforms/quantconnect/DualMAVolTarget.py`](../platforms/quantconnect/DualMAVolTarget.py).
3. Backtest 2019-01-01, cash 1,000,000.
4. Share → copy URL here. Deploy Paper Trading. **Done:** [Determined Orange Jaguar](https://www.quantconnect.cloud/backtest/97782a6933f5ad26546e921833bcb2e3/?theme=darkly)
5. Save a PNG of runtime + statistics as `docs/screenshots/qc_backtest.png`.
6. Strategy description: paste [`docs/qc_community_research.md`](qc_community_research.md). **Done:** [Research #21289](https://www.quantconnect.com/research/21289/dual-ma-trend-with-volatility-targeting-on-csi-300-etf-portability-not-alpha/p1)

## JoinQuant checklist

1. New strategy → paste [`platforms/joinquant/dual_ma_vol_target.py`](../platforms/joinquant/dual_ma_vol_target.py).
2. 回测 2019-01-01 至今，资金 100 万。
3. 分享策略 / 启动模拟盘。**Done:** [社区帖 #78746](https://www.joinquant.com/view/community/detail/78746) · [模拟盘](https://www.joinquant.com/algorithm/live/index?backtestId=55e474b188c8afb46a66d4dcd5ddf5d7)
4. Optional: save `docs/screenshots/jq_backtest.png`.
5. 发帖。**Done:** 同上社区帖。
