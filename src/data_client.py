import numpy as np
import pandas as pd
import yfinance as yf


def fetch(ticker: str, period: str = "1y") -> pd.DataFrame:
    """
    Fetch daily OHLCV data via yfinance.

    - Handles multi-level columns (yfinance quirk for some versions).
    - Handles no-volume instruments (^VIX): leaves Volume as NaN so
      compute.py can fall back to arithmetic mean.
    - Handles futures rollover gaps: isolated Volume=0 rows are forward-filled
      so sigma is not distorted, but only if NOT all volume is zero.
    """
    data = yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
    )

    if data.empty:
        raise ValueError(f"找不到此代碼的數據：{ticker}。請確認格式正確，或此品種是否已退市。")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.rename(columns=str.title)

    for col in ("Open", "High", "Low", "Close"):
        if col not in data.columns:
            raise ValueError(f"返回數據缺少必要欄位：{col}（{ticker}）")

    if "Volume" not in data.columns:
        data["Volume"] = np.nan

    data = data[["Open", "High", "Low", "Close", "Volume"]].copy()
    data = data.dropna(subset=["High", "Low", "Close"])

    # Futures rollover: scattered zero-volume rows → ffill
    # But keep all-zero (e.g. ^VIX) untouched so compute can detect no-volume
    vol = data["Volume"]
    if (vol == 0).any() and not (vol == 0).all():
        data.loc[data["Volume"] == 0, "Volume"] = np.nan
        data["Volume"] = data["Volume"].ffill()

    return data
