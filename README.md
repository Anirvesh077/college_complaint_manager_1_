# College Complaint Manager

GreenFuture Hack, Project #23 (Campus & Administration).

A Python app for logging student complaints, putting them in a category, and
following each one until it is resolved. It runs as a menu in the terminal and
as a Tkinter window, and the two can be open at the same time because they
share one SQLite database. The core uses only the standard library
(Python 3.10 or newer); matplotlib is optional and only adds a PNG chart.

## Running it

```
python main.py                     # terminal menu
python main.py --gui               # graphical window
python main.py --data my.json      # use a plain JSON data file instead of SQLite
python seed_data.py                # reset the demo data (43 sample complaints)
python -m unittest discover -s tests   # run the tests (62)
```

On Linux, Tkinter may need `sudo apt install python3-tk`. The terminal version
works without it. For the optional chart: `pip install -r requirements-optional.txt`.

## What it does

| Feature | Where |
|---|---|
| Log complaints with category, priority and a priority-based deadline | `manager.py` |
| Input validation (names, roll numbers, dates, lengths, duplicates, future dates) | `validators.py` |
| Change status / category; a note is required when closing | `manager.py` |
| Change history kept for every complaint (who/what/when) | `manager.py` |
| SQLite storage (default) or JSON file, same interface | `storage.py` |
| Search by keyword, category, status, priority | `manager.search()` |
| Summary: totals, rates, average days to resolve, deadline hit rate, monthly trend, text bar charts | `reports.py` |
| Exports: Markdown, text audit log (with history), CSV, JSON, PNG chart | `reports.py` |
| Warnings: overdue, critical still open, bad data, repeat filers | `reports.warnings()` |
| Bulk import from CSV or JSON with row-by-row errors | `importer.py` |
| Standard `logging` with a rotating log file (`logs/ccm.log`) | `applog.py` |
| Terminal menu / Tkinter window | `cli.py` / `gui.py` |
| Streamlit web interface: dashboard, filters, details + history, forms, import/export, warnings | `streamlit_app.py` |

### Deadlines

Each complaint gets a due date from its priority: Critical 2 days, High 5,
Medium 10, Low 20. Anything still Open or In Progress after its due date is
overdue and shown in red in both interfaces.

## Design notes

**Layers.** `cli.py` and `gui.py` only talk to `ComplaintManager`. The manager
holds the rules and only talks to a repository. `storage.py` is the only
module that touches files. Swapping the storage means writing one new class
with `load_all / insert / insert_many / update`.

**Why SQLite by default.** Flat JSON files are rewritten in full on every
save, which does not scale and is awkward when two programs use the file. SQLite
gives row-level updates, indexes on status, category and roll number, and its
own locking, so the terminal app and the window can run side by side. The
window checks for outside changes every 5 seconds (and has a Refresh button);
the terminal menu re-reads before every prompt.

**Concurrent writers.** If two programs try to take the same complaint ID, the
database rejects the second insert and the manager retries with the next free
ID. The unit tests start six threads adding complaints at once on both
backends and check that no ID is lost or repeated.

**JSON backend.** Still available (`--data file.json`). Writes happen under a
lock file (stale locks from crashed runs are cleaned up) and are swapped in
atomically from a temp file, so a crash cannot leave half a file.

**Bad or missing storage.**
* Missing file: a new empty one is created.
* Corrupted JSON or database: the old file is renamed to `<name>.corrupt-<time>`
  and the app starts clean, so nothing is silently lost.
* Stored records that fail the format check are skipped and the user is told.

**Moving old JSON data into SQLite.** Choose "Import" and give the JSON file
(for example `data/sample_complaints.json`). Every record goes through the same
validation as a normal entry.

**Logging.** Adds, status changes, imports, damaged files and rejected import
rows all go through the standard `logging` module. Set `CCM_LOG_LEVEL=DEBUG`
for more detail.

## Importing

Required columns/keys: `student_name, roll_no, category, description, priority, date_filed`.
Optional: `status, date_resolved, resolution_note`.

`data/legacy_import_demo.csv` is a deliberately messy file (3 good rows, 9 bad
ones) to show how rejected rows are reported.

## Suggested demo

1. Start the app and show the menu and the overdue count.
2. Log a complaint with a bad name, a bad roll number and a too-short
   description to show the validation, then fix them.
3. Search for a keyword, then update the status of the new complaint.
4. View that complaint to show its history.
5. Open the summary and the warnings.
6. Import `data/legacy_import_demo.csv` and show the rejected rows.
7. Exit, start again, and show that the new complaint is still there.
8. Export the reports and open the Markdown file and the PNG chart.
9. Run `python main.py --gui` next to the terminal to show the shared data.

## Layout

```
main.py            entry point
streamlit_app.py   Streamlit web interface (theme in .streamlit/config.toml)
cli.py             terminal menu
gui.py             Tkinter window
manager.py         Complaint record + ComplaintManager (the rules)
validators.py      all input checks
storage.py         SQLite and JSON repositories, file lock
reports.py         summary, warnings, exports, charts
importer.py        CSV / JSON import
applog.py          logging setup
seed_data.py       rebuilds the sample data
data/              complaints.db, sample CSV/JSON, demo import file
exports/           generated reports
logs/              application log (created on first run)
tests/             unit tests
```
