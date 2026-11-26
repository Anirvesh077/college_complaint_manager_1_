"""Menu-driven terminal interface."""
import os
import sqlite3
import sys

import applog
import importer
import reports
import storage
import validators as v
from manager import ComplaintManager

PAGE_SIZE = 10
USE_COLOR = sys.stdout.isatty()

if os.name == "nt":
    os.system("")  # nudges older Windows consoles into understanding ANSI codes

CODES = {"red": "31", "green": "32", "yellow": "33", "cyan": "36", "grey": "90", "bold": "1"}

BANNER = r"""
  +--------------------------------------------------+
  |        COLLEGE  COMPLAINT  MANAGER               |
  |        GreenFuture Hack  -  Project #23          |
  +--------------------------------------------------+"""

MENU = """
  1. Log a new complaint
  2. View all complaints
  3. View one complaint
  4. Search / filter
  5. Update status
  6. Change category
  7. Summary report
  8. Warnings
  9. Export reports
 10. Import from CSV / JSON file
 11. Open graphical window
  0. Exit
"""


def paint(text, color=None):
    if not color or not USE_COLOR:
        return text
    return f"\033[{CODES[color]}m{text}\033[0m"


# ------------------------------------------------------------ input helpers

def ask(prompt, check, default=None):
    """Keep asking until check() accepts the answer."""
    while True:
        hint = f" [{default}]" if default else ""
        raw = input(f"  {prompt}{hint}: ").strip()
        if not raw and default is not None:
            raw = default
        try:
            return check(raw)
        except ValueError as err:
            print(paint(f"    ! {err}", "red"))


def ask_choice(prompt, options, allow_blank=False):
    for number, option in enumerate(options, start=1):
        print(f"     {number}. {option}")

    def check(raw):
        if allow_blank and raw == "":
            return ""
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        return v.pick(raw, options, prompt)

    suffix = " (number or name, Enter to skip)" if allow_blank else " (number or name)"
    return ask(prompt + suffix, check)


def ask_id(manager):
    return ask("Complaint ID (e.g. C0007 or just 7)", lambda raw: manager.get(raw).id)


# ------------------------------------------------------------ display helpers

def row_color(c):
    if c.is_overdue():
        return "red"
    if c.status == "Resolved":
        return "green"
    if c.status == "Rejected":
        return "grey"
    return None


def show_rows(rows, title="Results"):
    print("\n" + paint(f"{title} ({len(rows)})", "bold"))
    if not rows:
        print("  Nothing found.")
        return
    head, rule = reports.table_header()
    for start in range(0, len(rows), PAGE_SIZE):
        print(head)
        print(rule)
        for c in rows[start:start + PAGE_SIZE]:
            print(paint(reports.table_row(c), row_color(c)))
        shown = min(start + PAGE_SIZE, len(rows))
        if shown < len(rows):
            answer = input(f"-- {shown} of {len(rows)} shown. Enter for more, q to stop -- ")
            if answer.strip().lower() == "q":
                break
    if any(c.is_overdue() for c in rows):
        print(paint("  (red rows are overdue)", "grey"))


def show_detail(c):
    print()
    print(paint(f"  {c.id}  -  {c.status}", "bold"))
    print(f"  Student   : {c.student_name} ({c.roll_no})")
    print(f"  Category  : {c.category}")
    print(f"  Priority  : {c.priority}")
    print(f"  Filed     : {c.date_filed}   Due: {c.due_date}")
    if c.is_overdue():
        print(paint(f"  OVERDUE by {c.days_late()} day(s)", "red"))
    if c.date_resolved:
        print(f"  Closed on : {c.date_resolved}")
    print(f"  Details   : {c.description}")
    if c.resolution_note:
        print(f"  Outcome   : {c.resolution_note}")
    if c.history:
        print("  History   :")
        for entry in c.history:
            print(paint(f"     {entry}", "grey"))


# ------------------------------------------------------------ menu actions

def log_complaint(manager):
    print(paint("\n  New complaint", "cyan"))
    name = ask("Student name", v.check_name)
    roll = ask("Roll number (like 22CS1042)", v.check_roll)
    category = ask_choice("Category", v.CATEGORIES)
    priority = ask_choice("Priority", v.PRIORITIES)
    description = ask("What happened (10-500 chars)", v.check_description)

    while True:
        # separate loop so a duplicate/date problem doesn't make them retype everything
        filed = ask("Date filed YYYY-MM-DD (Enter for today)", lambda raw: raw, default="")
        try:
            c = manager.add(name, roll, category, description, priority, filed or None)
            break
        except ValueError as err:
            print(paint(f"    ! {err}", "red"))
            if "duplicate" in str(err).lower():
                return
    print(paint(f"\n  Logged as {c.id}. It is due on {c.due_date} ({c.priority} priority).", "green"))


