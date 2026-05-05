"""
discovery_dialog.py – Synergy Teacher Dashboard
UI for reviewing and confirming auto-discovered students before DB import.
"""

import json
from typing import List, Dict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QWidget, QProgressBar, QAbstractItemView, QMessageBox,
    QSpinBox, QLineEdit, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QColor, QFont

from styles import QSS
from database import DB


class DiscoveryDialog(QDialog):
    """
    Shows a table of discovered student candidates.
    Teacher ticks which ones to import, edits any wrong fields inline,
    then clicks Import.
    """

    students_imported = pyqtSignal(int)   # emits count

    def __init__(self, db: DB, candidates: List[Dict], parent=None):
        super().__init__(parent)
        self.db = db
        self.candidates = candidates
        self.setWindowTitle(f"Import Discovered Students  ({len(candidates)} found)")
        self.setMinimumSize(820, 560)
        self.setStyleSheet(QSS)
        self._build()
        self._populate()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        hdr = QLabel(
            f"<b>{len(self.candidates)}</b> student records were found on the page. "
            "Review them below — tick those you want to import, edit any incorrect fields, "
            "then click <b>Import Selected</b>."
        )
        hdr.setWordWrap(True)
        hdr.setStyleSheet("color:#8ab0d8;font-size:12px;")
        layout.addWidget(hdr)

        # Select all / none
        sel_row = QHBoxLayout()
        btn_all  = QPushButton("☑  Select all")
        btn_none = QPushButton("☐  Deselect all")
        btn_new_only = QPushButton("☑  New only (skip existing)")
        for b in (btn_all, btn_none, btn_new_only):
            b.setFixedHeight(26)
            b.setStyleSheet(
                "QPushButton{background:#0e2140;color:#5b9bd5;border:1px solid #1e3a6e;"
                "border-radius:5px;font-size:10px;padding:0 10px;}"
                "QPushButton:hover{background:#1a3d7c;}"
            )
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        btn_new_only.clicked.connect(self._select_new_only)
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        sel_row.addWidget(btn_new_only)
        sel_row.addStretch()

        self.lbl_sel_count = QLabel("0 selected")
        self.lbl_sel_count.setStyleSheet("color:#4a6fa5;font-size:10px;")
        sel_row.addWidget(self.lbl_sel_count)
        layout.addLayout(sel_row)

        # Table: ✓ | Name | Year | Form | Ref | URL | Status
        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(
            ["", "Name", "Year", "Form", "Ref / ID", "Dashboard URL", "Status"]
        )
        self.tbl.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.tbl.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.Stretch
        )
        self.tbl.horizontalHeader().resizeSection(0, 32)
        self.tbl.horizontalHeader().resizeSection(2, 52)
        self.tbl.horizontalHeader().resizeSection(3, 60)
        self.tbl.horizontalHeader().resizeSection(4, 90)
        self.tbl.horizontalHeader().resizeSection(6, 120)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setStyleSheet(
            "QTableWidget{background:#080f1c;alternate-background-color:#0a1420;"
            "border:1px solid #1a2a40;font-size:11px;}"
            "QHeaderView::section{background:#0d1b2a;color:#4a6fa5;font-size:11px;}"
        )
        self.tbl.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(self.tbl, 1)

        # Progress bar (hidden until import starts)
        self.prog = QProgressBar()
        self.prog.setStyleSheet(
            "QProgressBar{background:#0e2140;border:1px solid #1e3a6e;border-radius:5px;"
            "height:12px;}"
            "QProgressBar::chunk{background:#1a3d7c;border-radius:5px;}"
        )
        self.prog.hide()
        layout.addWidget(self.prog)

        # Bottom buttons
        btn_row = QHBoxLayout()
        self.btn_import = QPushButton("⬇  Import Selected")
        self.btn_import.setObjectName("btn_sync")
        self.btn_import.setFixedHeight(34)
        self.btn_import.clicked.connect(self._do_import)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(34)
        btn_cancel.clicked.connect(self.reject)

        self.lbl_result = QLabel("")
        self.lbl_result.setStyleSheet("color:#4dd88a;font-size:11px;font-weight:700;")

        btn_row.addWidget(self.btn_import)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self.lbl_result)
        layout.addLayout(btn_row)

        self._checkboxes: List[QCheckBox] = []

    def _populate(self):
        existing_names = {
            s["name"].lower().strip()
            for s in self.db.get_students()
        }

        self.tbl.setRowCount(0)
        self._checkboxes = []

        for c in self.candidates:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)

            # Checkbox
            chk = QCheckBox()
            chk.setChecked(True)
            chk.stateChanged.connect(self._update_sel_count)
            chk_w = QWidget()
            chk_l = QHBoxLayout(chk_w)
            chk_l.addWidget(chk)
            chk_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_l.setContentsMargins(0, 0, 0, 0)
            self.tbl.setCellWidget(r, 0, chk_w)
            self._checkboxes.append(chk)

            # Editable fields
            name_item = QTableWidgetItem(c.get("name", ""))
            year_item = QTableWidgetItem(str(c.get("year_group", "")))
            form_item = QTableWidgetItem(c.get("form_class", ""))
            ref_item  = QTableWidgetItem(c.get("student_ref", ""))
            url_item  = QTableWidgetItem(c.get("synergy_url", ""))

            for item in (name_item, year_item, form_item, ref_item, url_item):
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

            self.tbl.setItem(r, 1, name_item)
            self.tbl.setItem(r, 2, year_item)
            self.tbl.setItem(r, 3, form_item)
            self.tbl.setItem(r, 4, ref_item)
            self.tbl.setItem(r, 5, url_item)

            # Status
            name_lower = c.get("name", "").lower().strip()
            if name_lower in existing_names:
                status = "Already exists"
                si = QTableWidgetItem(status)
                si.setForeground(QColor("#4a6fa5"))
                chk.setChecked(False)   # don't auto-import duplicates
            else:
                status = "New"
                si = QTableWidgetItem(status)
                si.setForeground(QColor("#4dd88a"))
            self.tbl.setItem(r, 6, si)

        self._update_sel_count()

    def _set_all(self, checked: bool):
        for chk in self._checkboxes:
            chk.setChecked(checked)

    def _select_new_only(self):
        for r, chk in enumerate(self._checkboxes):
            status_item = self.tbl.item(r, 6)
            if status_item:
                chk.setChecked(status_item.text() == "New")

    def _update_sel_count(self):
        n = sum(1 for c in self._checkboxes if c.isChecked())
        self.lbl_sel_count.setText(f"{n} selected")

    def _do_import(self):
        rows_to_import = [
            r for r, chk in enumerate(self._checkboxes) if chk.isChecked()
        ]
        if not rows_to_import:
            QMessageBox.information(self, "Nothing selected",
                                    "Tick at least one student to import.")
            return

        self.btn_import.setEnabled(False)
        self.prog.setMaximum(len(rows_to_import))
        self.prog.setValue(0)
        self.prog.show()

        imported = 0
        for i, r in enumerate(rows_to_import):
            name = (self.tbl.item(r, 1).text() or "").strip()
            if not name:
                continue

            year_text = (self.tbl.item(r, 2).text() or "").strip()
            try:
                year = int(re.sub(r"[^\d]", "", year_text)) if year_text else 7
                year = max(7, min(13, year))
            except Exception:
                year = 7

            form = (self.tbl.item(r, 3).text() or "").strip()
            ref  = (self.tbl.item(r, 4).text() or "").strip()
            url  = (self.tbl.item(r, 5).text() or "").strip()

            try:
                self.db.add_student(
                    name=name, ref=ref, year=year, form=form, url=url
                )
                si = QTableWidgetItem("✅ Imported")
                si.setForeground(QColor("#4dd88a"))
                self.tbl.setItem(r, 6, si)
                imported += 1
            except Exception as e:
                si = QTableWidgetItem(f"Error: {e}")
                si.setForeground(QColor("#ff6b6b"))
                self.tbl.setItem(r, 6, si)

            self.prog.setValue(i + 1)

        self.lbl_result.setText(
            f"✅ {imported} student{'s' if imported != 1 else ''} imported"
        )
        self.btn_import.setEnabled(True)
        self.students_imported.emit(imported)


import re  # used in _do_import
