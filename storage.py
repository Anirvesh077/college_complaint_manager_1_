"""Where complaints are kept on disk.

Two interchangeable repositories share the same small interface
(load_all / insert / insert_many / update / take_notices):

* SqliteRepository - the default, data/complaints.db. SQLite does its own
  locking, so the terminal app and the window can run at the same time.
* JsonRepository   - a plain JSON file (any path ending in .json). Writes
  are guarded by a lock file and swapped in atomically.

open_repository() picks one from the file extension.
"""
import json
import logging
import os
import shutil
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import datetime

log = logging.getLogger("ccm.storage")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
DEFAULT_FILE = os.path.join(DATA_DIR, "complaints.db")
SAMPLE_JSON = os.path.join(DATA_DIR, "sample_complaints.json")
SAMPLE_IMPORT = os.path.join(DATA_DIR, "legacy_import_demo.csv")

COLUMNS = [
    "id", "student_name", "roll_no", "category", "description", "priority",
    "status", "date_filed", "due_date", "date_resolved", "resolution_note",
]


class DuplicateIdError(Exception):
    """Raised when a complaint ID is already taken (someone else got there first)."""


def _move_aside(path):
    """Keep a broken file as <name>.corrupt-<time> instead of overwriting it."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.corrupt-{stamp}"
    shutil.move(path, backup)
    for extra in ("-wal", "-shm"):
        if os.path.exists(path + extra):
            os.remove(path + extra)
    log.error("Damaged data file moved to %s", backup)
    return backup


@contextmanager
def file_lock(path, timeout=10.0, stale_after=60.0):
    """Cross-platform lock using an exclusive-create lock file next to `path`.

    A lock file older than stale_after seconds is assumed to belong to a
    crashed process and is removed.
    """
    lock_path = path + ".lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock_path) > stale_after:
                    os.remove(lock_path)
                    log.warning("Removed stale lock file %s", lock_path)
                    continue
            except OSError:
                continue  # lock vanished between the checks, just try again
            if time.monotonic() > deadline:
                raise TimeoutError(f"Could not lock {os.path.basename(path)}; is another copy of the app stuck?")
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            os.remove(lock_path)
        except OSError:
            pass


# ---------------------------------------------------------------- SQLite

SCHEMA = """
CREATE TABLE IF NOT EXISTS complaints (
    id              TEXT PRIMARY KEY,
    student_name    TEXT NOT NULL,
    roll_no         TEXT NOT NULL,
    category        TEXT NOT NULL,
    description     TEXT NOT NULL,
    priority        TEXT NOT NULL,
    status          TEXT NOT NULL,
    date_filed      TEXT NOT NULL,
    due_date        TEXT NOT NULL,
    date_resolved   TEXT NOT NULL DEFAULT '',
    resolution_note TEXT NOT NULL DEFAULT '',
    history         TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_complaints_status   ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_category ON complaints(category);
CREATE INDEX IF NOT EXISTS idx_complaints_roll     ON complaints(roll_no);
"""

INSERT_SQL = (
    "INSERT INTO complaints (" + ", ".join(COLUMNS) + ", history) VALUES ("
    + ", ".join(":" + c for c in COLUMNS) + ", :history)"
)
UPDATE_SQL = (
    "UPDATE complaints SET " + ", ".join(f"{c} = :{c}" for c in COLUMNS[1:])
    + ", history = :history WHERE id = :id"
)


class SqliteRepository:
    name = "SQLite database"

    def __init__(self, path):
        self.path = path
        self._notices = []
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        existed = os.path.exists(path)
        try:
            self._setup()
        except sqlite3.DatabaseError as err:
            if "not a database" not in str(err) and "malformed" not in str(err):
                raise
            backup = _move_aside(path)
            self._notices.append(f"The database file was damaged. It was saved as {os.path.basename(backup)} and a clean one started.")
            self._setup()
        else:
            if not existed:
                log.info("Created new database %s", path)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _setup(self):
        with closing(self._connect()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @staticmethod
    def _params(record):
        params = {c: record.get(c, "") for c in COLUMNS}
        params["history"] = json.dumps(record.get("history", []))
        return params

    def take_notices(self):
        notices, self._notices = self._notices, []
        return notices

    def load_all(self):
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM complaints ORDER BY id").fetchall()
        records = []
        for row in rows:
            record = dict(row)
            try:
                record["history"] = json.loads(record.get("history") or "[]")
            except json.JSONDecodeError:
                record["history"] = []
            records.append(record)
        return records

    def insert(self, record):
        self.insert_many([record])

    def insert_many(self, records):
        try:
            with closing(self._connect()) as conn, conn:
                conn.executemany(INSERT_SQL, [self._params(r) for r in records])
        except sqlite3.IntegrityError as err:
            if "UNIQUE" in str(err):
                raise DuplicateIdError(str(err)) from None
            raise

    def update(self, record):
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(UPDATE_SQL, self._params(record))
            if cursor.rowcount == 0:
                raise KeyError(record["id"])


# ------------------------------------------------------------------ JSON

class JsonRepository:
    name = "JSON file"

    def __init__(self, path):
        self.path = path
        self._notices = []

    def take_notices(self):
        notices, self._notices = self._notices, []
        return notices

    def _read(self):
        """Raw list from disk. Missing or damaged files are replaced by a clean one."""
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            self._write([])
            log.info("Created new data file %s", self.path)
            return []
        except (json.JSONDecodeError, UnicodeDecodeError):
            backup = _move_aside(self.path)
            self._notices.append(f"The data file was damaged. It was saved as {os.path.basename(backup)} and a clean one started.")
            self._write([])
            return []
        if not isinstance(data, list):
            backup = _move_aside(self.path)
            self._notices.append(f"The data file had an unexpected layout. It was saved as {os.path.basename(backup)}.")
            self._write([])
            return []
        return data

    def _write(self, records):
        """Write to a temp file first so a crash can't leave half a file behind."""
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp_path = f"{self.path}.{os.getpid()}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.path)

    def load_all(self):
        return self._read()

    @staticmethod
    def _ids(records):
        return {r.get("id") for r in records if isinstance(r, dict)}

    def insert(self, record):
        self.insert_many([record])

    def insert_many(self, records):
        with file_lock(self.path):
            existing = self._read()
            taken = self._ids(existing)
            for record in records:
                if record["id"] in taken:
                    raise DuplicateIdError(record["id"])
                taken.add(record["id"])
            self._write(existing + list(records))

    def update(self, record):
        with file_lock(self.path):
            existing = self._read()
            for index, item in enumerate(existing):
                if isinstance(item, dict) and item.get("id") == record["id"]:
                    existing[index] = record
                    self._write(existing)
                    return
        raise KeyError(record["id"])


def open_repository(path):
    if str(path).lower().endswith(".json"):
        return JsonRepository(path)
    return SqliteRepository(path)
