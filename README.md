# Fitbit CSV exporter

Program tworzy CSV z paczki ZIP Fitbit.

## Uruchomienie

```powershell
python -m pip install -r requirements.txt
python fitbit_exporter.py
```

W Windows mozna tez kliknac `uruchom_fitbit_exporter.bat`.

## Tryby dat

Program wymaga jednej z dwoch opcji:

1. Reczne wpisanie zakresow dat dla `V1`, `V3`, `V4`, `V6`.
2. Wybor opcji `Importuj zakresy na podstawie bazy dat` i wskazanie pliku `.csv`, `.xlsx` albo `.xls`.

Baza dat powinna zawierac kolumne identyfikujaca pacjenta, np. `patient`, `patient_id`, `pacjent`, `id`, `folder`, `kod`, `uczestnik`.

Dla wizyt program rozpoznaje m.in. kolumny:

```text
v1_start, v1_end
v1_od, v1_do
start_v1, end_v1
od_v1, do_v1
```

Analogicznie dla `v3`, `v4`, `v6`.

