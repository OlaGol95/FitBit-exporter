"""
sleep_score_resting_hr.py – dzienne resting_heart_rate z plików typu *sleep*score*.csv

Dla podanego pacjenta i zakresu dat:
- przeszukuje katalogi pacjenta (Gxxxx oraz Gxxxx_google),
- znajduje pliki CSV, których nazwa zawiera "sleep" i "score" (np.
  'Sleep Score\\sleep_score.csv'),
- z każdego wiersza odczytuje:
    timestamp, resting_heart_rate
- przypisuje resting_heart_rate do daty (na podstawie timestampu),
- zapisuje CSV:

    timestamp, resting_heart_rate

timestamp = YYYY-MM-DDT00:00:00

Jeśli brak danych (brak pliku lub brak wpisu dla dnia) -> resting_heart_rate = "N".
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, Any, Optional

from fitbit_source_paths import iter_allowed_fitbit_files




def _to_float_safe(x):

    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        x = x.strip()
        if not x:
            return None
        try:
            return float(x.replace(",", "."))
        except ValueError:
            return None
    return None


def normalize_patient_id(raw: str) -> str:
    raw = raw.strip().upper()
    if not raw:
        raise ValueError("Brak numeru pacjenta.")
    if raw.startswith("G"):
        return raw
    return f"G{raw}"


def _parse_input_date(s: str) -> date:

    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Nieprawidłowy format daty: {s}")


def _parse_timestamp_to_date(ts: str) -> Optional[date]:

    if not ts:
        return None
    ts = ts.strip().replace("Z", "")


    try:
        return datetime.fromisoformat(ts).date()
    except Exception:
        pass


    try:
        return datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").date()
    except Exception:
        return None


def _N_if_none(x):
    return "N" if x is None else x


def _find_cols(fieldnames):

    ts_col = None
    rhr_col = None
    for name in fieldnames or []:
        if not name:
            continue
        key = name.strip().lower().replace("_", "").replace(" ", "")
        if ts_col is None and "timestamp" in key:
            ts_col = name
        if rhr_col is None and ("restingheartrate" in key or "restingheartrate" in key):
            rhr_col = name
    return ts_col, rhr_col




def collect_resting_hr_by_date(root: Path, pid: str) -> Dict[date, float]:

    result: Dict[date, float] = {}

    for base in [root / pid, root / f"{pid}_google"]:
        if not base.exists():
            continue


        for p in iter_allowed_fitbit_files(base, "*.csv"):
            name_low = p.name.lower()
            if "sleep" not in name_low or "score" not in name_low:
                continue

            try:
                with p.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    ts_col, rhr_col = _find_cols(reader.fieldnames)
                    if not ts_col or not rhr_col:
                        continue

                    for row in reader:
                        ts = (row.get(ts_col) or "").strip()
                        d = _parse_timestamp_to_date(ts)
                        if d is None:
                            continue

                        rhr = _to_float_safe(row.get(rhr_col))
                        if rhr is None:
                            continue

                        result[d] = rhr

            except Exception:

                continue

    return result


def main():
    default_root = Path(r"C:\Users\UMB\Desktop\FitBit Data download")

    print("=== Sleep Score – resting_heart_rate (MULTI-DAY) ===")
    root_in = input(
        f"Podaj katalog ROOT (Enter = domyślny: {default_root}): "
    ).strip()
    root = Path(root_in) if root_in else default_root

    if not root.is_dir():
        print(f"[ERROR] Katalog ROOT nie istnieje: {root}")
        return

    pid_raw = input("Podaj numer pacjenta (np. G0902 lub 0902): ").strip()
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

    print("[INFO] Zbieram resting_heart_rate z plików *sleep*score*.csv...")
    rhr_by_date = collect_resting_hr_by_date(root, pid)

    rows = []
    current = date_from
    while current <= date_to:
        rhr = rhr_by_date.get(current)
        timestamp = f"{current.isoformat()}T00:00:00"
        rows.append(
            {
                "timestamp": timestamp,
                "resting_heart_rate": _N_if_none(
                    round(rhr, 3) if isinstance(rhr, (int, float)) else None
                ),
            }
        )
        current += timedelta(days=1)

    out_dir = root / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"SleepScore_restingHR_{pid}_{date_from.isoformat()}_to_{date_to.isoformat()}.csv"

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "resting_heart_rate"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[OK] Zapisano wyniki do pliku: {out_path}")


if __name__ == "__main__":
    main()
