import pandas as pd
import plotly.graph_objects as go


def make_candle_chart(
    data: pd.DataFrame,
    levels: dict,
    ticker: str,
    chart_window: int = 120,
) -> go.Figure:
    """
    Candlestick chart with four horizontal level lines:
      VWAP₆₀  — blue dashed
      止盈     — green solid
      止損     — red solid
      動態 E[max] — purple dotted
    """
    chart_data = data.tail(chart_window).copy()

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=chart_data.index,
            open=chart_data["Open"],
            high=chart_data["High"],
            low=chart_data["Low"],
            close=chart_data["Close"],
            name="Price",
            increasing_line_color="#16a34a",
            decreasing_line_color="#dc2626",
        )
    )

    lines = [
        ("vwap",         "VWAP₆₀",      "#2563eb", "dash"),
        ("take_profit",  "止盈",         "#16a34a", "solid"),
        ("stop_loss",    "止損",         "#dc2626", "solid"),
        ("dynamic_emax", "動態 E[max]",  "#9333ea", "dot"),
    ]

    for key, label, color, dash in lines:
        value = float(levels[key])
        fig.add_hline(
            y=value,
            line_color=color,
            line_dash=dash,
            line_width=1.5,
            annotation_text=f"{label}: {value:.2f}",
            annotation_position="top left",
            annotation_font_color=color,
        )

    fig.update_layout(
        title=(
            f"{ticker}  |  {levels['date'].date()}  |"
            f"  State={levels['state']} {levels['state_label']}"
        ),
        xaxis_title="日期",
        yaxis_title="價格",
        template="plotly_white",
        height=600,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig
