"""Fetch crypto daily bars via Gate.io (Binance fallback), reused from data-pipeline patterns."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from backtest.utils import http_session, normalize_crypto_pair, retry

INTERVAL_SECONDS = {"1d": 86400, "1h": 3600, "4h": 14400}


def fetch_crypto_daily(
    symbol: str,
    *,
    start: str,
    end: str | None = None,
    interval: str = "1d",
    gate_base_url: str = "https://api.gateio.ws/api/v4",
    binance_base_url: str = "https://api.binance.com",
) -> pd.DataFrame:
    """Download crypto OHLCV from Gate, falling back to Binance."""
    pair = normalize_crypto_pair(symbol)
    if interval not in INTERVAL_SECONDS:
        raise ValueError(f"Unsupported interval: {interval}")

    start_ts = int(datetime.fromisoformat(start.replace("/", "-")[:10]).replace(tzinfo=timezone.utc).timestamp())
    if end:
        end_dt = datetime.fromisoformat(end.replace("/", "-")[:10]).replace(tzinfo=timezone.utc)
    else:
        end_dt = datetime.now(timezone.utc)
    end_ts = int(end_dt.timestamp())

    errors: list[str] = []
    for name, fn in (
        ("gate", lambda: _from_gate(pair, interval, start_ts, end_ts, gate_base_url)),
        ("binance", lambda: _from_binance(pair, interval, start_ts, end_ts, binance_base_url)),
    ):
        try:
            raw = fn()
            return _standardize(raw, pair, interval, name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    raise RuntimeError(f"Crypto fetch failed for {pair}. " + " | ".join(errors))


def _from_gate(pair: str, interval: str, start_ts: int, end_ts: int, base_url: str) -> pd.DataFrame:
    step = INTERVAL_SECONDS[interval] * 900
    cursor = start_ts
    rows: list[list] = []
    session = http_session()
    while cursor < end_ts:
        to_ts = min(cursor + step, end_ts)

        def _call(from_ts: int = cursor, until: int = to_ts) -> list:
            resp = session.get(
                f"{base_url.rstrip('/')}/spot/candlesticks",
                params={
                    "currency_pair": pair,
                    "interval": interval,
                    "from": from_ts,
                    "to": until,
                    "limit": 1000,
                },
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict) and payload.get("label"):
                raise RuntimeError(payload)
            return payload

        chunk = retry(_call)
        rows.extend(chunk or [])
        cursor = to_ts
        time.sleep(0.1)

    if not rows:
        raise RuntimeError(f"Gate returned no candles for {pair}")
    n = len(rows[0])
    columns = ["datetime", "volume", "close", "high", "low", "open", "amount"]
    if n > len(columns):
        columns = columns + [f"extra_{i}" for i in range(n - len(columns))]
    frame = pd.DataFrame(rows, columns=columns[:n])
    frame["datetime"] = pd.to_datetime(pd.to_numeric(frame["datetime"]), unit="s", utc=True).dt.tz_localize(None)
    return frame


def _from_binance(pair: str, interval: str, start_ts: int, end_ts: int, base_url: str) -> pd.DataFrame:
    symbol = pair.replace("_", "")
    start_ms = start_ts * 1000
    end_ms = end_ts * 1000
    cursor = start_ms
    rows: list[list] = []
    session = http_session()
    while cursor < end_ms:

        def _call(open_ms: int = cursor) -> list:
            resp = session.get(
                f"{base_url.rstrip('/')}/api/v3/klines",
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": open_ms,
                    "endTime": end_ms,
                    "limit": 1000,
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

        chunk = retry(_call)
        if not chunk:
            break
        rows.extend(chunk)
        last_open = int(chunk[-1][0])
        nxt = last_open + INTERVAL_SECONDS[interval] * 1000
        if nxt <= cursor:
            break
        cursor = nxt
        time.sleep(0.1)

    if not rows:
        raise RuntimeError(f"Binance returned no candles for {symbol}")
    frame = pd.DataFrame(
        rows,
        columns=[
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "amount",
            "trades",
            "taker_base",
            "taker_quote",
            "ignore",
        ][: len(rows[0])],
    )
    frame["datetime"] = pd.to_datetime(pd.to_numeric(frame["datetime"]), unit="ms", utc=True).dt.tz_localize(None)
    return frame


def _standardize(df: pd.DataFrame, symbol: str, interval: str, source: str) -> pd.DataFrame:
    out = df.copy()
    for col in ("open", "high", "low", "close", "volume", "amount"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    out["adj_factor"] = 1.0
    out["symbol"] = symbol
    out["timeframe"] = interval
    out["source"] = source
    out = out.dropna(subset=["datetime", "close"])
    out = out.drop_duplicates(subset=["datetime"], keep="last")
    out = out.sort_values("datetime").reset_index(drop=True)
    vol = out["volume"].fillna(0.0) if "volume" in out.columns else pd.Series(0.0, index=out.index)
    out["suspended"] = vol <= 0
    cols = [
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "adj_factor",
        "symbol",
        "timeframe",
        "source",
        "suspended",
    ]
    for c in cols:
        if c not in out.columns:
            out[c] = pd.NA
    return out[cols]
