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

第 3 周（510300 双均线 + 波动率标的，三平台可移植）：

```powershell
python examples/run_dma_vol_research.py
python examples/run_attribution.py
```

只跑单元测试：

```powershell
python -m pytest -q
```

## 默认回测标的

1. **ETF 组合（第 1–2 周教学版）**：沪深300ETF `510300` + 中证500ETF `510500`，自 2019-01-01（≥5 年），20/60 日 SMA 双均线，多标的等权。
2. **加密货币**：`BTC_USDT` 日线（Gate，失败回退 Binance），12/26 日 EMA。
3. **第 3 周 canonical**：单标的 `510300`，SMA 30/120 + ATR 过滤 + 12% 波动率标的（见上）。

## 模块结构

```
backtest/                 # 事件驱动引擎（数据/信号/成交）
performance_analytics/    # 第2周：费率、滑点、完整指标、报告
platforms/                # 第3周：QuantConnect Lean / 聚宽粘贴稿
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

## 第 3 周：三平台复现与差异归因

Canonical 策略不再用教学版 20/60 等权组合，而是单标的 **510300 双均线 + ATR 强度过滤 + 波动率标的**（SMA 30/120，k=1，目标波动 12%，仓位 10% 步进）。参数只在 2019–2022 上选择，2023+ 只报告。

| 文档 / 代码 | 用途 |
| --- | --- |
| [docs/STRATEGY_SPEC.md](docs/STRATEGY_SPEC.md) | 三平台必须对齐的公式与成交合约 |
| [docs/DMA_VOL_RESEARCH.md](docs/DMA_VOL_RESEARCH.md) | IS/OOS 与买入持有对照 |
| [docs/qc_research_report.md](docs/qc_research_report.md) | QuantConnect 英文研究报告 |
| [docs/joinquant_strategy_post.md](docs/joinquant_strategy_post.md) | 聚宽发帖稿 |
| [docs/CROSS_PLATFORM_ATTRIBUTION.md](docs/CROSS_PLATFORM_ATTRIBUTION.md) | **Day 5–6 核心产出**：一页归因表（数据/成交/费率/绩效口径均已量化） |
| [docs/PLATFORM_LINKS.md](docs/PLATFORM_LINKS.md) | 公开回测、Research 帖、聚宽链接 |
| [`platforms/quantconnect/DualMAVolTarget.py`](platforms/quantconnect/DualMAVolTarget.py) | Lean 自定义数据算法 |
| [`platforms/joinquant/dual_ma_vol_target.py`](platforms/joinquant/dual_ma_vol_target.py) | 聚宽粘贴稿 |

QC 云端没有上交所 ETF：自定义数据用本仓库导出的 [`platforms/quantconnect/data/510300.csv`](platforms/quantconnect/data/510300.csv)。公开链接：[QC 回测](https://www.quantconnect.cloud/backtest/97782a6933f5ad26546e921833bcb2e3/?theme=darkly) · [QC Research](https://www.quantconnect.com/research/21289/dual-ma-trend-with-volatility-targeting-on-csi-300-etf-portability-not-alpha/p1) · [聚宽帖](https://www.joinquant.com/view/community/detail/78746) · [聚宽模拟盘](https://www.joinquant.com/algorithm/live/index?backtestId=55e474b188c8afb46a66d4dcd5ddf5d7)。

## 配置

编辑 `config.yaml`（`fee_profile`、`slippage_type` 等）。可选 `TUSHARE_TOKEN`。

## 许可

MIT
