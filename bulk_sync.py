"""
bulk_sync.py – Synergy Teacher Dashboard
QThread worker for syncing multiple students from Synergy in the background.
Reports per-student progress back to the UI via signals.
"""

import re
from typing import List, Dict

from PyQt6.QtCore import QThread, pyqtSignal

from scraper import SynergyScaper
from database import DB


class BulkSyncWorker(QThread):
    """
    Syncs a list of students from Synergy.
    Emits progress and per-student results so the UI can update live.
    """
    progress    = pyqtSignal(int, int, str)          # done, total, student_name
    student_done = pyqtSignal(int, dict, str)         # student_id, scraped_data, status_msg
    finished_all = pyqtSignal(int, int)               # success_count, fail_count

    def __init__(self, db: DB, student_ids: List[int], mappings: Dict, parent=None):
        super().__init__(parent)
        self.db = db
        self.student_ids = student_ids
        self.mappings = mappings
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        total   = len(self.student_ids)
        success = 0
        fail    = 0

        scraper = SynergyScaper(mappings=self.mappings)

        for i, sid in enumerate(self.student_ids):
            if self._abort:
                break

            student = self.db.get_student(sid)
            if not student:
                fail += 1
                continue

            name = student.get("name", f"ID {sid}")
            url  = student.get("synergy_url", "").strip()

            self.progress.emit(i + 1, total, name)

            if not url:
                self.student_done.emit(sid, {}, "No URL set")
                fail += 1
                continue

            try:
                data = scraper.scrape_student_page(url)
            except Exception as e:
                self.student_done.emit(sid, {}, f"Error: {e}")
                fail += 1
                continue

            if not data:
                self.student_done.emit(sid, {}, "No data returned")
                fail += 1
                continue

            # Persist scraped data
            if data.get("praise_points"):
                try:
                    pts = int(re.sub(r"[^\d]", "", data["praise_points"]))
                    if pts:
                        self.db.add_behaviour(sid, "praise", pts, "Bulk sync")
                except Exception:
                    pass

            if data.get("sanction_points"):
                try:
                    pts = int(re.sub(r"[^\d]", "", data["sanction_points"]))
                    if pts:
                        self.db.add_behaviour(sid, "sanction", pts, "Bulk sync")
                except Exception:
                    pass

            phones = [data.get(f"phone_{j}", "") for j in range(1, 4)]
            phones = [p for p in phones if p]
            if phones:
                self.db.update_student(sid, phones=phones)
            else:
                self.db.update_student(sid)   # still bumps sync_time

            fields_found = sum(1 for v in data.values() if v)
            self.student_done.emit(sid, data, f"OK – {fields_found} fields")
            success += 1

        self.finished_all.emit(success, fail)


# ── Bulk Sync Dialog ───────────────────────────────────────────────────────

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QScrollArea, QWidget, QFrame
)
from PyQt6.QtGui import QColor


