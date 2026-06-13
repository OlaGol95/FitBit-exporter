from __future__ import annotations

import csv
import math
import shutil
import statistics
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox, ttk
from typing import Any

import pandas as pd

import HRV as hrv_mod
import activity as activity_mod
import heart as heart_mod
import resting_HR as rhr_mod
import sleep_daily_extract as sleep_mod
import steps_distance_etc as steps_mod


SEGMENTS = ("v1", "v3", "v4", "v6")

FIELDNAMES = [
    "patient_id", "segment", "Timestamp",
    "HR average", "HR min", "HR max", "HR SD",
    "Minute SpO2 AV", "Minute SpO2 var",
    "Steps", "Distance",
    "Start Time", "End Time",
    "Minutes Asleep", "Minutes Awake", "Number of Awakenings", "Time in Bed",
    "Minutes REM Sleep", "Minutes Light Sleep", "Minutes Deep Sleep",
    "rmssd", "nremhr", "entropy", "resting_heart_rate",
    "Sedentary", "Light", "Moderate", "Very", "MVPA", "Total Active",
    "Mean_Steps", "SD_Steps", "CV_Steps",
    "Mean_Distance", "Step_Length",
    "Mean_RMSSD", "CV_RMSSD",
    "Mean_Sedentary", "Mean_Light", "Mean_Moderate",
    "Mean_Very", "Mean_MVPA", "Mean_TotalActive",
    "Mean_HR", "SD_HR", "CV_HR",
    "Mean_Resting_HR", "SD_Resting_HR",
    "Mean_HR_Range", "SD_HR_Range",
    "Mean_HR_SD", "SD_HR_SD",
    "Mean_Sleep_Time", "SD_Sleep_Time",
    "Sleep_Efficiency", "SD_Sleep_Efficiency", "Fragmentation_Index",
    "Mean_Deep_Percent", "SD_Deep_Percent",
]


def patient_folder_name(value: str) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("G"):
        text = text[1:]
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        raise ValueError("Nie podano poprawnego numeru pacjenta.")
    return f"G{int(digits):04d}"


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if pd.isna(value):
        raise ValueError("Pusta data.")
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        raise ValueError(f"Nieprawidlowa data: {value}")
    return parsed.date()


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("Data koncowa nie moze byc przed poczatkowa.")
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def normalize_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum())


def first_number(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return str(int(digits)) if digits else ""


def missing_to_n(value: Any) -> Any:
    if value is None:
        return "N"
    if isinstance(value, float) and math.isnan(value):
        return "N"
    return value


def safe_mean(values: list[Any]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float)) and not math.isnan(float(v))]
    return statistics.mean(clean) if clean else None


def safe_sd(values: list[Any]) -> float | None:
    clean = [float(v) for v in values if isinstance(v, (int, float)) and not math.isnan(float(v))]
    if len(clean) <= 1:
        return 0.0
    return statistics.stdev(clean)


