"""Plotly 图表构建。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def _layout(fig: go.Figure, title: str, height: int = 360) -> go.Figure:
    fig.update_layout(
        title=title,
        height=height,
        margin=dict(l=20, r=20, t=48, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        template="plotly_white",
    )
    return fig


def index_chart(norm_df: pd.DataFrame, title: str = "主要指数区间走势（期初=100）") -> go.Figure:
    fig = go.Figure()
    for name, sub in norm_df.groupby("指数"):
        fig.add_trace(go.Scatter(x=sub["日期"], y=sub["净值"], name=name, mode="lines"))
    return _layout(fig, title, height=420)


def pe_chart(pe_df: pd.DataFrame, name: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=pe_df["日期"],
            y=pe_df["滚动市盈率"],
            mode="lines",
            name="滚动市盈率",
            line=dict(color="#2563eb"),
        )
    )
    latest = pe_df.iloc[-1]
    fig.add_annotation(
        x=latest["日期"], y=latest["滚动市盈率"],
        text=f"{float(latest['滚动市盈率']):.1f}",
        showarrow=False, yshift=10,
    )
    return _layout(fig, f"{name} 滚动市盈率（乐咕乐股）")


def industry_bar(rank_df: pd.DataFrame, top_n: int = 20, title: str = "行业区间涨跌幅（%）") -> go.Figure:
    df = rank_df.head(top_n).iloc[::-1]
    colors = ["#dc2626" if v >= 0 else "#16a34a" for v in df["区间涨跌幅%"]]
    fig = go.Figure(
        go.Bar(
            x=df["区间涨跌幅%"],
            y=df["行业"],
            orientation="h",
            marker_color=colors,
            text=[f"{v:.1f}" for v in df["区间涨跌幅%"]],
            textposition="outside",
        )
    )
    return _layout(fig, title, height=max(420, len(df) * 18))


def margin_chart(margin_hist: pd.DataFrame, title: str = "两融余额与融资买入（亿元）") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=margin_hist["日期"],
            y=margin_hist["融资融券余额"] / 1e8,
            name="两融余额",
            fill="tozeroy",
            line=dict(color="#2563eb"),
        )
    )
    if "融资买入额" in margin_hist.columns:
        buy20 = margin_hist["融资买入额"].rolling(20).mean() / 1e8
        fig.add_trace(go.Scatter(x=margin_hist["日期"], y=buy20, name="融资买入(20日均)", line=dict(color="#f59e0b")))
    return _layout(fig, title, height=380)


def northbound_chart(nb_hist: pd.DataFrame, _start=None, cutoff: str = "2024-08-16") -> go.Figure:
    s = nb_hist.copy()
    s["日期"] = pd.to_datetime(s["日期"], errors="coerce")
    s = s[s["日期"] >= pd.Timestamp("2015-01-01")]
    s["net"] = pd.to_numeric(s["当日成交净买额"], errors="coerce")
    colors = np.where(s["net"].fillna(0) >= 0, "#dc2626", "#16a34a")
    fig = go.Figure(
        go.Bar(x=s["日期"], y=s["net"], marker_color=colors, name="当日净买入(亿)")
    )
    fig.add_vline(x=cutoff, line_dash="dash", line_color="#64748b")
    fig.add_annotation(x=cutoff, y=fig.data[0].y.max() if len(fig.data) and fig.data[0].y is not None else 100,
                       text="2024-08 停止披露", showarrow=False, xshift=8, font=dict(size=11))
    return _layout(fig, "北向资金当日净买入（亿元，2024年8月后官方停止披露）", height=340)


def erp_chart(erp_hist: pd.DataFrame, title: str = "股债性价比：1/沪深300PE - 10Y国债（%）") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=erp_hist["日期"], y=erp_hist["ERP"], mode="lines", name="ERP", line=dict(color="#7c3aed")))
    fig.add_hline(y=0, line_dash="dot", line_color="#94a3b8")
    return _layout(fig, title, height=320)


def etf_bar(etf_df: pd.DataFrame, title: str = "主要ETF份额变化（亿份）") -> go.Figure:
    colors = ["#dc2626" if v >= 0 else "#16a34a" for v in etf_df["份额变化(亿份)"]]
    fig = go.Figure(
        go.Bar(
            x=etf_df["名称"],
            y=etf_df["份额变化(亿份)"],
            marker_color=colors,
            text=[f"{v:+.1f}" for v in etf_df["份额变化(亿份)"]],
            textposition="outside",
        )
    )
    return _layout(fig, title, height=360)


def fund_chart(agg: pd.DataFrame, title: str = "新发基金募集份额（亿元）") -> go.Figure:
    fig = go.Figure()
    for typ, sub in agg.groupby("类型"):
        fig.add_trace(go.Bar(x=sub["月份"], y=sub["募集份额(亿)"], name=typ))
    fig.update_layout(barmode="stack")
    return _layout(fig, title, height=360)


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str, positive_color: bool = False) -> go.Figure:
    colors = None
    if positive_color:
        colors = ["#dc2626" if v >= 0 else "#16a34a" for v in df[y]]
    fig = go.Figure(go.Bar(x=df[x], y=df[y], marker_color=colors))
    return _layout(fig, title, height=340)


def line_chart(df: pd.DataFrame, x: str, y: str, title: str, color: str = "#2563eb") -> go.Figure:
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="lines", line=dict(color=color)))
    return _layout(fig, title, height=320)


def macro_multi_line(df: pd.DataFrame, x: str, columns: list[str], title: str) -> go.Figure:
    fig = go.Figure()
    for col in columns:
        fig.add_trace(go.Scatter(x=df[x], y=df[col], name=col, mode="lines"))
    return _layout(fig, title, height=340)
