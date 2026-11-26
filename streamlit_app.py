"""Streamlit web interface for the College Complaint Manager.

    streamlit run streamlit_app.py

It talks to the same ComplaintManager as the terminal menu and the Tkinter
window, so all three can be open at once on the same SQLite database.
To use a JSON file instead:  CCM_DATA=data/my.json streamlit run streamlit_app.py
"""
import html
import os
import tempfile
from datetime import date

import pandas as pd
import streamlit as st

import applog
import importer
import reports
import storage
import validators as v
from manager import ComplaintManager

GREEN = "#1b6b4a"
GREEN_DARK = "#14533a"
GREEN_LIGHT = "#2e8b6a"

PRIORITY_COLORS = {"Low": "#6b8f7f", "Medium": "#d9a21b", "High": "#e8742c", "Critical": "#d64545"}
STATUS_COLORS = {"Open": "#3b7dd8", "In Progress": "#d9a21b", "Resolved": "#1b6b4a", "Rejected": "#8a8f98"}
CATEGORY_ICONS = {
    "Hostel": "🏠", "Academics": "📚", "Library": "📖", "Canteen": "🍽️",
    "Transport": "🚌", "Infrastructure": "🏗️", "Administration": "🗂️", "Other": "💬",
}

CSS = f"""
<style>
.block-container {{ padding-top: 1.4rem; max-width: 1250px; }}
#MainMenu, footer {{ visibility: hidden; }}

.hero {{
    background: linear-gradient(120deg, {GREEN_DARK} 0%, {GREEN} 55%, {GREEN_LIGHT} 100%);
    border-radius: 18px; padding: 26px 32px; margin-bottom: 18px; color: white;
    box-shadow: 0 8px 24px rgba(27,107,74,.25);
}}
.hero h1 {{ margin: 0; font-size: 2rem; font-weight: 800; color: white; padding: 0; }}
.hero p  {{ margin: 6px 0 0 0; opacity: .88; font-size: 1rem; }}

.kpi {{
    background: white; border-radius: 14px; padding: 16px 18px;
    border: 1px solid #e3ece7; border-left: 6px solid {GREEN};
    box-shadow: 0 2px 10px rgba(0,0,0,.05);
}}
.kpi .label {{ font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; color: #5f7a6d; font-weight: 600; }}
.kpi .value {{ font-size: 1.9rem; font-weight: 800; color: #17342a; line-height: 1.2; }}
.kpi .sub   {{ font-size: .8rem; color: #7b8f85; }}
.kpi.red    {{ border-left-color: #d64545; }}
.kpi.amber  {{ border-left-color: #d9a21b; }}
.kpi.blue   {{ border-left-color: #3b7dd8; }}

.badge {{
    display: inline-block; padding: 3px 11px; border-radius: 999px;
    font-size: .76rem; font-weight: 700; color: white; margin-right: 6px;
}}
.card {{
    background: white; border: 1px solid #e3ece7; border-radius: 16px;
    padding: 20px 24px; box-shadow: 0 2px 12px rgba(0,0,0,.05); margin-bottom: 14px;
}}
.card h3 {{ margin: 0 0 8px 0; color: #17342a; }}
.meta {{ color: #5f7a6d; font-size: .9rem; margin: 2px 0; }}
.desc {{
    background: #f3f6f4; border-radius: 10px; padding: 12px 16px; margin: 12px 0;
    color: #25382f; font-size: .98rem; line-height: 1.5;
}}
.late {{ color: #d64545; font-weight: 700; }}

.timeline {{ border-left: 3px solid #cfe3d8; margin-left: 6px; padding-left: 16px; }}
.timeline .ev {{ margin: 0 0 10px 0; font-size: .88rem; color: #31453b; position: relative; }}
.timeline .ev:before {{
    content: ""; width: 10px; height: 10px; background: {GREEN}; border-radius: 50%;
    position: absolute; left: -22px; top: 5px;
}}
.timeline .when {{ color: #7b8f85; font-size: .78rem; display: block; }}

.warn {{ border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; font-size: .92rem; border-left: 5px solid; }}
.warn.OVERDUE  {{ background: #fdecec; border-color: #d64545; }}
.warn.CRITICAL {{ background: #fff1e6; border-color: #e8742c; }}
.warn.REPEAT   {{ background: #fff8e1; border-color: #d9a21b; }}
.warn.DATA     {{ background: #eef2ff; border-color: #6b7fd7; }}
.warn b {{ margin-right: 8px; }}

section[data-testid="stSidebar"] {{ background: #eef5f1; }}
div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] {{
    background: {GREEN}; border: none; color: white; font-weight: 600; border-radius: 10px;
}}
div.stButton > button[kind="primary"]:hover, div.stFormSubmitButton > button[kind="primary"]:hover {{
    background: {GREEN_DARK};
}}
button[data-baseweb="tab"] {{ font-weight: 600; }}
</style>
"""


