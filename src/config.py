"""读取 config.yaml 并解析路径。"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_root"] = ROOT
    cfg["data_dir"] = ROOT / cfg["project"]["data_dir"]
    cfg["report_dir"] = ROOT / cfg["project"]["report_dir"]
    cfg["cache_dir"] = cfg["data_dir"] / "cache"
    cfg["manual_dir"] = cfg["data_dir"] / "manual"
    for d in (cfg["cache_dir"], cfg["manual_dir"], cfg["report_dir"]):
        d.mkdir(parents=True, exist_ok=True)
    return cfg


def yaml_to_py(val) -> object:
    """方便把 yaml 里的 python 类型值转出来（备用）。"""
    return val

