"""Core logic: the Complaint record and the ComplaintManager that owns the list."""
import copy
import logging
import random
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta

import storage
import validators as v

log = logging.getLogger("ccm.manager")

ACTIVE = ("Open", "In Progress")
CLOSED = ("Resolved", "Rejected")
ID_RETRIES = 25


def _text(value):
    return "" if value is None else str(value)


@dataclass
class Complaint:
    id: str
    student_name: str
    roll_no: str
    category: str
    description: str
    priority: str
    status: str
    date_filed: str
    due_date: str
    date_resolved: str = ""
    resolution_note: str = ""
    history: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, raw):
        names = [f.name for f in fields(cls) if f.name != "history"]
        required = names[:9]
        missing = [k for k in required if k not in raw]
        if missing:
            raise ValueError("missing field(s): " + ", ".join(missing))
        history = raw.get("history", [])
        if not isinstance(history, list):
            history = []
        return cls(**{k: _text(raw.get(k)) for k in names}, history=[_text(h) for h in history])

    def check(self):
        """Sanity check for records read back from storage."""
        if self.category not in v.CATEGORIES:
            raise ValueError("bad category")
        if self.priority not in v.PRIORITIES:
            raise ValueError("bad priority")
        if self.status not in v.STATUSES:
            raise ValueError("bad status")
        v.check_date(self.date_filed)
        v.check_date(self.due_date)
        if self.date_resolved:
            v.check_date(self.date_resolved)

    def add_history(self, event, when=None):
        stamp = when or datetime.now().strftime("%Y-%m-%d %H:%M")
        self.history.append(f"{stamp}  {event}")

    def filed_on(self):
        return v.check_date(self.date_filed)

    def due_on(self):
        return v.check_date(self.due_date)

    def is_active(self):
        return self.status in ACTIVE

    def days_late(self, today=None):
        today = today or date.today()
        if not self.is_active():
            return 0
        return max(0, (today - self.due_on()).days)

    def is_overdue(self, today=None):
        return self.days_late(today) > 0


