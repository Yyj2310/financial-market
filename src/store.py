"""本地缓存：CSV + JSON 元信息，简单可靠。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def _safe_key(key: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in key)


def save(cache_dir: Path, key: str, df: pd.DataFrame) -> None:
    safe = _safe_key(key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_dir / f"{safe}.csv", index=False, encoding="utf-8-sig")
    meta = {"key": key, "updated_at": datetime.now().isoformat(timespec="seconds")}
    with open(cache_dir / f"{safe}.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)


def load(cache_dir: Path, key: str) -> tuple[pd.DataFrame | None, datetime | None]:
    safe = _safe_key(key)
    csv_path = cache_dir / f"{safe}.csv"
    json_path = cache_dir / f"{safe}.json"
    if not csv_path.exists():
        return None, None
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return None, None
    updated_at = None
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                updated_at = datetime.fromisoformat(json.load(f)["updated_at"])
        except Exception:
            updated_at = None
    return df, updated_at


def is_fresh(updated_at: datetime | None, max_hours: float) -> bool:
    if updated_at is None:
        return False
    age = (datetime.now() - updated_at).total_seconds() / 3600.0
    return age <= max_hours

