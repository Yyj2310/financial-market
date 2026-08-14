"""自动摘要文本。"""

from __future__ import annotations

from . import indicators as ind


def _pct(x) -> str:
    return "—" if x is None else f"{x:+.2f}%"


def market_text(perf: "pd.DataFrame", style_g: dict, pe: "pd.DataFrame", erp: dict) -> list[str]:
    lines = []
    if perf is not None and not perf.empty:
        top = perf.iloc[0]
        bottom = perf.iloc[-1]
        lines.append(
            f"区间内表现最强的是**{top['指数']}**（{_pct(top['区间涨跌幅%'])}，最大回撤 {top['区间最大回撤%']:.1f}%），"
            f"表现最弱的是**{bottom['指数']}**（{_pct(bottom['区间涨跌幅%'])}）。"
        )
        sh = perf[perf["指数"] == "上证指数"]
        if not sh.empty:
            lines.append(f"上证指数区间涨跌 {_pct(sh.iloc[0]['区间涨跌幅%'])}，最新收于 {sh.iloc[0]['期末收盘']}。")
    if style_g.get("小盘-大盘") is not None:
        lines.append(f"风格上，小盘相对大盘{_pct(style_g['小盘-大盘'])}，成长相对价值{_pct(style_g['成长-价值'])}。")
    if pe is not None and not pe.empty:
        row = pe[pe["指数"] == "沪深300"]
        if not row.empty:
            lines.append(
                f"估值方面，沪深300 最新滚动市盈率 {row.iloc[0]['最新PE']}，处于历史约 {row.iloc[0]['历史分位%']:.0f}% 分位。"
            )
    if erp.get("ok"):
        lines.append(
            f"股债性价比（1/PE − 10Y国债）为 {erp['ERP']:.2f}%，处于历史 {erp['ERP分位%']:.0f}% 分位。"
        )
    return lines


def macro_text(hub) -> list[str]:
    lines = []
    try:
        gdp = hub.gdp()
        if gdp is not None and not gdp.empty:
            latest = gdp.iloc[-1]
            lines.append(f"最新 GDP 同比增速 {latest['GDP同比']}%（{latest['季度']}）。")
    except Exception:  # noqa: BLE001
        pass
    try:
        cpi = hub.cpi().dropna()
        if not cpi.empty:
            lines.append(f"最新 CPI 同比 {cpi.iloc[-1]['CPI同比']}%。")
    except Exception:  # noqa: BLE001
        pass
    try:
        ppi = hub.ppi().dropna()
        if not ppi.empty:
            lines.append(f"最新 PPI 同比 {ppi.iloc[-1]['PPI同比']}%。")
    except Exception:  # noqa: BLE001
        pass
    try:
        pmi = hub.pmi().dropna()
        if not pmi.empty:
            latest = pmi.iloc[-1]
            lines.append(f"最新制造业 PMI {latest['制造业PMI']}（荣枯线 50）。")
    except Exception:  # noqa: BLE001
        pass
    try:
        ms = hub.money_supply().dropna()
        if not ms.empty:
            latest = ms.iloc[-1]
            lines.append(f"最新 M2 同比 {latest['M2同比']}%，M1 同比 {latest['M1同比']}%。")
    except Exception:  # noqa: BLE001
        pass
    return lines