class ComplaintManager:
    def __init__(self, path=storage.DEFAULT_FILE):
        self.path = path
        self.repo = storage.open_repository(path)
        self.complaints = []
        self.notices = []  # things worth telling the user about at startup
        self._pending = []  # records added with commit=False, waiting for flush()
        self._skipped = 0
        self.reload()

    # ---------- loading ----------

    def reload(self):
        """Read everything again, so changes made by another window show up."""
        self.flush()
        raw = self.repo.load_all()
        self.notices.extend(self.repo.take_notices())

        loaded, skipped = [], 0
        for item in raw:
            try:
                record = Complaint.from_dict(item)
                record.check()
                loaded.append(record)
            except (ValueError, TypeError, AttributeError):
                skipped += 1
        if skipped and skipped != self._skipped:
            log.warning("Skipped %d stored record(s) with an unexpected format", skipped)
            self.notices.append(f"Skipped {skipped} stored record(s) that didn't match the expected format.")
        self._skipped = skipped
        self.complaints = loaded

    def flush(self):
        """Write records added with commit=False in one batch."""
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        self.repo.insert_many([c.to_dict() for c in batch])
        log.info("Stored a batch of %d complaint(s)", len(batch))

    # ---------- lookups ----------

    def _next_id(self):
        numbers = [int(c.id[1:]) for c in self.complaints if c.id[1:].isdigit()]
        return f"C{(max(numbers) + 1 if numbers else 1):04d}"

    def get(self, complaint_id):
        key = str(complaint_id or "").strip().upper()
        if key.isdigit():
            key = f"C{int(key):04d}"
        for c in self.complaints:
            if c.id == key:
                return c
        raise ValueError(f"No complaint found with ID {complaint_id!r}")

    # ---------- changing things ----------

    def add(self, name, roll_no, category, description, priority, date_filed=None,
            status="Open", date_resolved="", note="", commit=True):
        name = v.check_name(name)
        roll_no = v.check_roll(roll_no)
        category = v.pick(category, v.CATEGORIES, "Category")
        description = v.check_description(description)
        priority = v.pick(priority, v.PRIORITIES, "Priority")
        status = v.pick((status or "").strip() or "Open", v.STATUSES, "Status")
        note = v.check_note(note)
        date_resolved = (date_resolved or "").strip()

        today = date.today()
        date_filed = (date_filed or "").strip()
        filed = v.check_date(date_filed, "Filing date") if date_filed else today
        if filed > today:
            raise ValueError("Filing date can't be in the future")

        for other in self.complaints:
            if other.roll_no == roll_no and other.description.lower() == description.lower():
                raise ValueError(f"Looks like a duplicate of {other.id}")

        closed_on = ""
        if status in CLOSED:
            if not date_resolved:
                raise ValueError(f"A {status} complaint needs a closing date")
            closed = v.check_date(date_resolved, "Closing date")
            if closed < filed:
                raise ValueError("Closing date is before the filing date")
            if closed > today:
                raise ValueError("Closing date can't be in the future")
            closed_on = closed.isoformat()
        elif date_resolved:
            raise ValueError("Only Resolved or Rejected complaints can have a closing date")

        due = filed + timedelta(days=v.SLA_DAYS[priority])
        record = Complaint(
            id=self._next_id(), student_name=name, roll_no=roll_no, category=category,
            description=description, priority=priority, status=status,
            date_filed=filed.isoformat(), due_date=due.isoformat(),
            date_resolved=closed_on, resolution_note=note,
        )
        record.add_history(f"Filed as {priority} priority in {category}", when=filed.isoformat())
        if closed_on:
            record.add_history(f"Marked {status}: {note or 'no note'}", when=closed_on)

        if commit:
            self._insert_with_retry(record)
        else:
            self._pending.append(record)
        self.complaints.append(record)
        log.info("Added %s (%s, %s)", record.id, category, priority)
        return record

    def _insert_with_retry(self, record):
        """Insert, and if another window grabbed the same ID meanwhile, take the next one."""
        for attempt in range(ID_RETRIES):
            try:
                self.repo.insert(record.to_dict())
                return
            except storage.DuplicateIdError:
                log.info("ID %s was taken by someone else, trying again", record.id)
                self.reload()
                record.id = self._next_id()
                time.sleep(random.uniform(0, 0.01) * (attempt + 1))
        raise RuntimeError("Couldn't get a free complaint ID, please try again")

    def _persist(self, record, before):
        """Save an edited record; put it back the way it was if saving fails."""
        try:
            self.repo.update(record.to_dict())
        except KeyError:
            record.__dict__.update(before.__dict__)
            raise ValueError(f"{record.id} no longer exists in storage") from None
        except Exception:
            record.__dict__.update(before.__dict__)
            raise

    def assign_category(self, complaint_id, category):
        record = self.get(complaint_id)
        category = v.pick(category, v.CATEGORIES, "Category")
        if category == record.category:
            raise ValueError(f"{record.id} is already in {category}")
        before = copy.deepcopy(record)
        record.add_history(f"Category changed from {record.category} to {category}")
        record.category = category
        self._persist(record, before)
        log.info("%s moved to %s", record.id, category)
        return record

    def update_status(self, complaint_id, status, note=""):
        record = self.get(complaint_id)
        status = v.pick(status, v.STATUSES, "Status")
        note = v.check_note(note)
        if status == record.status:
            raise ValueError(f"{record.id} is already marked {status}")
        if status in CLOSED and not note:
            raise ValueError("Please add a short note explaining the outcome")

        before = copy.deepcopy(record)
        record.add_history(f"Status changed from {record.status} to {status}" + (f": {note}" if note else ""))
        if status in CLOSED:
            record.date_resolved = date.today().isoformat()
        else:
            record.date_resolved = ""  # re-opened or still being worked on
        record.resolution_note = note
        record.status = status
        self._persist(record, before)
        log.info("%s is now %s", record.id, status)
        return record

    # ---------- finding things ----------

    def search(self, keyword="", category="", status="", priority=""):
        words = keyword.lower().split()
        found = []
        for c in self.complaints:
            if category and c.category != category:
                continue
            if status and c.status != status:
                continue
            if priority and c.priority != priority:
                continue
            text = " ".join([c.id, c.student_name, c.roll_no, c.description, c.resolution_note]).lower()
            if all(w in text for w in words):
                found.append(c)
        return found

    def overdue(self, today=None):
        late = [c for c in self.complaints if c.is_overdue(today)]
        return sorted(late, key=lambda c: c.days_late(today), reverse=True)
