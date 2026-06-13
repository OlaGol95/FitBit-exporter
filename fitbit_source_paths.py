from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional


ALLOWED_TOP_LEVEL_DIRS = {
    "Application",
    "Biometrics",
    "Fitbit Care",
    "Google Data",
    "Global Export Data",
    "Heart",
    "Menstrual Health",
    "Other",
    "Personal & Account",
    "Physical Activity",
    "Programs",
    "Sleep",
    "Social",
    "Stress",
    "TIMESERIES_GoogleData",
}


def allowed_dir_count(root: Path) -> int:
    try:
        return sum(1 for child in root.iterdir() if child.is_dir() and child.name in ALLOWED_TOP_LEVEL_DIRS)
    except OSError:
        return 0


def resolve_fitbit_content_root(base: Path) -> Optional[Path]:

    if not base.exists():
        return None

    top_count = allowed_dir_count(base)
    if top_count:
        return base

    best_root = None
    best_count = 0
    try:
        for child in base.iterdir():
            if not child.is_dir():
                continue
            count = allowed_dir_count(child)
            if count > best_count:
                best_root = child
                best_count = count
    except OSError:
        return None

    return best_root if best_count else None


def iter_allowed_fitbit_files(base: Path, pattern: str) -> Iterable[Path]:
    content_root = resolve_fitbit_content_root(base)
    if content_root is None:
        return []

    results = []
    seen = set()
    for dirname in sorted(ALLOWED_TOP_LEVEL_DIRS):
        source_dir = content_root / dirname
        if not source_dir.exists():
            continue
        for path in source_dir.rglob(pattern):
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(path)
    return results