class BulkSyncDialog(QDialog):
    sync_complete = pyqtSignal()

    def __init__(self, db: DB, parent=None):
        super().__init__(parent)
        self.db = db
        self.worker: BulkSyncWorker = None
        self.setWindowTitle("Bulk Sync from Synergy")
        self.setMinimumSize(680, 520)
        self._build()
        self._load_students()

    def _build(self):
        from styles import QSS
        self.setStyleSheet(QSS)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Info
        info = QLabel(
            "Select students to sync from Synergy. Only students with a Dashboard URL "
            "and saved field mappings will be updated.\n"
            "Syncing runs in the background — you can watch progress below."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#8ab0d8;font-size:11px;")
        layout.addWidget(info)

        # Select all / none row
        sel_row = QHBoxLayout()
        btn_all  = QPushButton("☑  Select all with URL")
        btn_none = QPushButton("☐  Deselect all")
        for b in (btn_all, btn_none):
            b.setFixedHeight(26)
            b.setStyleSheet(
                "QPushButton{background:#0e2140;color:#5b9bd5;border:1px solid #1e3a6e;"
                "border-radius:5px;font-size:10px;padding:0 10px;}"
                "QPushButton:hover{background:#1a3d7c;}"
            )
        btn_all.clicked.connect(self._select_all)
        btn_none.clicked.connect(self._deselect_all)
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Student table
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["", "Name", "Year", "Form", "Status"])
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().resizeSection(0, 30)
        self.tbl.horizontalHeader().resizeSection(2, 50)
        self.tbl.horizontalHeader().resizeSection(3, 60)
        self.tbl.horizontalHeader().resizeSection(4, 160)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.tbl, 1)

        # Progress
        self.prog_bar = QProgressBar()
        self.prog_bar.setValue(0)
        self.prog_bar.setStyleSheet(
            "QProgressBar{background:#0e2140;border:1px solid #1e3a6e;border-radius:5px;"
            "height:14px;text-align:center;color:#c8d8f0;font-size:10px;}"
            "QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1a3d7c,stop:1 #4a90d9);border-radius:5px;}"
        )
        self.prog_bar.hide()
        layout.addWidget(self.prog_bar)

        self.lbl_prog = QLabel("")
        self.lbl_prog.setStyleSheet("color:#5b9bd5;font-size:10px;")
        self.lbl_prog.hide()
        layout.addWidget(self.lbl_prog)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("⟳  Start Sync")
        self.btn_start.setObjectName("btn_sync")
        self.btn_start.setFixedHeight(34)
        self.btn_start.clicked.connect(self._start_sync)

        self.btn_abort = QPushButton("✕  Abort")
        self.btn_abort.setObjectName("btn_danger")
        self.btn_abort.setFixedHeight(34)
        self.btn_abort.clicked.connect(self._abort_sync)
        self.btn_abort.setEnabled(False)

        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(self.accept)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_abort)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _load_students(self):
        students = self.db.get_students()
        self.tbl.setRowCount(0)
        self._checkboxes = []
        for s in students:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            chk = QCheckBox()
            has_url = bool(s.get("synergy_url", "").strip())
            chk.setChecked(has_url)
            chk.setProperty("student_id", s["id"])
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self.tbl.setCellWidget(r, 0, chk_widget)
            self._checkboxes.append(chk)

            self.tbl.setItem(r, 1, QTableWidgetItem(s["name"]))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(s.get("year_group", ""))))
            self.tbl.setItem(r, 3, QTableWidgetItem(s.get("form_class", "")))

            status_text = "Ready" if has_url else "No URL"
            si = QTableWidgetItem(status_text)
            si.setForeground(QColor("#4a6fa5" if has_url else "#4a3a2a"))
            self.tbl.setItem(r, 4, si)

    def _select_all(self):
        for chk in self._checkboxes:
            sid = chk.property("student_id")
            s = self.db.get_student(sid)
            if s and s.get("synergy_url", "").strip():
                chk.setChecked(True)

    def _deselect_all(self):
        for chk in self._checkboxes:
            chk.setChecked(False)

    def _selected_ids(self):
        return [
            chk.property("student_id")
            for chk in self._checkboxes
            if chk.isChecked()
        ]

    def _start_sync(self):
        ids = self._selected_ids()
        if not ids:
            return

        mappings = self.db.get_mappings()
        if not mappings:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Mappings",
                "No field mappings saved. Use the Live Map tab first.")
            return

        self.btn_start.setEnabled(False)
        self.btn_abort.setEnabled(True)
        self.prog_bar.setMaximum(len(ids))
        self.prog_bar.setValue(0)
        self.prog_bar.show()
        self.lbl_prog.show()

        self.worker = BulkSyncWorker(self.db, ids, mappings, parent=self)
        self.worker.progress.connect(self._on_progress)
        self.worker.student_done.connect(self._on_student_done)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _abort_sync(self):
        if self.worker:
            self.worker.abort()

    def _on_progress(self, done: int, total: int, name: str):
        self.prog_bar.setValue(done)
        self.lbl_prog.setText(f"Syncing {done}/{total}: {name}…")

    def _on_student_done(self, sid: int, data: dict, msg: str):
        # Find the row for this student and update status cell
        for r in range(self.tbl.rowCount()):
            chk_widget = self.tbl.cellWidget(r, 0)
            if chk_widget:
                chk = chk_widget.findChild(QCheckBox)
                if chk and chk.property("student_id") == sid:
                    si = QTableWidgetItem(msg)
                    ok = msg.startswith("OK")
                    si.setForeground(QColor("#4dd88a" if ok else "#ff6b6b"))
                    self.tbl.setItem(r, 4, si)
                    break

    def _on_finished(self, success: int, fail: int):
        self.btn_start.setEnabled(True)
        self.btn_abort.setEnabled(False)
        self.lbl_prog.setText(
            f"✅ Done — {success} synced successfully, {fail} failed"
        )
        self.lbl_prog.setStyleSheet("color:#4dd88a;font-size:11px;font-weight:700;")
        self.sync_complete.emit()