def view_all(manager):
    rows = sorted(manager.complaints, key=lambda c: c.id)
    show_rows(rows, "All complaints")


def view_one(manager):
    show_detail(manager.get(ask_id(manager)))


def search(manager):
    print(paint("\n  Search (leave anything blank to ignore it)", "cyan"))
    keyword = input("  Keyword: ").strip()
    category = ask_choice("Category", v.CATEGORIES, allow_blank=True)
    status = ask_choice("Status", v.STATUSES, allow_blank=True)
    priority = ask_choice("Priority", v.PRIORITIES, allow_blank=True)
    show_rows(manager.search(keyword, category, status, priority), "Matches")


def update_status(manager):
    c = manager.get(ask_id(manager))
    print(f"  Currently: {c.status}")
    while True:
        new_status = ask_choice("New status", v.STATUSES)
        note = ""
        if new_status in ("Resolved", "Rejected"):
            note = ask("Short note on the outcome", lambda raw: raw)
        try:
            c = manager.update_status(c.id, new_status, note)
            break
        except ValueError as err:
            print(paint(f"    ! {err}", "red"))
    print(paint(f"  {c.id} is now {c.status}.", "green"))


def change_category(manager):
    c = manager.get(ask_id(manager))
    print(f"  Currently: {c.category}")
    while True:
        new_cat = ask_choice("New category", v.CATEGORIES)
        try:
            c = manager.assign_category(c.id, new_cat)
            break
        except ValueError as err:
            print(paint(f"    ! {err}", "red"))
    print(paint(f"  {c.id} moved to {c.category}.", "green"))


def summary(manager):
    print()
    for line in reports.format_summary(reports.summarize(manager.complaints)):
        print("  " + line)


def show_warnings(manager):
    flags = reports.warnings(manager.complaints)
    print("\n" + paint(f"Warnings ({len(flags)})", "bold"))
    if not flags:
        print("  Nothing needs attention.")
    colors = {"OVERDUE": "red", "CRITICAL": "red", "DATA": "yellow", "REPEAT": "yellow"}
    for label, text in flags:
        print("  " + paint(f"[{label}]", colors.get(label)) + " " + text)


def export(manager):
    paths = reports.export_all(manager.complaints, storage.EXPORT_DIR)
    print(paint("\n  Reports written:", "green"))
    for p in paths:
        print("   -", os.path.relpath(p))


def import_file(manager):
    path = ask("CSV or JSON file path", lambda raw: raw, default=os.path.relpath(storage.SAMPLE_IMPORT))
    try:
        added, errors = importer.import_file(manager, path)
    except FileNotFoundError:
        print(paint("    ! That file doesn't exist.", "red"))
        return
    except (ValueError, OSError) as err:
        print(paint(f"    ! Couldn't read that file: {err}", "red"))
        return
    print(paint(f"\n  Imported {added} row(s), rejected {len(errors)}.", "green" if not errors else "yellow"))
    for line in errors:
        print("   - " + line)
    if errors:
        print(f"  Rejected rows are also in the log: {os.path.relpath(applog.LOG_FILE)}")


def open_gui(manager):
    try:
        import gui
    except ImportError:
        print(paint("    ! Tkinter isn't installed on this Python, so the window can't open.", "red"))
        return
    print("  Opening the window... close it to come back to the menu.")
    gui.run(manager.path)


ACTIONS = {
    "1": log_complaint, "2": view_all, "3": view_one, "4": search, "5": update_status,
    "6": change_category, "7": summary, "8": show_warnings, "9": export,
    "10": import_file, "11": open_gui,
}


def run(path=storage.DEFAULT_FILE):
    manager = ComplaintManager(path)
    print(paint(BANNER, "cyan"))
    for note in manager.notices:
        print(paint(f"  Note: {note}", "yellow"))
    late = len(manager.overdue())
    print(f"\n  {len(manager.complaints)} complaints loaded from {os.path.relpath(manager.path)}, {late} overdue.")

    while True:
        try:
            manager.reload()  # the window may have changed things since last time round
        except (OSError, sqlite3.Error) as err:
            print(paint(f"    ! Couldn't refresh from storage: {err}", "red"))
        print(MENU)
        try:
            choice = input("  Choose an option: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if choice == "0":
            break
        action = ACTIONS.get(choice)
        if action is None:
            print(paint("    ! Please type a number from the menu.", "red"))
            continue
        try:
            action(manager)
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
        except ValueError as err:
            print(paint(f"    ! {err}", "red"))
        except (OSError, sqlite3.Error) as err:
            print(paint(f"    ! Storage problem: {err}", "red"))
    print("\n  Everything is saved. Bye!")