# ---------------------------------------------------------------- helpers

def esc(text):
    return html.escape(str(text))


def badge(text, color):
    return f'<span class="badge" style="background:{color}">{esc(text)}</span>'


def kpi(label, value, sub="", tone=""):
    return (f'<div class="kpi {tone}"><div class="label">{esc(label)}</div>'
            f'<div class="value">{esc(value)}</div><div class="sub">{esc(sub)}</div></div>')


def na(value, suffix=""):
    return "n/a" if value is None else f"{value}{suffix}"


def to_frame(complaints):
    rows = []
    for c in complaints:
        rows.append({
            "ID": c.id,
            "Filed": c.date_filed,
            "Student": c.student_name,
            "Roll no": c.roll_no,
            "Category": c.category,
            "Priority": c.priority,
            "Status": c.status,
            "Due": c.due_date,
            "Days late": c.days_late(),
            "Description": c.description,
        })
    columns = ["ID", "Filed", "Student", "Roll no", "Category", "Priority", "Status", "Due", "Days late", "Description"]
    return pd.DataFrame(rows, columns=columns)


def style_frame(df):
    """Colour priority/status cells and tint overdue rows. Falls back to the plain frame."""
    try:
        def row_style(row):
            base = "background-color: #fdecec" if row["Days late"] > 0 else ""
            return [base] * len(row)

        def cell_color(value, palette):
            color = palette.get(value)
            return f"color: {color}; font-weight: 700" if color else ""

        styler = df.style.apply(row_style, axis=1)
        styler = styler.map(lambda x: cell_color(x, PRIORITY_COLORS), subset=["Priority"])
        styler = styler.map(lambda x: cell_color(x, STATUS_COLORS), subset=["Status"])
        return styler
    except Exception:  # old pandas without Styler.map, or jinja2 missing
        return df


def show_table(df, height=420):
    try:
        st.dataframe(style_frame(df), width="stretch", hide_index=True, height=height)
    except TypeError:
        st.dataframe(style_frame(df), use_container_width=True, hide_index=True, height=height)


def show_chart(chart):
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def flash(kind, message):
    st.session_state["flash"] = (kind, message)


