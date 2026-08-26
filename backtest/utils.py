"""Shared helpers: HTTP session, retries, symbol normalization."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import requests

T = TypeVar("T")

USER_AGENT = "Mozilla/5.0 (event-driven-backtest-engine/0.1)"


def retry(fn: Callable[[], T], attempts: int = 4, delay: float = 1.5) -> T:
    """Retry a callable with linear backoff."""
    last_error: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if i == attempts - 1:
                break
            time.sleep(delay * (i + 1))
    assert last_error is not None
    raise last_error


def http_session() -> requests.Session:
    """Session that ignores system proxy (common Windows Clash pitfall)."""
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def normalize_ashare_symbol(code: str) -> str:
    """Normalize A-share / ETF codes to 6 digits."""
    compact = (
        code.strip()
        .upper()
        .replace("SZ", "")
        .replace("SH", "")
        .replace(".", "")
        .replace("-", "")
    )
    digits = "".join(ch for ch in compact if ch.isdigit())
    if len(digits) < 6:
        raise ValueError(f"Invalid A-share symbol: {code}")
    return digits[-6:]


def to_tushare_code(code: str) -> str:
    """Map 6-digit code to Tushare ts_code (ETF: 5xxxxx -> SH)."""
    symbol = normalize_ashare_symbol(code)
    if symbol.startswith(("5", "6", "9")):
        suffix = "SH"
    else:
        suffix = "SZ"
    return f"{symbol}.{suffix}"


def normalize_crypto_pair(symbol: str) -> str:
    """Normalize crypto pairs to BASE_QUOTE (e.g. BTC_USDT)."""
    compact = symbol.strip().upper().replace("-", "_")
    if "_" not in compact:
        if compact.endswith("USDT"):
            compact = compact[:-4] + "_USDT"
        elif compact.endswith("USD"):
            compact = compact[:-3] + "_USD"
    if "_" not in compact:
        raise ValueError(f"Invalid crypto pair: {symbol}")
    return compact
