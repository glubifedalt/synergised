"""
main_window.py – Synergy Dashboard Tool
Main Qt application: student list, detail panel, compass, live-map, export.
"""

import sys
import json
import csv
import io
from datetime import datetime
from typing import Optional, List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QTextEdit, QComboBox, QSpinBox, QTabWidget, QFrame,
    QMessageBox, QInputDialog, QFileDialog, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
    QDialogButtonBox, QGroupBox, QStatusBar, QFormLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPalette, QPixmap

from database import DB
from compass_chart import CompassChart
from scraper import SynergyScaper, FIELD_LABELS
from live_map_panel import LiveMapPanel, WEBENGINE_OK
from contact_log import ContactLogWidget, ensure_contact_table
from call_sheet import generate_call_sheet
from bulk_sync import BulkSyncDialog
from discovery_dialog import DiscoveryDialog
from timetable_capture import TimetableCapture
from timetable_widget import StudentTimetablePanel, TimetableBrowserWidget

# ═══════════════════════════════════════════════════════════════
#  STYLESHEET  (imported from styles.py)
# ═══════════════════════════════════════════════════════════════
from styles import QSS


# ═══════════════════════════════════════════════════════════════
#  STUDENT DETAIL DIALOG
# ═══════════════════════════════════════════════════════════════
class StudentDialog(QDialog):
    def __init__(self, db: DB, student_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.student_id = student_id
        self.setWindowTitle("Edit Student" if student_id else "Add Student")
        self.setMinimumWidth(420)
        self.setStyleSheet(QSS)
        self._build()
        if student_id:
            self._load()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(8)

        self.f_name = QLineEdit(); self.f_name.setPlaceholderText("Full name")
        self.f_ref  = QLineEdit(); self.f_ref.setPlaceholderText("Synergy student ID")
        self.f_year = QSpinBox(); self.f_year.setRange(7, 13); self.f_year.setValue(7)
        self.f_form = QLineEdit(); self.f_form.setPlaceholderText("e.g. 9A")
        self.f_url  = QLineEdit(); self.f_url.setPlaceholderText("https://synergy…/student/123")

        phones_group = QGroupBox("Phone Numbers")
        pg = QVBoxLayout(phones_group)
        self.phone_inputs = []
        for i in range(3):
            row = QHBoxLayout()
            lbl = QLabel(f"Phone {i+1}:")
            lbl.setFixedWidth(60)
            lbl.setStyleSheet("color:#5b9bd5;font-size:11px;")
            inp = QLineEdit(); inp.setPlaceholderText("07xxx xxxxxx")
            self.phone_inputs.append(inp)
            row.addWidget(lbl); row.addWidget(inp)
            pg.addLayout(row)

        self.f_notes = QTextEdit(); self.f_notes.setPlaceholderText("Notes…")
        self.f_notes.setMaximumHeight(80)

        form.addRow("Name *", self.f_name)
        form.addRow("Synergy Ref", self.f_ref)
        form.addRow("Year Group", self.f_year)
        form.addRow("Form Class", self.f_form)
        form.addRow("Dashboard URL", self.f_url)
        layout.addLayout(form)
        layout.addWidget(phones_group)
        form2 = QFormLayout()
        form2.addRow("Notes", self.f_notes)
        layout.addLayout(form2)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load(self):
        s = self.db.get_student(self.student_id)
        if not s: return
        self.f_name.setText(s.get("name",""))
        self.f_ref.setText(s.get("student_ref",""))
        self.f_year.setValue(s.get("year_group",7))
        self.f_form.setText(s.get("form_class",""))
        self.f_url.setText(s.get("synergy_url",""))
        self.f_notes.setPlainText(s.get("notes",""))
        phones = s.get("phones",[])
        for i, inp in enumerate(self.phone_inputs):
            inp.setText(phones[i] if i < len(phones) else "")

    def _save(self):
        name = self.f_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        phones = [inp.text().strip() for inp in self.phone_inputs if inp.text().strip()]
        kwargs = dict(
            name=name,
            ref=self.f_ref.text().strip(),
            year=self.f_year.value(),
            form=self.f_form.text().strip(),
            phones=phones,
            url=self.f_url.text().strip(),
        )
        if self.student_id:
            self.db.update_student(self.student_id, **{
                "name": kwargs["name"],
                "student_ref": kwargs["ref"],
                "year_group": kwargs["year"],
                "form_class": kwargs["form"],
                "phones": kwargs["phones"],
                "synergy_url": kwargs["url"],
                "notes": self.f_notes.toPlainText().strip(),
            })
        else:
            self.student_id = self.db.add_student(**kwargs)
        self.accept()


# ═══════════════════════════════════════════════════════════════
#  ADD BEHAVIOUR DIALOG
# ═══════════════════════════════════════════════════════════════
class AddBehaviourDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record Behaviour")
        self.setStyleSheet(QSS)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        self.cb_type = QComboBox()
        self.cb_type.addItems(["praise", "sanction"])
        self.sp_points = QSpinBox(); self.sp_points.setRange(1, 20); self.sp_points.setValue(1)
        self.le_reason = QLineEdit(); self.le_reason.setPlaceholderText("Reason / description…")

        form.addRow("Type:", self.cb_type)
        form.addRow("Points:", self.sp_points)
        form.addRow("Reason:", self.le_reason)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


# ═══════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DB()
        ensure_contact_table(self.db.conn)
        self.db.init_timetable_schema()
        self._timetable_capture: Optional[TimetableCapture] = None
        self.current_student_id: Optional[int] = None
        self.setWindowTitle("Synergy Teacher Dashboard")
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(QSS)

        self._build_ui()
        self._refresh_student_list()
        self._update_status()

    # ── UI BUILD ──────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)

        # ── Sidebar ──
        sidebar = QWidget(); sidebar.setObjectName("sidebar")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        logo = QLabel("SYNERGY"); logo.setObjectName("logo")
        sub  = QLabel("TEACHER DASHBOARD"); sub.setObjectName("subtitle")
        sb_layout.addWidget(logo)
        sb_layout.addWidget(sub)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#1e3a6e;")
        sb_layout.addWidget(sep)

        # Search
        self.le_search = QLineEdit(); self.le_search.setObjectName("search")
        self.le_search.setPlaceholderText("🔍  Search students…")
        self.le_search.textChanged.connect(self._refresh_student_list)
        sb_layout.addSpacing(8)
        sb_layout.addWidget(self.le_search)
        sb_layout.addSpacing(6)

        # Student list
        self.lst_students = QListWidget()
        self.lst_students.setObjectName("student_list")
        self.lst_students.currentRowChanged.connect(self._on_student_selected)
        sb_layout.addWidget(self.lst_students, 1)

        # Sidebar buttons
        btn_add = QPushButton("＋  Add Student")
        btn_add.clicked.connect(self._add_student)
        btn_compass = QPushButton("🧭  Compass View")
        btn_compass.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        btn_bulk = QPushButton("⟳  Bulk Sync")
        btn_bulk.clicked.connect(self._bulk_sync)
        btn_callsheet = QPushButton("🖨  Call Sheet")
        btn_callsheet.clicked.connect(self._export_call_sheet)
        btn_export = QPushButton("📊  Export CSV")
        btn_export.clicked.connect(self._export_csv)

        for b in (btn_add, btn_compass, btn_bulk, btn_callsheet, btn_export):
            b.setFixedHeight(34)
            sb_layout.addWidget(b)
        sb_layout.addSpacing(8)

        splitter.addWidget(sidebar)

        # ── Right panel ──
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(10)

        # Top toolbar
        top = QHBoxLayout()
        self.lbl_student_name = QLabel("Select a student →")
        self.lbl_student_name.setStyleSheet(
            "font-size:20px;font-weight:800;color:#e0e8ff;letter-spacing:0.5px;"
        )
        top.addWidget(self.lbl_student_name)
        top.addStretch()

        btn_edit = QPushButton("✏  Edit")
        btn_edit.clicked.connect(self._edit_student)
        btn_del = QPushButton("🗑  Delete")
        btn_del.setObjectName("btn_danger")
        btn_del.clicked.connect(self._delete_student)
        btn_sync = QPushButton("⟳  Sync from Synergy")
        btn_sync.setObjectName("btn_sync")
        btn_sync.clicked.connect(self._sync_student)
        btn_map = QPushButton("🎯  Live Map")
        btn_map.clicked.connect(self._open_live_map)

        for b in (btn_map, btn_sync, btn_edit, btn_del):
            b.setFixedHeight(32)
            top.addWidget(b)
        right_layout.addLayout(top)

        # ── Tabs ──
        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs, 1)

        # Tab 0 – Overview
        self.tab_overview = self._build_overview_tab()
        self.tabs.addTab(self.tab_overview, "📋  Overview")

        # Tab 1 – Behaviours
        self.tab_behaviour = self._build_behaviour_tab()
        self.tabs.addTab(self.tab_behaviour, "📊  Behaviour Log")

        # Tab 2 – Contact Log
        self.tab_contact = ContactLogWidget(self.db.conn)
        self.tabs.addTab(self.tab_contact, "📞  Contacts")

        # Tab 3 – Timetable (per-student)
        self.tab_timetable = StudentTimetablePanel(self.db)
        self.tab_timetable.capture_requested.connect(self._start_timetable_capture)
        self.tabs.addTab(self.tab_timetable, "🗓  Timetable")

        # Tab 4 – Compass
        self.tab_compass = CompassChart()
        self.tab_compass.student_clicked.connect(self._select_student_by_id)
        self.tabs.addTab(self.tab_compass, "🧭  Compass")

        # Tab 5 – All Timetables browser
        self.tab_tt_browser = TimetableBrowserWidget(self.db)
        self.tab_tt_browser.student_selected.connect(self._select_student_by_id)
        self.tabs.addTab(self.tab_tt_browser, "🗂  All Timetables")

        # Tab 6 – Live Map (embedded browser)
        self.tab_livemap = LiveMapPanel(fields=FIELD_LABELS)
        self.tab_livemap.field_mapped.connect(self._on_field_mapped)
        self.tab_livemap.mapping_complete.connect(self._on_mappings_complete)
        self.tab_livemap.discovery_ready.connect(self._on_discovery_ready)
        self.tab_livemap.timetable_region_ready.connect(self._on_timetable_region)
        self.tabs.addTab(self.tab_livemap, "🎯  Live Map")

        # Tab 7 – Settings
        self.tab_settings = self._build_settings_tab()
        self.tabs.addTab(self.tab_settings, "⚙  Settings")

        self.tabs.currentChanged.connect(self._on_tab_changed)

        splitter.addWidget(right)
        splitter.setSizes([255, 845])
        root.addWidget(splitter)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    # ── Overview Tab ──────────────────────────────────────────────────────

    def _build_overview_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(14)

        # Stat cards row
        cards = QHBoxLayout()
        cards.setSpacing(12)

        # Praise card
        self.card_praise = QFrame(); self.card_praise.setObjectName("card_praise")
        cp_l = QVBoxLayout(self.card_praise)
        self.lbl_praise_val = QLabel("0")
        self.lbl_praise_val.setStyleSheet("font-size:36px;font-weight:900;color:#4dd88a;")
        cp_l.addWidget(QLabel("PRAISE POINTS"))
        cp_l.addWidget(self.lbl_praise_val)

        # Sanction card
        self.card_sanc = QFrame(); self.card_sanc.setObjectName("card_sanction")
        cs_l = QVBoxLayout(self.card_sanc)
        self.lbl_sanc_val = QLabel("0")
        self.lbl_sanc_val.setStyleSheet("font-size:36px;font-weight:900;color:#ff9944;")
        cs_l.addWidget(QLabel("SANCTION POINTS"))
        cs_l.addWidget(self.lbl_sanc_val)

        # Phone card
        self.card_phone = QFrame(); self.card_phone.setObjectName("card_phone")
        ph_l = QVBoxLayout(self.card_phone)
        ph_l.addWidget(QLabel("PHONE NUMBERS"))
        self.lbl_phones = QLabel("—")
        self.lbl_phones.setStyleSheet("font-size:14px;color:#7eb8ff;font-weight:600;")
        self.lbl_phones.setWordWrap(True)
        ph_l.addWidget(self.lbl_phones)

        for card in (self.card_praise, self.card_sanc, self.card_phone):
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        # Quick add behaviour
        qa_group = QGroupBox("Quick Record Behaviour")
        qa_l = QHBoxLayout(qa_group)
        btn_add_praise = QPushButton("＋  Add Praise")
        btn_add_praise.setObjectName("btn_praise")
        btn_add_praise.clicked.connect(lambda: self._quick_behaviour("praise"))
        btn_add_sanc = QPushButton("＋  Add Sanction")
        btn_add_sanc.setObjectName("btn_sanction")
        btn_add_sanc.clicked.connect(lambda: self._quick_behaviour("sanction"))
        qa_l.addWidget(btn_add_praise)
        qa_l.addWidget(btn_add_sanc)
        qa_l.addStretch()
        layout.addWidget(qa_group)

        # Details grid
        info_group = QGroupBox("Student Information")
        info_layout = QFormLayout(info_group)
        self.ov_ref    = QLabel("—"); self.ov_ref.setStyleSheet("color:#7eb8ff;")
        self.ov_year   = QLabel("—"); self.ov_year.setStyleSheet("color:#7eb8ff;")
        self.ov_form   = QLabel("—"); self.ov_form.setStyleSheet("color:#7eb8ff;")
        self.ov_url    = QLabel("—"); self.ov_url.setStyleSheet("color:#7eb8ff;word-break:break-all;")
        self.ov_sync   = QLabel("—"); self.ov_sync.setStyleSheet("color:#4a6fa5;font-size:10px;")
        self.ov_notes  = QLabel("—"); self.ov_notes.setWordWrap(True); self.ov_notes.setStyleSheet("color:#8ab0d8;")
        for lbl, val in [
            ("Synergy Ref:", self.ov_ref), ("Year Group:", self.ov_year),
            ("Form Class:", self.ov_form), ("Dashboard URL:", self.ov_url),
            ("Last Synced:", self.ov_sync), ("Notes:", self.ov_notes),
        ]:
            l = QLabel(lbl); l.setStyleSheet("color:#4a6fa5;font-weight:600;")
            info_layout.addRow(l, val)
        layout.addWidget(info_group)
        layout.addStretch()

        return w

    # ── Behaviour Tab ─────────────────────────────────────────────────────

    def _build_behaviour_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        tb = QHBoxLayout()
        btn_add_b = QPushButton("＋  Record Behaviour")
        btn_add_b.setObjectName("btn_sync")
        btn_add_b.clicked.connect(self._add_behaviour)
        btn_del_b = QPushButton("🗑  Remove Selected")
        btn_del_b.setObjectName("btn_danger")
        btn_del_b.clicked.connect(self._delete_behaviour)
        self.cb_filter = QComboBox()
        self.cb_filter.addItems(["All", "Praise only", "Sanctions only"])
        self.cb_filter.currentIndexChanged.connect(self._refresh_behaviour_table)
        tb.addWidget(btn_add_b); tb.addWidget(btn_del_b)
        tb.addStretch()
        tb.addWidget(QLabel("Filter:"))
        tb.addWidget(self.cb_filter)
        layout.addLayout(tb)

        self.tbl_behaviour = QTableWidget(0, 5)
        self.tbl_behaviour.setHorizontalHeaderLabels(["Type", "Points", "Reason", "Date", "ID"])
        self.tbl_behaviour.setColumnHidden(4, True)
        self.tbl_behaviour.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_behaviour.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_behaviour.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.tbl_behaviour, 1)

        return w

    # ── Settings Tab ──────────────────────────────────────────────────────

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(w)
        layout = QVBoxLayout(w)
        layout.setSpacing(14)

        # Synergy URL
        grp_url = QGroupBox("Synergy Base URL")
        url_l = QHBoxLayout(grp_url)
        self.le_base_url = QLineEdit()
        self.le_base_url.setPlaceholderText("https://synergy.school.org.uk/")
        self.le_base_url.setText(self.db.get_setting("synergy_base_url"))
        btn_save_url = QPushButton("Save")
        btn_save_url.clicked.connect(self._save_base_url)
        url_l.addWidget(self.le_base_url, 1)
        url_l.addWidget(btn_save_url)
        layout.addWidget(grp_url)

        # Field mappings viewer
        grp_map = QGroupBox("Saved Field Mappings")
        map_l = QVBoxLayout(grp_map)
        self.tbl_mappings = QTableWidget(0, 3)
        self.tbl_mappings.setHorizontalHeaderLabels(["Field", "Selector", "Sample"])
        self.tbl_mappings.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_mappings.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        map_l.addWidget(self.tbl_mappings)
        btn_open_map = QPushButton("🎯  Open Live Map Tab")
        btn_open_map.setObjectName("btn_sync")
        btn_open_map.clicked.connect(self._open_live_map)
        map_l.addWidget(btn_open_map)
        layout.addWidget(grp_map)

        # Timetable settings
        grp_tt = QGroupBox("Timetable Capture")
        tt_l = QFormLayout(grp_tt)
        self.sp_settle = QSpinBox()
        self.sp_settle.setRange(200, 8000)
        self.sp_settle.setSingleStep(200)
        self.sp_settle.setSuffix(" ms")
        self.sp_settle.setValue(int(self.db.get_setting("timetable_settle_ms", "1200")))
        self.sp_settle.setToolTip(
            "How long to wait after the region is selected before taking the screenshot.\n"
            "Increase if dynamic timetable content hasn't loaded yet."
        )
        btn_save_settle = QPushButton("Save")
        btn_save_settle.clicked.connect(self._save_settle_ms)
        settle_row = QHBoxLayout()
        settle_row.addWidget(self.sp_settle)
        settle_row.addWidget(btn_save_settle)
        tt_l.addRow("Page settle time:", settle_row)
        ocr_note = QLabel(
            "OCR requires: <code>pip install pytesseract pillow</code> "
            "and Tesseract installed on your system."
        )
        ocr_note.setStyleSheet("color:#4a6fa5;font-size:10px;")
        ocr_note.setWordWrap(True)
        tt_l.addRow(ocr_note)
        layout.addWidget(grp_tt)

        # About
        about = QLabel(
            "<b>Synergy Teacher Dashboard Tool</b><br>"
            "Version 1.0 — Offline-capable<br><br>"
            "Data stored locally in: <code>~/.synergy_tool/synergy.db</code><br>"
            "No data leaves your machine except when syncing from Synergy."
        )
        about.setStyleSheet("color:#4a6fa5;font-size:11px;line-height:160%;")
        about.setWordWrap(True)
        layout.addWidget(about)
        layout.addStretch()

        return sa

    # ── DATA / EVENT HANDLERS ─────────────────────────────────────────────

    def _refresh_student_list(self):
        q = self.le_search.text().strip()
        students = self.db.get_students(q)
        self.lst_students.clear()
        for s in students:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            stats = self.db.get_student_stats(s["id"])
            praise   = stats["praise"]
            sanction = stats["sanctions"]
            name = s["name"]
            form = s.get("form_class","")
            year = s.get("year_group","")
            item.setText(f"{name}\n{form}  Yr{year}  |  ✅{praise}  ⚠{sanction}")
            self.lst_students.addItem(item)

            # Colour code by sanctions
            if sanction >= 10:
                item.setForeground(QColor("#ff6b6b"))
            elif sanction >= 5:
                item.setForeground(QColor("#ffaa44"))
            else:
                item.setForeground(QColor("#b0c8e8"))

    def _on_student_selected(self, row: int):
        item = self.lst_students.item(row)
        if not item:
            return
        self.current_student_id = item.data(Qt.ItemDataRole.UserRole)
        self._load_student_detail()

    def _select_student_by_id(self, student_id: int):
        """Select a student in the sidebar list by their DB id (e.g. from compass click)."""
        for i in range(self.lst_students.count()):
            item = self.lst_students.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == student_id:
                self.lst_students.setCurrentRow(i)
                self.tabs.setCurrentIndex(0)   # switch to Overview
                break

    def _load_student_detail(self):
        if not self.current_student_id:
            return
        s = self.db.get_student(self.current_student_id)
        if not s:
            return

        self.lbl_student_name.setText(s["name"])
        stats = self.db.get_student_stats(self.current_student_id)
        self.lbl_praise_val.setText(str(stats["praise"]))
        self.lbl_sanc_val.setText(str(stats["sanctions"]))
        phones = s.get("phones", [])
        self.lbl_phones.setText("\n".join(phones) if phones else "—")

        self.ov_ref.setText(s.get("student_ref","—") or "—")
        self.ov_year.setText(str(s.get("year_group","—")))
        self.ov_form.setText(s.get("form_class","—") or "—")
        self.ov_url.setText(s.get("synergy_url","—") or "—")
        self.ov_sync.setText(s.get("sync_time","Never synced") or "Never synced")
        self.ov_notes.setText(s.get("notes","") or "—")

        self._refresh_behaviour_table()

        # Update contact log tab
        self.tab_contact.set_student(self.current_student_id, phones)

        # Update timetable tab
        self.tab_timetable.set_student(self.current_student_id)

    def _refresh_behaviour_table(self):
        if not self.current_student_id:
            return
        behaviours = self.db.get_behaviours(self.current_student_id)
        filt = self.cb_filter.currentText()
        if filt == "Praise only":
            behaviours = [b for b in behaviours if b["btype"] == "praise"]
        elif filt == "Sanctions only":
            behaviours = [b for b in behaviours if b["btype"] == "sanction"]

        self.tbl_behaviour.setRowCount(0)
        for b in behaviours:
            r = self.tbl_behaviour.rowCount()
            self.tbl_behaviour.insertRow(r)

            type_item = QTableWidgetItem(b["btype"].upper())
            if b["btype"] == "praise":
                type_item.setForeground(QColor("#4dd88a"))
            else:
                type_item.setForeground(QColor("#ff9944"))
            self.tbl_behaviour.setItem(r, 0, type_item)
            self.tbl_behaviour.setItem(r, 1, QTableWidgetItem(str(b["points"])))
            self.tbl_behaviour.setItem(r, 2, QTableWidgetItem(b.get("reason","")))
            self.tbl_behaviour.setItem(r, 3, QTableWidgetItem(str(b.get("event_date",""))[:16]))
            self.tbl_behaviour.setItem(r, 4, QTableWidgetItem(str(b["id"])))

    def _add_student(self):
        dlg = StudentDialog(self.db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_student_list()
            self._update_status()

    def _edit_student(self):
        if not self.current_student_id:
            return
        dlg = StudentDialog(self.db, self.current_student_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_student_list()
            self._load_student_detail()

    def _delete_student(self):
        if not self.current_student_id:
            return
        s = self.db.get_student(self.current_student_id)
        if QMessageBox.question(
            self, "Delete Student",
            f"Delete {s['name']} and all their behaviour records?",
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_student(self.current_student_id)
            self.current_student_id = None
            self.lbl_student_name.setText("Select a student →")
            self._refresh_student_list()
            self._update_status()

    def _quick_behaviour(self, btype: str):
        if not self.current_student_id:
            QMessageBox.information(self, "No student", "Select a student first.")
            return
        dlg = AddBehaviourDialog(self)
        dlg.cb_type.setCurrentText(btype)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.add_behaviour(
                self.current_student_id,
                dlg.cb_type.currentText(),
                dlg.sp_points.value(),
                dlg.le_reason.text().strip(),
            )
            self._load_student_detail()
            self._refresh_student_list()

    def _add_behaviour(self):
        self._quick_behaviour("praise")

    def _delete_behaviour(self):
        rows = self.tbl_behaviour.selectedItems()
        if not rows:
            return
        row = self.tbl_behaviour.currentRow()
        bid_item = self.tbl_behaviour.item(row, 4)
        if not bid_item:
            return
        self.db.delete_behaviour(int(bid_item.text()))
        self._load_student_detail()
        self._refresh_student_list()

    def _sync_student(self):
        if not self.current_student_id:
            QMessageBox.information(self, "No student", "Select a student first.")
            return
        s = self.db.get_student(self.current_student_id)
        url = s.get("synergy_url","").strip()
        if not url:
            QMessageBox.warning(self, "No URL",
                "No Synergy URL set for this student.\nEdit the student record first.")
            return
        mappings = self.db.get_mappings()
        if not mappings:
            QMessageBox.warning(self, "No Mappings",
                "No field mappings configured.\nUse Live Map mode to map fields first.")
            return

        self.status_bar.showMessage(f"Syncing {s['name']}…")
        QApplication.processEvents()

        scraper = SynergyScaper(base_url=url, mappings=mappings)
        data = scraper.scrape_student_page(url)

        updates = {}
        if "praise_points" in data and data["praise_points"]:
            try:
                pts = int(re.sub(r"[^\d]", "", data["praise_points"]))
                self.db.add_behaviour(self.current_student_id, "praise", pts, "Synced from Synergy")
            except Exception:
                pass
        if "sanction_points" in data and data["sanction_points"]:
            try:
                pts = int(re.sub(r"[^\d]", "", data["sanction_points"]))
                self.db.add_behaviour(self.current_student_id, "sanction", pts, "Synced from Synergy")
            except Exception:
                pass

        phones = [data.get(f"phone_{i}","") for i in range(1,4)]
        phones = [p for p in phones if p]
        if phones:
            updates["phones"] = phones

        if updates:
            self.db.update_student(self.current_student_id, **updates)

        self.db.update_student(self.current_student_id)  # bumps sync_time
        self._load_student_detail()
        self._refresh_student_list()
        self.status_bar.showMessage(f"✅ {s['name']} synced — {len(data)} fields found", 4000)

    def _open_live_map(self):
        base_url = self.db.get_setting("synergy_base_url", "")
        if base_url and hasattr(self.tab_livemap, "le_url"):
            self.tab_livemap.le_url.setText(base_url)
        existing = self.db.get_mappings()
        if existing and hasattr(self.tab_livemap, "load_existing_mappings"):
            self.tab_livemap.load_existing_mappings(existing)
        self.tabs.setCurrentWidget(self.tab_livemap)

    def _on_field_mapped(self, field: str, selector: str, sample: str):
        self.db.save_mapping(field, selector, sample=sample)
        self.status_bar.showMessage(f"Mapped: {field}", 2000)

    def _on_mappings_complete(self, mappings: dict):
        for field, data in mappings.items():
            self.db.save_mapping(field, data.get("selector", ""), sample=data.get("sample", ""))
        self._refresh_settings_mappings()
        self.status_bar.showMessage(f"{len(mappings)} field mappings saved", 4000)

    def _on_discovery_ready(self, candidates: list):
        if not candidates:
            self.status_bar.showMessage("🔍 No students found on this page — try a class list or student directory page", 5000)
            return
        self.status_bar.showMessage(f"🔍 Found {len(candidates)} candidates — opening import dialog…", 3000)
        dlg = DiscoveryDialog(self.db, candidates, parent=self)
        dlg.students_imported.connect(self._on_students_imported)
        dlg.exec()

    def _on_students_imported(self, count: int):
        self._refresh_student_list()
        self._update_status()
        self.status_bar.showMessage(f"✅ {count} student{'s' if count != 1 else ''} added to database", 5000)

    def _refresh_settings_mappings(self):
        mappings = self.db.get_mappings()
        self.tbl_mappings.setRowCount(0)
        for field, m in mappings.items():
            r = self.tbl_mappings.rowCount()
            self.tbl_mappings.insertRow(r)
            self.tbl_mappings.setItem(r, 0, QTableWidgetItem(field))
            self.tbl_mappings.setItem(r, 1, QTableWidgetItem(m.get("selector", "")))
            self.tbl_mappings.setItem(r, 2, QTableWidgetItem(m.get("sample_text", "")[:60]))

    def _bulk_sync(self):
        dlg = BulkSyncDialog(self.db, parent=self)
        dlg.sync_complete.connect(self._refresh_student_list)
        dlg.exec()

    def _export_call_sheet(self):
        from PyQt6.QtWidgets import QCheckBox as _QCB
        students_raw = self.db.get_all_stats()
        if not students_raw:
            QMessageBox.information(self, "No students", "No students in database.")
            return

        # Build full student dicts with behaviours and phones
        students_full = []
        for s in students_raw:
            full = self.db.get_student(s["id"])
            if not full:
                continue
            behaviours = self.db.get_behaviours(s["id"])
            students_full.append({
                "name":       full["name"],
                "year_group": full.get("year_group", ""),
                "form_class": full.get("form_class", ""),
                "phones":     full.get("phones", []),
                "praise":     s["praise"],
                "sanctions":  s["sanctions"],
                "notes":      full.get("notes", ""),
                "behaviours": behaviours,
            })

        html = generate_call_sheet(
            students_full,
            title="Parent Call Sheet",
            include_behaviour_log=True,
            include_call_notes_box=True,
        )

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Call Sheet", "call_sheet.html", "HTML files (*.html)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            self.status_bar.showMessage(
                f"✅ Call sheet saved → {path}  (open in any browser to print)", 5000
            )
            # Try to open in default browser
            import webbrowser, os
            try:
                webbrowser.open(f"file://{os.path.abspath(path)}")
            except Exception:
                pass

    def _start_timetable_capture(self):
        """Navigate to Live Map tab and activate timetable capture mode."""
        if not self.current_student_id:
            QMessageBox.information(self, "No student selected",
                "Select a student first, then navigate to their timetable page in Live Map.")
            return
        # Switch to Live Map tab
        self.tabs.setCurrentWidget(self.tab_livemap)
        self.status_bar.showMessage(
            "Navigate to the student's timetable page, then click 📸 Capture Timetable"
        )

    def _on_timetable_region(self, region_json: str):
        """Browser sent us the bounding box — now screenshot and OCR."""
        if not self.current_student_id:
            self.status_bar.showMessage("⚠ No student selected — cannot save timetable", 4000)
            return

        settle_ms = int(self.db.get_setting("timetable_settle_ms", "1200"))
        self._timetable_capture = TimetableCapture(
            self.tab_livemap.browser, settle_ms=settle_ms, parent=self
        )
        self._timetable_capture.status_update.connect(
            lambda msg: self.status_bar.showMessage(msg, 3000)
        )
        self._timetable_capture.capture_done.connect(self._on_timetable_captured)
        self._timetable_capture.capture_failed.connect(
            lambda err: self.status_bar.showMessage(f"❌ {err}", 5000)
        )
        self._timetable_capture.receive_region(region_json)

    def _on_timetable_captured(self, image_path: str, ocr_text: str, teachers: list):
        """Screenshot saved — persist to DB, update UI."""
        from datetime import datetime
        week_label = f"Week of {datetime.now().strftime('%d %b %Y')}"
        self.db.add_timetable(
            self.current_student_id, image_path,
            ocr_text=ocr_text, teachers=teachers, week_label=week_label
        )
        self.tab_timetable.show_new_capture(image_path, ocr_text, teachers)
        # Refresh global browser if it's visible
        self.tab_tt_browser.refresh()
        self.status_bar.showMessage(
            f"✅ Timetable saved — {len(teachers)} teacher(s) detected via OCR", 5000
        )
        # Switch back to timetable tab
        self.tabs.setCurrentWidget(self.tab_timetable)

    def _on_tab_changed(self, idx: int):
        widget = self.tabs.widget(idx)
        if widget is self.tab_compass:
            all_stats = self.db.get_all_stats()
            self.tab_compass.load_students(all_stats)
        elif widget is self.tab_tt_browser:
            self.tab_tt_browser.refresh()
        elif widget is self.tab_livemap:
            existing = self.db.get_mappings()
            if existing and hasattr(self.tab_livemap, "load_existing_mappings"):
                self.tab_livemap.load_existing_mappings(existing)
        elif widget is self.tab_settings:
            self._refresh_settings_mappings()

    def _save_base_url(self):
        self.db.set_setting("synergy_base_url", self.le_base_url.text().strip())
        self.status_bar.showMessage("Base URL saved.", 2000)

    def _save_settle_ms(self):
        self.db.set_setting("timetable_settle_ms", str(self.sp_settle.value()))
        self.status_bar.showMessage(
            f"Settle time set to {self.sp_settle.value()}ms", 2000
        )

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "synergy_students.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        students = self.db.get_students()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Name","Ref","Year","Form","Phones","Praise","Sanctions","Notes","Synced"])
            for s in students:
                stats = self.db.get_student_stats(s["id"])
                w.writerow([
                    s["name"], s["student_ref"], s["year_group"], s["form_class"],
                    "; ".join(s.get("phones",[])),
                    stats["praise"], stats["sanctions"],
                    s.get("notes",""), s.get("sync_time",""),
                ])
        self.status_bar.showMessage(f"Exported {len(students)} students → {path}", 4000)

    def _update_status(self):
        count = self.db.student_count()
        self.status_bar.showMessage(f"{count} student{'s' if count != 1 else ''} in local database  •  Offline-ready")

    def closeEvent(self, e):
        self.db.close()
        super().closeEvent(e)


import re  # needed in _sync_student


# ── ENTRY ──────────────────────────────────────────────────────────────────
def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Synergy Teacher Dashboard")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
