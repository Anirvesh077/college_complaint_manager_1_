import csv
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importer  # noqa: E402
import reports  # noqa: E402
import storage  # noqa: E402
import validators as v  # noqa: E402
from manager import ComplaintManager  # noqa: E402


class BackendCase(unittest.TestCase):
    """Base class: every subclass below runs once for SQLite and once for JSON."""
    ext = ".db"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "complaints" + self.ext)
        self.manager = ComplaintManager(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, **overrides):
        args = dict(name="Test Student", roll_no="22CS1001", category="Hostel",
                    description="The fan in my room is broken.", priority="Medium")
        args.update(overrides)
        return self.manager.add(**args)


# ------------------------------------------------------------ validators

class ValidationTests(unittest.TestCase):
    def test_name_rules(self):
        self.assertEqual(v.check_name("  Priya   Nair "), "Priya Nair")
        for bad in ["", "A", "R2D2", "x" * 61]:
            with self.assertRaises(ValueError):
                v.check_name(bad)

    def test_roll_rules(self):
        self.assertEqual(v.check_roll("22cs1042"), "22CS1042")
        for bad in ["", "CS-77", "2CS1042", "22CS12"]:
            with self.assertRaises(ValueError):
                v.check_roll(bad)

    def test_description_boundaries(self):
        self.assertEqual(v.check_description("a" * 10), "a" * 10)
        self.assertEqual(len(v.check_description("a" * 500)), 500)
        with self.assertRaises(ValueError):
            v.check_description("a" * 9)
        with self.assertRaises(ValueError):
            v.check_description("a" * 501)

    def test_dates(self):
        self.assertEqual(v.check_date("2026-02-28"), date(2026, 2, 28))
        for bad in ["2026-02-30", "28/02/2026", "", "1999-01-01"]:
            with self.assertRaises(ValueError):
                v.check_date(bad)

    def test_pick_ignores_case(self):
        self.assertEqual(v.pick("in progress", v.STATUSES, "Status"), "In Progress")
        with self.assertRaises(ValueError):
            v.pick("urgent", v.PRIORITIES, "Priority")


# --------------------------------------------------------------- manager

