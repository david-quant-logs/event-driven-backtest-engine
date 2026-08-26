"""Fetch A-share ETF daily bars (AkShare / Eastmoney / Sina / optional Tushare)."""

from __future__ import annotations

import os
from datetime import date, datetime

import pandas as pd

from backtest.utils import http_session, normalize_ashare_symbol, retry, to_tushare_code

EASTMONEY_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EASTMONEY_UT = (
    "fa5fd1943c7b386f172d6893dbfba10b",
    "7eea3edcaed734bea9cbfc24409ed989",
)

STANDARD_COLUMNS = [
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


def fetch_etf_daily(
    symbol: str,
    *,
    start: str,
    end: str | None = None,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    Download ETF daily OHLCV + adj_factor for ``symbol``.

    Source order: Tencent → AkShare → Eastmoney → Sina → optional Tushare.
    ``adj_factor`` is 1.0 when the vendor already returns adjusted bars.
    """
    code = normalize_ashare_symbol(symbol)
    end_date = end or date.today().isoformat()
    start_c = _compact(start)
    end_c = _compact(end_date)

    errors: list[str] = []
    for name, fn in (
        ("tencent", lambda: _from_tencent(code, start, end_date, adjust)),
        ("akshare", lambda: _from_akshare(code, start_c, end_c, adjust)),
        ("eastmoney", lambda: _from_eastmoney(code, start_c, end_c, adjust)),
        ("sina", lambda: _from_sina(code, start_c, end_c, adjust)),
    ):
        try:
            raw = fn()
            return _standardize(raw, code, name, adjust)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")

    if os.getenv("TUSHARE_TOKEN"):
        try:
            raw = _from_tushare(code, start_c, end_c)
            return _standardize(raw, code, "tushare", adjust)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tushare: {exc}")

    raise RuntimeError(f"ETF fetch failed for {code}. " + " | ".join(errors))


def _compact(value: str) -> str:
    return datetime.fromisoformat(value.replace("/", "-")[:10]).strftime("%Y%m%d")


def _from_tencent(code: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    """
    Tencent fq k-line API (works when Eastmoney is blocked / mis-proxied).

    Long ranges silently return only the latest ~640 bars, so we request
    fixed ~500-day windows from ``start`` forward.
    """
    from datetime import timedelta

    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    ts_symbol = f"{prefix}{code}"
    adj_key = {"qfq": "qfqday", "hfq": "hfqday", "": "day"}.get(adjust, "qfqday")
    adj_param = {"qfq": "qfq", "hfq": "hfq", "": ""}.get(adjust, "qfq")
    session = http_session()
    cursor = datetime.fromisoformat(start.replace("/", "-")[:10]).date()
    end_d = datetime.fromisoformat(end.replace("/", "-")[:10]).date()
    rows: list[list] = []
    window = timedelta(days=500)

    while cursor <= end_d:
        win_end = min(cursor + window, end_d)
        param = f"{ts_symbol},day,{cursor.isoformat()},{win_end.isoformat()},640,{adj_param}"
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

        def _call(p: str = param) -> dict:
            resp = session.get(url, params={"param": p}, timeout=30)
            resp.raise_for_status()
            return resp.json()

        payload = retry(_call)
        block = ((payload.get("data") or {}).get(ts_symbol) or {})
        series = block.get(adj_key) or block.get("day") or []
        if not series:
            cursor = win_end + timedelta(days=1)
            continue
        rows.extend(series)
        cursor = win_end + timedelta(days=1)

    if not rows:
        raise RuntimeError(f"Tencent returned no bars for {ts_symbol}")

    frame = pd.DataFrame(rows)
    # [date, open, close, high, low, volume, ...]
    frame = frame.iloc[:, :6]
    frame.columns = ["datetime", "open", "close", "high", "low", "volume"]
    frame["amount"] = pd.NA
    frame["adj_factor"] = 1.0
    frame["datetime"] = pd.to_datetime(frame["datetime"])
    start_ts = pd.Timestamp(start[:10])
    end_ts = pd.Timestamp(end[:10])
    frame = frame[(frame["datetime"] >= start_ts) & (frame["datetime"] <= end_ts)]
    return frame.drop_duplicates(subset=["datetime"]).sort_values("datetime")


def _from_akshare(code: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    import akshare as ak

    def _call() -> pd.DataFrame:
        # fund_etf_hist_em is the ETF-specific endpoint; stock hist also works for 51xxxx.
        try:
            df = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust=adjust,
            )
        except Exception:  # noqa: BLE001
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust=adjust,
                timeout=30,
            )
        if df is None or df.empty:
            raise RuntimeError(f"AkShare returned no rows for {code}")
        return df

    return retry(_call)


def _from_eastmoney(code: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    market = 1 if code.startswith(("5", "6", "9")) else 0
    fqt = {"qfq": "1", "hfq": "2", "": "0"}.get(adjust, "1")
    session = http_session()
    last_error: Exception | None = None
    for ut in EASTMONEY_UT:
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
            "ut": ut,
            "klt": "101",
            "fqt": fqt,
            "secid": f"{market}.{code}",
            "beg": start,
            "end": end,
        }
        try:

            def _get() -> dict:
                resp = session.get(EASTMONEY_URL, params=params, timeout=30)
                resp.raise_for_status()
                return resp.json()

            payload = retry(_get)
            klines = (payload.get("data") or {}).get("klines") or []
            if not klines:
                raise RuntimeError(f"Eastmoney returned no klines for {code}")
            frame = pd.DataFrame([row.split(",") for row in klines])
            frame = frame.iloc[:, :7]
            frame.columns = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]
            return frame
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    assert last_error is not None
    raise last_error


def _from_sina(code: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    import akshare as ak

    sina_symbol = ("sh" if code.startswith(("5", "6", "9")) else "sz") + code

    def _call() -> pd.DataFrame:
        df = ak.stock_zh_a_daily(
            symbol=sina_symbol,
            start_date=start,
            end_date=end,
            adjust=adjust,
        )
        if df is None or df.empty:
            raise RuntimeError(f"Sina returned no rows for {code}")
        return df.rename(columns={"date": "datetime"})

    return retry(_call)


def _from_tushare(code: str, start: str, end: str) -> pd.DataFrame:
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN missing")
    import tushare as ts

    ts_code = to_tushare_code(code)

    def _call() -> pd.DataFrame:
        pro = ts.pro_api(token)
        daily = pro.fund_daily(ts_code=ts_code, start_date=start, end_date=end)
        if daily is None or daily.empty:
            daily = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
        if daily is None or daily.empty:
            raise RuntimeError(f"Tushare returned no rows for {ts_code}")
        adj = pro.fund_adj(ts_code=ts_code, start_date=start, end_date=end)
        if adj is None or adj.empty:
            adj = pro.adj_factor(ts_code=ts_code, start_date=start, end_date=end)
        daily = daily.rename(columns={"trade_date": "datetime", "vol": "volume"})
        daily["datetime"] = pd.to_datetime(daily["datetime"], format="%Y%m%d")
        if adj is not None and not adj.empty:
            adj = adj.rename(columns={"trade_date": "datetime"})
            adj["datetime"] = pd.to_datetime(adj["datetime"], format="%Y%m%d")
            factor_col = "adj_factor" if "adj_factor" in adj.columns else None
            if factor_col:
                daily = daily.merge(adj[["datetime", factor_col]], on="datetime", how="left")
        return daily.sort_values("datetime")

    return retry(_call)


def _standardize(df: pd.DataFrame, symbol: str, source: str, adjust: str) -> pd.DataFrame:
    out = df.copy()
    rename: dict = {}
    for col in out.columns:
        key = str(col).strip().lower()
        mapping = {
            "日期": "datetime",
            "时间": "datetime",
            "date": "datetime",
            "datetime": "datetime",
            "trade_date": "datetime",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "vol": "volume",
            "amount": "amount",
            "adj_factor": "adj_factor",
        }
        if key in mapping:
            rename[col] = mapping[key]
    out = out.rename(columns=rename)
    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume", "amount", "adj_factor"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        elif col == "adj_factor":
            out[col] = 1.0
        elif col == "amount":
            out[col] = pd.NA
        elif col == "volume":
            out[col] = 0.0

    out["symbol"] = symbol
    out["timeframe"] = "1d"
    out["source"] = source
    out = out.dropna(subset=["datetime", "close"])
    out = out.drop_duplicates(subset=["datetime"], keep="last")
    out = out.sort_values("datetime").reset_index(drop=True)

    # Suspension: zero (or near-zero) volume bars — keep price, mark flag.
    vol = out["volume"].fillna(0.0)
    out["suspended"] = vol <= 0
    out.attrs["requested_adjust"] = adjust

    for col in STANDARD_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    return out[STANDARD_COLUMNS]
