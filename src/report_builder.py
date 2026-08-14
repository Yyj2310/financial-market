"""生成 Markdown 报告快照。"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from . import indicators as ind


def _table(rows: list[dict]) -> str:
    if not rows:
        return "（无数据）"
    cols = list(rows[0].keys())
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    body = []
    for r in rows:
        body.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join([head, sep] + body)


def build_markdown(hub, cfg, start, end) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    out = [f"# 证券市场分析报告（{start} 至 {end}）", "", f"> 数据生成时间：{today} ｜ 数据来源：免费公开接口（新浪/腾讯/同花顺/乐咕/东财/国家统计局等）", ""]

    perf = ind.index_performance(hub, cfg, start, end)
    out += ["## 一、市场全景", ""]
    if not perf.empty:
        out.append(_table(perf.to_dict("records")))
        out.append("")

    out += ["## 二、估值与风格", ""]
    pe = ind.pe_analysis(hub, cfg, start)
    if not pe.empty:
        out.append(_table(pe.to_dict("records")))
        out.append("")
    erp = ind.equity_risk_premium(hub)
    if erp.get("ok"):
        out.append(f"- 股债性价比（1/沪深300PE − 10Y国债）：{erp['ERP']:.2f}%，历史分位 {erp['ERP分位%']:.0f}%")
        out.append("")

    out += ["## 三、宏观经济", ""]
    macro_lines = []
    macro_sources = [
        ("GDP", hub.gdp(), ["GDP同比", "季度"]),
        ("CPI", hub.cpi(), ["CPI同比"]),
        ("PPI", hub.ppi(), ["PPI同比"]),
        ("PMI", hub.pmi(), ["制造业PMI"]),
        ("M2/M1", hub.money_supply(), ["M2同比", "M1同比"]),
        ("LPR", hub.lpr(), ["LPR1Y", "LPR5Y"]),
    ]
    for label, df, cols in macro_sources:
        try:
            if df is None or df.empty:
                continue
            d = df.copy()
            d["日期"] = pd.to_datetime(d["日期"], errors="coerce")
            d = d.dropna(subset=cols).sort_values("日期")
            if d.empty:
                continue
            latest = d.iloc[-1]
            parts = []
            for c in cols:
                v = latest[c]
                parts.append(f"{c} {v:g}" if isinstance(v, (int, float)) else f"{c} {v}")
            macro_lines.append(f"- {label}：{'，'.join(parts)}")
        except Exception:  # noqa: BLE001
            continue
    out += macro_lines
    out.append("")

    out += ["## 四、供需与资金", ""]
    mg = ind.margin_metrics(hub, start, end)
    if mg.get("ok"):
        out.append(f"- 两融余额 {mg['两融余额(亿)']} 亿元，区间变化 {mg['区间变化(亿)']:+.2f} 亿元")
    nb = ind.northbound_metrics(hub, start, end)
    if nb.get("ok"):
        out.append(f"- 北向资金区间净买入 {nb['区间净买入合计(亿)']} 亿元（披露口径截至2024年8月）")
    etf = ind.etf_flow(hub, cfg, ind._first_trading_date(hub, start), ind._last_trading_date(hub, end))
    if not etf.empty:
        clean = etf[etf["疑似折算"] == "否"]
        out.append(f"- 观察池 ETF 份额合计变化 {clean['份额变化(亿份)'].sum():+.1f} 亿份（剔除疑似份额折算）")
    funds = ind.fund_issuance(hub, start, end)
    if not funds.empty:
        out.append(f"- 区间新发基金合计募集 {funds['募集份额(亿)'].sum():.0f} 亿元")
    rp = ind.repurchase_stats(hub, start, end)
    if rp.get("ok"):
        out.append(f"- 区间已披露回购金额合计 {rp['区间已回购金额合计(亿)']} 亿元")
    ipo = ind.ipo_stats(hub, start, end)
    if ipo.get("ok"):
        src = "巨潮" if ipo.get("source") == "cninfo" else "次新"
        out.append(f"- 区间新上市公司 {ipo['新上市公司数']} 家（{src}口径），IPO募资 {ipo['募资合计(亿)'] or '—'} 亿元")
    inv = ind.investor_metrics(hub, start, end)
    if inv.get("ok"):
        stale = (
            "数据日期" in inv
            and inv["数据日期"]
            and (pd.Timestamp(inv["数据日期"]) < pd.Timestamp.now() - pd.DateOffset(months=6))
        )
        note = "（免费源停更，供参考）" if stale else ""
        out.append(f"- 最新单月新增开户 {inv['最新单月新增(万)']} 万户（同比 {inv['最新单月同比%']:+.0f}%）{note}")
    out.append("")

    out += ["## 五、机构行为", ""]
    out.append("- 两融（杠杆资金）、北向（外资，披露受限）、ETF（被动资金）、新发基金（公募供给）、回购（产业资本）详见交互网页。")
    out.append("")

    out += ["## 六、风险提示", ""]
    out.append("- 本报告由公开数据自动生成，仅供研究参考，不构成投资建议。免费数据源可能存在延迟或口径差异。")
    return "\n".join(out)


def save_report(hub, cfg, start, end) -> str:
    md = build_markdown(hub, cfg, start, end)
    path = cfg["report_dir"] / f"市场报告_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    path.write_text(md, encoding="utf-8")
    return str(path)
