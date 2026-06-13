"""
steps_distance.py – daily Steps & Distance (Fitbit / Google exports)

Dla podanego pacjenta i zakresu dat:
- przeszukuje katalogi pacjenta (Gxxxx oraz Gxxxx_google),
- znajduje wszystkie pliki:
    steps-*.json
    distance-*.json
- z każdego pliku czyta wpisy i na podstawie daty w rekordzie
  (lub daty w nazwie pliku) przypisuje kroki / dystans do konkretnej doby,
- sumuje wartości dla każdej doby w zadanym zakresie,
- zapisuje CSV:

    date (dd.mm.yyyy), date_iso, Steps, Distance

Jeśli dla dnia brak danych -> wstawia "N".
"""

from __future__ import annotations

import json
import csv
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any

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


def _parse_iso_dt(s: Optional[str]) -> Optional[datetime]:

    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")


    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass


    try:
        if "+" in s:
            s2 = s.split("+", 1)[0]
            return datetime.fromisoformat(s2)
    except Exception:
        pass


    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _parse_date_from_string(s: str):

    if not s:
        return None
    s = s.strip()


    if "-" in s and s[0:4].isdigit():
        dt = _parse_iso_dt(s)
        if dt is not None:
            return dt.date()

    token = s.split()[0]


    if "-" in token and len(token) == 10:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(token, fmt).date()
            except ValueError:
                continue


    if "/" in token:
        for fmt in ("%m/%d/%y", "%d/%m/%y"):
            try:
                return datetime.strptime(token, fmt).date()
            except ValueError:
                continue

    return None


def _parse_input_date(s: str):

    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Nieprawidłowy format daty: {s}")


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


def _N_if_none(x):
    return "N" if x is None else x