class ManagerTests(BackendCase):
    def test_add_sets_id_and_deadline(self):
        c = self.add(priority="High", date_filed="2026-10-01")
        self.assertEqual(c.id, "C0001")
        self.assertEqual(c.due_date, "2026-10-06")
        self.assertEqual(c.status, "Open")

    def test_future_filing_date_rejected(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            self.add(date_filed=tomorrow)

    def test_duplicate_rejected(self):
        self.add()
        with self.assertRaises(ValueError):
            self.add()

    def test_status_flow(self):
        c = self.add()
        with self.assertRaises(ValueError):
            self.manager.update_status(c.id, "Resolved")  # note required
        self.manager.update_status(c.id, "Resolved", "Fixed it")
        self.assertEqual(c.date_resolved, date.today().isoformat())
        self.manager.update_status(c.id, "Open")
        self.assertEqual(c.date_resolved, "")
        with self.assertRaises(ValueError):
            self.manager.update_status(c.id, "Open")

    def test_category_change(self):
        c = self.add()
        self.manager.assign_category("1", "Library")
        self.assertEqual(c.category, "Library")
        with self.assertRaises(ValueError):
            self.manager.assign_category("1", "Library")

    def test_unknown_id(self):
        with self.assertRaises(ValueError):
            self.manager.get("C9999")

    def test_history_is_recorded(self):
        c = self.add()
        self.manager.assign_category(c.id, "Library")
        self.manager.update_status(c.id, "Resolved", "All sorted")
        again = ComplaintManager(self.path).get(c.id)
        self.assertEqual(len(again.history), 3)
        self.assertIn("Filed", again.history[0])
        self.assertIn("Library", again.history[1])
        self.assertIn("Resolved", again.history[2])

    def test_search(self):
        self.add(description="Projector is broken in room 5.", category="Infrastructure")
        self.add(roll_no="22CS1002", description="Mess food was cold today.", category="Canteen")
        self.assertEqual(len(self.manager.search("projector")), 1)
        self.assertEqual(len(self.manager.search(category="Canteen")), 1)
        self.assertEqual(len(self.manager.search("MESS cold")), 1)
        self.assertEqual(len(self.manager.search("nothing like this")), 0)

    def test_overdue(self):
        old = (date.today() - timedelta(days=30)).isoformat()
        late = self.add(date_filed=old, priority="Low")
        self.add(roll_no="22CS1002")
        self.assertEqual([c.id for c in self.manager.overdue()], [late.id])
        self.manager.update_status(late.id, "Rejected", "Not valid")
        self.assertEqual(self.manager.overdue(), [])

    def test_persistence(self):
        self.add()
        again = ComplaintManager(self.path)
        self.assertEqual(len(again.complaints), 1)
        self.assertEqual(again.complaints[0].student_name, "Test Student")

    def test_bulk_insert(self):
        for i in range(500):
            self.add(roll_no=f"22CS{1000 + i % 9000}", description=f"Bulk complaint number {i} here.", commit=False)
        self.manager.flush()
        again = ComplaintManager(self.path)
        self.assertEqual(len(again.complaints), 500)
        self.assertEqual(again.complaints[-1].id, "C0500")
        self.assertEqual(len(again.search("bulk complaint")), 500)


class ManagerTestsJson(ManagerTests):
    ext = ".json"


# ----------------------------------------------- two windows, one data file

class SharedAccessTests(BackendCase):
    def test_second_manager_sees_changes_after_reload(self):
        other = ComplaintManager(self.path)
        self.add()
        self.assertEqual(len(other.complaints), 0)
        other.reload()
        self.assertEqual(len(other.complaints), 1)

    def test_stale_manager_gets_a_fresh_id(self):
        other = ComplaintManager(self.path)  # loaded before anything was added
        first = self.add()
        second = other.add("Other Student", "22CS1002", "Library", "Books are missing from shelf.", "Low")
        self.assertEqual(first.id, "C0001")
        self.assertEqual(second.id, "C0002")
        self.manager.reload()
        self.assertEqual(len(self.manager.complaints), 2)

    def test_edit_from_stale_manager_hits_the_right_row(self):
        c = self.add()
        other = ComplaintManager(self.path)
        other.update_status(c.id, "In Progress", "Looking into it")
        self.manager.reload()
        self.assertEqual(self.manager.get(c.id).status, "In Progress")

    def test_many_threads_adding_at_once(self):
        errors = []

        def worker(n):
            try:
                mine = ComplaintManager(self.path)
                for i in range(8):
                    mine.add(f"Worker {chr(65 + n)}", f"22CS{1000 + n}", "Other",
                             f"Complaint {i} from worker {n} about something.", "Low")
            except Exception as err:  # noqa: BLE001 - we want to see anything that goes wrong
                errors.append(repr(err))

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.manager.reload()
        ids = [c.id for c in self.manager.complaints]
        self.assertEqual(len(ids), 48)
        self.assertEqual(len(set(ids)), 48)


class SharedAccessTestsJson(SharedAccessTests):
    ext = ".json"


# ---------------------------------------------------------------- storage

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def test_extension_picks_backend(self):
        self.assertIsInstance(storage.open_repository(self.path("a.json")), storage.JsonRepository)
        self.assertIsInstance(storage.open_repository(self.path("a.db")), storage.SqliteRepository)

    def test_missing_json_file_is_created(self):
        manager = ComplaintManager(self.path("new.json"))
        self.assertTrue(os.path.exists(self.path("new.json")))
        self.assertEqual(manager.complaints, [])

    def test_corrupt_json_is_moved_aside(self):
        with open(self.path("data.json"), "w") as handle:
            handle.write("{ not json")
        fresh = ComplaintManager(self.path("data.json"))
        self.assertEqual(fresh.complaints, [])
        self.assertTrue(fresh.notices)
        self.assertEqual(len([f for f in os.listdir(self.tmp.name) if "corrupt" in f]), 1)

    def test_corrupt_database_is_moved_aside(self):
        with open(self.path("data.db"), "wb") as handle:
            handle.write(b"this is definitely not a sqlite file" * 20)
        fresh = ComplaintManager(self.path("data.db"))
        self.assertEqual(fresh.complaints, [])
        self.assertTrue(fresh.notices)
        self.assertEqual(len([f for f in os.listdir(self.tmp.name) if "corrupt" in f]), 1)
        fresh.add("Test Student", "22CS1001", "Hostel", "The fan in my room is broken.", "Low")
        self.assertEqual(len(ComplaintManager(self.path("data.db")).complaints), 1)

    def test_bad_json_records_skipped(self):
        good = ComplaintManager(self.path("data.json"))
        record = good.add("Test Student", "22CS1001", "Hostel", "The fan in my room is broken.", "Low").to_dict()
        with open(self.path("data.json"), "w") as handle:
            json.dump([record, {"id": "C0002"}, "garbage"], handle)
        again = ComplaintManager(self.path("data.json"))
        self.assertEqual(len(again.complaints), 1)
        self.assertTrue(again.notices)

    def test_lock_times_out_when_held(self):
        target = self.path("thing.json")
        with storage.file_lock(target):
            with self.assertRaises(TimeoutError):
                with storage.file_lock(target, timeout=0.2):
                    pass

    def test_stale_lock_is_removed(self):
        target = self.path("thing.json")
        lock = target + ".lock"
        with open(lock, "w") as handle:
            handle.write("123")
        old = os.path.getmtime(lock) - 600
        os.utime(lock, (old, old))
        with storage.file_lock(target, timeout=1):
            pass
        self.assertFalse(os.path.exists(lock))

    def test_lock_is_released_after_error(self):
        target = self.path("thing.json")
        with self.assertRaises(RuntimeError):
            with storage.file_lock(target):
                raise RuntimeError("boom")
        self.assertFalse(os.path.exists(target + ".lock"))


# ----------------------------------------------------------------- import

class ImportTests(BackendCase):
    def write_csv(self, rows):
        path = os.path.join(self.tmp.name, "in.csv")
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["student_name", "roll_no", "category", "description", "priority", "date_filed"])
            writer.writerows(rows)
        return path

    def test_row_errors_are_reported_and_logged(self):
        path = self.write_csv([
            ["Good Student", "22CS1010", "Library", "Books are missing from shelf.", "Low", "2026-10-01"],
            ["Bad Roll", "XYZ", "Library", "Books are missing from shelf.", "Low", "2026-10-01"],
            ["Bad Cat", "22CS1011", "Gym", "Equipment is rusted over.", "Low", "2026-10-01"],
        ])
        with self.assertLogs("ccm.importer", level="WARNING") as captured:
            added, errors = importer.import_csv(self.manager, path)
        self.assertEqual(added, 1)
        self.assertEqual(len(errors), 2)
        self.assertTrue(errors[0].startswith("Row 3"))
        self.assertEqual(len(captured.records), 2)
        self.assertEqual(len(ComplaintManager(self.path).complaints), 1)

    def test_missing_columns(self):
        path = os.path.join(self.tmp.name, "bad.csv")
        with open(path, "w") as handle:
            handle.write("a,b\n1,2\n")
        with self.assertRaises(ValueError):
            importer.import_csv(self.manager, path)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            importer.import_csv(self.manager, os.path.join(self.tmp.name, "nope.csv"))

    def test_unsupported_extension(self):
        with self.assertRaises(ValueError):
            importer.import_file(self.manager, os.path.join(self.tmp.name, "data.xlsx"))

    def test_json_import_and_bad_json(self):
        path = os.path.join(self.tmp.name, "in.json")
        with open(path, "w") as handle:
            json.dump([
                {"student_name": "Json Student", "roll_no": "22CS1020", "category": "Canteen",
                 "description": "Tea is served cold every day.", "priority": "Low", "date_filed": "2026-10-02"},
                "not an object",
                {"student_name": "X", "roll_no": "22CS1021"},
            ], handle)
        added, errors = importer.import_file(self.manager, path)
        self.assertEqual(added, 1)
        self.assertEqual(len(errors), 2)
        self.assertTrue(errors[0].startswith("Record 2"))

        with open(path, "w") as handle:
            handle.write("[ oops")
        with self.assertRaises(ValueError):
            importer.import_json(self.manager, path)

    def test_export_then_import_round_trip(self):
        self.add()
        self.add(roll_no="22CS1002", description="Mess food was cold today.", category="Canteen")
        exported = reports.export_json(self.manager.complaints, self.tmp.name)
        fresh = ComplaintManager(os.path.join(self.tmp.name, "fresh" + self.ext))
        added, errors = importer.import_file(fresh, exported)
        self.assertEqual((added, errors), (2, []))
        self.assertEqual([c.category for c in fresh.complaints], ["Hostel", "Canteen"])


