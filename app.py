import numpy as np
import streamlit as st

from src.charts import make_candle_chart
from src.compute import (
    PROFILE_CONFIGS,
    PROFILE_LABELS,
    LevelConfig,
    calculate_levels,
    levels_to_table,
)
from src.data_client import fetch

st.set_page_config(page_title="逃命線", page_icon="🛡️", layout="wide")

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🛡️ 逃命線")
    st.caption("動態止盈止損計算工具")
    st.divider()

    ticker_input = st.text_input(
        "代碼",
        placeholder="例：GC=F / AAPL / 0700.HK / BTC-USD",
    )

    profile = st.selectbox(
        "品種類型",
        options=list(PROFILE_LABELS.keys()),
        format_func=lambda k: PROFILE_LABELS[k],
    )

    n_days = st.slider("回溯窗口 N（天）", min_value=30, max_value=120, value=60, step=5)

    base = PROFILE_CONFIGS[profile]
    with st.expander("高級設置"):
        z_val = st.slider(
            "Z 值 (k)",
            min_value=1.0, max_value=3.0,
            value=float(base.z_value), step=0.005, format="%.3f",
            key=f"z_{profile}",
        )
        vol_thr = st.slider(
            "波動擴展閾值",
            min_value=1.0, max_value=2.0,
            value=float(base.vol_expansion_threshold), step=0.05,
            key=f"vt_{profile}",
        )
        pe_thr = st.slider(
            "趨勢觸發閾值 (PE)",
            min_value=0.1, max_value=0.9,
            value=float(base.trend_trigger_threshold), step=0.05,
            key=f"pe_{profile}",
        )

    query = st.button("查詢", type="primary", use_container_width=True)
    st.divider()
    st.markdown("[☕ 支持這個工具](https://ko-fi.com/pangju)")


# ── Data fetching (cached 5 min) ─────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def _fetch(ticker: str) -> object:
    return fetch(ticker)


# ── Query handler ────────────────────────────────────────────────────────────
if query:
    if not ticker_input.strip():
        st.error("請輸入代碼。")
    else:
        symbol = ticker_input.strip().upper()
        with st.spinner(f"正在查詢 {symbol}…"):
            try:
                data = _fetch(symbol)
                config = LevelConfig(
                    lookback=n_days,
                    micro_window=20,
                    z_value=z_val,
                    vol_expansion_threshold=vol_thr,
                    trend_trigger_threshold=pe_thr,
                )
                levels = calculate_levels(data, config)
                st.session_state.update(
                    data=data,
                    levels=levels,
                    ticker=symbol,
                    error=None,
                )
            except Exception as exc:
                st.session_state["error"] = str(exc)
                st.session_state.pop("levels", None)


# ── Display ──────────────────────────────────────────────────────────────────
if st.session_state.get("error"):
    st.error(f"查詢失敗：{st.session_state['error']}")

elif "levels" in st.session_state:
    data = st.session_state["data"]
    levels = st.session_state["levels"]
    ticker_disp = st.session_state["ticker"]
    price = levels["latest_close"]

    # ── Warnings ──────────────────────────────────────────────────────────
    if levels["no_volume"]:
        st.info("ℹ️ 此品種無成交量數據，已自動使用算術均值代替 VWAP。")

    if levels["data_rows"] < levels["lookback"]:
        st.warning(
            f"⚠️ 數據僅 {levels['data_rows']} 天（不足 {levels['lookback']} 天），"
            f"已用實際天數計算。結果僅供參考。"
        )

    if not np.isnan(levels["pe20"]) and levels["pe20"] > 1:
        st.warning("⚠️ PE₂₀ > 1，振幅計算可能異常（分母接近0）。結果仍輸出，請謹慎參考。")

    if price > levels["take_profit"]:
        excess = (price / levels["take_profit"] - 1) * 100
        st.warning(
            f"⚠️ 現價已超出止盈線 +{excess:.1f}%，動能可能過度釋放，"
            f"可考慮縮短窗口 N 至 30 天重新評估。"
        )

    # ── Metric cards ──────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("現價", f"{price:.2f}")
    c2.metric("止盈", f"{levels['take_profit']:.2f}", f"{levels['pct_to_tp']:+.2f}%")
    c3.metric("止損", f"{levels['stop_loss']:.2f}", f"{levels['pct_above_sl']:+.2f}%")
    c4.metric("VWAP₆₀", f"{levels['vwap']:.2f}")

    # ── K-line chart ──────────────────────────────────────────────────────
    fig = make_candle_chart(data, levels, ticker=ticker_disp)
    st.plotly_chart(fig, width="stretch")

    # ── Detail table (collapsible) ────────────────────────────────────────
    with st.expander("計算明細"):
        st.table(levels_to_table(levels))

else:
    # ── Welcome screen ────────────────────────────────────────────────────
    st.markdown(
        """
## 逃命線 — 動態止盈止損計算工具

基於 **VWAP₆₀** 的統計學止損線（95% 置信下界）與動態極值中點止盈線。

$$\\text{止損} = \\text{VWAP}_{60} - 1.645 \\times \\frac{\\sigma_{60}}{\\sqrt{60}}$$

$$\\text{止盈} = \\text{VWAP}_{60} + \\frac{E[\\max] - \\text{VWAP}_{60}}{2}$$

---

**支持品種範例**

| 類型 | 代碼 |
|------|------|
| 美股 | `AAPL`、`TSLA`、`SPY` |
| 港股 | `0700.HK`、`9988.HK` |
| A股  | `600519.SS`、`000858.SZ` |
| 期貨 | `GC=F`（黃金）、`SI=F`（白銀）、`CL=F`（原油） |
| 指數 | `^VIX`、`^HSI`、`^N225` |
| 加密 | `BTC-USD`、`ETH-USD` |

在左側填入代碼，選擇品種類型，點擊 **查詢** 即可。
        """
    )
