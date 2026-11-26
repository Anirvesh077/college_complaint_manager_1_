"""Tables, summary numbers, warning flags and file exports."""
import csv
import json
import os
from collections import Counter, defaultdict
from dataclasses import fields
from datetime import date, datetime

import validators as v
from manager import Complaint

TABLE_COLUMNS = [
    ("ID", 6, "id"),
    ("Filed", 10, "date_filed"),
    ("Student", 18, "student_name"),
    ("Category", 14, "category"),
    ("Priority", 8, "priority"),
    ("Status", 11, "status"),
    ("Due", 10, "due_date"),
]


def clip(text, width):
    text = str(text)
    return text if len(text) <= width else text[: width - 3] + "..."


def table_header():
    head = " | ".join(name.ljust(w) for name, w, _ in TABLE_COLUMNS)
    rule = "-+-".join("-" * w for _, w, _ in TABLE_COLUMNS)
    return head, rule


def table_row(c):
    return " | ".join(clip(getattr(c, attr), w).ljust(w) for _, w, attr in TABLE_COLUMNS)


def format_table(rows):
    if not rows:
        return ["(nothing to show)"]
    head, rule = table_header()
    return [head, rule] + [table_row(c) for c in rows]


# ---------------------------------------------------------------- summary

def summarize(complaints, today=None):
    today = today or date.today()
    total = len(complaints)

    resolved = [c for c in complaints if c.status == "Resolved" and c.date_resolved]
    days_taken = [(v.check_date(c.date_resolved) - c.filed_on()).days for c in resolved]
    on_time = sum(1 for c in resolved if c.date_resolved <= c.due_date)

    active = [c for c in complaints if c.is_active()]
    ages = [(today - c.filed_on()).days for c in active]
    overdue = [c for c in active if c.is_overdue(today)]

    per_category = defaultdict(list)
    for c, days in zip(resolved, days_taken):
        per_category[c.category].append(days)

    return {
        "today": today.isoformat(),
        "total": total,
        "by_status": Counter(c.status for c in complaints),
        "by_category": Counter(c.category for c in complaints),
        "by_priority": Counter(c.priority for c in complaints),
        "by_month": dict(sorted(Counter(c.date_filed[:7] for c in complaints).items())),
        "resolved_count": len(resolved),
        "resolution_rate": round(100 * len(resolved) / total, 1) if total else 0.0,
        "avg_days_to_resolve": round(sum(days_taken) / len(days_taken), 1) if days_taken else None,
        "on_time_rate": round(100 * on_time / len(resolved), 1) if resolved else None,
        "active_count": len(active),
        "avg_age_active": round(sum(ages) / len(ages), 1) if ages else None,
        "overdue_count": len(overdue),
        "category_avg_days": {k: round(sum(d) / len(d), 1) for k, d in per_category.items()},
    }


def trend_text(by_month):
    months = list(by_month.items())
    if len(months) < 2:
        return "Not enough months of data to show a trend yet."
    busiest = max(months, key=lambda m: m[1])
    (prev_month, prev_n), (last_month, last_n) = months[-2], months[-1]
    if last_n > prev_n:
        direction = f"up from {prev_n} in {prev_month}"
    elif last_n < prev_n:
        direction = f"down from {prev_n} in {prev_month}"
    else:
        direction = f"same as {prev_month}"
    return f"Busiest month: {busiest[0]} ({busiest[1]}). Latest month {last_month}: {last_n} ({direction})."


def _fmt(value, suffix=""):
    return "n/a" if value is None else f"{value}{suffix}"


def bar(count, biggest, width=18):
    """Little text bar for the terminal summary, e.g. '######'."""
    if not biggest or not count:
        return ""
    return "#" * max(1, round(width * count / biggest))


def format_summary(data):
    """Plain-text version of the summary, returned as a list of lines."""
    lines = [
        f"SUMMARY as of {data['today']}",
        "=" * 44,
        f"Total complaints        : {data['total']}",
        f"Resolved                : {data['resolved_count']} ({data['resolution_rate']}%)",
        f"Still active            : {data['active_count']}",
        f"Overdue                 : {data['overdue_count']}",
        f"Avg days to resolve     : {_fmt(data['avg_days_to_resolve'])}",
        f"Resolved within deadline: {_fmt(data['on_time_rate'], '%')}",
        f"Avg age of active ones  : {_fmt(data['avg_age_active'], ' days')}",
        "",
        "By status",
    ]
    biggest = max(data["by_status"].values(), default=0)
    for name in v.STATUSES:
        n = data["by_status"].get(name, 0)
        lines.append(f"  {name:<13}{n:>4}  {bar(n, biggest)}")
    lines += ["", "By category (count, avg days to resolve)"]
    biggest = max(data["by_category"].values(), default=0)
    for name, n in data["by_category"].most_common():
        avg = data["category_avg_days"].get(name)
        lines.append(f"  {name:<15}{n:>3}  {bar(n, biggest):<18} {_fmt(avg)}")
    lines += ["", "By priority"]
    biggest = max(data["by_priority"].values(), default=0)
    for name in reversed(v.PRIORITIES):
        n = data["by_priority"].get(name, 0)
        lines.append(f"  {name:<10}{n:>4}  {bar(n, biggest)}")
    lines += ["", "Trend", "  " + trend_text(data["by_month"])]
    return lines


# --------------------------------------------------------------- warnings

