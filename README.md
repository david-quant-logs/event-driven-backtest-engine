# event-driven-backtest-engine

可审计的事件驱动回测引擎：数据 → 信号 → 成交 → 绩效。基于此前
[quant-data-pipeline](https://github.com/david-quant-lab/quant-data-pipeline)
的拉取经验做成独立第 1 周项目。

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

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

只跑单元测试：

```powershell
python -m pytest -q
```

单独示例：

```powershell
python examples/run_etf_dual_ma.py
python examples/run_crypto_dual_ma.py
python examples/run_lookahead_check.py
```

## 默认回测标的

1. **ETF 组合**：沪深300ETF `510300` + 中证500ETF `510500`，自 2019-01-01（≥5 年），20/60 日 SMA 双均线，多标的等权。
2. **加密货币**：`BTC_USDT` 日线（Gate，失败回退 Binance），12/26 日 EMA。

输出目录：

```
output/reports/etf_dual_ma/     # 资金曲线、交易明细、持仓、指标
output/reports/crypto_dual_ma/
output/reports/lookahead_detection.md
output/charts/*_equity.png
docs/LOOKAHEAD_REPORT.md        # 前视偏差检测报告（交付物）
```

## 模块结构

```
backtest/
  data/          # 拉取、复权、停牌、质量检查
  signals/       # 双均线 + 执行移位
  execution/     # 滑点、成交价模式
  engine.py      # 多标的事件循环
  metrics.py     # 组合 / 单标的绩效
  lookahead.py   # 完美信号前视检测
  report.py      # CSV / Markdown / 图
examples/        # 两个策略示例 + 检测脚本
tests/
docs/
```

## 前视偏差检测

`backtest/lookahead.py` 用「知道下一根收盘涨跌」的完美信号对比：

- **泄漏路径**：信号不移位，当日收盘成交 → 应出现过高收益
- **安全路径**：强制 `shift(1)` + T+1 开盘成交 → 收益显著更低

若安全路径仍接近泄漏路径，判定引擎存在漏洞。报告见 `docs/LOOKAHEAD_REPORT.md`。

## 配置

编辑 `config.yaml`。可选 `TUSHARE_TOKEN`（复制 `.env.example` → `.env`）作为 ETF 拉取最后回退。

## 许可

MIT
