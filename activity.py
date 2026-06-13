from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List

from fitbit_source_paths import iter_allowed_fitbit_files






def normalize_patient_id(raw: str) -> str:
    raw = raw.strip().upper()
    if not raw:
        raise ValueError("Brak numeru pacjenta.")
    if raw.startswith("G"):
        return raw
    return f"G{raw}"


def parse_fitbit_date(dt_str: str) -> date | None:
    formats = [
        "%m/%d/%y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt).date()
        except:
            continue
    return None






def collect_activity_files(root: Path, pid: str):
    bases = [root / pid, root / f"{pid}_google"]
    files = []

    for base in bases:
        if not base.exists():
            continue

        for p in iter_allowed_fitbit_files(base, "*active_minutes*.json"):
            files.append(p)

        for p in iter_allowed_fitbit_files(base, "sedentary_minutes*.json"):
            files.append(p)

    return files






def compute_activity_for_dates(
    root: Path,
    pid: str,
    dates: List[date]
) -> Dict[date, Dict[str, float]]:

    if not dates:
        return {}

    date_set = set(dates)
    files = collect_activity_files(root, pid)

    result: Dict[date, Dict[str, float]] = {}

    for path in files:

        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except:
            continue

        if not isinstance(data, list):
            continue

        filename = path.name.lower()

        for item in data:

            dt_str = item.get("dateTime")
            val = item.get("value")

            if dt_str is None or val is None:
                continue

            dt = parse_fitbit_date(dt_str)
            if dt is None or dt not in date_set:
                continue

            try:
                val = float(val)
            except:
                continue

            result.setdefault(dt, {
                "sedentary": 0.0,
                "light": 0.0,
                "moderate": 0.0,
                "very": 0.0,
                "mvpa": 0.0,
                "total_active": 0.0,
                "active_pct": 0.0,
                "sedentary_pct": 0.0,
                "mvpa_pct": 0.0,
            })

            if "sedentary" in filename:
                result[dt]["sedentary"] = val

            elif "lightly" in filename:
                result[dt]["light"] = val

            elif "moderately" in filename or "fairly" in filename:
                result[dt]["moderate"] = val

            elif "very" in filename:
                result[dt]["very"] = val


    for dt, vals in result.items():

        vals["mvpa"] = vals["moderate"] + vals["very"]
        vals["total_active"] = vals["light"] + vals["moderate"] + vals["very"]

        total_day = vals["sedentary"] + vals["total_active"]

        if total_day > 0:
            vals["active_pct"] = 100 * vals["total_active"] / total_day
            vals["sedentary_pct"] = 100 * vals["sedentary"] / total_day
            vals["mvpa_pct"] = 100 * vals["mvpa"] / total_day

    return result
