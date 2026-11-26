"""Bulk import of legacy CSV or JSON files, with a row-by-row error report.

Rejected rows are returned to the caller (so the screen can list them) and
also written to the application log at WARNING level.
"""
import csv
import json
import logging
import os

log = logging.getLogger("ccm.importer")

REQUIRED = ["student_name", "roll_no", "category", "description", "priority", "date_filed"]
OPTIONAL = ["status", "date_resolved", "resolution_note"]


def import_file(manager, path):
    """Pick the importer from the file extension. Returns (added, errors)."""
    extension = os.path.splitext(str(path))[1].lower()
    if extension == ".json":
        return import_json(manager, path)
    if extension == ".csv":
        return import_csv(manager, path)
    raise ValueError("Only .csv and .json files can be imported")


def import_csv(manager, csv_path):
    """Add every valid row to the manager. Returns (added, errors).

    errors is a list of strings like "Row 4: Category must be one of ...".
    Row numbers match what you'd see in a spreadsheet (header is row 1).
    Raises FileNotFoundError or ValueError if the file itself is unusable.
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [col for col in REQUIRED if col not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("CSV is missing required column(s): " + ", ".join(missing))
        return _add_rows(manager, enumerate(reader, start=2), "Row", csv_path)


def import_json(manager, json_path):
    """Same as import_csv but for a JSON list of complaint objects.

    Works on files written by the JSON export, so it doubles as a way to
    move an old JSON data file into the SQLite database.
    """
    with open(json_path, encoding="utf-8-sig") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as err:
            raise ValueError(f"That isn't valid JSON ({err.msg} at line {err.lineno})") from None
    if not isinstance(data, list):
        raise ValueError("The JSON file must contain a list of complaint objects")
    return _add_rows(manager, enumerate(data, start=1), "Record", json_path)


def _add_rows(manager, numbered_rows, label, source):
    added = 0
    errors = []
    try:
        for number, row in numbered_rows:
            if not isinstance(row, dict):
                errors.append(f"{label} {number}: expected an object with complaint fields")
                continue
            try:
                manager.add(
                    name=row.get("student_name"),
                    roll_no=row.get("roll_no"),
                    category=row.get("category"),
                    description=row.get("description"),
                    priority=row.get("priority"),
                    date_filed=row.get("date_filed"),
                    status=row.get("status"),
                    date_resolved=row.get("date_resolved"),
                    note=row.get("resolution_note"),
                    commit=False,
                )
                added += 1
            except ValueError as err:
                errors.append(f"{label} {number}: {err}")
    finally:
        manager.flush()

    name = os.path.basename(str(source))
    for line in errors:
        log.warning("%s - %s", name, line)
    log.info("Import of %s finished: %d added, %d rejected", name, added, len(errors))
    return added, errors
