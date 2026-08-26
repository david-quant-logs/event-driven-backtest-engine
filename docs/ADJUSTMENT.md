# 复权选择说明（审计用）

本引擎默认使用 **前复权（qfq / forward adjustment）** 价格做信号与回测盯市，并保留 `adj_factor` 列便于核对。

## 为什么选前复权

| 方式 | 对双均线的影响 | 本项目选择 |
| --- | --- | --- |
| 不复权 | 分红/拆分日出现价格跳空，容易制造假交叉 | 否 |
| 后复权（hfq） | 交叉日期与前复权接近，但绝对价格远离现价，仓位审计困难 | 否 |
| 前复权（qfq） | 历史 K 线与最新收盘连续，和常见行情软件一致，适合 MA 信号 | **是** |

实现见 `backtest/data/adjust.py`。AkShare/东财在请求时已带 `adjust=qfq`；若将来接入未复权 + 独立复权因子序列，`apply_adjustment` 会按 `factor / last_factor` 缩放到前复权尺度。

## 停牌

- 成交量 ≤ 0 的 bar 标记 `suspended=True`，价格保留（停牌日价格不变）。
- 执行层 `is_tradable` 在停牌日 **跳过成交**，持仓与目标差异会留在当日持仓明细的 `skipped_suspended` 字段。
