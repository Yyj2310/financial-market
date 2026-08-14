"""命令行更新数据：python scripts/update_data.py [--skip-industry]"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config
from src.fetcher import DataHub


def main() -> None:
    parser = argparse.ArgumentParser(description="更新证券市场数据缓存")
    parser.add_argument("--skip-industry", action="store_true", help="跳过行业指数历史（较慢）")
    args = parser.parse_args()

    cfg = load_config()
    hub = DataHub(cfg, force=True)

    print("[1/6] 指数行情…")
    for name, symbol in cfg["indices"].items():
        try:
            df = hub.index_daily(symbol)
            print(f"  - {name}: {len(df)} 行")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {name} 失败：{exc}")
    idx_dates = pd.to_datetime(hub.index_daily("sh000001")["日期"], errors="coerce").dropna()
    first = idx_dates[idx_dates >= "2026-01-01"].min().strftime("%Y%m%d")
    last = idx_dates.max().strftime("%Y%m%d")
    print(f"  交易日范围：{first} ~ {last}")

    print("[2/6] 估值…")
    for name in cfg["pe_indices"].values():
        try:
            hub.pe_history(name)
            print(f"  - {name} OK")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {name} 失败：{exc}")

    print("[3/6] 行业（同花顺）…")
    try:
        names = hub.industry_names()
        if not args.skip_industry:
            for i, name in enumerate(names["name"].tolist(), 1):
                hub.industry_hist(name)
                if i % 10 == 0:
                    print(f"  - {i}/{len(names)}")
        else:
            print("  - 已跳过（--skip-industry）")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! 行业失败：{exc}")

    print("[4/6] 资金数据…")
    for label, fn in [
        ("两融", hub.margin_total),
        ("北向历史", hub.northbound_hist),
        ("ETF份额(年初)", lambda: hub.etf_scale_sse(first)),
        ("ETF份额(最新)", lambda: hub.etf_scale_sse(last)),
        ("成交额快照", hub.amount_history),
    ]:
        try:
            df = fn()
            print(f"  - {label}: {len(df)} 行")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {label} 失败：{exc}")

    print("[5/6] 宏观数据…")
    for label, fn in [
        ("GDP", hub.gdp),
        ("CPI", hub.cpi),
        ("PPI", hub.ppi),
        ("PMI", hub.pmi),
        ("M1/M2", hub.money_supply),
        ("社融", hub.social_financing),
        ("LPR", hub.lpr),
        ("财政", hub.fiscal_revenue),
        ("固投", hub.fixed_investment),
        ("社零", hub.retail_sales),
        ("工业", hub.industrial),
        ("出口", hub.exports),
        ("中美利率", hub.bond_rates),
        ("开户", hub.investor_stats),
    ]:
        try:
            df = fn()
            print(f"  - {label}: {len(df)} 行")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {label} 失败：{exc}")

    print("[6/6] 新股 / 基金 / 回购…")
    for label, fn in [
        ("次新股", hub.new_stocks),
        ("新股(巨潮)", hub.new_ipo_cninfo),
        ("IPO申报", hub.ipo_pipeline),
        ("新发基金", hub.new_funds),
        ("回购", hub.repurchase),
    ]:
        try:
            df = fn()
            print(f"  - {label}: {len(df)} 行")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {label} 失败：{exc}")

    print("\n完成。警告：")
    for w in hub.warnings:
        print("  -", w)
    if not hub.warnings:
        print("  （无）")


if __name__ == "__main__":
    main()
