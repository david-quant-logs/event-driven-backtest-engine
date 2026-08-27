# 把一条「能讲清楚」的双均线，同时搬到聚宽、QuantConnect 和自研引擎

> 策略研究帖，不是收益排行榜。完整规格与三平台代码在 GitHub：
> [event-driven-backtest-engine](https://github.com/david-quant-logs/event-driven-backtest-engine)
> 聚宽粘贴稿：`platforms/joinquant/dual_ma_vol_target.py`
>
> 已发布：[社区帖 #78746](https://www.joinquant.com/view/community/detail/78746) · [模拟盘](https://www.joinquant.com/algorithm/live/index?backtestId=55e474b188c8afb46a66d4dcd5ddf5d7)

## 1. 为什么不是 20/60 等权两只 ETF

第 1–2 周的教学版（510300+510500、20/60 SMA、等权）全样本年化大约 0.5%、夏普 0.11。那份结果只适合证明「引擎没有前视」，不适合当成公开代表作。

这一版收成 **单标的 510300**，做三件事：

1. **慢速趋势**：SMA(30) 上穿 SMA(120) 才考虑做多（Brock et al. 1992 的均线；时序动量见 Moskowitz et al. 2012）。
2. **强度过滤**：\((MA_{fast}-MA_{slow})/ATR_{20} > 1\)，把「均线缠绕」挡在门外。
3. **波动率标的**：进入趋势后仓位 \(w=\mathrm{round}_{10\%}(\min(1, 12\%/\sigma_{20}))\)，现金账户不杠杆（Moreira & Muir / Barroso）。10% 步进是为了避免波动率每天抖 1bp 就刷单。

参数只在 **2019-01-01～2022-12-31** 上用夏普（且回撤不差于 -40%）选出来。2023 年以后是样本外，**不再改窗口**。

## 2. 本地回测（与聚宽应对齐的合约）

成交约定：T 日收盘后算信号，**T+1 开盘**成交，整手 100，停牌（成交量 0）跳过。费率按场内 ETF：佣金万 1、过户万 0.1、**无印花税**，滑点 5bps。复权用静态前复权。

| 区间 | 策略年化 | 夏普 | 最大回撤 | 510300 买入持有年化 | 持有夏普 | 持有回撤 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 样本内 2019–2022 | 2.82% | 0.356 | -11.73% | 10.98% | 0.566 | -40.22% |
| 样本外 2023– | 2.50% | 0.339 | -10.27% | 7.31% | 0.472 | -24.15% |
| 全样本 | 1.93% | 0.258 | -17.38% | 9.26% | 0.525 | -44.75% |

样本外夏普几乎没掉（0.34 vs 0.36）。代价很清楚：**趋势+降杠杆会系统性跑输牛市里的买入持有**，回撤大约只有 ETF 的三分之一。这是产品设计，不是没调好参数。

震荡市（2021–2022、2023–2024 一段）才是这套过滤器赚钱的地方；单边慢牛、浅回调，它会因为现金和均线滞后而落后。

## 3. 聚宽实现时必须改掉的默认值

不改下面几项，回测数字和本地/QC 对不上，也不要拿来发帖：

| 默认陷阱 | 本策略做法 |
| --- | --- |
| 股票佣金万 3 + 印花税千 1 | `set_order_cost(..., type='fund')`，佣金万 1、印花税 0 |
| `handle_data` 日频容易用到当日收盘 | `run_daily(rebalance, time='09:31')`，`attribute_history` 不含今日 |
| 静态前复权用未来因子 | `set_option('use_real_price', True)` + `avoid_future_data` |
| `skip_paused=True` 把停牌日从均线窗口删掉 | `skip_paused=False`，但 `volume<=0` 当日不下单 |
| 默认滑点偏大 | `PriceRelatedSlippage(0.0005)` |

动态复权相对本地静态 qfq，会在除权日附近把均线交叉平移 0～1 天。这是差异归因里单独量化的一项，不是「聚宽不准」。

## 4. 怎么跑、怎么公开

1. 新建策略，粘贴仓库里的 `platforms/joinquant/dual_ma_vol_target.py`。
2. 回测区间 2019-01-01 至今，初始资金 100 万，日频。
3. 点「分享策略 / 模拟盘」，把可点击链接发在帖子置顶。
4. 截图回测耗时和绩效，对照 GitHub [`docs/CROSS_PLATFORM_ATTRIBUTION.md`](https://github.com/david-quant-logs/event-driven-backtest-engine/blob/main/docs/CROSS_PLATFORM_ATTRIBUTION.md)。

英文版研究报告（QuantConnect）：
[Portability, Not Alpha](https://www.quantconnect.com/research/21289/dual-ma-trend-with-volatility-targeting-on-csi-300-etf-portability-not-alpha/p1)

Lean 公开回测：
[Determined Orange Jaguar](https://www.quantconnect.cloud/backtest/97782a6933f5ad26546e921833bcb2e3/?theme=darkly)
同一条公式，三个撮合引擎。总收益 QC 15.62% / 本地 15.09% / 聚宽 20.97%（年化 2.60%，最大回撤 16.82%；平台夏普 −0.153 为 rf≈4%）。

## 5. 一句结论

这不是「年化碾压沪深300」的策略。它是一条 **可审计、可移植、样本外夏普稳定、用回撤换收益** 的趋势袖套。把聚宽链接、QC 链接和本地归因表放在一起，比再调一个窗口更有说服力。
