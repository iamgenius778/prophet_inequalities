# 逃命線 — 動態止盈止損計算工具

基於 VWAP + 統計學的全品種量化止盈止損工具，部署在 Streamlit Community Cloud。

## 算法

$$\text{止損} = \text{VWAP}_{60} - 1.645 \times \frac{\sigma_{60}}{\sqrt{60}}$$

$$\text{止盈} = \text{VWAP}_{60} + \frac{E[\max] - \text{VWAP}_{60}}{2}$$

動態 E[max] 根據市場狀態（高波防守 / 趨勢 / 震盪）自動選用 10/15/20 天窗口。

## 本地運行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 支持品種

| 類型 | 代碼範例 |
|------|---------|
| 美股 / A股 | `AAPL`、`600519.SS` |
| 港股 | `0700.HK` |
| 期貨 | `GC=F`（黃金）、`SI=F`（白銀）、`CL=F`（原油） |
| 指數 | `^VIX`、`^HSI`、`^N225` |
| 加密 | `BTC-USD`、`ETH-USD` |

## 部署（Streamlit Community Cloud）

1. Push 到 GitHub
2. 進 [share.streamlit.io](https://share.streamlit.io)，選擇 repo / branch=main / Main file=`app.py`
3. Python 版本選 **3.11**

## Support

If this tool helps you: [ko-fi.com/yourname](https://ko-fi.com/yourname)