def extract_zip(zip_path: Path, target_dir: Path) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(zip_path) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        names = [item.filename.replace("\\", "/").strip("/") for item in members]
        parts_list = [name.split("/") for name in names if name]
        strip_root = bool(parts_list) and len({parts[0] for parts in parts_list}) == 1 and all(len(parts) > 1 for parts in parts_list)
        for item in members:
            name = item.filename.replace("\\", "/").strip("/")
            if not name:
                continue
            parts = [part for part in name.split("/") if part]
            if strip_root and len(parts) > 1:
                parts = parts[1:]
            if not parts:
                continue
            destination = target_dir.joinpath(*parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, destination.open("wb") as handle:
                shutil.copyfileobj(source, handle)
            count += 1
    return count


def collect_hr_spo2(root: Path, patient_id: str, dates: list[date]) -> dict[date, dict[str, Any]]:
    hr_files = heart_mod.collect_hr_files_by_date(root, patient_id)
    spo2_files = heart_mod.collect_spo2_files_by_date(root, patient_id)
    result = {}
    for day in dates:
        hr_arrays = []
        for path in hr_files.get(day, []):
            values = heart_mod.load_hr_values_from_json(path)
            if len(values):
                hr_arrays.append(values)
        if hr_arrays:
            import numpy as np
            hr_stats = heart_mod.compute_hr_stats(np.concatenate(hr_arrays))
        else:
            hr_stats = {"HR average": None, "HR min": None, "HR max": None, "HR SD": None}
        spo2_path = spo2_files.get(day)
        if spo2_path:
            spo2_stats = heart_mod.compute_spo2_stats(heart_mod.load_spo2_values_from_csv(spo2_path))
        else:
            spo2_stats = {"Minute SpO2 AV": None, "Minute SpO2 var": None}
        result[day] = {**hr_stats, **spo2_stats}
    return result


def collect_steps_distance(root: Path, patient_id: str) -> tuple[dict[date, Any], dict[date, Any]]:
    return steps_mod.collect_steps_by_date(root, patient_id), steps_mod.collect_distance_by_date(root, patient_id)


def collect_sleep(root: Path, patient_id: str, dates: list[date]) -> dict[date, dict[str, Any]]:
    logs = sleep_mod.load_all_sleep_logs(root, patient_id)
    wanted = set(dates)
    by_date = {}
    for log in logs:
        log_date = sleep_mod._get_log_date(log)
        if log_date in wanted:
            by_date[log_date] = sleep_mod.compute_sleep_metrics_for_log(log)
    return by_date


def sleep_output(metrics: dict[str, Any] | None) -> dict[str, Any]:
    if not metrics:
        return {}
    start_dt = metrics.get("start_dt")
    end_dt = metrics.get("end_dt")
    fmt = "%d-%m-%Y %I:%M %p"
    return {
        "Start Time": start_dt.strftime(fmt).lower() if start_dt else None,
        "End Time": end_dt.strftime(fmt).lower() if end_dt else None,
        "Minutes Asleep": metrics.get("minutes_asleep"),
        "Minutes Awake": metrics.get("minutes_awake"),
        "Number of Awakenings": metrics.get("awakenings"),
        "Time in Bed": metrics.get("time_in_bed"),
        "Minutes REM Sleep": metrics.get("rem_minutes"),
        "Minutes Light Sleep": metrics.get("light_minutes"),
        "Minutes Deep Sleep": metrics.get("deep_minutes"),
    }


def segment_statistics(ranges, hr_spo2, steps, distance, hrv, resting_hr, sleep, activity):
    output = {}
    for segment, start, end in ranges:
        days = date_range(start, end)
        stats = {}
        hr_vals = [hr_spo2.get(day, {}).get("HR average") for day in days]
        hr_vals = [value for value in hr_vals if isinstance(value, (int, float))]
        mean_hr = safe_mean(hr_vals)
        sd_hr = safe_sd(hr_vals)
        stats["Mean_HR"] = mean_hr
        stats["SD_HR"] = sd_hr
        stats["CV_HR"] = (sd_hr / mean_hr * 100) if mean_hr and sd_hr else None
        rhr_vals = [resting_hr.get(day) for day in days]
        rhr_vals = [value for value in rhr_vals if isinstance(value, (int, float))]
        stats["Mean_Resting_HR"] = safe_mean(rhr_vals)
        stats["SD_Resting_HR"] = safe_sd(rhr_vals)
        hr_range_vals = []
        for day in days:
            item = hr_spo2.get(day, {})
            hr_min = item.get("HR min")
            hr_max = item.get("HR max")
            if isinstance(hr_min, (int, float)) and isinstance(hr_max, (int, float)):
                hr_range_vals.append(hr_max - hr_min)
        stats["Mean_HR_Range"] = safe_mean(hr_range_vals)
        stats["SD_HR_Range"] = safe_sd(hr_range_vals)
        hr_sd_vals = [hr_spo2.get(day, {}).get("HR SD") for day in days]
        hr_sd_vals = [value for value in hr_sd_vals if isinstance(value, (int, float))]
        stats["Mean_HR_SD"] = safe_mean(hr_sd_vals)
        stats["SD_HR_SD"] = safe_sd(hr_sd_vals)
        sleep_time = []
        sleep_efficiency = []
        fragmentation = []
        deep_percent = []
        for day in days:
            item = sleep.get(day)
            if not item:
                continue
            asleep = item.get("minutes_asleep")
            bed = item.get("time_in_bed")
            awakenings = item.get("awakenings")
            deep = item.get("deep_minutes")
            if isinstance(asleep, (int, float)):
                sleep_time.append(asleep)
            if isinstance(asleep, (int, float)) and isinstance(bed, (int, float)) and bed > 0:
                sleep_efficiency.append(asleep / bed)
            if isinstance(awakenings, (int, float)) and isinstance(bed, (int, float)) and bed > 0:
                fragmentation.append(awakenings / bed)
            if isinstance(deep, (int, float)) and isinstance(asleep, (int, float)) and asleep > 0:
                deep_percent.append(deep / asleep)
        stats["Mean_Sleep_Time"] = safe_mean(sleep_time)
        stats["SD_Sleep_Time"] = safe_sd(sleep_time)
        stats["Sleep_Efficiency"] = safe_mean(sleep_efficiency)
        stats["SD_Sleep_Efficiency"] = safe_sd(sleep_efficiency)
        stats["Fragmentation_Index"] = safe_mean(fragmentation)
        stats["Mean_Deep_Percent"] = safe_mean(deep_percent)
        stats["SD_Deep_Percent"] = safe_sd(deep_percent)
        step_vals = [steps.get(day) for day in days]
        step_vals = [value for value in step_vals if isinstance(value, (int, float))]
        mean_steps = safe_mean(step_vals)
        sd_steps = safe_sd(step_vals)
        stats["Mean_Steps"] = mean_steps
        stats["SD_Steps"] = sd_steps
        stats["CV_Steps"] = (sd_steps / mean_steps * 100) if mean_steps and sd_steps else None
        distance_vals = [distance.get(day) for day in days]
        distance_vals = [value for value in distance_vals if isinstance(value, (int, float))]
        stats["Mean_Distance"] = safe_mean(distance_vals)
        stats["Step_Length"] = (stats["Mean_Distance"] / mean_steps) if mean_steps and stats["Mean_Distance"] else None
        rmssd_vals = [hrv.get(day, {}).get("rmssd") for day in days]
        rmssd_vals = [value for value in rmssd_vals if isinstance(value, (int, float))]
        mean_rmssd = safe_mean(rmssd_vals)
        sd_rmssd = safe_sd(rmssd_vals)
        stats["Mean_RMSSD"] = mean_rmssd
        stats["CV_RMSSD"] = (sd_rmssd / mean_rmssd * 100) if mean_rmssd and sd_rmssd else None
        for key, name in [
            ("sedentary", "Mean_Sedentary"),
            ("light", "Mean_Light"),
            ("moderate", "Mean_Moderate"),
            ("very", "Mean_Very"),
            ("mvpa", "Mean_MVPA"),
            ("total_active", "Mean_TotalActive"),
        ]:
            values = [activity.get(day, {}).get(key) for day in days]
            stats[name] = safe_mean([value for value in values if isinstance(value, (int, float))])
        output[segment] = stats
    return output


def load_ranges_from_database(path: Path, patient_id: str):
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
    else:
        frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError("Baza dat jest pusta.")
    headers = {normalize_header(column): column for column in frame.columns}
    patient_keys = ["patient", "patientid", "pacjent", "id", "folder", "kod", "uczestnik"]
    patient_column = next((headers[key] for key in patient_keys if key in headers), None)
    if patient_column is None:
        patient_column = frame.columns[0]
    wanted = first_number(patient_id)
    selected = None
    for _, row in frame.iterrows():
        if first_number(row.get(patient_column)) == wanted:
            selected = row
            break
    if selected is None:
        raise ValueError(f"Nie znaleziono pacjenta {patient_id} w bazie dat.")
    ranges = []
    for segment in SEGMENTS:
        keys = {
            "start": [
                f"{segment}start", f"{segment}od", f"{segment}from", f"start{segment}", f"od{segment}",
                f"{segment}poczatek", f"{segment}początek",
            ],
            "end": [
                f"{segment}end", f"{segment}do", f"{segment}to", f"end{segment}", f"do{segment}",
                f"{segment}koniec",
            ],
        }
        start_column = next((headers[normalize_header(key)] for key in keys["start"] if normalize_header(key) in headers), None)
        end_column = next((headers[normalize_header(key)] for key in keys["end"] if normalize_header(key) in headers), None)
        if start_column is not None and end_column is not None:
            start_value = selected.get(start_column)
            end_value = selected.get(end_column)
            if not pd.isna(start_value) and not pd.isna(end_value):
                ranges.append((segment, parse_date(start_value), parse_date(end_value)))
    if not ranges:
        raise ValueError("Nie znaleziono zakresow V1/V3/V4/V6 dla tego pacjenta.")
    return ranges


def export_csv(zip_path: Path, patient_id: str, ranges, work_root: Path, output_path: Path | None = None) -> Path:
    if not zip_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku ZIP: {zip_path}")
    pid = patient_folder_name(patient_id)
    patient_dir = work_root / pid
    patient_dir.mkdir(parents=True, exist_ok=True)
    local_zip = patient_dir / f"{pid}.zip"
    if zip_path.resolve() != local_zip.resolve():
        shutil.copy2(zip_path, local_zip)
    extracted = extract_zip(local_zip, patient_dir)
    if extracted == 0:
        raise ValueError("Nie rozpakowano zadnych plikow z ZIP.")
    all_days = []
    for _, start, end in ranges:
        all_days.extend(date_range(start, end))
    all_days = sorted(set(all_days))
    hr_spo2 = collect_hr_spo2(work_root, pid, all_days)
    steps, distance = collect_steps_distance(work_root, pid)
    hrv = hrv_mod.collect_hrv_by_date(work_root, pid)
    resting_hr = rhr_mod.collect_resting_hr_by_date(work_root, pid)
    sleep = collect_sleep(work_root, pid, all_days)
    activity = activity_mod.compute_activity_for_dates(work_root, pid, all_days)
    stats = segment_statistics(ranges, hr_spo2, steps, distance, hrv, resting_hr, sleep, activity)
    destination = output_path or patient_dir / f"{pid}_EXPORT.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for segment, start, end in ranges:
            for day in date_range(start, end):
                row = {"patient_id": pid, "segment": segment, "Timestamp": f"{day.isoformat()}T00:00:00"}
                row.update(hr_spo2.get(day, {}))
                row["Steps"] = steps.get(day)
                row["Distance"] = distance.get(day)
                row.update(sleep_output(sleep.get(day)))
                row.update(hrv.get(day, {}))
                row["resting_heart_rate"] = resting_hr.get(day)
                act = activity.get(day, {})
                row["Sedentary"] = act.get("sedentary")
                row["Light"] = act.get("light")
                row["Moderate"] = act.get("moderate")
                row["Very"] = act.get("very")
                row["MVPA"] = act.get("mvpa")
                row["Total Active"] = act.get("total_active")
                row.update(stats.get(segment, {}))
                writer.writerow({key: missing_to_n(row.get(key)) for key in FIELDNAMES})
    return destination


class App:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Fitbit CSV exporter")
        self.root.geometry("820x520")
        self.zip_path = StringVar()
        self.patient_id = StringVar()
        self.work_root = StringVar(value=str(Path.home() / "Fitbit CSV robocze"))
        self.output_path = StringVar()
        self.database_path = StringVar()
        self.use_database = BooleanVar(value=False)
        self.status = StringVar(value="Wybierz ZIP i podaj zakresy dat albo baze dat.")
        self.date_vars = {segment: (StringVar(), StringVar()) for segment in SEGMENTS}
        self.build()

    def build(self):
        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="ZIP Fitbit").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.zip_path).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(frame, text="Wybierz plik", command=self.choose_zip).grid(row=0, column=2, sticky="ew")
        ttk.Label(frame, text="Pacjent").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.patient_id, width=18).grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))
        ttk.Label(frame, text="Folder roboczy").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.work_root).grid(row=2, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(frame, text="Wybierz folder", command=self.choose_work_root).grid(row=2, column=2, sticky="ew", pady=(8, 0))
        ttk.Label(frame, text="Zapisz CSV jako").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.output_path).grid(row=3, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(frame, text="Wybierz miejsce", command=self.choose_output).grid(row=3, column=2, sticky="ew", pady=(8, 0))
        ttk.Checkbutton(frame, text="Importuj zakresy na podstawie bazy dat", variable=self.use_database).grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Label(frame, text="Baza dat").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.database_path).grid(row=5, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(frame, text="Wybierz baze", command=self.choose_database).grid(row=5, column=2, sticky="ew", pady=(8, 0))
        ranges = ttk.LabelFrame(frame, text="Zakres dat reczny")
        ranges.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ranges.columnconfigure(1, weight=1)
        ranges.columnconfigure(2, weight=1)
        ttk.Label(ranges, text="Wizyta").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Label(ranges, text="Od").grid(row=0, column=1, sticky="w", padx=8, pady=6)
        ttk.Label(ranges, text="Do").grid(row=0, column=2, sticky="w", padx=8, pady=6)
        for row, segment in enumerate(SEGMENTS, start=1):
            start_var, end_var = self.date_vars[segment]
            ttk.Label(ranges, text=segment.upper()).grid(row=row, column=0, sticky="w", padx=8, pady=4)
            ttk.Entry(ranges, textvariable=start_var).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
            ttk.Entry(ranges, textvariable=end_var).grid(row=row, column=2, sticky="ew", padx=8, pady=4)
        actions = ttk.Frame(frame)
        actions.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        actions.columnconfigure(0, weight=1)
        ttk.Button(actions, text="Utworz CSV", command=self.run).grid(row=0, column=1, sticky="e")
        ttk.Label(frame, textvariable=self.status).grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 0))

    def choose_zip(self):
        path = filedialog.askopenfilename(title="Wybierz ZIP Fitbit", filetypes=(("ZIP", "*.zip"), ("Wszystkie pliki", "*.*")))
        if path:
            self.zip_path.set(path)
            if not self.patient_id.get().strip():
                try:
                    self.patient_id.set(patient_folder_name(Path(path).stem))
                except ValueError:
                    pass

    def choose_work_root(self):
        path = filedialog.askdirectory(title="Wybierz folder roboczy")
        if path:
            self.work_root.set(path)

    def choose_output(self):
        initial = "fitbit_export.csv"
        if self.patient_id.get().strip():
            try:
                initial = f"{patient_folder_name(self.patient_id.get())}_EXPORT.csv"
            except ValueError:
                pass
        path = filedialog.asksaveasfilename(title="Zapisz CSV jako", defaultextension=".csv", initialfile=initial, filetypes=(("CSV", "*.csv"), ("Wszystkie pliki", "*.*")))
        if path:
            self.output_path.set(path)

    def choose_database(self):
        path = filedialog.askopenfilename(title="Wybierz baze dat", filetypes=(("Baza dat", "*.xlsx;*.xls;*.csv"), ("Wszystkie pliki", "*.*")))
        if path:
            self.database_path.set(path)
            self.use_database.set(True)

    def manual_ranges(self):
        ranges = []
        for segment, (start_var, end_var) in self.date_vars.items():
            start_text = start_var.get().strip()
            end_text = end_var.get().strip()
            if not start_text and not end_text:
                continue
            if not start_text or not end_text:
                raise ValueError(f"Uzupelnij obie daty dla {segment.upper()}.")
            ranges.append((segment, parse_date(start_text), parse_date(end_text)))
        if not ranges:
            raise ValueError("Podaj zakresy dat albo wybierz import z bazy dat.")
        return ranges

    def read_ranges(self, patient_id: str):
        if self.use_database.get():
            database = Path(self.database_path.get().strip().strip('"'))
            if not database.exists():
                raise FileNotFoundError("Nie znaleziono bazy dat.")
            return load_ranges_from_database(database, patient_id)
        return self.manual_ranges()

    def run(self):
        try:
            zip_path = Path(self.zip_path.get().strip().strip('"'))
            patient_id = self.patient_id.get().strip()
            if not patient_id:
                raise ValueError("Wpisz pacjenta.")
            work_root = Path(self.work_root.get().strip().strip('"'))
            output_text = self.output_path.get().strip().strip('"')
            output_path = Path(output_text) if output_text else None
            ranges = self.read_ranges(patient_id)
            self.status.set("Tworze CSV...")
            self.root.update_idletasks()
            result = export_csv(zip_path, patient_id, ranges, work_root, output_path)
        except Exception as exc:
            self.status.set(f"Blad: {exc}")
            messagebox.showerror("Blad", str(exc))
            return
        self.status.set(f"Gotowe: {result}")
        messagebox.showinfo("Gotowe", f"Zapisano CSV:\n{result}")


def main():
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
