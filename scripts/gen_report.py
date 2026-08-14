"""生成 Markdown 报告：python scripts/gen_report.py --start 2026-01-01"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config
from src.fetcher import DataHub
from src.report_builder import save_report


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Markdown 报告快照")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default=str(date.today()))
    args = parser.parse_args()

    cfg = load_config()
    hub = DataHub(cfg, force=False)
    path = save_report(hub, cfg, args.start, args.end)
    print(f"报告已生成：{path}")
    for w in hub.warnings:
        print("警告:", w)


if __name__ == "__main__":
    main()
