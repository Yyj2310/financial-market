"""Streamlit 页面渲染。"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from . import charts, indicators as ind, narrative, report_builder


def _df(df: pd.DataFrame | None, height: int | None = None):
    if df is None or df.empty:
        st.info("暂无数据")
        return
    kwargs = {"width": "stretch", "hide_index": True}
    if height is not None:
        kwargs["height"] = height
    st.dataframe(df, **kwargs)


def _metric_row(items: list[tuple[str, str, str]]):
    cols = st.columns(len(items))
    for col, (label, value, help_) in zip(cols, items):
        col.metric(label, value, help=help_)


def show_warnings(hub) -> None:
    if hub.warnings:
        with st.expander(f"⚠️ 数据更新提示（{len(hub.warnings)} 条）"):
            for w in hub.warnings:
                st.caption(w)


# ---------------- 市场全景 ----------------


def page_market(hub, cfg, start, end):
    st.subheader("指数表现")
    perf = ind.index_performance(hub, cfg, start, end)
    if not perf.empty:
        def ret(name):
            row = perf[perf["指数"] == name]
            return row.iloc[0]["区间涨跌幅%"] if not row.empty else None

        items = []
        for name in ["上证指数", "沪深300", "创业板指", "中证1000", "科创50"]:
            v = ret(name)
            items.append((name, f"{v:+.2f}%" if v is not None else "—", "区间涨跌幅"))
        _metric_row(items)
    _df(perf)
    if not perf.empty:
        norm = ind.normalized_index_df(hub, cfg, start, end)
        if not norm.empty:
            st.plotly_chart(charts.index_chart(norm), width="stretch", key="mkt_index")

    st.subheader("风格与结构")
    style_g = ind.style_gap(perf, cfg)
    _metric_row(
        [
            ("小盘-大盘", f"{style_g['小盘-大盘']:+.2f}%" if style_g["小盘-大盘"] is not None else "—", "中证1000-沪深300"),
            ("成长-价值", f"{style_g['成长-价值']:+.2f}%" if style_g["成长-价值"] is not None else "—", "创业板指-上证50"),
            ("大盘", f"{style_g['大盘']:+.2f}%" if style_g["大盘"] is not None else "—", "沪深300"),
            ("小盘", f"{style_g['小盘']:+.2f}%" if style_g["小盘"] is not None else "—", "中证1000"),
        ]
    )
    st.caption("风格代理：大盘=沪深300，小盘=中证1000，成长=创业板指，价值=上证50。")

    st.subheader("行业轮动（同花顺行业指数）")
    bar = st.progress(0.0, text="正在更新行业数据…（首次较慢，之后有缓存）")

    def progress(p: float, name: str):
        bar.progress(p, text=f"行业数据 {p*100:.0f}%：{name}")

    rank = ind.industry_ranking(hub, start, end, progress=progress)
    bar.empty()
    if not rank.empty:
        top_n = st.slider("行业榜显示数量", 5, 30, 15, key="industry_n")
        st.plotly_chart(charts.industry_bar(rank, top_n=top_n), width="stretch", key="mkt_industry")
        with st.expander("全部行业涨跌幅表"):
            _df(rank)

    st.subheader("估值与股债性价比")
    pe = ind.pe_analysis(hub, cfg, start)
    _df(pe)
    if not pe.empty:
        col1, col2 = st.columns(2)
        with col1:
            options = list(cfg["pe_indices"].keys())
            sel = st.selectbox("查看估值历史", options)
            try:
                pe_df = hub.pe_history(cfg["pe_indices"][sel])
                st.plotly_chart(charts.pe_chart(pe_df, sel), width="stretch", key="mkt_pe")
            except Exception:  # noqa: BLE001
                st.warning("估值历史获取失败")
        with col2:
            erp = ind.equity_risk_premium(hub)
            if erp.get("ok"):
                _metric_row(
                    [
                        ("沪深300 PE", f"{erp['PE']}", "最新滚动市盈率"),
                        ("10Y国债", f"{erp['国债10Y']}%", "中国10年国债收益率"),
                        ("ERP", f"{erp['ERP']}%", "1/PE − 10Y"),
                        ("ERP分位", f"{erp['ERP分位%']}%", "历史分位"),
                    ]
                )
                st.plotly_chart(charts.erp_chart(erp["历史"]), width="stretch", key="mkt_erp")
            else:
                st.info("股债性价比数据暂不可用")

    st.subheader("市场成交额（快照累积）")
    try:
        amt = hub.amount_history()
        if amt is not None and not amt.empty:
            _metric_row([("最新两市成交额", f"{amt.iloc[-1]['两市成交额(亿)']:.0f} 亿元", "沪市+深市，每日更新一次")])
            st.plotly_chart(charts.line_chart(amt, "日期", "两市成交额(亿)", "两市成交额（亿元，自启用后累积）"), width="stretch", key="mkt_amount")
            st.caption("说明：该序列从你第一次使用本工具开始累积，历史越长越有参考意义。")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"成交额数据获取失败：{exc}")


# ---------------- 宏观经济 ----------------


def page_macro(hub, cfg, start, end):
    st.subheader("增长与价格")
    latest = {}
    try:
        g = hub.gdp()
        if g is not None and not g.empty:
            latest["GDP"] = g.iloc[-1]
    except Exception:  # noqa: BLE001
        pass
    try:
        latest["CPI"] = hub.cpi().dropna().iloc[-1]
    except Exception:  # noqa: BLE001
        pass
    try:
        latest["PPI"] = hub.ppi().dropna().iloc[-1]
    except Exception:  # noqa: BLE001
        pass
    try:
        latest["PMI"] = hub.pmi().dropna().iloc[-1]
    except Exception:  # noqa: BLE001
        pass
    try:
        latest["MS"] = hub.money_supply().dropna().iloc[-1]
    except Exception:  # noqa: BLE001
        pass
    try:
        lpr = hub.lpr().dropna(subset=["LPR1Y"])
        latest["LPR"] = lpr.iloc[-1]
    except Exception:  # noqa: BLE001
        pass

    items = []
    if "GDP" in latest:
        items.append(("GDP同比", f"{latest['GDP']['GDP同比']}%", str(latest["GDP"]["季度"])))
    if "CPI" in latest:
        items.append(("CPI同比", f"{latest['CPI']['CPI同比']}%", "居民消费价格"))
    if "PPI" in latest:
        items.append(("PPI同比", f"{latest['PPI']['PPI同比']}%", "工业生产者出厂价格"))
    if "PMI" in latest:
        items.append(("制造业PMI", f"{latest['PMI']['制造业PMI']}", "荣枯线50"))
    if "MS" in latest:
        items.append(("M2同比", f"{latest['MS']['M2同比']}%", "货币供应量"))
        items.append(("M1同比", f"{latest['MS']['M1同比']}%", "货币供应量"))
    if "LPR" in latest:
        items.append(("LPR1Y", f"{latest['LPR']['LPR1Y']}%", "贷款市场报价利率"))
    if items:
        _metric_row(items)

    col1, col2 = st.columns(2)
    with col1:
        try:
            g = hub.gdp()
            if g is not None and not g.empty:
                st.plotly_chart(charts.bar_chart(g.tail(16), "季度", "GDP同比", "GDP 同比增速（%）"), width="stretch", key="mac_gdp")
        except Exception:  # noqa: BLE001
            pass
        try:
            cpi = hub.cpi().dropna().tail(120)
            ppi = hub.ppi().dropna().tail(120)
            merged = cpi.merge(ppi, on="日期", how="outer").sort_values("日期")
            st.plotly_chart(charts.macro_multi_line(merged, "日期", ["CPI同比", "PPI同比"], "CPI 与 PPI 同比（%）"), width="stretch", key="mac_cpi_ppi")
        except Exception:  # noqa: BLE001
            pass
        try:
            pmi = hub.pmi().dropna().tail(60)
            st.plotly_chart(
                charts.macro_multi_line(pmi, "日期", ["制造业PMI", "非制造业PMI"], "PMI（荣枯线50）"), width="stretch", key="mac_pmi"
            )
        except Exception:  # noqa: BLE001
            pass
    with col2:
        try:
            ms = hub.money_supply().dropna().tail(60)
            st.plotly_chart(charts.macro_multi_line(ms, "日期", ["M2同比", "M1同比"], "M2 / M1 同比（%）"), width="stretch", key="mac_m2")
        except Exception:  # noqa: BLE001
            pass
        try:
            sf = hub.social_financing().dropna().tail(24)
            st.plotly_chart(charts.bar_chart(sf, "日期", "社融增量(亿)", "社会融资规模增量（亿元）"), width="stretch", key="mac_sf")
        except Exception:  # noqa: BLE001
            pass
        try:
            lpr = hub.lpr().dropna(subset=["LPR1Y"]).tail(120)
            st.plotly_chart(charts.macro_multi_line(lpr, "日期", ["LPR1Y", "LPR5Y"], "LPR（%）"), width="stretch", key="mac_lpr")
        except Exception:  # noqa: BLE001
            pass

    st.subheader("财政与内外需")
    col1, col2 = st.columns(2)
    with col1:
        try:
            fs = hub.fiscal_revenue().dropna().tail(36)
            st.plotly_chart(charts.line_chart(fs, "日期", "财政收入累计同比", "财政收入累计同比（%）"), width="stretch", key="mac_fiscal")
        except Exception:  # noqa: BLE001
            pass
        try:
            fai = hub.fixed_investment().dropna().tail(36)
            st.plotly_chart(charts.line_chart(fai, "日期", "固投当月同比", "固定资产投资当月同比（%）"), width="stretch", key="mac_fai")
        except Exception:  # noqa: BLE001
            pass
    with col2:
        try:
            rt = hub.retail_sales().dropna().tail(36)
            st.plotly_chart(charts.line_chart(rt, "日期", "社零累计同比", "社会消费品零售累计同比（%）"), width="stretch", key="mac_retail")
        except Exception:  # noqa: BLE001
            pass
        try:
            indus = hub.industrial().dropna().tail(36)
            exp = hub.exports().dropna().tail(36)
            m = indus.merge(exp, on="日期", how="outer").sort_values("日期")
            st.plotly_chart(charts.macro_multi_line(m, "日期", ["工业增加值同比", "出口同比"], "工业增加值与出口同比（%）"), width="stretch", key="mac_ie")
        except Exception:  # noqa: BLE001
            pass

    st.subheader("利率环境")
    try:
        bond = hub.bond_rates().dropna(subset=["中国国债收益率10年"]).tail(240)
        if not bond.empty:
            bond["中美利差"] = bond["中国国债收益率10年"] - bond["美国国债收益率10年"]
            st.plotly_chart(
                charts.macro_multi_line(bond, "日期", ["中国国债收益率10年", "美国国债收益率10年", "中美利差"], "中美国债10年期收益率（%）"),
                width="stretch", key="mac_bond",
            )
    except Exception:  # noqa: BLE001
        pass


# ---------------- 供需与资金 ----------------


def page_supply_demand(hub, cfg, start, end):
    st.subheader("股票供给")
    ipo = ind.ipo_stats(hub, start, end)
    if ipo.get("ok"):
        src = "巨潮口径" if ipo.get("source") == "cninfo" else "次新股口径"
        _metric_row(
            [
                ("新上市公司数", f"{ipo['新上市公司数']}", src),
                ("IPO募资合计", f"{ipo['募资合计(亿)'] or '—'} 亿元", src),
            ]
        )
        if not ipo.get("monthly", pd.DataFrame()).empty:
            st.plotly_chart(
                charts.bar_chart(ipo["monthly"], "月份", "募资(亿)", "月度 IPO 募资（亿元）"),
                width="stretch", key="sd_ipo",
            )
    st.caption("新股数据来自巨潮资讯（含上市日期、发行价、发行数量），统计区间内的上市公司家数与募资总额。")
    pipeline = ind.pipeline_stats(hub)
    if not pipeline.empty:
        with st.expander("IPO 申报/审核状态（东财数据中心）"):
            _df(pipeline)

    rp = ind.repurchase_stats(hub, start, end)
    if rp.get("ok"):
        _metric_row(
            [
                ("区间已回购金额", f"{rp['区间已回购金额合计(亿)']} 亿元", "已披露回购金额合计"),
                ("区间回购公告家数", f"{rp['区间公告计划家数']}", "最新公告日期落在区间内"),
            ]
        )
        col1, col2 = st.columns(2)
        with col1:
            if not rp["monthly"].empty:
                st.plotly_chart(charts.bar_chart(rp["monthly"], "月份", "已回购金额(亿)", "月度已回购金额（亿元）"), width="stretch", key="sd_rep")
        with col2:
            if not rp["plans"].empty:
                st.plotly_chart(charts.bar_chart(rp["plans"], "月份", "计划下限(亿)", "月度新增回购计划（下限，亿元）"), width="stretch", key="sd_plan")

    manual_ipo = hub.read_manual("manual_ipo")
    if manual_ipo is not None:
        st.subheader("手动导入：IPO / 再融资 / 解禁 / 减持")
        _df(manual_ipo)
        if "月份" in manual_ipo.columns and "IPO募资额(亿元)" in manual_ipo.columns:
            m = manual_ipo.dropna(subset=["IPO募资额(亿元)"])
            if not m.empty:
                st.plotly_chart(charts.bar_chart(m, "月份", "IPO募资额(亿元)", "IPO 募资（亿元，手动数据）"), width="stretch", key="sd_manual_ipo")
    else:
        st.info("可选：把 data/manual/manual_ipo.csv 填入官方 IPO/再融资/解禁/减持数据后自动展示。")

    st.divider()
    st.subheader("资金需求侧（买方资金）")
    mg = ind.margin_metrics(hub, start, end)
    if mg.get("ok"):
        _metric_row(
            [
                ("两融余额", f"{mg['两融余额(亿)']} 亿元", f"截至 {mg['最新日期']}"),
                ("区间变化", f"{mg['区间变化(亿)']:+.2f} 亿元", "区间首日至今"),
                ("融资买入20日均", f"{mg['融资余额20日均买入(亿)'] or '—'} 亿元", "杠杆资金活跃度"),
            ]
        )
        st.plotly_chart(charts.margin_chart(mg["历史"]), width="stretch", key="sd_margin")

    nb = ind.northbound_metrics(hub, start, end)
    if nb.get("ok"):
        _metric_row(
            [
                ("北向区间净买入", f"{nb['区间净买入合计(亿)']:+.2f} 亿元", f"{nb['区间有效交易日']} 个有效交易日"),
                ("历史累计净买额", f"{nb['历史累计净买额(亿)'] or '—'} 亿元", "2014年以来累计"),
            ]
        )
        st.plotly_chart(charts.northbound_chart(nb["历史"], start), width="stretch", key="sd_north")
        st.caption("2024年8月起交易所停止披露北向资金实时净买入，此后该序列无数据；可在 data/manual/manual_northbound.csv 手动补充。")

    etf = ind.etf_flow(hub, cfg, ind._first_trading_date(hub, start), ind._last_trading_date(hub, end))
    if not etf.empty:
        clean = etf[etf["疑似折算"] == "否"]
        total = clean["份额变化(亿份)"].sum() if not clean.empty else 0.0
        _metric_row([("观察池ETF份额合计", f"{total:+.1f} 亿份", "剔除疑似份额折算，上证所口径")])
        st.plotly_chart(charts.etf_bar(etf), width="stretch", key="sd_etf")
        with st.expander("ETF 份额明细表"):
            _df(etf)
        st.caption("已自动识别份额折算/合并（单月跳变>25%），此类基金不纳入合计；明细表里会标注。")

    funds = ind.fund_issuance(hub, start, end)
    if not funds.empty:
        _metric_row([("区间新发基金合计", f"{funds['募集份额(亿)'].sum():.0f} 亿元", f"{len(funds)} 条月度记录")])
        st.plotly_chart(charts.fund_chart(funds), width="stretch", key="sd_fund")

    inv = ind.investor_metrics(hub, start, end)
    if inv.get("ok"):
        stale = "数据日期" in inv and inv["数据日期"] and (pd.Timestamp(inv["数据日期"]) < pd.Timestamp.now() - pd.DateOffset(months=6))
        _metric_row(
            [
                ("最新单月新增开户", f"{inv['最新单月新增(万)']} 万户", f"最新月份 {inv['最新月份']}"),
                ("新增开户同比", f"{inv['最新单月同比%']:+.0f}%", "中国结算口径"),
                ("期末投资者总量", f"{inv['期末投资者总量(万)']:.0f} 万", "中国结算口径"),
            ]
        )
        if stale:
            st.caption(f"⚠️ 免费源的开户数据停更于 {inv['最新月份']}，仅供历史参考；可用手动 CSV 补充最新月份。")


# ---------------- 机构行为 ----------------


def page_institutions(hub, cfg, start, end):
    st.markdown("本章把资金分门别类：杠杆资金（两融）、外资（北向）、被动资金（ETF）、公募供给（新发基金）、产业资本（回购）。")
    st.subheader("杠杆资金：两融")
    mg = ind.margin_metrics(hub, start, end)
    if mg.get("ok"):
        _metric_row(
            [
                ("融资余额", f"{mg['融资余额(亿)']} 亿元", f"截至 {mg['最新日期']}"),
                ("融券余额", f"{mg['融券余额(亿)']} 亿元", ""),
                ("区间变化", f"{mg['区间变化(亿)']:+.2f} 亿元", "区间首日至今"),
            ]
        )
        st.plotly_chart(charts.margin_chart(mg["历史"]), width="stretch", key="inst_margin")

    st.subheader("外资：北向资金")
    nb = ind.northbound_metrics(hub, start, end)
    if nb.get("ok"):
        st.plotly_chart(charts.northbound_chart(nb["历史"], start), width="stretch", key="inst_north")
        st.caption("2024年8月起官方停止披露北向净买入，此后可使用手动数据补充。")
    manual_nb = hub.read_manual("manual_northbound")
    if manual_nb is not None:
        st.subheader("手动导入：北向净买入")
        _df(manual_nb)
        if {"日期", "北向净买入(亿元)"}.issubset(manual_nb.columns):
            m = manual_nb.copy()
            m["日期"] = pd.to_datetime(m["日期"], errors="coerce")
            st.plotly_chart(charts.bar_chart(m.dropna(subset=["日期"]), "日期", "北向净买入(亿元)", "北向净买入（亿元，手动数据）", positive_color=True), width="stretch", key="inst_manual_nb")

    st.subheader("被动资金：主要 ETF 份额")
    etf = ind.etf_flow(hub, cfg, ind._first_trading_date(hub, start), ind._last_trading_date(hub, end))
    if not etf.empty:
        st.plotly_chart(charts.etf_bar(etf), width="stretch", key="inst_etf")
        _df(etf)

    st.subheader("公募供给：新发基金")
    funds = ind.fund_issuance(hub, start, end)
    if not funds.empty:
        st.plotly_chart(charts.fund_chart(funds), width="stretch", key="inst_fund")
        with st.expander("新发基金明细表"):
            _df(funds)

    st.subheader("产业资本：回购")
    rp = ind.repurchase_stats(hub, start, end)
    if rp.get("ok"):
        if not rp["monthly"].empty:
            st.plotly_chart(charts.bar_chart(rp["monthly"], "月份", "已回购金额(亿)", "月度已回购金额（亿元）"), width="stretch", key="inst_rep")

    st.subheader("公募 / 险资 / 社保持仓（手动数据）")
    manual_inst = hub.read_manual("manual_institutions")
    if manual_inst is not None:
        _df(manual_inst)
        if "季度" in manual_inst.columns:
            cols = [c for c in ["公募偏股基金仓位(%)", "公募基金持股市值(亿元)", "险资持股市值(亿元)", "社保基金持股市值(亿元)"] if c in manual_inst.columns]
            if cols:
                m = manual_inst.copy()
                for c in cols:
                    m[c] = pd.to_numeric(m[c], errors="coerce")
                st.plotly_chart(charts.macro_multi_line(m, "季度", cols, "机构持仓（手动数据）"), width="stretch", key="inst_manual_inst")
    else:
        st.info("季度披露的公募仓位、险资/社保持仓等数据免费源拿不到全量，把官方季报数字填入 data/manual/manual_institutions.csv 即可在这里展示。")


# ---------------- 总结与展望 ----------------


def page_summary(hub, cfg, start, end):
    st.subheader("核心信号")
    signals = ind.build_signals(hub, cfg, start, end)
    if signals:
        cols = st.columns(len(signals))
        for col, sig in zip(cols, signals):
            color = "#dc2626" if "利" in sig["信号"] else "#16a34a" if "空" in sig["信号"] else "#64748b"
            col.metric(sig["指标"], sig["数值"], help=sig["说明"])
            col.markdown(f"<div style='color:{color};font-weight:600'>{sig['信号']}</div>", unsafe_allow_html=True)

    st.subheader("自动摘要")
    try:
        perf = ind.index_performance(hub, cfg, start, end)
        style_g = ind.style_gap(perf, cfg)
        pe = ind.pe_analysis(hub, cfg, start)
        erp = ind.equity_risk_premium(hub)
        for line in narrative.market_text(perf, style_g, pe, erp):
            st.markdown("- " + line)
        st.markdown("**宏观经济：**")
        for line in narrative.macro_text(hub):
            st.markdown("- " + line)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"摘要生成失败：{exc}")

    st.subheader("本期观点（你自己写）")
    notes_path = cfg["data_dir"] / "notes.md"
    old = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
    text = st.text_area("记录本期的判断、关注点或政策变化", height=180, key="note_editor")
    if st.button("保存本期观点"):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(notes_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n## {stamp}\n\n{text}\n")
        st.success("已保存")
        st.rerun()
    if old:
        with st.expander("历史观点"):
            st.markdown(old)

    st.subheader("导出报告")
    if st.button("生成 Markdown 报告快照", type="primary"):
        try:
            path = report_builder.save_report(hub, cfg, start, end)
            md = report_builder.build_markdown(hub, cfg, start, end)
            st.success(f"已生成：{path}")
            st.download_button("下载 Markdown", md, file_name="市场报告.md", mime="text/markdown")
        except Exception as exc:  # noqa: BLE001
            st.error(f"生成失败：{exc}")
