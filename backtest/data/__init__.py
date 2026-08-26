"""Data ingestion, adjustment, suspension marking, and quality checks."""

from __future__ import annotations

from backtest.data.adjust import apply_adjustment, choose_adjustment
from backtest.data.fetch_crypto import fetch_crypto_daily
from backtest.data.fetch_etf import fetch_etf_daily
from backtest.data.prepare import load_or_fetch_panel, prepare_symbol_frame
from backtest.data.quality import DataQualityReport, check_data_quality
from backtest.data.store import load_frame, save_frame

__all__ = [
    "DataQualityReport",
    "apply_adjustment",
    "check_data_quality",
    "choose_adjustment",
    "fetch_crypto_daily",
    "fetch_etf_daily",
    "load_frame",
    "load_or_fetch_panel",
    "prepare_symbol_frame",
    "save_frame",
]
