"""Tkinter window for the complaint manager.

Uses exactly the same ComplaintManager as the terminal version, so both
interfaces read and write the same data file.
"""
import os
import sqlite3
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

import applog
import importer
import reports
import storage
import validators as v
from manager import ComplaintManager

BG = "#f3f6f4"
GREEN = "#1b6b4a"
RED_ROW = "#fde8e8"


REFRESH_MS = 5000  # how often to check whether the terminal app changed anything


class ComplaintApp(tk.Tk):
    def __init__(self, path=storage.DEFAULT_FILE):
        super().__init__()
        self.title("College Complaint Manager - GreenFuture Hack #23")
        self.geometry("1120x700")
        self.minsize(980, 620)
        self.configure(bg=BG)

        self.manager = ComplaintManager(path)
        self.keyword = tk.StringVar()
        self.cat_filter = tk.StringVar(value="All")
        self.status_filter = tk.StringVar(value="All")
        self.prio_filter = tk.StringVar(value="All")

        self._setup_style()
        self._build_header()
        self._build_tabs()
        self.refresh_table()

        # traces go on last, otherwise they'd fire before the table exists
        self.keyword.trace_add("write", lambda *_: self.refresh_table())

        for note in self.manager.notices:
            messagebox.showinfo("Heads up", note)
        self.after(REFRESH_MS, self._auto_refresh)

    # ------------------------------------------------------------ layout

    def _setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, font=("TkDefaultFont", 10))
        style.configure("TLabelframe", background=BG)
        style.configure("TLabelframe.Label", background=BG, foreground=GREEN, font=("TkDefaultFont", 10, "bold"))
        style.configure("Treeview", rowheight=26, font=("TkDefaultFont", 10))
        style.configure("Treeview.Heading", font=("TkDefaultFont", 10, "bold"))
        style.configure("Accent.TButton", background=GREEN, foreground="white", padding=6)
        style.map("Accent.TButton", background=[("active", "#14533a")])
        style.configure("TButton", padding=6)

    def _build_header(self):
        bar = tk.Frame(self, bg=GREEN)
        bar.pack(fill="x")
        tk.Label(bar, text="College Complaint Manager", bg=GREEN, fg="white",
                 font=("TkDefaultFont", 18, "bold")).pack(side="left", padx=16, pady=10)
        self.stats_label = tk.Label(bar, text="", bg=GREEN, fg="#d7efe4", font=("TkDefaultFont", 10))
        self.stats_label.pack(side="right", padx=16)

    def _build_tabs(self):
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)

        self.list_tab = ttk.Frame(self.tabs)
        self.form_tab = ttk.Frame(self.tabs)
        self.summary_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.list_tab, text="  Complaints  ")
        self.tabs.add(self.form_tab, text="  New complaint  ")
        self.tabs.add(self.summary_tab, text="  Summary  ")

        self._build_list_tab()
        self._build_form_tab()
        self._build_summary_tab()
        self.tabs.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _combo(self, parent, label, var, values, width=14):
        ttk.Label(parent, text=label).pack(side="left", padx=(12, 4))
        box = ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=width)
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_table())

    def _build_list_tab(self):
        top = ttk.Frame(self.list_tab)
        top.pack(fill="x", padx=10, pady=(10, 6))
        ttk.Label(top, text="Search").pack(side="left")
        ttk.Entry(top, textvariable=self.keyword, width=26).pack(side="left", padx=(6, 0))
        self._combo(top, "Category", self.cat_filter, ["All"] + v.CATEGORIES)
        self._combo(top, "Status", self.status_filter, ["All"] + v.STATUSES, width=11)
        self._combo(top, "Priority", self.prio_filter, ["All"] + v.PRIORITIES, width=9)
        ttk.Button(top, text="Clear", command=self.clear_filters).pack(side="left", padx=12)

        holder = ttk.Frame(self.list_tab)
        holder.pack(fill="both", expand=True, padx=10)
        columns = ("id", "filed", "student", "category", "priority", "status", "due")
        widths = (70, 95, 190, 120, 85, 100, 95)
        titles = ("ID", "Filed", "Student", "Category", "Priority", "Status", "Due")
        self.tree = ttk.Treeview(holder, columns=columns, show="headings", selectmode="browse")
        for col, w, title in zip(columns, widths, titles):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=w, anchor="w")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.tag_configure("overdue", background=RED_ROW)
        self.tree.tag_configure("resolved", foreground=GREEN)
        self.tree.tag_configure("rejected", foreground="#8a8a8a")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.show_details())

        details = ttk.LabelFrame(self.list_tab, text="Details")
        details.pack(fill="x", padx=10, pady=8)
        self.details = tk.Text(details, height=7, wrap="word", state="disabled", bg="white",
                               relief="flat", font=("TkDefaultFont", 10))
        self.details.pack(fill="x", padx=6, pady=6)

        buttons = ttk.Frame(self.list_tab)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Update status", style="Accent.TButton",
                   command=self.change_status).pack(side="left")
        ttk.Button(buttons, text="Change category", command=self.change_category).pack(side="left", padx=6)
        ttk.Button(buttons, text="Import file...", command=self.import_csv).pack(side="right")
        ttk.Button(buttons, text="Refresh", command=self.manual_refresh).pack(side="right", padx=6)
        ttk.Button(buttons, text="Export reports", command=self.export_reports).pack(side="right", padx=6)

    def _build_form_tab(self):
        box = ttk.LabelFrame(self.form_tab, text="Log a complaint")
        box.pack(anchor="n", padx=30, pady=24, ipadx=14, ipady=10)

        self.f_name = tk.StringVar()
        self.f_roll = tk.StringVar()
        self.f_cat = tk.StringVar()
        self.f_prio = tk.StringVar(value="Medium")
        self.f_date = tk.StringVar(value=date.today().isoformat())

        rows = [
            ("Student name", ttk.Entry(box, textvariable=self.f_name, width=40)),
            ("Roll number", ttk.Entry(box, textvariable=self.f_roll, width=20)),
            ("Category", ttk.Combobox(box, textvariable=self.f_cat, values=v.CATEGORIES, state="readonly", width=22)),
            ("Priority", ttk.Combobox(box, textvariable=self.f_prio, values=v.PRIORITIES, state="readonly", width=22)),
            ("Date filed", ttk.Entry(box, textvariable=self.f_date, width=20)),
        ]
        for i, (label, widget) in enumerate(rows):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w", padx=10, pady=6)
            widget.grid(row=i, column=1, sticky="w", padx=10, pady=6)

        ttk.Label(box, text="What happened").grid(row=5, column=0, sticky="nw", padx=10, pady=6)
        self.f_desc = tk.Text(box, width=50, height=6, wrap="word", font=("TkDefaultFont", 10))
        self.f_desc.grid(row=5, column=1, sticky="w", padx=10, pady=6)

        self.form_msg = ttk.Label(box, text="", wraplength=420)
        self.form_msg.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=4)

        actions = ttk.Frame(box)
        actions.grid(row=7, column=0, columnspan=2, sticky="e", padx=10, pady=(6, 0))
        ttk.Button(actions, text="Clear", command=self.clear_form).pack(side="left", padx=6)
        ttk.Button(actions, text="Submit complaint", style="Accent.TButton",
                   command=self.submit_complaint).pack(side="left")

    def _build_summary_tab(self):
        left = ttk.Frame(self.summary_tab)
        left.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)
        self.summary_text = tk.Text(left, width=52, wrap="none", bg="white", relief="flat",
                                    font=("TkFixedFont", 10), state="disabled")
        self.summary_text.pack(fill="both", expand=True)

        right = ttk.Frame(self.summary_tab)
        right.pack(side="right", fill="both", expand=True, padx=(5, 10), pady=10)
        self.chart = tk.Canvas(right, bg="white", height=330, highlightthickness=0)
        self.chart.pack(fill="x")
        ttk.Label(right, text="Warnings", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(10, 2))
        self.warn_box = tk.Text(right, height=9, wrap="word", bg="white", relief="flat",
                                font=("TkDefaultFont", 9), state="disabled")
        self.warn_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------ table

    def refresh_table(self, keep=None):
        def value(var):
            return "" if var.get() == "All" else var.get()

        rows = self.manager.search(self.keyword.get(), value(self.cat_filter),
                                   value(self.status_filter), value(self.prio_filter))
        rows.sort(key=lambda c: c.id)
        self.tree.delete(*self.tree.get_children())
        for c in rows:
            tag = ()
            if c.is_overdue():
                tag = ("overdue",)
            elif c.status == "Resolved":
                tag = ("resolved",)
            elif c.status == "Rejected":
                tag = ("rejected",)
            self.tree.insert("", "end", iid=c.id, tags=tag, values=(
                c.id, c.date_filed, c.student_name, c.category, c.priority, c.status, c.due_date))
        if keep and self.tree.exists(keep):
            self.tree.selection_set(keep)
            self.tree.see(keep)
        self.show_details()
        self._update_stats()

    def _update_stats(self):
        total = len(self.manager.complaints)
        active = sum(1 for c in self.manager.complaints if c.is_active())
        late = len(self.manager.overdue())
        self.stats_label.config(text=f"{total} complaints   |   {active} active   |   {late} overdue")

    def _signature(self):
        return tuple((c.id, c.status, c.category) for c in self.manager.complaints)

    def _reload_if_changed(self):
        before = self._signature()
        self.manager.reload()
        if self._signature() != before:
            chosen = self.tree.selection()
            self.refresh_table(keep=chosen[0] if chosen else None)
            if self.tabs.select() == str(self.summary_tab):
                self.refresh_summary()

    def _auto_refresh(self):
        try:
            self._reload_if_changed()
        except (OSError, sqlite3.Error):
            pass  # try again next time, the file may just be busy
        self.after(REFRESH_MS, self._auto_refresh)

    def manual_refresh(self):
        try:
            self._reload_if_changed()
        except (OSError, sqlite3.Error) as err:
            messagebox.showerror("Refresh", f"Couldn't read the data: {err}")

    def clear_filters(self):
        self.cat_filter.set("All")
        self.status_filter.set("All")
        self.prio_filter.set("All")
        self.keyword.set("")
        self.refresh_table()

    def selected(self):
        chosen = self.tree.selection()
        return self.manager.get(chosen[0]) if chosen else None

    def show_details(self):
        c = self.selected()
        if c is None:
            text = "Select a complaint above to see the full details."
        else:
            text = (f"{c.id} - {c.student_name} ({c.roll_no})\n"
                    f"{c.description}\n"
                    f"Filed {c.date_filed}, due {c.due_date}"
                    + (f"  -  OVERDUE by {c.days_late()} day(s)" if c.is_overdue() else "") + "\n")
            if c.resolution_note:
                text += f"Outcome ({c.date_resolved}): {c.resolution_note}\n"
            if c.history:
                text += "History:  " + "   |   ".join(c.history[-3:])
        self.details.config(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.config(state="disabled")

    # ------------------------------------------------------------ actions

    def _dialog(self, title, label, options, current, ask_note, action):
        """Small popup used for both 'update status' and 'change category'."""
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self)
        win.resizable(False, False)

        value = tk.StringVar(value=current)
        note = tk.StringVar()
        ttk.Label(win, text=label).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 4))
        ttk.Combobox(win, textvariable=value, values=options, state="readonly",
                     width=24).grid(row=0, column=1, padx=14, pady=(14, 4))
        if ask_note:
            ttk.Label(win, text="Note").grid(row=1, column=0, sticky="w", padx=14, pady=4)
            ttk.Entry(win, textvariable=note, width=40).grid(row=1, column=1, padx=14, pady=4)
        error = ttk.Label(win, text="", foreground="#b00020", wraplength=320)
        error.grid(row=2, column=0, columnspan=2, sticky="w", padx=14)

        def apply():
            try:
                action(value.get(), note.get())
            except (ValueError, OSError, sqlite3.Error) as err:
                error.config(text=str(err))
                return
            win.destroy()

        buttons = ttk.Frame(win)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", padx=14, pady=12)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="left", padx=6)
        ttk.Button(buttons, text="Save", style="Accent.TButton", command=apply).pack(side="left")
        win.grab_set()
        self.wait_window(win)

    def _need_selection(self):
        c = self.selected()
        if c is None:
            messagebox.showinfo("Pick a complaint", "Click a complaint in the table first.")
        return c

    def change_status(self):
        c = self._need_selection()
        if c is None:
            return

        def apply(new_status, note):
            self.manager.update_status(c.id, new_status, note)
            self.refresh_table(keep=c.id)

        self._dialog(f"Update {c.id}", "New status", v.STATUSES, c.status, True, apply)

    def change_category(self):
        c = self._need_selection()
        if c is None:
            return

        def apply(new_category, _note):
            self.manager.assign_category(c.id, new_category)
            self.refresh_table(keep=c.id)

        self._dialog(f"Category for {c.id}", "New category", v.CATEGORIES, c.category, False, apply)

    def clear_form(self):
        self.f_name.set("")
        self.f_roll.set("")
        self.f_cat.set("")
        self.f_prio.set("Medium")
        self.f_date.set(date.today().isoformat())
        self.f_desc.delete("1.0", "end")
        self.form_msg.config(text="")

    def submit_complaint(self):
        try:
            c = self.manager.add(self.f_name.get(), self.f_roll.get(), self.f_cat.get(),
                                 self.f_desc.get("1.0", "end"), self.f_prio.get(), self.f_date.get())
        except ValueError as err:
            self.form_msg.config(text=f"Problem: {err}", foreground="#b00020")
            return
        except (OSError, sqlite3.Error, RuntimeError) as err:
            messagebox.showerror("Couldn't save", str(err))
            return
        self.clear_form()
        self.form_msg.config(text=f"Logged as {c.id}, due {c.due_date}.", foreground=GREEN)
        self.clear_filters()
        self.tabs.select(self.list_tab)
        self.tree.selection_set(c.id)
        self.tree.see(c.id)

    def import_csv(self):
        path = filedialog.askopenfilename(
            title="Choose a CSV or JSON file", initialdir=storage.DATA_DIR,
            filetypes=[("CSV or JSON", "*.csv *.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            added, errors = importer.import_file(self.manager, path)
        except FileNotFoundError:
            messagebox.showerror("Import", "That file doesn't exist.")
            return
        except (ValueError, OSError, sqlite3.Error) as err:
            messagebox.showerror("Import", f"Couldn't read that file:\n{err}")
            return
        self.refresh_table()
        message = f"Imported {added} row(s), rejected {len(errors)}."
        if errors:
            message += "\n\n" + "\n".join(errors[:8])
            if len(errors) > 8:
                message += f"\n...and {len(errors) - 8} more"
            message += "\n\nRejected rows are also written to the log file."
        messagebox.showinfo("Import finished", message)

    def export_reports(self):
        try:
            paths = reports.export_all(self.manager.complaints, storage.EXPORT_DIR)
        except OSError as err:
            messagebox.showerror("Export", str(err))
            return
        messagebox.showinfo("Export finished", "Saved:\n" + "\n".join(os.path.relpath(p) for p in paths))

    # ------------------------------------------------------------ summary tab

    def _on_tab_change(self, _event):
        if self.tabs.select() == str(self.summary_tab):
            self.refresh_summary()

    def _fill(self, widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def refresh_summary(self):
        data = reports.summarize(self.manager.complaints)
        self._fill(self.summary_text, "\n".join(reports.format_summary(data)))
        flags = reports.warnings(self.manager.complaints)
        shown = [f"[{label}] {text}" for label, text in flags[:25]]
        if len(flags) > 25:
            shown.append(f"...and {len(flags) - 25} more")
        self._fill(self.warn_box, "\n".join(shown) if shown else "Nothing needs attention.")
        self.draw_chart(data["by_category"])

    def draw_chart(self, counts):
        cv = self.chart
        cv.delete("all")
        cv.create_text(12, 16, text="Complaints by category", anchor="w", font=("TkDefaultFont", 11, "bold"))
        if not counts:
            return
        biggest = max(counts.values())
        y = 42
        for name, n in counts.most_common():
            length = int(250 * n / biggest)
            cv.create_text(12, y + 10, text=name, anchor="w", font=("TkDefaultFont", 9))
            cv.create_rectangle(120, y, 120 + length, y + 20, fill=GREEN, outline="")
            cv.create_text(126 + length, y + 10, text=str(n), anchor="w", font=("TkDefaultFont", 9))
            y += 34


def run(path=storage.DEFAULT_FILE):
    ComplaintApp(path).mainloop()


if __name__ == "__main__":
    applog.setup()
    run()
