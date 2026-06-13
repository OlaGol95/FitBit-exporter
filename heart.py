"""
heart.py – HR & SpO2 metrics for multiple days (Fitbit exports)

Dla podanego pacjenta i zakresu dat:
- szuka plików "Minute SpO2 - YYYY-MM-DD.csv" w katalogach pacjenta,
- szuka plików "heart_rate-YYYY-MM-DD.json" w katalogach pacjenta,
- dla każdej doby w zakresie liczy:
    HR average, HR min, HR max, HR SD,
    Minute SpO2 AV, Minute SpO2 var
- zapisuje wszystko do jednego pliku CSV gotowego do Excela.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from fitbit_source_paths import iter_allowed_fitbit_files






def _to_float_safe(x):

    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x.replace(",", "."))
        except ValueError:
            return None
    return None


def _extract_hr_from_dict(d):

    if not isinstance(d, dict):
        return None


    for key in ("hr", "bpm"):
        if key in d:
            v = _to_float_safe(d[key])
            if v is not None:
                return v


    if "value" in d:
        v = d["value"]


        num = _to_float_safe(v)
        if num is not None:
            return num


        if isinstance(v, dict):
            for key in ("bpm", "hr", "fpVal"):
                if key in v:
                    num = _to_float_safe(v[key])
                    if num is not None:
                        return num


        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    for key in ("bpm", "hr", "fpVal"):
                        if key in item:
                            num = _to_float_safe(item[key])
                            if num is not None:
                                return num

    return None






def load_hr_values_from_json(path: Path) -> np.ndarray:

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    raw_values = []


    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                v = _extract_hr_from_dict(item)
                if v is not None:
                    raw_values.append(v)
            else:
                num = _to_float_safe(item)
                if num is not None:
                    raw_values.append(num)


    elif isinstance(data, dict):

        intraday = (
            data.get("activities-heart-intraday")
            or data.get("activities-heart", {}).get("intraday")
        )
        if isinstance(intraday, dict) and "dataset" in intraday:
            dataset = intraday["dataset"]
            if isinstance(dataset, list):
                for item in dataset:
                    if isinstance(item, dict):
                        v = _extract_hr_from_dict(item)
                        if v is not None:
                            raw_values.append(v)


        if not raw_values and isinstance(data.get("data"), list):
            for rec in data["data"]:
                if not isinstance(rec, dict):
                    continue
                v = rec.get("value")
                if isinstance(v, list):
                    for sub in v:
                        if isinstance(sub, dict):
                            num = None
                            if "fpVal" in sub:
                                num = _to_float_safe(sub["fpVal"])
                            elif "bpm" in sub:
                                num = _to_float_safe(sub["bpm"])
                            if num is not None:
                                raw_values.append(num)
                else:
                    num = _to_float_safe(v)
                    if num is not None:
                        raw_values.append(num)


    values = []
    for v in raw_values:
        num = _to_float_safe(v)
        if num is not None:
            values.append(num)

    if not values:
        return np.array([], dtype=float)

    return np.array(values, dtype=float)






def load_spo2_values_from_csv(path: Path, value_column: Optional[str] = None) -> np.ndarray:

    values = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if value_column is None:

            for row in reader:
                for col, val in row.items():
                    if val is None or val == "":
                        continue
                    try:
                        float(str(val).replace(",", "."))
                        value_column = col
                        break
                    except ValueError:
                        continue
                if value_column is not None:
                    first_val = row.get(value_column)
                    if first_val not in (None, ""):
                        try:
                            values.append(float(str(first_val).replace(",", ".")))
                        except ValueError:
                            pass
                    break

            if value_column is None:
                return np.array([], dtype=float)

            for row in reader:
                val = row.get(value_column)
                if val in (None, ""):
                    continue
                try:
                    values.append(float(str(val).replace(",", ".")))
                except ValueError:
                    continue
        else:
            for row in reader:
                val = row.get(value_column)
                if val in (None, ""):
                    continue
                try:
                    values.append(float(str(val).replace(",", ".")))
                except ValueError:
                    continue

    if not values:
        return np.array([], dtype=float)

    return np.array(values, dtype=float)






def compute_hr_stats(hr_array: np.ndarray) -> Dict[str, Optional[float]]:
    if hr_array.size == 0:
        return {
            "HR average": None,
            "HR min": None,
            "HR max": None,
            "HR SD": None,
        }
    return {
        "HR average": float(np.nanmean(hr_array)),
        "HR min": float(np.nanmin(hr_array)),
        "HR max": float(np.nanmax(hr_array)),
        "HR SD": float(np.nanstd(hr_array, ddof=1)),
    }


def compute_spo2_stats(spo2_array: np.ndarray) -> Dict[str, Optional[float]]:
    if spo2_array.size == 0:
        return {
            "Minute SpO2 AV": None,
            "Minute SpO2 var": None,
        }
    return {
        "Minute SpO2 AV": float(np.nanmean(spo2_array)),
        "Minute SpO2 var": float(np.nanvar(spo2_array, ddof=1)),
    }






def normalize_patient_id(raw: str) -> str:
    raw = raw.strip().upper()
    if not raw:
        raise ValueError("Brak numeru pacjenta.")
    if raw.startswith("G"):
        return raw
    return f"G{raw}"


_date_re = re.compile(r"\d{4}-\d{2}-\d{2}")


def extract_date_from_name(name: str):

    m = _date_re.search(name)
    if not m:
        return None
    s = m.group(0)
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def collect_hr_files_by_date(root: Path, patient_id: str) -> Dict[datetime.date, List[Path]]:

    files_by_date: Dict[datetime.date, List[Path]] = {}

    for base in [root / patient_id, root / f"{patient_id}_google"]:
        if not base.exists():
            continue
        for p in iter_allowed_fitbit_files(base, "heart_rate-*.json"):
            d = extract_date_from_name(p.name)
            if d is None:
                continue
            files_by_date.setdefault(d, []).append(p)

    return files_by_date


def collect_spo2_files_by_date(root: Path, patient_id: str) -> Dict[datetime.date, Path]:

    files_by_date: Dict[datetime.date, Path] = {}

    for base in [root / patient_id, root / f"{patient_id}_google"]:
        if not base.exists():
            continue
        for p in iter_allowed_fitbit_files(base, "Minute SpO2 - *.csv"):
            d = extract_date_from_name(p.name)
            if d is None:
                continue
            files_by_date[d] = p

    return files_by_date






def _N_if_none(x):

    return "N" if x is None else x


def main():
    default_root = Path(r"C:\Users\UMB\Desktop\FitBit Data download")

    print("=== HR & SpO2 metrics – MULTI-DAY ===")
    root_in = input(f"Podaj katalog ROOT (Enter = domyślny: {default_root}): ").strip()
    root = Path(root_in) if root_in else default_root

    if not root.is_dir():
        print(f"[ERROR] Katalog ROOT nie istnieje: {root}")
        return

    pid_raw = input("Podaj numer pacjenta (np. G0039 lub 0039): ").strip()
    try:
        pid = normalize_patient_id(pid_raw)
    except ValueError as e:
        print(f"[ERROR] {e}")
        return

    df_str = input("Data od (YYYY-MM-DD): ").strip()
    dt_str = input("Data do (YYYY-MM-DD): ").strip()

    try:
        date_from = datetime.strptime(df_str, "%Y-%m-%d").date()
        date_to = datetime.strptime(dt_str, "%Y-%m-%d").date()
    except ValueError:
        print("[ERROR] Daty muszą być w formacie YYYY-MM-DD.")
        return

    if date_to < date_from:
        print("[ERROR] Data DO nie może być wcześniejsza niż data OD.")
        return

    print("[INFO] Szukam plików HR i SpO2...")
    hr_files = collect_hr_files_by_date(root, pid)
    spo2_files = collect_spo2_files_by_date(root, pid)

    if not hr_files and not spo2_files:
        print("[WARN] Nie znaleziono żadnych plików HR ani SpO2 dla tego pacjenta.")
        return

    rows = []
    current = date_from

    while current <= date_to:
        hr_paths = hr_files.get(current, [])
        spo2_path = spo2_files.get(current)

        if not hr_paths and not spo2_path:

            current += timedelta(days=1)
            continue

        print(f"[INFO] Przetwarzam dzień: {current.isoformat()}")


        hr_arrays = []
        for p in hr_paths:
            arr = load_hr_values_from_json(p)
            if arr.size:
                hr_arrays.append(arr)

        if hr_arrays:
            hr_all = np.concatenate(hr_arrays)
        else:
            hr_all = np.array([], dtype=float)


        if spo2_path:
            spo2_array = load_spo2_values_from_csv(spo2_path)
        else:
            spo2_array = np.array([], dtype=float)

        metrics = {}
        metrics.update(compute_hr_stats(hr_all))
        metrics.update(compute_spo2_stats(spo2_array))

        row = {
            "date": current.isoformat(),
            "HR average": metrics["HR average"],
            "HR min": metrics["HR min"],
            "HR max": metrics["HR max"],
            "HR SD": metrics["HR SD"],

            "Minute SpO2 AV": _N_if_none(metrics["Minute SpO2 AV"]),
            "Minute SpO2 var": _N_if_none(metrics["Minute SpO2 var"]),
        }
        rows.append(row)

        current += timedelta(days=1)

    if not rows:
        print("[WARN] W podanym zakresie dat nie znaleziono żadnych danych.")
        return


    out_dir = root / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"HR_SpO2_daily_{pid}_{df_str}_to_{dt_str}.csv"

    fieldnames = [
        "date",
        "HR average",
        "HR min",
        "HR max",
        "HR SD",
        "Minute SpO2 AV",
        "Minute SpO2 var",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[OK] Zapisano wyniki do pliku: {out_path}")


if __name__ == "__main__":
    main()
