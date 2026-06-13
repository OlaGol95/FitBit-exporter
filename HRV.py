"""
hrv.py – daily HRV summary from Fitbit/Google exports

Dla podanego pacjenta i zakresu dat:
- przeszukuje katalogi pacjenta (Gxxxx oraz Gxxxx_google),
- znajduje wszystkie pliki CSV, których nazwa zawiera:
    "Daily Heart Rate Variability Summary"
- z każdego pliku odczytuje wiersze i przypisuje je do dnia na podstawie timestampu,
- dla każdej daty z zakresu zapisuje do CSV wiersz:

    timestamp, rmssd, nremhr, entropy

timestamp = YYYY-MM-DDT00:00:00

Jeśli brak danych dla dnia -> rmssd, nremhr, entropy = "N".
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, Optional, Any

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






def _find_hrv_columns(fieldnames):

    ts_col = rmssd_col = nremhr_col = entropy_col = None

    for name in fieldnames:
        if name is None:
            continue
        key = name.strip().lower().replace(" ", "").replace("_", "")

        if ts_col is None and ("timestamp" in key or ("date" in key and "time" in key)):
            ts_col = name
        elif rmssd_col is None and "rmssd" in key:
            rmssd_col = name
        elif nremhr_col is None and ("nremhr" in key or "hrnrem" in key):
            nremhr_col = name
        elif entropy_col is None and "entropy" in key:
            entropy_col = name

    return ts_col, rmssd_col, nremhr_col, entropy_col


def collect_hrv_by_date(root: Path, patient_id: str) -> Dict[date, Dict[str, Any]]:

    hrv_by_date: Dict[date, Dict[str, Any]] = {}

    for base in [root / patient_id, root / f"{patient_id}_google"]:
        if not base.exists():
            continue


        for p in iter_allowed_fitbit_files(base, "*.csv"):
            name_low = p.name.lower()
            if "daily heart rate variability summary" not in name_low:
                continue

            try:
                with p.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    ts_col, rmssd_col, nremhr_col, entropy_col = _find_hrv_columns(reader.fieldnames or [])
                    if not ts_col:

                        continue

                    for row in reader:
                        ts = (row.get(ts_col) or "").strip()
                        d = _parse_timestamp_to_date(ts)
                        if d is None:
                            continue

                        rmssd = _to_float_safe(row.get(rmssd_col)) if rmssd_col else None
                        nremhr = _to_float_safe(row.get(nremhr_col)) if nremhr_col else None
                        entropy = _to_float_safe(row.get(entropy_col)) if entropy_col else None


                        hrv_by_date[d] = {
                            "rmssd": rmssd,
                            "nremhr": nremhr,
                            "entropy": entropy,
                        }

            except Exception:

                continue

    return hrv_by_date






def main():
    default_root = Path(r"C:\Users\UMB\Desktop\FitBit Data download")

    print("=== HRV daily summary – MULTI-DAY ===")
    root_in = input(f"Podaj katalog ROOT (Enter = domyślny: {default_root}): ").strip()
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

    print("[INFO] Szukam plików HRV i buduję mapę dat...")
    hrv_by_date = collect_hrv_by_date(root, pid)

    rows = []
    current = date_from

    while current <= date_to:
        info = hrv_by_date.get(current, {})
        rmssd = info.get("rmssd")
        nremhr = info.get("nremhr")
        entropy = info.get("entropy")

        timestamp = f"{current.isoformat()}T00:00:00"

        row = {
            "timestamp": timestamp,
            "rmssd": _N_if_none(round(rmssd, 3) if isinstance(rmssd, (int, float)) else None),
            "nremhr": _N_if_none(round(nremhr, 3) if isinstance(nremhr, (int, float)) else None),
            "entropy": _N_if_none(round(entropy, 3) if isinstance(entropy, (int, float)) else None),
        }
        rows.append(row)
        current += timedelta(days=1)

    out_dir = root / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"HRV_daily_{pid}_{date_from.isoformat()}_to_{date_to.isoformat()}.csv"

    fieldnames = ["timestamp", "rmssd", "nremhr", "entropy"]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[OK] Zapisano wyniki do pliku: {out_path}")


if __name__ == "__main__":
    main()
