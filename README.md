# FitBit-exporter
A local Python tool for converting Fitbit ZIP exports into structured CSV files using manually entered visit date ranges or date ranges imported from a CSV/XLSX visit database.
Fitbit CSV Exporter is a local Python desktop tool for processing Fitbit data export ZIP files and generating structured CSV outputs for visit-based analysis.

The user selects a Fitbit ZIP file, enters a patient identifier, and either provides date ranges manually for V1, V3, V4, and V6 or imports those ranges from a CSV/XLSX visit-date database. The program extracts activity, heart rate, sleep, SpO2, HRV, resting heart rate, and activity-minute summaries into one CSV file.

The tool runs locally and does not upload data or connect to external services. It is intended for research data preparation where raw Fitbit exports need to be converted into a consistent tabular format.
