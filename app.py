"""交互式网页入口：streamlit run app.py"""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.config import load_config
from src.fetcher import DataHub
from src import ui


st.set_page_config(page_title="证券市场分析报告", page_icon="📈", layout="wide")
cfg = load_config()

st.sidebar.title("📈 证券市场分析")
st.sidebar.caption("宏观 × 供需 × 机构行为，数据自动更新")

default_start = date(2026, 1, 1)
start = st.sidebar.date_input("区间开始", default_start)
end = st.sidebar.date_input("区间结束", date.today())
if start > end:
    start, end = end, start

offline = st.sidebar.checkbox("离线模式（只用本地缓存）", value=False)
if st.sidebar.button("立即更新全部数据", width="stretch"):
    st.session_state["force_refresh"] = True
    st.rerun()
st.sidebar.caption("首次打开会联网取数，之后每天自动增量更新。行业数据首次较慢（约1-2分钟）。")

force = st.session_state.pop("force_refresh", False)
hub = DataHub(cfg, force=force, offline=offline)

st.title(f"证券市场分析报告：{start} 至 {end}")
ui.show_warnings(hub)

tab_market, tab_macro, tab_sd, tab_inst, tab_summary = st.tabs(
    ["市场全景", "宏观经济", "供需与资金", "机构行为", "总结与展望"]
)

with tab_market:
    ui.page_market(hub, cfg, start, end)
with tab_macro:
    ui.page_macro(hub, cfg, start, end)
with tab_sd:
    ui.page_supply_demand(hub, cfg, start, end)
with tab_inst:
    ui.page_institutions(hub, cfg, start, end)
with tab_summary:
    ui.page_summary(hub, cfg, start, end)

st.sidebar.divider()
st.sidebar.caption(
    "数据来源：新浪财经、腾讯财经、同花顺、乐咕乐股、东方财富数据中心、国家统计局、央行、中国结算等免费公开接口。"
    "本工具仅供研究参考，不构成投资建议。"
)
