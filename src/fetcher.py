"""数据抓取层：AKShare 免费公开接口 + 本地缓存 + 手动 CSV 兜底。"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd

from . import store


def _parse_cn_month(s) -> pd.Timestamp:
    """把 '2026年07月份' / '201501' / '2026年第1-2季度' 等转成 Timestamp。"""
    text = str(s).strip()
    m = re.match(r"(\d{4})年(\d{1,2})月", text)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    m = re.match(r"(\d{4})-(\d{1,2})", text)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    m = re.match(r"(\d{4})(\d{2})", text)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    m = re.match(r"(\d{4})年", text)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=12, day=31)
    return pd.NaT


def _to_date_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df = df.copy()
    df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


class DataHub:
    """统一的数据入口：按 key 缓存、失败重试、记录警告。"""

    def __init__(self, cfg: dict, force: bool = False, offline: bool = False):
        self.cfg = cfg
        self.force = force
        self.offline = offline
        self.warnings: list[str] = []
        self._mem: dict[str, pd.DataFrame] = {}

    # ---------- 基础缓存 ----------
    def _fresh_hours(self, key: str) -> float:
        return float(self.cfg["cache_freshness_hours"].get(key, 24))

    def _get(self, key: str, fetch) -> pd.DataFrame:
        if key in self._mem:
            return self._mem[key]
        cache_dir = self.cfg["cache_dir"]
        df, updated_at = store.load(cache_dir, key)
        fresh = store.is_fresh(updated_at, self._fresh_hours(key))
        if self.force or (not self.offline and not fresh):
            last_exc = None
            for attempt in range(3):
                try:
                    df = fetch()
                    store.save(cache_dir, key, df)
                    last_exc = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    time.sleep(2 * (attempt + 1))
            if last_exc is not None:
                self.warnings.append(f"{key}：自动更新失败（{type(last_exc).__name__}: {last_exc}），使用本地缓存/手动数据。")
                if df is None:
                    raise last_exc
        self._mem[key] = df
        return df

    def read_manual(self, name: str) -> pd.DataFrame | None:
        """读取 data/manual/{name}.csv，不存在则返回 None。"""
        path: Path = self.cfg["manual_dir"] / f"{name}.csv"
        if not path.exists():
            return None
        try:
            return pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            self.warnings.append(f"手动数据 {name}.csv 读取失败：{exc}")
            return None

    # ---------- 行情 ----------
    def index_daily(self, symbol: str) -> pd.DataFrame:
        def fetch():
            df = ak.stock_zh_index_daily(symbol=symbol)
            df = df.rename(columns={"date": "日期", "close": "收盘"})
            return _to_date_col(df, "日期")

        return self._get(f"index_{symbol}", fetch)

    def index_spot(self) -> pd.DataFrame:
        return self._get("index_spot", lambda: ak.stock_zh_index_spot_sina())

    def pe_history(self, pe_name: str) -> pd.DataFrame:
        def fetch():
            df = ak.stock_index_pe_lg(symbol=pe_name)
            df = df[["日期", "指数", "滚动市盈率"]].copy()
            return _to_date_col(df, "日期")

        return self._get(f"pe_{pe_name}", fetch)

    # ---------- 行业 ----------
    def industry_names(self) -> pd.DataFrame:
        return self._get("industry_names", lambda: ak.stock_board_industry_name_ths())

    def industry_hist(self, name: str) -> pd.DataFrame:
        def fetch():
            df = ak.stock_board_industry_index_ths(
                symbol=name, start_date="20240101", end_date=datetime.now().strftime("%Y%m%d")
            )
            df = df.rename(columns={"日期": "日期", "收盘价": "收盘"})
            return _to_date_col(df, "日期")

        return self._get(f"industry_{name}", fetch)

    # ---------- 资金与杠杆 ----------
    def margin_total(self) -> pd.DataFrame:
        def fetch():
            sh = ak.macro_china_market_margin_sh()
            sz = ak.macro_china_market_margin_sz()
            sh = sh.rename(
                columns={
                    "日期": "日期",
                    "融资余额": "SH融资",
                    "融券余额": "SH融券",
                    "融资买入额": "SH融资买入",
                    "融资融券余额": "SH两融",
                }
            )
            sz = sz.rename(
                columns={
                    "日期": "日期",
                    "融资余额": "SZ融资",
                    "融券余额": "SZ融券",
                    "融资买入额": "SZ融资买入",
                    "融资融券余额": "SZ两融",
                }
            )
            sh = _to_date_col(sh, "日期")
            sz = _to_date_col(sz, "日期")
            df = sh.merge(sz, on="日期", how="outer").sort_values("日期").reset_index(drop=True)
            for col in ["SH融资", "SH融券", "SZ融资", "SZ融券", "SH融资买入", "SZ融资买入"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["融资余额"] = df[["SH融资", "SZ融资"]].sum(axis=1, min_count=1)
            df["融券余额"] = df[["SH融券", "SZ融券"]].sum(axis=1, min_count=1)
            df["融资融券余额"] = df["融资余额"].fillna(0) + df["融券余额"].fillna(0)
            df["融资买入额"] = df[["SH融资买入", "SZ融资买入"]].sum(axis=1, min_count=1)
            return df[["日期", "融资余额", "融券余额", "融资融券余额", "融资买入额", "SH融资", "SZ融资"]]

        return self._get("margin_v2", fetch)

    def northbound_hist(self) -> pd.DataFrame:
        def fetch():
            df = ak.stock_hsgt_hist_em(symbol="北向资金")
            df = df[["日期", "当日成交净买额", "历史累计净买额", "持股市值"]].copy()
            return _to_date_col(df, "日期")

        return self._get("northbound", fetch)

    def hsgt_summary(self) -> pd.DataFrame:
        return self._get("hsgt_summary", lambda: ak.stock_hsgt_fund_flow_summary_em())

    # ---------- 债券收益率 ----------
    def bond_rates(self) -> pd.DataFrame:
        def fetch():
            df = ak.bond_zh_us_rate(start_date="20150101")
            df = df[["日期", "中国国债收益率10年", "美国国债收益率10年"]].copy()
            return _to_date_col(df, "日期")

        return self._get("bond_rate", fetch)

    # ---------- 宏观 ----------
    def cpi(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_cpi_monthly()
            df = df[df["商品"] == "中国CPI月率报告"][["日期", "今值"]].rename(columns={"今值": "CPI同比"})
            return _to_date_col(df, "日期")

        return self._get("macro_cpi", fetch)

    def ppi(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_ppi()
            df = df.rename(columns={"月份": "月份", "当月同比增长": "PPI同比"})[["月份", "PPI同比"]]
            df["日期"] = df["月份"].map(_parse_cn_month)
            return _to_date_col(df.drop(columns=["月份"]), "日期")

        return self._get("macro_ppi", fetch)

    def pmi(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_pmi()
            df = df.rename(columns={"月份": "月份", "制造业-指数": "制造业PMI", "非制造业-指数": "非制造业PMI"})[
                ["月份", "制造业PMI", "非制造业PMI"]
            ]
            df["日期"] = df["月份"].map(_parse_cn_month)
            return _to_date_col(df.drop(columns=["月份"]), "日期")

        return self._get("macro_pmi", fetch)

    def money_supply(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_money_supply()
            df = df.rename(
                columns={
                    "月份": "月份",
                    "货币和准货币(M2)-同比增长": "M2同比",
                    "货币(M1)-同比增长": "M1同比",
                }
            )[["月份", "M2同比", "M1同比"]]
            df["日期"] = df["月份"].map(_parse_cn_month)
            return _to_date_col(df.drop(columns=["月份"]), "日期")

        return self._get("macro_m2", fetch)

    def social_financing(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_shrzgm()
            df = df.rename(
                columns={
                    "月份": "月份",
                    "社会融资规模增量": "社融增量(亿)",
                    "其中-非金融企业境内股票融资": "股票融资(亿)",
                }
            )[["月份", "社融增量(亿)", "股票融资(亿)"]]
            df["日期"] = df["月份"].map(_parse_cn_month)
            return _to_date_col(df.drop(columns=["月份"]), "日期")

        return self._get("macro_sf", fetch)

    def lpr(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_lpr()
            df = df[["TRADE_DATE", "LPR1Y", "LPR5Y"]].rename(columns={"TRADE_DATE": "日期", "LPR1Y": "LPR1Y", "LPR5Y": "LPR5Y"})
            return _to_date_col(df, "日期")

        return self._get("macro_lpr", fetch)

    def fiscal_revenue(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_czsr()
            df = df.rename(columns={"月份": "月份", "当月-同比增长": "财政收入当月同比", "累计-同比增长": "财政收入累计同比"})
            df["日期"] = df["月份"].map(_parse_cn_month)
            return _to_date_col(df.drop(columns=["月份"]), "日期")

        return self._get("macro_fiscal", fetch)

    def fixed_investment(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_gdzctz()
            df = df.rename(columns={"月份": "月份", "同比增长": "固投当月同比", "自年初累计": "固投累计(亿)"})
            df["日期"] = df["月份"].map(_parse_cn_month)
            return _to_date_col(df.drop(columns=["月份"]), "日期")

        return self._get("macro_fai", fetch)

    def retail_sales(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_consumer_goods_retail()
            df = df.rename(columns={"月份": "月份", "累计-同比增长": "社零累计同比", "当月-同比增长": "社零当月同比"})
            df["日期"] = df["月份"].map(_parse_cn_month)
            return _to_date_col(df.drop(columns=["月份"]), "日期")

        return self._get("macro_retail", fetch)

    def industrial(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_industrial_production_yoy()
            df = df[df["商品"] == "中国规模以上工业增加值年率报告"][["日期", "今值"]].rename(columns={"今值": "工业增加值同比"})
            return _to_date_col(df, "日期")

        return self._get("macro_indus", fetch)

    def exports(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_exports_yoy()
            df = df[df["商品"] == "中国以美元计算出口年率报告"][["日期", "今值"]].rename(columns={"今值": "出口同比"})
            return _to_date_col(df, "日期")

        return self._get("macro_exports", fetch)

    def gdp(self) -> pd.DataFrame:
        def fetch():
            df = ak.macro_china_gdp()
            df = df.rename(columns={"季度": "季度", "国内生产总值-同比增长": "GDP同比", "国内生产总值-绝对值": "GDP(亿)"})
            df["日期"] = df["季度"].map(_parse_cn_month)
            return _to_date_col(df[["日期", "季度", "GDP同比", "GDP(亿)"]], "日期")

        return self._get("macro_gdp", fetch)

    # ---------- 开户 / 新股 / 基金 / 回购 ----------
    def investor_stats(self) -> pd.DataFrame:
        return self._get("investor_stats", lambda: ak.stock_account_statistics_em())

    def etf_scale_sse(self, date_str: str) -> pd.DataFrame:
        def fetch():
            df = ak.fund_etf_scale_sse(date=date_str)
            return df[["基金代码", "基金简称", "基金份额"]].copy()

        return self._get(f"etf_scale_{date_str}", fetch)

    def etf_spot(self) -> pd.DataFrame:
        return self._get("etf_spot", lambda: ak.fund_etf_spot_em())

    def new_funds(self) -> pd.DataFrame:
        return self._get("new_funds", lambda: ak.fund_new_found_em())

    def repurchase(self) -> pd.DataFrame:
        return self._get("repurchase", lambda: ak.stock_repurchase_em())

    def new_stocks(self) -> pd.DataFrame:
        return self._get("new_stocks", lambda: ak.stock_new_a_spot_em())

    def new_ipo_cninfo(self) -> pd.DataFrame:
        return self._get("new_ipo_cninfo", lambda: ak.stock_new_ipo_cninfo())

    def ipo_pipeline(self) -> pd.DataFrame:
        return self._get("ipo_pipeline", lambda: ak.stock_ipo_declare_em())

    def amount_history(self) -> pd.DataFrame:
        """两市成交额快照（每天更新一次，历史自动累积）。"""

        def fetch():
            spot = ak.stock_zh_index_spot_sina()
            row = spot[spot["代码"].isin(["sh000001", "sz399001"])].set_index("代码")["成交额"]
            amt = (row.get("sh000001", 0) + row.get("sz399001", 0)) / 1e8
            today = pd.Timestamp(datetime.now().date())
            prev, _ = store.load(self.cfg["cache_dir"], "amount_history")
            if prev is not None and not prev.empty:
                prev = _to_date_col(prev, "日期")
                if today in set(pd.DatetimeIndex(prev["日期"]).normalize()):
                    return prev
                new = pd.DataFrame({"日期": [today], "两市成交额(亿)": [round(amt, 2)]})
                return (
                    pd.concat([prev, new], ignore_index=True)
                    .drop_duplicates("日期")
                    .sort_values("日期")
                    .reset_index(drop=True)
                )
            return pd.DataFrame({"日期": [today], "两市成交额(亿)": [round(amt, 2)]})

        return self._get("amount_history", fetch)
