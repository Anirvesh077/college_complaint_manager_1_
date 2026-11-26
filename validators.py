"""Input checks shared by the terminal menu, the GUI and the CSV importer.

Every check_* function either returns a cleaned value or raises ValueError
with a message that is fine to show straight to the user.
"""
import re
from datetime import datetime

CATEGORIES = [
    "Hostel", "Academics", "Library", "Canteen",
    "Transport", "Infrastructure", "Administration", "Other",
]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
STATUSES = ["Open", "In Progress", "Resolved", "Rejected"]
DATE_FORMAT = "%Y-%m-%d"

# How many days the college gets to deal with a complaint, by priority.
SLA_DAYS = {"Critical": 2, "High": 5, "Medium": 10, "Low": 20}

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,59}$")
ROLL_RE = re.compile(r"^\d{2}[A-Z]{2,4}\d{3,4}$")

MIN_DESC = 10
MAX_DESC = 500
MAX_NOTE = 300


def tidy(text):
    """Collapse runs of whitespace and strip the ends. None becomes ''."""
    return " ".join(str(text or "").split())


def check_name(value):
    value = tidy(value)
    if not NAME_RE.match(value):
        raise ValueError("Name must be 2-60 characters and use only letters, spaces, . ' or -")
    return value


def check_roll(value):
    value = str(value or "").strip().upper()
    if not ROLL_RE.match(value):
        raise ValueError("Roll number should look like 22CS1042 (2 digits, 2-4 letters, 3-4 digits)")
    return value


def pick(value, options, label):
    """Match value against options ignoring case, return the official spelling."""
    value = tidy(value)
    for opt in options:
        if opt.lower() == value.lower():
            return opt
    raise ValueError(f"{label} must be one of: " + ", ".join(options))


def check_description(value):
    value = tidy(value)
    if len(value) < MIN_DESC:
        raise ValueError(f"Please describe the problem in at least {MIN_DESC} characters")
    if len(value) > MAX_DESC:
        raise ValueError(f"Description is too long ({len(value)} characters, max {MAX_DESC})")
    return value


def check_note(value):
    value = tidy(value)
    if len(value) > MAX_NOTE:
        raise ValueError(f"Note is too long (max {MAX_NOTE} characters)")
    return value


def check_date(value, label="Date"):
    """Parse a YYYY-MM-DD string into a date object."""
    try:
        parsed = datetime.strptime(str(value or "").strip(), DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"{label} must be a real date written as YYYY-MM-DD") from None
    if parsed.year < 2000:
        raise ValueError(f"{label} looks too old, please check the year")
    return parsed
