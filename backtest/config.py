"""Configuration loading for the backtest engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class EngineConfig:
    """Execution and portfolio settings shared by all examples."""

    initial_capital: float = 1_000_000.0
    fill_on: str = "next_open"  # next_open | next_close
    delay_bars: int = 0
    slippage_type: str = "percent"  # percent | ticks
    slippage_value: float = 0.001
    tick_size: float = 0.001
    commission_rate: float = 0.0
    lot_size: int = 100


@dataclass
class EtfRunConfig:
    """ETF dual-MA example defaults."""

    symbols: list[str] = field(default_factory=lambda: ["510300", "510500"])
    start: str = "2019-01-01"
    end: str | None = None
    fast: int = 20
    slow: int = 60
    ma_type: str = "sma"
    side: str = "long_only"


@dataclass
class CryptoRunConfig:
    """Crypto dual-MA example defaults."""

    symbol: str = "BTC_USDT"
    interval: str = "1d"
    start: str = "2019-01-01"
    fast: int = 12
    slow: int = 26
    ma_type: str = "ema"
    side: str = "long_only"
    lot_size: int = 0
    tick_size: float = 0.01
    initial_capital: float = 10_000.0


@dataclass
class AppConfig:
    """Top-level config from config.yaml."""

    engine: EngineConfig = field(default_factory=EngineConfig)
    etf: EtfRunConfig = field(default_factory=EtfRunConfig)
    crypto: CryptoRunConfig = field(default_factory=CryptoRunConfig)
    output_dir: Path = Path("output")
    data_dir: Path = Path("data")


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load YAML config and optional .env (TUSHARE_TOKEN)."""
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    raw: dict[str, Any] = {}
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    engine_keys = {
        "initial_capital",
        "fill_on",
        "delay_bars",
        "slippage_type",
        "slippage_value",
        "tick_size",
        "commission_rate",
        "lot_size",
    }
    engine_raw = {k: raw[k] for k in engine_keys if k in raw}
    etf_raw = dict(raw.get("etf") or {})
    crypto_raw = dict(raw.get("crypto") or {})

    return AppConfig(
        engine=EngineConfig(**engine_raw),
        etf=EtfRunConfig(**etf_raw),
        crypto=CryptoRunConfig(**crypto_raw),
        output_dir=Path(raw.get("output_dir") or "output"),
        data_dir=Path(raw.get("data_dir") or "data"),
    )