def _parse_datetime_from_string(s: Optional[str]) -> Optional[datetime]:

    if not s:
        return None
    s = str(s).strip()

    if "-" in s and s[0:4].isdigit():
        dt = _parse_iso_dt(s)
        if dt is not None:
            return dt
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue

    for fmt in ("%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%d/%m/%y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    return None


def _merge_daily_max(target: Dict, source: Dict):

    for d, val in source.items():
        if d is None or val is None:
            continue
        current = target.get(d)
        if current is None or float(val) > float(current):
            target[d] = float(val)


def _merge_timestamp_max(target: Dict, source: Dict):

    for ts, val in source.items():
        if ts is None or val is None:
            continue
        current = target.get(ts)
        if current is None or float(val) > float(current):
            target[ts] = float(val)


def _daily_from_timestamps(timestamp_map: Dict) -> Dict:
    out: Dict = {}
    for ts, val in timestamp_map.items():
        if ts is None or val is None:
            continue
        d = ts.date()
        out[d] = out.get(d, 0.0) + float(val)
    return out


def _merge_best_daily_candidate(target: Dict, timestamp_map: Dict):

    grouped: Dict = {}
    for ts, val in timestamp_map.items():
        if ts is None or val is None:
            continue
        d = ts.date()
        info = grouped.setdefault(d, {"count": 0, "sum": 0.0})
        info["count"] += 1
        info["sum"] += float(val)

    for d, info in grouped.items():
        current = target.get(d)
        if current is None:
            target[d] = info
            continue
        if info["count"] > current["count"] or (info["count"] == current["count"] and info["sum"] > current["sum"]):
            target[d] = info


def _normalize_distance_minute_value(val: Optional[float]) -> Optional[float]:

    if val is None:
        return None
    if float(val) > 50.0:
        return float(val) / 100.0
    return float(val)


def _extract_step_timestamps(obj: Any, fallback_date) -> Dict:

    result: Dict = {}

    if isinstance(obj, list):
        for rec in obj:
            if not isinstance(rec, dict):
                continue
            ts = _parse_datetime_from_string(rec.get("dateTime") or rec.get("timestamp") or rec.get("datetime"))
            if ts is None:
                continue
            val = _to_float_safe(rec.get("value") or rec.get("steps"))
            if val is not None:
                result[ts] = max(result.get(ts, float("-inf")), float(val))
        return result

    if not isinstance(obj, dict):
        return result

    intraday = obj.get("activities-steps-intraday")
    if isinstance(intraday, dict) and isinstance(intraday.get("dataset"), list) and fallback_date is not None:
        for rec in intraday["dataset"]:
            if not isinstance(rec, dict):
                continue
            time_str = str(rec.get("time") or "").strip()
            if not time_str:
                continue
            try:
                ts = datetime.strptime(f"{fallback_date.isoformat()} {time_str}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            val = _to_float_safe(rec.get("value"))
            if val is not None:
                result[ts] = max(result.get(ts, float("-inf")), float(val))

    if isinstance(obj.get("data"), list):
        for rec in obj["data"]:
            if not isinstance(rec, dict):
                continue
            ts = _parse_iso_dt(rec.get("startTime") or rec.get("start_time"))
            if ts is None:
                continue
            val_field = rec.get("value")
            values = val_field if isinstance(val_field, list) else [val_field]
            for vobj in values:
                if isinstance(vobj, dict) and "intVal" in vobj:
                    val = _to_float_safe(vobj.get("intVal"))
                else:
                    val = _to_float_safe(vobj)
                if val is not None:
                    result[ts] = max(result.get(ts, float("-inf")), float(val))
    return result


def _extract_distance_timestamps(obj: Any, fallback_date) -> Dict:

    result: Dict = {}

    if isinstance(obj, list):
        for rec in obj:
            if not isinstance(rec, dict):
                continue
            ts = _parse_datetime_from_string(rec.get("dateTime") or rec.get("timestamp") or rec.get("datetime"))
            if ts is None:
                continue
            val = _normalize_distance_minute_value(_to_float_safe(rec.get("value") or rec.get("distance")))
            if val is not None:
                result[ts] = max(result.get(ts, float("-inf")), float(val))
        return result

    if not isinstance(obj, dict):
        return result

    intraday = obj.get("activities-distance-intraday")
    if isinstance(intraday, dict) and isinstance(intraday.get("dataset"), list) and fallback_date is not None:
        for rec in intraday["dataset"]:
            if not isinstance(rec, dict):
                continue
            time_str = str(rec.get("time") or "").strip()
            if not time_str:
                continue
            try:
                ts = datetime.strptime(f"{fallback_date.isoformat()} {time_str}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            val = _normalize_distance_minute_value(_to_float_safe(rec.get("value")))
            if val is not None:
                result[ts] = max(result.get(ts, float("-inf")), float(val))

    if isinstance(obj.get("data"), list):
        for rec in obj["data"]:
            if not isinstance(rec, dict):
                continue
            ts = _parse_iso_dt(rec.get("startTime") or rec.get("start_time"))
            if ts is None:
                continue
            val_field = rec.get("value")
            values = val_field if isinstance(val_field, list) else [val_field]
            for vobj in values:
                if isinstance(vobj, dict) and "fpVal" in vobj:
                    val = _to_float_safe(vobj.get("fpVal"))
                else:
                    val = _to_float_safe(vobj)
                if val is not None:
                    result[ts] = max(result.get(ts, float("-inf")), float(val))
    return result






def _add_steps_record(date_map: Dict, d, val):

    if d is None or val is None:
        return
    date_map[d] = date_map.get(d, 0.0) + float(val)


def _parse_steps_from_json_obj(obj: Any, fallback_date, date_map: Dict):


    if isinstance(obj, list):
        for rec in obj:
            if not isinstance(rec, dict):
                continue
            date_str = rec.get("dateTime") or rec.get("date")
            dt = None
            if isinstance(date_str, str):
                dt = _parse_date_from_string(date_str)
            if dt is None:
                dt = fallback_date

            val = rec.get("value") or rec.get("steps")
            val_f = _to_float_safe(val)
            _add_steps_record(date_map, dt, val_f)
        return


    if not isinstance(obj, dict):
        return

    intraday = obj.get("activities-steps-intraday")
    used_intraday_total = False
    if isinstance(intraday, dict) and isinstance(intraday.get("dataset"), list):
        total = 0.0
        has_values = False
        for rec in intraday["dataset"]:
            if not isinstance(rec, dict):
                continue
            v = _to_float_safe(rec.get("value"))
            if v is not None:
                total += v
                has_values = True
        if has_values:
            _add_steps_record(date_map, fallback_date, total)
            used_intraday_total = True




    if not used_intraday_total and isinstance(obj.get("activities-steps"), list):
        _parse_steps_from_json_obj(obj["activities-steps"], fallback_date, date_map)


    if isinstance(obj.get("data"), list):
        for rec in obj["data"]:
            if not isinstance(rec, dict):
                continue
            d = None
            st = rec.get("startTime") or rec.get("start_time")
            if isinstance(st, str):
                dt = _parse_iso_dt(st)
                if dt is not None:
                    d = dt.date()
            if d is None:
                d = fallback_date

            val_field = rec.get("value")
            if isinstance(val_field, list):
                for vobj in val_field:
                    if not isinstance(vobj, dict):
                        continue
                    if "intVal" in vobj:
                        val = _to_float_safe(vobj.get("intVal"))
                        _add_steps_record(date_map, d, val)
            else:
                val = _to_float_safe(val_field)
                _add_steps_record(date_map, d, val)


def collect_steps_by_date(root: Path, patient_id: str) -> Dict:

    steps_by_date: Dict = {}
    minute_candidates: Dict = {}

    for base in [root / patient_id, root / f"{patient_id}_google"]:
        if not base.exists():
            continue

        for p in iter_allowed_fitbit_files(base, "steps-*.json"):
            fallback_date = extract_date_from_name(p.name)
            try:
                with p.open(encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            timestamp_values = _extract_step_timestamps(data, fallback_date)
            if timestamp_values:
                _merge_best_daily_candidate(minute_candidates, timestamp_values)
                continue

            file_daily: Dict = {}
            _parse_steps_from_json_obj(data, fallback_date, file_daily)
            _merge_daily_max(steps_by_date, file_daily)

    for d, info in minute_candidates.items():
        steps_by_date[d] = float(info["sum"])
    return steps_by_date






def _add_distance_record(date_map: Dict, d, val):

    if d is None or val is None:
        return
    date_map[d] = date_map.get(d, 0.0) + float(val)


def _parse_distance_from_json_obj(obj: Any, fallback_date, date_map: Dict):

    if isinstance(obj, list):
        for rec in obj:
            if not isinstance(rec, dict):
                continue
            date_str = rec.get("dateTime") or rec.get("date")
            dt = None
            if isinstance(date_str, str):
                dt = _parse_date_from_string(date_str)
            if dt is None:
                dt = fallback_date

            val = rec.get("value") or rec.get("distance")
            val_f = _to_float_safe(val)
            _add_distance_record(date_map, dt, val_f)
        return

    if not isinstance(obj, dict):
        return

    intraday = obj.get("activities-distance-intraday")
    used_intraday_total = False
    if isinstance(intraday, dict) and isinstance(intraday.get("dataset"), list):
        total = 0.0
        has_values = False
        for rec in intraday["dataset"]:
            if not isinstance(rec, dict):
                continue
            v = _to_float_safe(rec.get("value"))
            if v is not None:
                total += v
                has_values = True
        if has_values:
            _add_distance_record(date_map, fallback_date, total)
            used_intraday_total = True



    if not used_intraday_total and isinstance(obj.get("activities-distance"), list):
        _parse_distance_from_json_obj(obj["activities-distance"], fallback_date, date_map)

    if isinstance(obj.get("data"), list):
        for rec in obj["data"]:
            if not isinstance(rec, dict):
                continue
            d = None
            st = rec.get("startTime") or rec.get("start_time")
            if isinstance(st, str):
                dt = _parse_iso_dt(st)
                if dt is not None:
                    d = dt.date()
            if d is None:
                d = fallback_date

            val_field = rec.get("value")
            if isinstance(val_field, list):
                for vobj in val_field:
                    if not isinstance(vobj, dict):
                        continue
                    if "fpVal" in vobj:
                        val = _to_float_safe(vobj.get("fpVal"))
                        _add_distance_record(date_map, d, val)
            else:
                val = _to_float_safe(val_field)
                _add_distance_record(date_map, d, val)


def collect_distance_by_date(root: Path, patient_id: str) -> Dict:

    dist_by_date: Dict = {}
    minute_candidates: Dict = {}

    for base in [root / patient_id, root / f"{patient_id}_google"]:
        if not base.exists():
            continue

        for p in iter_allowed_fitbit_files(base, "distance-*.json"):
            fallback_date = extract_date_from_name(p.name)
            try:
                with p.open(encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            timestamp_values = _extract_distance_timestamps(data, fallback_date)
            if timestamp_values:
                _merge_best_daily_candidate(minute_candidates, timestamp_values)
                continue

            file_daily: Dict = {}
            _parse_distance_from_json_obj(data, fallback_date, file_daily)
            _merge_daily_max(dist_by_date, file_daily)

    for d, info in minute_candidates.items():
        dist_by_date[d] = float(info["sum"])
    return dist_by_date






def main():
    default_root = Path(r"C:\Users\UMB\Desktop\FitBit Data download")

    print("=== Steps & Distance – MULTI-DAY ===")
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

    df_str = input("Data od (YYYY-MM-DD lub DD.MM.YYYY): ").strip()
    dt_str = input("Data do (YYYY-MM-DD lub DD.MM.YYYY): ").strip()

    try:
        date_from = _parse_input_date(df_str)
        date_to = _parse_input_date(dt_str)
    except ValueError:
        print("[ERROR] Daty muszą być w formacie YYYY-MM-DD lub DD.MM.YYYY.")
        return

    if date_to < date_from:
        print("[ERROR] Data DO nie może być wcześniejsza niż data OD.")
        return

    print("[INFO] Zbieram kroki...")
    steps_by_date = collect_steps_by_date(root, pid)
    print("[INFO] Zbieram dystans...")
    dist_by_date = collect_distance_by_date(root, pid)

    rows = []
    current = date_from

    while current <= date_to:
        steps = steps_by_date.get(current)
        dist = dist_by_date.get(current)

        if isinstance(steps, (int, float)):
            steps_out = int(round(steps))
        else:
            steps_out = None

        if isinstance(dist, (int, float)):
            dist_out = round(dist, 3)
        else:
            dist_out = None

        date_iso = current.isoformat()
        date_pl = current.strftime("%d.%m.%Y")

        row = {
            "date": date_pl,
            "date_iso": date_iso,
            "Steps": _N_if_none(steps_out),
            "Distance": _N_if_none(dist_out),
        }
        rows.append(row)
        current += timedelta(days=1)

    out_dir = root / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"Steps_Distance_daily_{pid}_{date_from.isoformat()}_to_{date_to.isoformat()}.csv"

    fieldnames = ["date", "date_iso", "Steps", "Distance"]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[OK] Zapisano wyniki do pliku: {out_path}")


if __name__ == "__main__":
    main()
