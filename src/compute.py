from dataclasses import dataclass
from math import sqrt
from typing import Literal

import numpy as np
import pandas as pd


MarketProfile = Literal["stock", "hk", "futures", "crypto"]


@dataclass(frozen=True)
class LevelConfig:
    lookback: int = 60
    micro_window: int = 20
    z_value: float = 1.645
    vol_expansion_threshold: float = 1.10
    trend_trigger_threshold: float = 0.40


PROFILE_CONFIGS: dict[str, LevelConfig] = {
    "stock":   LevelConfig(60, 20, 1.645, 1.10, 0.40),
    "hk":      LevelConfig(60, 20, 1.645, 1.15, 0.45),
    "futures": LevelConfig(60, 20, 1.645, 1.20, 0.50),
    "crypto":  LevelConfig(60, 20, 1.645, 1.40, 0.60),
}

PROFILE_LABELS: dict[str, str] = {
    "stock":   "美股 / A股",
    "hk":      "港股",
    "futures": "期貨 / 指數",
    "crypto":  "加密貨幣",
}


# ── Low-level helpers ────────────────────────────────────────────────────────

def calc_vwap(closes: pd.Series, volumes: pd.Series) -> float:
    """VWAP₆₀. Falls back to arithmetic mean when volume is absent or all-zero."""
    valid = volumes.notna() & (volumes > 0)
    if valid.any():
        return float((closes[valid] * volumes[valid]).sum() / volumes[valid].sum())
    return float(closes.mean())


def calc_emax(highs: pd.Series, seg_len: int) -> float:
    """
    Split `highs` into segments of `seg_len` rows each and return the mean
    of each segment's maximum — the expected extreme high.
    """
    segment_maxes = [
        highs.iloc[start : start + seg_len].max()
        for start in range(0, len(highs), seg_len)
    ]
    return float(np.mean(segment_maxes))


def calc_pe20(closes: pd.Series, highs: pd.Series, lows: pd.Series) -> float:
    """
    Directional purity over the micro window:
        |P_now - P_start| / (High_max - Low_min)
    Returns nan when the range is zero (flat market).
    """
    range_20 = float(highs.max() - lows.min())
    if range_20 <= 0:
        return float("nan")
    return abs(float(closes.iloc[-1]) - float(closes.iloc[0])) / range_20


def judge_state(
    vol_ratio: float, pe20: float, config: LevelConfig
) -> tuple[int, str]:
    """Return (state_window, state_label) based on vol_ratio and PE₂₀."""
    if not np.isnan(vol_ratio) and vol_ratio > config.vol_expansion_threshold:
        return 10, "高波防守"
    if not np.isnan(pe20) and pe20 > config.trend_trigger_threshold:
        return 20, "趨勢"
    return 15, "震盪"


# ── Main calculator ──────────────────────────────────────────────────────────

def calculate_levels(data: pd.DataFrame, config: LevelConfig | None = None) -> dict:
    """
    Run the full 9-step algorithm from algorithm.md and return a result dict.
    `data` must have columns: Open, High, Low, Close, Volume.
    """
    config = config or PROFILE_CONFIGS["stock"]
    n = config.lookback
    m = config.micro_window
    required = max(n, m + 1)

    actual_rows = len(data)
    if actual_rows < required:
        raise ValueError(
            f"需要至少 {required} 條日線數據，當前只有 {actual_rows} 條。"
            f"請嘗試縮短回溯窗口 N 或更換品種。"
        )

    recent = data.tail(n)
    micro = data.tail(m)

    close_n = recent["Close"]
    high_n = recent["High"]
    vol_n = recent["Volume"]

    # Step 2: VWAP₆₀ (or arithmetic mean when no volume)
    vwap = calc_vwap(close_n, vol_n)

    # Step 3: σ₆₀ anchored to VWAP (total std, ddof=0, per algorithm.md §2.2)
    sigma_n = float(np.sqrt(np.mean((close_n - vwap) ** 2)))

    # Step 3: σ₂₀ anchored to its own mean (per algorithm.md §2.3)
    sigma_m = float(micro["Close"].std(ddof=0))

    vol_ratio = float(sigma_m / sigma_n) if sigma_n > 0 else float("nan")

    # Step 4: PE₂₀
    pe20 = calc_pe20(micro["Close"], micro["High"], micro["Low"])

    # Step 5: State
    state, state_label = judge_state(vol_ratio, pe20, config)

    # Step 6: Three-tier E[max]
    emax_10 = calc_emax(high_n, 10)
    emax_15 = calc_emax(high_n, 15)
    emax_20 = calc_emax(high_n, 20)

    # Step 7: Dynamic E[max]
    dynamic_emax = {10: emax_10, 15: emax_15, 20: emax_20}[state]

    # Step 8: Stop-loss
    se = sigma_n / sqrt(n)
    stop_loss = vwap - config.z_value * se

    # Step 9: Take-profit
    take_profit = vwap + (dynamic_emax - vwap) / 2

    price_now = float(data["Close"].iloc[-1])
    latest_date = pd.Timestamp(data.index[-1])

    no_volume = bool(vol_n.isna().all() or (vol_n.fillna(0) == 0).all())

    return {
        "date": latest_date,
        "latest_close": price_now,
        "vwap": vwap,
        "sigma_n": sigma_n,
        "sigma_m": sigma_m,
        "se": se,
        "pe20": pe20,
        "vol_ratio": vol_ratio,
        "state": state,
        "state_label": state_label,
        "emax_10": emax_10,
        "emax_15": emax_15,
        "emax_20": emax_20,
        "dynamic_emax": dynamic_emax,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "pct_to_tp": (take_profit / price_now - 1) * 100,
        "pct_above_sl": (price_now / stop_loss - 1) * 100,
        "no_volume": no_volume,
        "data_rows": actual_rows,
        "lookback": n,
    }


def levels_to_table(levels: dict) -> pd.DataFrame:
    pe_str = f"{levels['pe20']:.4f}" if not np.isnan(levels["pe20"]) else "N/A"
    vr_str = f"{levels['vol_ratio']:.4f}" if not np.isnan(levels["vol_ratio"]) else "N/A"

    rows = {
        "日期":              levels["date"].date(),
        "最新收盤價":         f"{levels['latest_close']:.4f}",
        "VWAP₆₀":           f"{levels['vwap']:.4f}",
        "σ₆₀":              f"{levels['sigma_n']:.4f}",
        "σ₂₀":              f"{levels['sigma_m']:.4f}",
        "SE₆₀":             f"{levels['se']:.4f}",
        "PE₂₀":             pe_str,
        "波動率比 σ₂₀/σ₆₀":  vr_str,
        "市場狀態":          f"State={levels['state']} ({levels['state_label']})",
        "E[max]₁₀":         f"{levels['emax_10']:.4f}",
        "E[max]₁₅":         f"{levels['emax_15']:.4f}",
        "E[max]₂₀":         f"{levels['emax_20']:.4f}",
        "動態 E[max]":       f"{levels['dynamic_emax']:.4f}",
        "止損線":            f"{levels['stop_loss']:.4f}",
        "止盈線":            f"{levels['take_profit']:.4f}",
        "距止盈":            f"{levels['pct_to_tp']:+.2f}%",
        "距止損":            f"{levels['pct_above_sl']:+.2f}%",
    }
    return pd.DataFrame.from_dict(rows, orient="index", columns=["數值"])