class ImportTestsJson(ImportTests):
    ext = ".json"


# ---------------------------------------------------------------- reports

class ReportTests(BackendCase):
    def test_summary_numbers(self):
        a = self.add(date_filed="2026-10-01", priority="High")
        self.add(roll_no="22CS1002")
        self.manager.update_status(a.id, "Resolved", "Done")
        data = reports.summarize(self.manager.complaints, date(2026, 11, 1))
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["resolved_count"], 1)
        self.assertEqual(data["resolution_rate"], 50.0)
        self.assertEqual(data["active_count"], 1)

    def test_empty_summary_does_not_crash(self):
        data = reports.summarize([])
        self.assertEqual(data["total"], 0)
        self.assertIsNone(data["avg_days_to_resolve"])
        self.assertTrue(reports.format_summary(data))

    def test_text_bars(self):
        self.assertEqual(reports.bar(0, 10), "")
        self.assertEqual(reports.bar(10, 10, width=8), "########")
        self.assertEqual(reports.bar(1, 100, width=8), "#")

    def test_exports_create_files(self):
        self.add()
        paths = reports.export_all(self.manager.complaints, self.tmp.name)
        extensions = {os.path.splitext(p)[1] for p in paths}
        self.assertTrue({".md", ".txt", ".csv", ".json"} <= extensions)
        for p in paths:
            self.assertTrue(os.path.getsize(p) > 0)

    def test_csv_export_has_no_history_column(self):
        self.add()
        path = reports.export_csv(self.manager.complaints, self.tmp.name)
        with open(path, newline="") as handle:
            header = next(csv.reader(handle))
        self.assertNotIn("history", header)
        self.assertIn("roll_no", header)

    def test_chart_is_made_when_matplotlib_exists(self):
        self.add()
        path = reports.export_chart(self.manager.complaints, self.tmp.name)
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.assertIsNone(path)
        else:
            self.assertTrue(os.path.getsize(path) > 1000)

    def test_repeat_filer_warning(self):
        for i in range(3):
            self.add(description=f"Problem number {i} in the hostel.")
        labels = [label for label, _ in reports.warnings(self.manager.complaints)]
        self.assertIn("REPEAT", labels)


if __name__ == "__main__":
    unittest.main()
