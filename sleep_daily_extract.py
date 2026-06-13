"""
sleep.py – Sleep episodes summary (Fitbit exports)

Dla podanego pacjenta i zakresu dat:
- znajduje wszystkie pliki "sleep-*.json" w katalogach pacjenta,
- z każdego pliku odczytuje logi snu,
- dla logów, których data snu (dateOfSleep albo data początku) mieści się w podanym zakresie,
  liczy i zapisuje do CSV:

    Start Time
    End Time
    Minutes Asleep
    Minutes Awake
    Number of Awakenings
    Time in Bed
    Minutes REM Sleep
    Minutes Light Sleep
    Minutes Deep Sleep

Każdy epizod snu = jeden wiersz (czyli uwzględnia też drzemki).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

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


def _fmt_dt_for_output(dt: Optional[datetime]) -> str:

    if dt is None:
        return ""
    return dt.strftime("%d-%m-%Y %I:%M %p").lower()


def normalize_patient_id(raw: str) -> str:
    raw = raw.strip().upper()
    if not raw:
        raise ValueError("Brak numeru pacjenta.")
    if raw.startswith("G"):
        return raw
    return f"G{raw}"


def _get_sleep_logs_from_data(data) -> List[dict]:

    if isinstance(data, dict):
        if isinstance(data.get("sleep"), list):
            return [x for x in data["sleep"] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _get_log_date(lg: dict):

    dos = lg.get("dateOfSleep") or lg.get("date_of_sleep")
    if isinstance(dos, str):
        try:
            return datetime.strptime(dos[:10], "%Y-%m-%d").date()
        except ValueError:
            pass

    start_str = (
        lg.get("startTime")
        or lg.get("bedtime")
        or lg.get("start")
        or (lg.get("levels") or {}).get("start")
    )
    start_dt = _parse_iso_dt(start_str)
    if start_dt is not None:
        return start_dt.date()

    return None


def _is_wake_level(level: str) -> bool:
    lv = level.lower()
    return lv in ("wake", "awake", "wakeup", "restless")






def load_all_sleep_logs(root: Path, patient_id: str) -> List[dict]:

    logs: List[dict] = []

    for base in [root / patient_id, root / f"{patient_id}_google"]:
        if not base.exists():
            continue

        for p in iter_allowed_fitbit_files(base, "sleep-*.json"):
            try:
                with p.open(encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            file_logs = _get_sleep_logs_from_data(data)
            logs.extend(file_logs)

    return logs






def compute_sleep_metrics_for_log(log: dict) -> Dict[str, Any]:



    start_str = (
        log.get("startTime")
        or log.get("bedtime")
        or log.get("start")
        or (log.get("levels") or {}).get("start")
    )
    end_str = log.get("endTime") or (log.get("levels") or {}).get("end")

    start_dt = _parse_iso_dt(start_str)
    end_dt = _parse_iso_dt(end_str)


    if end_dt is None and start_dt is not None:
        dur_ms = log.get("duration") or (log.get("levels") or {}).get("duration")
        if isinstance(dur_ms, (int, float)):
            end_dt = start_dt + timedelta(milliseconds=float(dur_ms))


    minutes_asleep = _to_float_safe(log.get("minutesAsleep"))
    minutes_awake_field = _to_float_safe(log.get("minutesAwake"))
    awakenings_count = _to_float_safe(log.get("awakeningsCount"))
    time_in_bed = _to_float_safe(log.get("timeInBed"))

    rem_minutes = None
    light_minutes = None
    deep_minutes = None
    awake_from_levels = 0.0
    awakenings_from_levels: Optional[float] = None

    levels = log.get("levels")


    if isinstance(levels, dict) and isinstance(levels.get("summary"), dict):
        summary = levels["summary"]

        def _get_min(stage):
            s = summary.get(stage) or {}
            return _to_float_safe(s.get("minutes"))

        def _get_count(stage):
            s = summary.get(stage) or {}
            return _to_float_safe(s.get("count"))

        rem_minutes = _get_min("rem")
        light_minutes = _get_min("light")
        deep_minutes = _get_min("deep")
        awake_from_levels_val = _get_min("wake")
        if awake_from_levels_val is not None:
            awake_from_levels = awake_from_levels_val
        awakenings_from_levels = _get_count("wake")


    if rem_minutes is None or light_minutes is None or deep_minutes is None:
        rem = 0.0 if rem_minutes is None else rem_minutes
        light = 0.0 if light_minutes is None else light_minutes
        deep = 0.0 if deep_minutes is None else deep_minutes
        awake_extra = 0.0

        data_list = []
        if isinstance(levels, dict):
            if isinstance(levels.get("data"), list):
                data_list = levels["data"]
        elif isinstance(levels, list):
            data_list = levels

        prev_is_wake = False
        aw_count_est = 0

        for sample in data_list:
            if not isinstance(sample, dict):
                continue

            level = sample.get("level") or sample.get("stage") or sample.get("sleepLevel")
            if level is None:
                continue

            seconds = sample.get("seconds")
            if seconds is None:
                dur_ms = sample.get("duration")
                if isinstance(dur_ms, (int, float)):
                    seconds = float(dur_ms) / 1000.0
            if seconds is None:
                continue

            minutes = float(seconds) / 60.0

            if isinstance(level, str):
                lv = level.lower()
                is_wake = _is_wake_level(lv)
                if lv in ("rem",):
                    rem += minutes
                elif lv in ("light", "l0"):
                    light += minutes
                elif lv in ("deep", "l3"):
                    deep += minutes
                elif is_wake:
                    awake_extra += minutes
                else:

                    light += minutes
            else:

                is_wake = False
                if level == 0:
                    light += minutes
                elif level == 1:
                    light += minutes
                elif level == 2:
                    deep += minutes
                elif level == 3:
                    deep += minutes


            if isinstance(level, str):
                is_w = _is_wake_level(level)
            else:
                is_w = False
            if is_w and not prev_is_wake:
                aw_count_est += 1
            prev_is_wake = is_w

        if rem_minutes is None:
            rem_minutes = rem
        if light_minutes is None:
            light_minutes = light
        if deep_minutes is None:
            deep_minutes = deep
        awake_from_levels += awake_extra
        if awakenings_from_levels is None and aw_count_est > 0:
            awakenings_from_levels = aw_count_est


    if minutes_asleep is None and any(x is not None for x in (rem_minutes, light_minutes, deep_minutes)):
        minutes_asleep = 0.0
        for v in (rem_minutes, light_minutes, deep_minutes):
            if v is not None:
                minutes_asleep += v


    if minutes_awake_field is None:
        minutes_awake = awake_from_levels
    else:
        minutes_awake = minutes_awake_field


    if awakenings_count is None:
        awakenings_count = awakenings_from_levels if awakenings_from_levels is not None else 0.0


    if time_in_bed is None:
        dur_ms = log.get("duration") or (levels or {}).get("duration")
        if isinstance(dur_ms, (int, float)):
            time_in_bed = float(dur_ms) / 60000.0
        elif minutes_asleep is not None or minutes_awake is not None:
            time_in_bed = (minutes_asleep or 0.0) + (minutes_awake or 0.0)

    return {
        "start_dt": start_dt,
        "end_dt": end_dt,
        "minutes_asleep": minutes_asleep,
        "minutes_awake": minutes_awake,
        "awakenings": awakenings_count,
        "time_in_bed": time_in_bed,
        "rem_minutes": rem_minutes,
        "light_minutes": light_minutes,
        "deep_minutes": deep_minutes,
    }






def main():
    default_root = Path(r"C:\Users\UMB\Desktop\FitBit Data download")

    print("=== Sleep episodes summary – MULTI-DAY ===")
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

    print("[INFO] Wczytuję wszystkie logi snu...")
    all_logs = load_all_sleep_logs(root, pid)

    if not all_logs:
        print("[WARN] Nie znaleziono żadnych logów snu dla tego pacjenta.")
        return


    selected_metrics: List[Dict[str, Any]] = []

    for lg in all_logs:
        d = _get_log_date(lg)
        if d is None:
            continue
        if not (date_from <= d <= date_to):
            continue

        m = compute_sleep_metrics_for_log(lg)
        if m["start_dt"] is None:
            continue
        selected_metrics.append(m)

    if not selected_metrics:
        print("[WARN] W podanym zakresie dat nie znaleziono żadnych epizodów snu.")
        return


    selected_metrics.sort(key=lambda x: x["start_dt"])


    rows: List[Dict[str, Any]] = []

    for m in selected_metrics:
        start_str = _fmt_dt_for_output(m["start_dt"])
        end_str = _fmt_dt_for_output(m["end_dt"])

        def _round_or_empty(val):
            return int(round(val)) if isinstance(val, (int, float)) else ""

        minutes_asleep = _round_or_empty(m["minutes_asleep"])
        minutes_awake = _round_or_empty(m["minutes_awake"])
        awakenings = _round_or_empty(m["awakenings"])
        time_in_bed = _round_or_empty(m["time_in_bed"])

        rem = m["rem_minutes"]
        light = m["light_minutes"]
        deep = m["deep_minutes"]

        if (rem is None and light is None and deep is None) or (
            (rem or 0) == 0 and (light or 0) == 0 and (deep or 0) == 0
        ):
            rem_out = light_out = deep_out = "N/A"
        else:
            rem_out = _round_or_empty(rem)
            light_out = _round_or_empty(light)
            deep_out = _round_or_empty(deep)

        row = {
            "Start Time": start_str,
            "End Time": end_str,
            "Minutes Asleep": minutes_asleep,
            "Minutes Awake": minutes_awake,
            "Number of Awakenings": awakenings,
            "Time in Bed": time_in_bed,
            "Minutes REM Sleep": rem_out,
            "Minutes Light Sleep": light_out,
            "Minutes Deep Sleep": deep_out,
        }
        rows.append(row)


    out_dir = root / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"Sleep_episodes_{pid}_{df_str}_to_{dt_str}.csv"

    fieldnames = [
        "Start Time",
        "End Time",
        "Minutes Asleep",
        "Minutes Awake",
        "Number of Awakenings",
        "Time in Bed",
        "Minutes REM Sleep",
        "Minutes Light Sleep",
        "Minutes Deep Sleep",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[OK] Zapisano wyniki do pliku: {out_path}")


if __name__ == "__main__":
    main()
