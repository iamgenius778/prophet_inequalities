import re
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

try:
    import akshare as ak
    _AKSHARE_OK = True
except ImportError:
    _AKSHARE_OK = False


# ── Column aliases (Simplified + Traditional Chinese + English) ──────────────
_COL_MAP = {
    "Open":   ["open",   "开盘", "開盤"],
    "High":   ["high",   "最高"],
    "Low":    ["low",    "最低"],
    "Close":  ["close",  "收盘", "收盤"],
    "Volume": ["volume", "成交量"],
}


def _route(ticker: str) -> str:
    """Return 'akshare_a', 'akshare_hk', or 'yfinance'."""
    t = ticker.strip().upper()
    if re.fullmatch(r"\d{6}", t) or t.endswith(".SS") or t.endswith(".SZ"):
        return "akshare_a"
    if re.fullmatch(r"\d+\.HK", t):
        return "akshare_hk"
    return "yfinance"


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to standard OHLCV names and enforce types."""
    rename = {}
    for std, aliases in _COL_MAP.items():
        for col in df.columns:
            if str(col).lower() in aliases or str(col) in aliases:
                rename[col] = std
                break
    df = df.rename(columns=rename)

    # Open is optional for compute; fall back to Close for candlestick display
    if "Open" not in df.columns:
        df["Open"] = df["Close"]
    if "Volume" not in df.columns:
        df["Volume"] = np.nan

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df.dropna(subset=["High", "Low", "Close"])
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ── AKShare ──────────────────────────────────────────────────────────────────

def _fetch_akshare_a(ticker: str) -> pd.DataFrame:
    if not _AKSHARE_OK:
        raise ImportError("AKShare 未安裝，請執行：pip install akshare")

    symbol = re.sub(r"\.(SS|SZ)$", "", ticker.upper())
    end = datetime.today()
    start = end - timedelta(days=500)

    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="hfq",
    )
    if df is None or df.empty:
        raise ValueError(
            f"找不到「{ticker}」，請確認代碼格式（A股加 .SS 或 .SZ）。"
        )

    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.set_index("日期")
    return _normalize(df)


def _fetch_akshare_hk(ticker: str) -> pd.DataFrame:
    if not _AKSHARE_OK:
        raise ImportError("AKShare 未安裝，請執行：pip install akshare")

    symbol = re.sub(r"\.HK$", "", ticker.upper()).zfill(5)
    end = datetime.today()
    start = end - timedelta(days=500)

    df = ak.stock_hk_hist(
        symbol=symbol,
        period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="hfq",
    )
    if df is None or df.empty:
        raise ValueError(
            f"找不到「{ticker}」，請確認代碼格式（港股加 .HK）。"
        )

    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.set_index("日期")
    return _normalize(df)


# ── yfinance (with exponential backoff retry) ────────────────────────────────

def _fetch_yfinance(ticker: str) -> pd.DataFrame:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            data = yf.download(
                ticker,
                period="1y",
                interval="1d",
                auto_adjust=True,
                progress=False,
                group_by="column",
            )
            if data.empty:
                raise ValueError(
                    f"找不到此代碼的數據：{ticker}。請確認格式正確，或此品種是否已退市。"
                )

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            data = data.rename(columns=str.title)

            # Futures rollover: ffill isolated Volume=0 rows
            if "Volume" in data.columns:
                vol = data["Volume"]
                if (vol == 0).any() and not (vol == 0).all():
                    data.loc[data["Volume"] == 0, "Volume"] = np.nan
                    data["Volume"] = data["Volume"].ffill()

            return _normalize(data)

        except Exception as exc:
            last_exc = exc
            # Don't retry on clear ticker-not-found errors
            if "找不到" in str(exc):
                raise
            if attempt < 2:
                time.sleep(2 ** attempt)  # 1s, 2s

    raise last_exc  # type: ignore[misc]


# ── Public entry point ───────────────────────────────────────────────────────

def fetch(ticker: str) -> pd.DataFrame:
    """
    Auto-route to AKShare (A/HK stocks) or yfinance (everything else).
    Returns a unified OHLCV DataFrame with DatetimeIndex.
    """
    route = _route(ticker)
    if route == "akshare_a":
        return _fetch_akshare_a(ticker)
    if route == "akshare_hk":
        return _fetch_akshare_hk(ticker)
    return _fetch_yfinance(ticker)