def warnings(complaints, today=None):
    """List of (label, message) pairs for anything that needs attention."""
    today = today or date.today()
    found = []

    late = [c for c in complaints if c.is_overdue(today)]
    for c in sorted(late, key=lambda c: c.days_late(today), reverse=True):
        found.append(("OVERDUE", f"{c.id} [{c.priority}, {c.category}] was due {c.due_date}, {c.days_late(today)} day(s) late"))

    for c in complaints:
        if c.priority == "Critical" and c.is_active():
            found.append(("CRITICAL", f"{c.id} is still {c.status.lower()}: {clip(c.description, 55)}"))
        if c.status == "Resolved" and not c.resolution_note:
            found.append(("DATA", f"{c.id} is resolved but has no resolution note"))
        if c.date_resolved and c.date_resolved < c.date_filed:
            found.append(("DATA", f"{c.id} has a closing date before its filing date"))

    names = {}
    counts = Counter()
    for c in complaints:
        counts[c.roll_no] += 1
        names[c.roll_no] = c.student_name
    for roll, n in counts.items():
        if n >= 3:
            found.append(("REPEAT", f"{roll} ({names[roll]}) has filed {n} complaints"))
    return found


# ---------------------------------------------------------------- exports

def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _target(folder, name, ext):
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{name}_{_stamp()}.{ext}")


def export_csv(complaints, folder):
    path = _target(folder, "complaints", "csv")
    columns = [f.name for f in fields(Complaint) if f.name != "history"]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for c in complaints:
            writer.writerow(c.to_dict())
    return path


def export_markdown(complaints, folder, today=None):
    data = summarize(complaints, today)
    path = _target(folder, "summary", "md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"# Complaint Summary ({data['today']})\n\n")
        handle.write(f"- **Total complaints:** {data['total']}\n")
        handle.write(f"- **Resolved:** {data['resolved_count']} ({data['resolution_rate']}%)\n")
        handle.write(f"- **Active:** {data['active_count']} (overdue: {data['overdue_count']})\n")
        handle.write(f"- **Average days to resolve:** {_fmt(data['avg_days_to_resolve'])}\n")
        handle.write(f"- **Resolved within deadline:** {_fmt(data['on_time_rate'], '%')}\n\n")

        handle.write("## By status\n\n| Status | Count |\n|---|---|\n")
        for name in v.STATUSES:
            handle.write(f"| {name} | {data['by_status'].get(name, 0)} |\n")

        handle.write("\n## By category\n\n| Category | Count | Avg days to resolve |\n|---|---|---|\n")
        for name, n in data["by_category"].most_common():
            handle.write(f"| {name} | {n} | {_fmt(data['category_avg_days'].get(name))} |\n")

        handle.write(f"\n## Trend\n\n{trend_text(data['by_month'])}\n\n")
        handle.write("## Warnings\n\n")
        flags = warnings(complaints, today)
        if flags:
            for label, text in flags:
                handle.write(f"- **{label}**: {text}\n")
        else:
            handle.write("Nothing needs attention.\n")

        handle.write("\n## All complaints\n\n| ID | Filed | Student | Category | Priority | Status | Due |\n|---|---|---|---|---|---|---|\n")
        for c in complaints:
            handle.write(f"| {c.id} | {c.date_filed} | {c.student_name} | {c.category} | {c.priority} | {c.status} | {c.due_date} |\n")
    return path


def export_text(complaints, folder, today=None):
    data = summarize(complaints, today)
    path = _target(folder, "audit_log", "txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("COLLEGE COMPLAINT MANAGER - AUDIT LOG\n")
        handle.write(f"Generated {datetime.now():%Y-%m-%d %H:%M}\n\n")
        handle.write("\n".join(format_summary(data)) + "\n\n")
        handle.write("WARNINGS\n" + "-" * 44 + "\n")
        flags = warnings(complaints, today)
        if flags:
            for label, text in flags:
                handle.write(f"[{label}] {text}\n")
        else:
            handle.write("none\n")
        handle.write("\nRECORDS\n" + "-" * 44 + "\n")
        handle.write("\n".join(format_table(complaints)) + "\n")
        handle.write("\nCHANGE HISTORY\n" + "-" * 44 + "\n")
        for c in complaints:
            handle.write(f"{c.id}\n")
            for entry in c.history:
                handle.write(f"    {entry}\n")
    return path


def export_json(complaints, folder):
    path = _target(folder, "complaints", "json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump([c.to_dict() for c in complaints], handle, indent=2, ensure_ascii=False)
    return path


def export_chart(complaints, folder, today=None):
    """PNG with three charts. Needs matplotlib; returns None if it isn't installed."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator
    except ImportError:
        return None

    data = summarize(complaints, today)
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 4.2))

    ax1.bar(v.STATUSES, [data["by_status"].get(s, 0) for s in v.STATUSES], color="#1b6b4a")
    ax1.set_title("By status")
    ax1.tick_params(axis="x", labelrotation=20)

    ranked = data["by_category"].most_common()
    ax2.barh([name for name, _ in reversed(ranked)], [n for _, n in reversed(ranked)], color="#2e8b6a")
    ax2.set_title("By category")

    months = list(data["by_month"].items())
    ax3.plot([m for m, _ in months], [n for _, n in months], marker="o", color="#1b6b4a")
    ax3.set_title("Filed per month")
    ax3.tick_params(axis="x", labelrotation=30)

    ax1.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax3.yaxis.set_major_locator(MaxNLocator(integer=True))

    fig.suptitle(f"College Complaint Manager - {data['total']} complaints as of {data['today']}")
    fig.tight_layout()
    path = _target(folder, "charts", "png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def export_all(complaints, folder):
    """Write every report format and return the file paths (the chart only if matplotlib is there)."""
    paths = [
        export_markdown(complaints, folder),
        export_text(complaints, folder),
        export_csv(complaints, folder),
        export_json(complaints, folder),
    ]
    chart = export_chart(complaints, folder)
    if chart:
        paths.append(chart)
    return paths
