# event-driven-backtest-engine

可审计的事件驱动回测引擎：数据 → 信号 → 成交 → 绩效。基于此前
[quant-data-pipeline](https://github.com/david-quant-logs/quant-data-pipeline)
的拉取经验做成独立项目（第 1–2 周）。

数据源：

- A 股 ETF：腾讯行情（东财不可达时的主路径）→ AkShare / 东财 / 新浪 → 可选 Tushare
- 加密货币：Gate → Binance

## 设计约定（避免前视）

| 环节 | 约定 |
| --- | --- |
| 信号 | T 日 **收盘后** 用当日及之前的收盘价计算（双均线 SMA/EMA） |
| 成交 | 最早在 **T+1** 开盘或收盘成交（`fill_on: next_open \| next_close`） |
| 延迟 | `delay_bars` 在 T+1 之外再推迟 N 根 K 线 |
| 复权 | 默认 **前复权**，说明见 [docs/ADJUSTMENT.md](docs/ADJUSTMENT.md) |
| 停牌 | `volume=0` → `suspended`，成交跳过 |
| 费率 | 可配置费率矩阵（股票 / ETF / 永续） |
| 滑点 | 固定比例、成交量冲击、波动率调整 |

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

第 2 周完整绩效报告（含滑点敏感性）：

```powershell
python examples/run_performance_report.py
```

只跑单元测试：

```powershell
python -m pytest -q
```

## 默认回测标的

1. **ETF 组合**：沪深300ETF `510300` + 中证500ETF `510500`，自 2019-01-01（≥5 年），20/60 日 SMA 双均线，多标的等权。
2. **加密货币**：`BTC_USDT` 日线（Gate，失败回退 Binance），12/26 日 EMA。

## 模块结构

```
backtest/                 # 事件驱动引擎（数据/信号/成交）
performance_analytics/    # 第2周：费率、滑点、完整指标、报告
examples/
tests/
docs/
```

### performance_analytics

- `fees.py` — 费率矩阵（万2.5+印花税 / ETF 万1无印花税 / Maker·Taker·资金费）
- `slippage.py` — 固定比例、volume participation、波动率调整滑点
- `metrics.py` — Sortino / Omega / 滚动夏普 / Bootstrap / 基准对比
- `sensitivity.py` — 滑点敏感性表
- `distribution.py` — 偏度峰度与夏普适用性讨论
- `report.py` — 一键 Markdown 绩效报告（资金曲线、回撤、月度热力图）

## 前视偏差检测

见 [docs/LOOKAHEAD_REPORT.md](docs/LOOKAHEAD_REPORT.md)。

## 第 2 周绩效报告

见 [docs/DUAL_MA_PERFORMANCE_REPORT.md](docs/DUAL_MA_PERFORMANCE_REPORT.md)（含滑点敏感性与收益分布讨论）。

## 配置

编辑 `config.yaml`（`fee_profile`、`slippage_type` 等）。可选 `TUSHARE_TOKEN`。

## 许可

MIT