def show_flash():
    item = st.session_state.pop("flash", None)
    if item:
        kind, message = item
        {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(message)


# ---------------------------------------------------------------- state

@st.cache_resource
def _init_logging():
    applog.setup()
    return True


def get_manager(path):
    """One manager per data file for this browser session, re-read on every rerun."""
    managers = st.session_state.setdefault("managers", {})
    if path not in managers:
        managers[path] = ComplaintManager(path)
    manager = managers[path]
    manager.reload()  # picks up changes made by the terminal app or the Tk window
    return manager


# ---------------------------------------------------------------- sections

def render_header(manager):
    st.markdown(
        '<div class="hero"><h1>🎓 College Complaint Manager</h1>'
        "<p>Log student complaints, track every one to resolution, and keep an eye on deadlines.</p></div>",
        unsafe_allow_html=True,
    )
    data = reports.summarize(manager.complaints)
    cols = st.columns(5)
    cards = [
        kpi("Total", data["total"], "complaints on record"),
        kpi("Active", data["active_count"], "open or in progress", "blue"),
        kpi("Overdue", data["overdue_count"], "past their due date", "red" if data["overdue_count"] else ""),
        kpi("Resolved", f"{data['resolution_rate']}%", f"{data['resolved_count']} resolved"),
        kpi("Avg. days to resolve", na(data["avg_days_to_resolve"]),
            f"on time: {na(data['on_time_rate'], '%')}", "amber"),
    ]
    for col, card in zip(cols, cards):
        col.markdown(card, unsafe_allow_html=True)
    st.write("")


def render_dashboard(manager):
    data = reports.summarize(manager.complaints)
    if not data["total"]:
        st.info("No complaints yet. Add one from the **New complaint** tab or import a file.")
        return

    import altair as alt

    left, right = st.columns(2)

    with left:
        st.subheader("By status")
        df = pd.DataFrame({"Status": v.STATUSES, "Count": [data["by_status"].get(s, 0) for s in v.STATUSES]})
        chart = alt.Chart(df).mark_arc(innerRadius=60, outerRadius=105).encode(
            theta="Count:Q",
            color=alt.Color("Status:N", sort=v.STATUSES, legend=alt.Legend(orient="right"),
                            scale=alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values()))),
            tooltip=["Status", "Count"],
        ).properties(height=260)
        show_chart(chart)

    with right:
        st.subheader("By priority")
        df = pd.DataFrame({"Priority": v.PRIORITIES, "Count": [data["by_priority"].get(p, 0) for p in v.PRIORITIES]})
        chart = alt.Chart(df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
            x=alt.X("Priority:N", sort=v.PRIORITIES, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Count:Q", axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("Priority:N", legend=None,
                            scale=alt.Scale(domain=list(PRIORITY_COLORS), range=list(PRIORITY_COLORS.values()))),
            tooltip=["Priority", "Count"],
        ).properties(height=260)
        show_chart(chart)

    left, right = st.columns(2)

    with left:
        st.subheader("By category")
        ranked = data["by_category"].most_common()
        df = pd.DataFrame({
            "Category": [f"{CATEGORY_ICONS.get(n, '')} {n}" for n, _ in ranked],
            "Count": [n for _, n in ranked],
            "Avg days to resolve": [data["category_avg_days"].get(n) for n, _ in ranked],
        })
        chart = alt.Chart(df).mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6, color=GREEN_LIGHT).encode(
            y=alt.Y("Category:N", sort="-x", title=None),
            x=alt.X("Count:Q", axis=alt.Axis(tickMinStep=1)),
            tooltip=["Category", "Count", "Avg days to resolve"],
        ).properties(height=300)
        show_chart(chart)

    with right:
        st.subheader("Filed per month")
        months = list(data["by_month"].items())
        df = pd.DataFrame({"Month": [m for m, _ in months], "Complaints": [n for _, n in months]})
        base = alt.Chart(df).encode(
            x=alt.X("Month:N", axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("Complaints:Q", axis=alt.Axis(tickMinStep=1)),
            tooltip=["Month", "Complaints"],
        )
        chart = (base.mark_area(opacity=0.18, color=GREEN) + base.mark_line(color=GREEN, strokeWidth=3)
                 + base.mark_point(color=GREEN, size=70, filled=True)).properties(height=300)
        show_chart(chart)
        st.caption(reports.trend_text(data["by_month"]))

    slow = data["category_avg_days"]
    if slow:
        st.subheader("Average days to resolve, by category")
        df = pd.DataFrame({"Category": list(slow), "Days": list(slow.values())}).sort_values("Days", ascending=False)
        cols = st.columns(min(4, len(df)))
        for i, (_, row) in enumerate(df.iterrows()):
            cols[i % len(cols)].markdown(
                kpi(f"{CATEGORY_ICONS.get(row['Category'], '')} {row['Category']}", f"{row['Days']}", "days on average"),
                unsafe_allow_html=True,
            )


def render_details(manager, c):
    st.markdown(
        f'<div class="card"><h3>{esc(c.id)} &nbsp;·&nbsp; {CATEGORY_ICONS.get(c.category, "")} {esc(c.category)}</h3>'
        f'{badge(c.priority, PRIORITY_COLORS[c.priority])}{badge(c.status, STATUS_COLORS[c.status])}'
        + (f'<span class="late">⚠ {c.days_late()} day(s) overdue</span>' if c.is_overdue() else "")
        + f'<p class="meta">👤 <b>{esc(c.student_name)}</b> ({esc(c.roll_no)})</p>'
        f'<p class="meta">📅 Filed {esc(c.date_filed)} &nbsp;·&nbsp; Due {esc(c.due_date)}'
        + (f' &nbsp;·&nbsp; Closed {esc(c.date_resolved)}' if c.date_resolved else "")
        + f'</p><div class="desc">{esc(c.description)}</div>'
        + (f'<p class="meta">📝 <b>Resolution note:</b> {esc(c.resolution_note)}</p>' if c.resolution_note else "")
        + "</div>",
        unsafe_allow_html=True,
    )

    form_col, history_col = st.columns([3, 2])

    with form_col:
        st.markdown("**Update this complaint**")
        with st.form(f"status_form_{c.id}"):
            new_status = st.selectbox("New status", v.STATUSES, index=v.STATUSES.index(c.status))
            note = st.text_input("Note (required when resolving or rejecting)", max_chars=v.MAX_NOTE)
            if st.form_submit_button("Update status", type="primary"):
                try:
                    manager.update_status(c.id, new_status, note)
                    flash("success", f"{c.id} is now {new_status}.")
                    st.rerun()
                except (ValueError, RuntimeError, TimeoutError) as err:
                    st.error(str(err))

        with st.form(f"category_form_{c.id}"):
            new_cat = st.selectbox("New category", v.CATEGORIES, index=v.CATEGORIES.index(c.category))
            if st.form_submit_button("Change category"):
                try:
                    manager.assign_category(c.id, new_cat)
                    flash("success", f"{c.id} moved to {new_cat}.")
                    st.rerun()
                except (ValueError, RuntimeError, TimeoutError) as err:
                    st.error(str(err))

    with history_col:
        st.markdown("**History**")
        events = "".join(
            f'<div class="ev"><span class="when">{esc(h[:16])}</span>{esc(h[16:].strip())}</div>'
            for h in c.history
        ) or '<div class="ev">No history recorded.</div>'
        st.markdown(f'<div class="timeline">{events}</div>', unsafe_allow_html=True)


def render_complaints(manager):
    f1, f2, f3, f4 = st.columns([2.2, 1.2, 1.2, 1.2])
    keyword = f1.text_input("🔍 Search", placeholder="name, roll no, ID or keyword", key="f_keyword")
    category = f2.selectbox("Category", ["All"] + v.CATEGORIES, key="f_category")
    status = f3.selectbox("Status", ["All"] + v.STATUSES, key="f_status")
    priority = f4.selectbox("Priority", ["All"] + v.PRIORITIES, key="f_priority")
    only_late = st.toggle("Show overdue only", key="f_late")

    rows = manager.search(
        keyword,
        "" if category == "All" else category,
        "" if status == "All" else status,
        "" if priority == "All" else priority,
    )
    if only_late:
        rows = [c for c in rows if c.is_overdue()]
    rows.sort(key=lambda c: c.id, reverse=True)

    st.caption(f"Showing {len(rows)} of {len(manager.complaints)} complaints · overdue rows are tinted red")
    if not rows:
        st.info("No complaints match those filters.")
        return
    show_table(to_frame(rows))

    st.markdown("### Complaint details")
    labels = {c.id: f"{c.id} — {c.student_name} — {c.category} ({c.status})" for c in rows}
    chosen = st.selectbox("Pick a complaint", list(labels), format_func=labels.get, key="picked_id")
    render_details(manager, manager.get(chosen))


def render_form(manager):
    st.markdown("### Log a new complaint")
    version = st.session_state.setdefault("form_version", 0)
    key = lambda name: f"{name}_{version}"  # noqa: E731  (a new version = a fresh, empty form)

    with st.form(f"new_complaint_{version}"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Student name", key=key("name"), placeholder="e.g. Ananya Rao")
        roll = c2.text_input("Roll number", key=key("roll"), placeholder="e.g. 22CS1042")
        c3, c4, c5 = st.columns(3)
        category = c3.selectbox("Category", v.CATEGORIES, key=key("cat"))
        priority = c4.selectbox("Priority", v.PRIORITIES, index=1, key=key("prio"))
        filed = c5.date_input("Date filed", value=date.today(), max_value=date.today(), key=key("date"))
        description = st.text_area(
            "What happened?", key=key("desc"), height=140, max_chars=v.MAX_DESC,
            placeholder=f"Describe the problem ({v.MIN_DESC}-{v.MAX_DESC} characters)",
        )
        st.caption("Due dates are set from priority: " + " · ".join(
            f"{p} {d} days" for p, d in sorted(v.SLA_DAYS.items(), key=lambda x: x[1])))
        submitted = st.form_submit_button("Submit complaint", type="primary")

    if submitted:
        try:
            record = manager.add(name, roll, category, description, priority, filed.isoformat())
            st.session_state["form_version"] = version + 1
            flash("success", f"Complaint {record.id} logged. It is due on {record.due_date}.")
            st.rerun()
        except (ValueError, RuntimeError, TimeoutError) as err:
            st.error(str(err))


def render_warnings(manager):
    flags = reports.warnings(manager.complaints)
    if not flags:
        st.success("Nothing needs attention right now. 🎉")
        return
    counts = {}
    for label, _ in flags:
        counts[label] = counts.get(label, 0) + 1
    st.caption(" · ".join(f"{label}: {n}" for label, n in counts.items()))
    wanted = st.multiselect("Show", list(counts), default=list(counts))
    for label, text in flags:
        if label in wanted:
            st.markdown(f'<div class="warn {esc(label)}"><b>{esc(label)}</b>{esc(text)}</div>',
                        unsafe_allow_html=True)


def render_import_export(manager):
    left, right = st.columns(2)

    with left:
        st.markdown("### 📥 Import")
        st.caption("CSV or JSON with columns: " + ", ".join(importer.REQUIRED)
                   + ". Optional: " + ", ".join(importer.OPTIONAL) + ".")
        upload = st.file_uploader("Choose a file", type=["csv", "json"])
        if upload is not None and st.button("Import file", type="primary"):
            suffix = os.path.splitext(upload.name)[1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(upload.getvalue())
                tmp_path = tmp.name
            try:
                added, errors = importer.import_file(manager, tmp_path)
                st.session_state["import_result"] = (upload.name, added, errors)
                st.rerun()
            except (ValueError, OSError, UnicodeDecodeError) as err:
                st.error(f"Couldn't import that file: {err}")
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        result = st.session_state.get("import_result")
        if result:
            name, added, errors = result
            (st.success if added else st.warning)(f"{name}: {added} added, {len(errors)} rejected.")
            if errors:
                with st.expander(f"Rejected rows ({len(errors)})", expanded=True):
                    for line in errors:
                        st.write("• " + line)

    with right:
        st.markdown("### 📤 Export reports")
        st.caption(f"Files are saved in `{os.path.relpath(storage.EXPORT_DIR)}` and can be downloaded here.")
        if st.button("Generate all reports", type="primary"):
            try:
                st.session_state["export_paths"] = reports.export_all(manager.complaints, storage.EXPORT_DIR)
            except OSError as err:
                st.error(f"Couldn't write the reports: {err}")

        mimes = {".md": "text/markdown", ".txt": "text/plain", ".csv": "text/csv",
                 ".json": "application/json", ".png": "image/png"}
        for path in st.session_state.get("export_paths", []):
            if not os.path.exists(path):
                continue
            with open(path, "rb") as handle:
                st.download_button(
                    f"⬇ {os.path.basename(path)}", handle.read(), file_name=os.path.basename(path),
                    mime=mimes.get(os.path.splitext(path)[1], "application/octet-stream"), key=f"dl_{path}",
                )
        if st.session_state.get("export_paths") and not any(p.endswith(".png") for p in st.session_state["export_paths"]):
            st.caption("Install matplotlib (`pip install -r requirements-optional.txt`) to also get the PNG chart.")


def render_sidebar(manager, path):
    with st.sidebar:
        st.markdown("## 🎓 Complaint Manager")
        st.caption("GreenFuture Hack · Project #23")
        st.divider()
        late = manager.overdue()
        st.metric("Overdue right now", len(late))
        if late:
            st.markdown("**Most overdue**")
            for c in late[:5]:
                st.markdown(f"- `{c.id}` {c.student_name} — **{c.days_late()}d** late")
        st.divider()
        if st.button("🔄 Refresh data"):
            st.rerun()
        st.caption(f"Storage: {manager.repo.name}\n\n`{os.path.basename(path)}`")
        st.caption("Shared with the terminal and Tkinter apps — changes appear here on refresh.")



# ---------------------------------------------------------------- main

def main():
    st.set_page_config(page_title="College Complaint Manager", page_icon="🎓", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    _init_logging()

    path = os.environ.get("CCM_DATA", storage.DEFAULT_FILE)
    try:
        manager = get_manager(path)
    except Exception as err:  # bad path, locked file, etc.
        st.error(f"Couldn't open the data file `{path}`: {err}")
        st.stop()

    for note in manager.notices:
        if note not in st.session_state.setdefault("seen_notices", []):
            st.session_state["seen_notices"].append(note)
            st.warning(note)

    render_sidebar(manager, path)
    render_header(manager)
    show_flash()

    overdue = len(manager.overdue())
    tabs = st.tabs([
        "📊 Dashboard", "📋 Complaints", "➕ New complaint",
        f"🚨 Warnings{f' ({overdue})' if overdue else ''}", "📁 Import / Export",
    ])
    with tabs[0]:
        render_dashboard(manager)
    with tabs[1]:
        render_complaints(manager)
    with tabs[2]:
        render_form(manager)
    with tabs[3]:
        render_warnings(manager)
    with tabs[4]:
        render_import_export(manager)


main()
