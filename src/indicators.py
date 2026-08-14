"""指标计算：把原始数据加工成报告所需的数字、表格与信号。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .fetcher import DataHub


def _slice(df: pd.DataFrame, date_col: str, start, end) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    return df[(df[date_col] >= start_ts) & (df[date_col] <= end_ts)]


def _find_col(df: pd.DataFrame, *subs: str) -> str | None:
    for col in df.columns:
        if all(s in str(col) for s in subs):
            return str(col)
    return None


def _fmt(x, nd: int = 2) -> str:
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


# ---------- 市场全景 ----------


def index_performance(hub: DataHub, cfg: dict, start, end) -> pd.DataFrame:
    rows = []
    for name, symbol in cfg["indices"].items():
        try:
            df = hub.index_daily(symbol)
        except Exception:  # noqa: BLE001
            continue
        s = _slice(df, "日期", start, end)
        if s is None or s.empty:
            continue
        first = s.iloc[0]["收盘"]
        last = s.iloc[-1]["收盘"]
        ret = (last / first - 1) * 100
        dd = (s["收盘"] / s["收盘"].cummax() - 1).min() * 100
        rows.append(
            {
                "指数": name,
                "期初收盘": round(float(first), 2),
                "期末收盘": round(float(last), 2),
                "区间涨跌幅%": round(float(ret), 2),
                "区间最大回撤%": round(float(dd), 2),
                "最新交易日": s.iloc[-1]["日期"].date(),
            }
        )
    return pd.DataFrame(rows).sort_values("区间涨跌幅%", ascending=False).reset_index(drop=True)


def normalized_index_df(hub: DataHub, cfg: dict, start, end) -> pd.DataFrame:
    frames = []
    for name, symbol in cfg["indices"].items():
        try:
            df = hub.index_daily(symbol)
        except Exception:  # noqa: BLE001
            continue
        s = _slice(df, "日期", start, end)
        if s is None or s.empty:
            continue
        base = s.iloc[0]["收盘"]
        tmp = pd.DataFrame(
            {"日期": s["日期"], "指数": name, "净值": s["收盘"] / base * 100}
        )
        frames.append(tmp)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def style_gap(perf: pd.DataFrame, cfg: dict) -> dict:
    st = cfg["style"]
    def ret_of(key: str) -> float | None:
        row = perf[perf["指数"] == st[key]]
        return None if row.empty else float(row.iloc[0]["区间涨跌幅%"])

    large, small, growth, value = ret_of("大盘"), ret_of("小盘"), ret_of("成长"), ret_of("价值")
    return {
        "小盘-大盘": (small - large) if (small is not None and large is not None) else None,
        "成长-价值": (growth - value) if (growth is not None and value is not None) else None,
        "小盘": small,
        "大盘": large,
        "成长": growth,
        "价值": value,
    }


# ---------- 估值 ----------


def pe_analysis(hub: DataHub, cfg: dict, start) -> pd.DataFrame:
    rows = []
    for display, pe_name in cfg["pe_indices"].items():
        try:
            df = hub.pe_history(pe_name)
        except Exception:  # noqa: BLE001
            continue
        if df is None or df.empty:
            continue
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
        s = df[df["日期"] >= pd.Timestamp(start)]
        if s.empty:
            continue
        pe_series = pd.to_numeric(s["滚动市盈率"], errors="coerce").dropna()
        if pe_series.empty:
            continue
        all_series = pd.to_numeric(df["滚动市盈率"], errors="coerce").dropna()
        latest = pe_series.iloc[-1]
        pct = float((all_series <= latest).mean() * 100)
        rows.append(
            {
                "指数": display,
                "最新PE": round(float(latest), 2),
                "历史分位%": round(pct, 1),
                "区间最低PE": round(float(pe_series.min()), 2),
                "区间最高PE": round(float(pe_series.max()), 2),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("历史分位%", ascending=False).reset_index(drop=True)


def equity_risk_premium(hub: DataHub) -> dict:
    """股债性价比：1/沪深300滚动PE - 中国10年国债收益率。"""
    try:
        pe = hub.pe_history("沪深300")
        bond = hub.bond_rates()
    except Exception:  # noqa: BLE001
        return {"ok": False}
    if pe is None or bond is None or pe.empty or bond.empty:
        return {"ok": False}
    pe["日期"] = pd.to_datetime(pe["日期"], errors="coerce")
    bond["日期"] = pd.to_datetime(bond["日期"], errors="coerce")
    pe = pe[["日期", "滚动市盈率"]].dropna(subset=["滚动市盈率"])
    bond = bond[["日期", "中国国债收益率10年"]].dropna(subset=["中国国债收益率10年"])
    m = pd.merge_asof(pe.sort_values("日期"), bond.sort_values("日期"), on="日期", direction="backward")
    m = m.dropna()
    if m.empty:
        return {"ok": False}
    m["ERP"] = 100.0 / m["滚动市盈率"] - m["中国国债收益率10年"]
    latest = m.iloc[-1]
    pct = float((m["ERP"] <= latest["ERP"]).mean() * 100)
    return {
        "ok": True,
        "日期": latest["日期"].date(),
        "PE": round(float(latest["滚动市盈率"]), 2),
        "国债10Y": round(float(latest["中国国债收益率10年"]), 3),
        "ERP": round(float(latest["ERP"]), 2),
        "ERP分位%": round(pct, 1),
        "历史": m[["日期", "ERP"]],
    }


# ---------- 行业 ----------


def industry_ranking(hub: DataHub, start, end, progress=None) -> pd.DataFrame:
    try:
        names = hub.industry_names()
    except Exception as exc:  # noqa: BLE001
        hub.warnings.append(f"行业列表获取失败：{exc}")
        return pd.DataFrame()
    rows = []
    all_names = names["name"].tolist()
    for i, name in enumerate(all_names):
        if progress is not None:
            progress((i + 1) / len(all_names), name)
        try:
            df = hub.industry_hist(name)
        except Exception:  # noqa: BLE001
            continue
        s = _slice(df, "日期", start, end)
        if s is None or s.empty or len(s) < 2:
            continue
        ret = (s.iloc[-1]["收盘"] / s.iloc[0]["收盘"] - 1) * 100
        rows.append({"行业": name, "区间涨跌幅%": round(float(ret), 2)})
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("区间涨跌幅%", ascending=False).reset_index(drop=True)
    out["排名"] = np.arange(1, len(out) + 1)
    return out


# ---------- 资金与供需 ----------


def margin_metrics(hub: DataHub, start, end) -> dict:
    try:
        df = hub.margin_total()
    except Exception as exc:  # noqa: BLE001
        hub.warnings.append(f"两融数据获取失败：{exc}")
        return {"ok": False}
    s = _slice(df, "日期", start, end)
    if s.empty:
        return {"ok": False}
    latest = s.iloc[-1]
    first = s.iloc[0]
    buy20 = s["融资买入额"].dropna().tail(20).mean()
    return {
        "ok": True,
        "最新日期": latest["日期"].date(),
        "融资余额(亿)": round(float(latest["融资余额"]) / 1e8, 2),
        "融券余额(亿)": round(float(latest["融券余额"]) / 1e8, 2),
        "两融余额(亿)": round(float(latest["融资融券余额"]) / 1e8, 2),
        "区间变化(亿)": round((latest["融资融券余额"] - first["融资融券余额"]) / 1e8, 2),
        "融资余额20日均买入(亿)": round(float(buy20) / 1e8, 2) if pd.notna(buy20) else None,
        "历史": s[["日期", "融资余额", "融券余额", "融资融券余额", "融资买入额"]].copy(),
    }


def northbound_metrics(hub: DataHub, start, end) -> dict:
    try:
        df = hub.northbound_hist()
    except Exception as exc:  # noqa: BLE001
        hub.warnings.append(f"北向数据获取失败：{exc}")
        return {"ok": False}
    s = _slice(df, "日期", start, end)
    net = pd.to_numeric(s["当日成交净买额"], errors="coerce")
    valid = net.dropna()
    cum = pd.to_numeric(df["历史累计净买额"], errors="coerce").dropna()
    return {
        "ok": True,
        "最新日期": s.iloc[-1]["日期"].date() if not s.empty else None,
        "区间有效交易日": int(valid.size),
        "区间净买入合计(亿)": round(float(valid.sum()), 2) if not valid.empty else 0.0,
        "历史累计净买额(亿)": round(float(cum.iloc[-1] * 10000), 2) if not cum.empty else None,
        "历史": df[["日期", "当日成交净买额"]].copy(),
    }


def etf_flow(hub: DataHub, cfg: dict, start_date_str: str, end_date_str: str) -> pd.DataFrame:
    """ETF 份额变化：用月度检查点识别份额折算/合并，避免把折算误判为赎回。"""
    watch = cfg["etf_watchlist"]
    codes = list(watch.keys())
    try:
        index_dates = pd.to_datetime(hub.index_daily("sh000001")["日期"], errors="coerce").dropna()
        s_start, s_end = pd.Timestamp(start_date_str), pd.Timestamp(end_date_str)
        months = pd.period_range(s_start.to_period("M"), s_end.to_period("M"), freq="M")
        checkpoints = [s_start]
        for m in months:
            day = index_dates[(index_dates >= m.start_time) & (index_dates <= m.end_time)]
            if not day.empty:
                d = day.min()
                if d not in checkpoints:
                    checkpoints.append(d)
        last = index_dates[index_dates <= s_end]
        if not last.empty and last.max() not in checkpoints:
            checkpoints.append(last.max())
        checkpoints = sorted(set(pd.Timestamp(c) for c in checkpoints))

        frames = {}
        for cp in checkpoints:
            date_str = pd.Timestamp(cp).strftime("%Y%m%d")
            df = hub.etf_scale_sse(date_str)
            if df is None or df.empty:
                continue
            frames[date_str] = df[df["基金代码"].isin(codes)].set_index("基金代码")["基金份额"]
        if len(frames) < 2:
            return pd.DataFrame()

        dates_sorted = sorted(frames.keys())
        rows = []
        for code in codes:
            series = pd.Series({d: frames[d].get(code) for d in dates_sorted}).astype(float)
            if series.notna().sum() < 2:
                continue
            first_v, last_v = series.iloc[0], series.iloc[-1]
            chg = (last_v - first_v) / 1e8
            pct = (last_v / first_v - 1) * 100 if first_v else 0.0
            vals = series.dropna()
            max_jump = max(
                (abs(vals.iloc[i] / vals.iloc[i - 1] - 1) * 100 for i in range(1, len(vals))),
                default=0.0,
            )
            missing = bool(series.isna().any())
            flag = "是" if (max_jump > 25 or missing) else "否"
            rows.append(
                {
                    "基金代码": code,
                    "名称": watch[code],
                    "期初份额(亿)": round(first_v / 1e8, 2),
                    "期末份额(亿)": round(last_v / 1e8, 2),
                    "份额变化(亿份)": round(chg, 2),
                    "份额变化%": round(pct, 2),
                    "单月最大跳变%": round(max_jump, 1),
                    "疑似折算": flag,
                }
            )
        out = pd.DataFrame(rows).sort_values("份额变化(亿份)", ascending=False).reset_index(drop=True)
        return out
    except Exception as exc:  # noqa: BLE001
        hub.warnings.append(f"ETF 份额数据获取失败：{exc}")
        return pd.DataFrame()


def fund_issuance(hub: DataHub, start, end) -> pd.DataFrame:
    try:
        df = hub.new_funds()
    except Exception as exc:  # noqa: BLE001
        hub.warnings.append(f"新发基金数据获取失败：{exc}")
        return pd.DataFrame()
    if df is None or df.empty or "成立日期" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["成立日期"] = pd.to_datetime(df["成立日期"], errors="coerce")
    s = df[(df["成立日期"] >= pd.Timestamp(start)) & (df["成立日期"] <= pd.Timestamp(end))].copy()
    if s.empty:
        return pd.DataFrame()
    s["月份"] = s["成立日期"].dt.to_period("M")
    s["募集份额(亿)"] = pd.to_numeric(s["募集份额"], errors="coerce").fillna(0)

    def category(t):
        t = str(t)
        if "债券" in t or "固收" in t:
            return "债券型"
        if "股票" in t or t.startswith("指数型") or "QDII" in t.upper():
            return "股票型"
        if "混合" in t:
            return "混合型"
        if "货币" in t:
            return "货币型"
        if "FOF" in t.upper() or "养老" in t:
            return "FOF/养老"
        return "其他"

    s["类型"] = s["基金类型"].map(category)
    agg = (
        s.groupby(["月份", "类型"], as_index=False)
        .agg({"募集份额(亿)": "sum", "基金代码": "count"})
        .rename(columns={"基金代码": "只数"})
    )
    agg["月份"] = agg["月份"].astype(str)
    return agg.sort_values(["月份", "募集份额(亿)"])


def repurchase_stats(hub: DataHub, start, end) -> dict:
    try:
        df = hub.repurchase()
    except Exception as exc:  # noqa: BLE001
        hub.warnings.append(f"回购数据获取失败：{exc}")
        return {"ok": False}
    if df is None or df.empty:
        return {"ok": False}
    df = df.copy()
    df["最新公告日期"] = pd.to_datetime(df["最新公告日期"], errors="coerce")
    s = _slice(df, "最新公告日期", start, end)
    if s.empty:
        return {"ok": False, "monthly": pd.DataFrame(), "plans": pd.DataFrame()}
    done = s[pd.to_numeric(s["已回购金额"], errors="coerce") > 0].copy()
    monthly = pd.DataFrame()
    if not done.empty:
        done["月份"] = done["最新公告日期"].dt.to_period("M").astype(str)
        done["已回购金额(亿)"] = pd.to_numeric(done["已回购金额"], errors="coerce") / 1e8
        monthly = done.groupby("月份", as_index=False)["已回购金额(亿)"].sum()
    plans = s.copy()
    plans["月份"] = plans["最新公告日期"].dt.to_period("M").astype(str)
    plans["计划下限(亿)"] = pd.to_numeric(plans["计划回购金额区间-下限"], errors="coerce") / 1e8
    plan_monthly = plans.groupby("月份", as_index=False)["计划下限(亿)"].sum()
    return {
        "ok": True,
        "区间已回购金额合计(亿)": round(float(monthly["已回购金额(亿)"].sum()), 2) if not monthly.empty else 0.0,
        "区间公告计划家数": int(len(plans)),
        "monthly": monthly,
        "plans": plan_monthly,
    }


def ipo_stats(hub: DataHub, start, end) -> dict:
    """新股供给：优先用巨潮（含募资额），失败时退回次新股口径。"""
    source = "cninfo"
    try:
        df = hub.new_ipo_cninfo()
        if df is None or df.empty:
            raise ValueError("空数据")
        date_col, price_col, qty_col = "上市日期", "发行价", "总发行数量"
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    except Exception as exc:  # noqa: BLE001
        source = "次新"
        hub.warnings.append(f"巨潮新股数据不可用（{exc}），退回次新股口径。")
        try:
            df = hub.new_stocks()
            if df is None or df.empty:
                raise ValueError("空数据")
            df = df.copy()
            date_col = _find_col(df, "上市日期") or "上市日期"
            price_col = None
            qty_col = None
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        except Exception as exc2:  # noqa: BLE001
            hub.warnings.append(f"次新股数据也不可用：{exc2}")
            return {"ok": False}

    s = df[(df[date_col] >= pd.Timestamp(start)) & (df[date_col] <= pd.Timestamp(end))].copy()
    if s.empty:
        return {"ok": True, "新上市公司数": 0, "募资合计(亿)": 0.0, "source": source, "monthly": pd.DataFrame()}

    result: dict = {"ok": True, "新上市公司数": int(len(s)), "source": source}
    if price_col and qty_col:
        s["募资(亿)"] = (
            pd.to_numeric(s[price_col], errors="coerce") * pd.to_numeric(s[qty_col], errors="coerce") / 10000
        )
        result["募资合计(亿)"] = round(float(s["募资(亿)"].sum()), 2)
        s["月份"] = s[date_col].dt.to_period("M").astype(str)
        monthly = (
            s.groupby("月份", as_index=False)
            .agg({"证券简称": "count", "募资(亿)": "sum"})
            .rename(columns={"证券简称": "家数"})
        )
        result["monthly"] = monthly
    else:
        result["募资合计(亿)"] = None
        result["monthly"] = pd.DataFrame()
    return result


def pipeline_stats(hub: DataHub) -> pd.DataFrame:
    try:
        df = hub.ipo_pipeline()
    except Exception as exc:  # noqa: BLE001
        hub.warnings.append(f"IPO 申报数据获取失败：{exc}")
        return pd.DataFrame()
    if df is None or df.empty or "最新状态" not in df.columns:
        return pd.DataFrame()
    return df["最新状态"].value_counts().rename_axis("状态").reset_index(name="家数")


def investor_metrics(hub: DataHub, start, end) -> dict:
    try:
        df = hub.investor_stats()
    except Exception as exc:  # noqa: BLE001
        hub.warnings.append(f"开户数据获取失败：{exc}")
        return {"ok": False}
    if df is None or df.empty or "数据日期" not in df.columns:
        return {"ok": False}
    df = df.copy()
    df["期间"] = pd.to_datetime(df["数据日期"] + "-01", errors="coerce")
    s = _slice(df, "期间", start, end)
    latest = df.sort_values("期间").iloc[-1]
    return {
        "ok": True,
        "最新月份": str(latest["数据日期"]),
        "数据日期": latest["期间"].date(),
        "最新单月新增(万)": round(float(latest["新增投资者-数量"]), 2),
        "最新单月同比%": round(float(latest["新增投资者-同比"]), 1),
        "期末投资者总量(万)": round(float(latest["期末投资者-总量"]), 0),
        "区间新增合计(万)": round(float(pd.to_numeric(s["新增投资者-数量"], errors="coerce").sum()), 2)
        if not s.empty
        else None,
    }


# ---------- 信号 ----------


def build_signals(hub: DataHub, cfg: dict, start, end) -> list[dict]:
    signals: list[dict] = []
    try:
        pe = pe_analysis(hub, cfg, start)
        if not pe.empty:
            row = pe[pe["指数"] == "沪深300"]
            if not row.empty:
                pct = float(row.iloc[0]["历史分位%"])
                signal = "偏低估（利多）" if pct < 30 else "偏高估（利空）" if pct > 75 else "中性"
                signals.append(
                    {"指标": "沪深300估值分位", "数值": f"{pct:.0f}%", "信号": signal, "说明": "按滚动市盈率在全部历史中的分位"}
                )
        erp = equity_risk_premium(hub)
        if erp.get("ok"):
            pct = erp["ERP分位%"]
            signal = "股债性价比高（利多）" if pct > 75 else "股债性价比低（利空）" if pct < 25 else "中性"
            signals.append(
                {"指标": "股债性价比", "数值": f"{erp['ERP']:.2f}%", "信号": signal, "说明": f"1/PE-10Y国债，分位 {pct:.0f}%"}
            )
    except Exception:  # noqa: BLE001
        pass
    mg = margin_metrics(hub, start, end)
    if mg.get("ok"):
        hist = mg["历史"]
        chg20 = (
            float(hist["融资余额"].iloc[-1] / hist["融资余额"].iloc[-21] - 1) * 100
            if len(hist) >= 21 and hist["融资余额"].iloc[-21] > 0
            else 0.0
        )
        signal = "杠杆资金流入（利多）" if chg20 > 1 else "杠杆资金流出（利空）" if chg20 < -1 else "中性"
        signals.append({"指标": "两融资金", "数值": f"{chg20:+.1f}%（20日）", "信号": signal, "说明": "融资余额 20 日变化率"})
    inv = investor_metrics(hub, start, end)
    stale = (
        "数据日期" in inv
        and inv["数据日期"]
        and (pd.Timestamp(inv["数据日期"]) < pd.Timestamp.now() - pd.DateOffset(months=6))
    )
    if inv.get("ok") and inv["最新单月同比%"] is not None and not stale:
        yoy = inv["最新单月同比%"]
        signal = "新增资金加速（利多）" if yoy > 20 else "新增资金放缓（利空）" if yoy < -20 else "中性"
        signals.append({"指标": "新增开户", "数值": f"{yoy:+.0f}%（同比）", "信号": signal, "说明": f"最新月份 {inv['最新月份']}"})
    try:
        etf = etf_flow(hub, cfg, _first_trading_date(hub, start), _last_trading_date(hub, end))
        if not etf.empty:
            clean = etf[etf["疑似折算"] == "否"]
            total = float(clean["份额变化(亿份)"].sum()) if not clean.empty else 0.0
            signal = "ETF 净申购（利多）" if total > 20 else "ETF 净赎回（利空）" if total < -20 else "中性"
            signals.append({"指标": "主要宽基ETF份额", "数值": f"{total:+.1f} 亿份", "信号": signal, "说明": "观察池 ETF 份额净变化（剔除疑似份额折算）"})
    except Exception:  # noqa: BLE001
        pass
    return signals


def _first_trading_date(hub: DataHub, start) -> str:
    try:
        dates = pd.to_datetime(hub.index_daily("sh000001")["日期"], errors="coerce").dropna()
        hit = dates[dates >= pd.Timestamp(start)].min()
        if pd.notna(hit):
            return hit.strftime("%Y%m%d")
    except Exception:  # noqa: BLE001
        pass
    return pd.Timestamp(start).strftime("%Y%m%d")


def _last_trading_date(hub: DataHub, end) -> str:
    try:
        dates = pd.to_datetime(hub.index_daily("sh000001")["日期"], errors="coerce").dropna()
        hit = dates[dates <= pd.Timestamp(end)].max()
        if pd.notna(hit):
            return hit.strftime("%Y%m%d")
    except Exception:  # noqa: BLE001
        pass
    return pd.Timestamp(end).strftime("%Y%m%d")
