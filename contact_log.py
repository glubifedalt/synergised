"""
contact_log.py – Synergy Teacher Dashboard
Parent contact log: record every call/text/email attempt,
outcome, and notes. Shown per-student and exportable.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QLabel, QDialogButtonBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from datetime import datetime
from typing import List, Dict, Optional


# ── DB schema addition (call from DB.__init__ if not already added) ────────
CONTACT_LOG_SQL = """
CREATE TABLE IF NOT EXISTS contact_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    method      TEXT    DEFAULT 'phone',
    outcome     TEXT    DEFAULT 'answered',
    phone_used  TEXT    DEFAULT '',
    summary     TEXT    DEFAULT '',
    logged_at   TEXT    DEFAULT (datetime('now'))
);
"""


def ensure_contact_table(conn):
    conn.executescript(CONTACT_LOG_SQL)
    conn.commit()


# ── DB helpers ─────────────────────────────────────────────────────────────

def add_contact(conn, student_id: int, method: str, outcome: str,
                phone_used: str, summary: str):
    conn.execute(
        "INSERT INTO contact_log(student_id,method,outcome,phone_used,summary)"
        " VALUES(?,?,?,?,?)",
        (student_id, method, outcome, phone_used, summary)
    )
    conn.commit()


def get_contacts(conn, student_id: int) -> List[Dict]:
    rows = conn.execute(
        "SELECT * FROM contact_log WHERE student_id=? ORDER BY logged_at DESC",
        (student_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def delete_contact(conn, cid: int):
    conn.execute("DELETE FROM contact_log WHERE id=?", (cid,))
    conn.commit()


def get_all_contacts(conn) -> List[Dict]:
    rows = conn.execute(
        """SELECT cl.*, s.name as student_name, s.form_class
           FROM contact_log cl
           JOIN students s ON s.id = cl.student_id
           ORDER BY cl.logged_at DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


# ── Add Contact Dialog ─────────────────────────────────────────────────────

class AddContactDialog(QDialog):
    def __init__(self, phones: List[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Parent Contact")
        self.setMinimumWidth(400)
        self._phones = phones or []
        self._build()

    def _build(self):
        from styles import QSS
        self.setStyleSheet(QSS)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self.cb_method = QComboBox()
        self.cb_method.addItems(["Phone call", "Text message", "Email", "In person", "Letter"])

        self.cb_outcome = QComboBox()
        self.cb_outcome.addItems([
            "Answered – positive",
            "Answered – concerned",
            "Answered – no action",
            "Voicemail left",
            "No answer",
            "Wrong number",
            "Not attempted",
        ])

        self.cb_phone = QComboBox()
        self.cb_phone.setEditable(True)
        for p in self._phones:
            self.cb_phone.addItem(p)
        self.cb_phone.addItem("(other)")

        self.te_summary = QTextEdit()
        self.te_summary.setPlaceholderText(
            "Brief summary of what was discussed, any actions agreed, parent's response…"
        )
        self.te_summary.setMinimumHeight(100)

        form.addRow("Method:", self.cb_method)
        form.addRow("Outcome:", self.cb_outcome)
        form.addRow("Phone used:", self.cb_phone)
        form.addRow("Notes:", self.te_summary)
        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def values(self):
        return {
            "method":    self.cb_method.currentText(),
            "outcome":   self.cb_outcome.currentText(),
            "phone_used": self.cb_phone.currentText(),
            "summary":   self.te_summary.toPlainText().strip(),
        }


# ── Contact Log Widget (embedded in student detail) ────────────────────────

OUTCOME_COLOURS = {
    "Answered – positive":   "#4dd88a",
    "Answered – concerned":  "#ffaa44",
    "Answered – no action":  "#8ab0d8",
    "Voicemail left":        "#7eb8ff",
    "No answer":             "#4a6fa5",
    "Wrong number":          "#ff6b6b",
    "Not attempted":         "#2a3a5a",
}


class ContactLogWidget(QWidget):
    """Embeddable table + button bar for one student's contact history."""

    contact_added = pyqtSignal()

    def __init__(self, db_conn, student_id: int = None,
                 phones: List[str] = None, parent=None):
        super().__init__(parent)
        self.conn = db_conn
        self.student_id = student_id
        self.phones = phones or []
        ensure_contact_table(self.conn)
        self._build()
        if student_id:
            self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Toolbar
        tb = QHBoxLayout()
        btn_add = QPushButton("📞  Log Contact")
        btn_add.setFixedHeight(30)
        btn_add.setStyleSheet(
            "QPushButton{background:#0e2a4a;color:#5b9bd5;border:1px solid #1e4a7e;"
            "border-radius:6px;font-weight:700;font-size:11px;padding:0 12px;}"
            "QPushButton:hover{background:#1e4a7e;color:#fff;}"
        )
        btn_add.clicked.connect(self._log_contact)

        btn_del = QPushButton("🗑")
        btn_del.setFixedSize(30, 30)
        btn_del.setStyleSheet(
            "QPushButton{background:#1e0808;color:#ff6b6b;border:1px solid #5a1a1a;"
            "border-radius:6px;font-size:12px;}"
            "QPushButton:hover{background:#5a1a1a;}"
        )
        btn_del.clicked.connect(self._delete_selected)
        btn_del.setToolTip("Delete selected entry")

        self.lbl_count = QLabel("No contacts logged")
        self.lbl_count.setStyleSheet("color:#4a6fa5;font-size:10px;")

        tb.addWidget(btn_add)
        tb.addWidget(btn_del)
        tb.addStretch()
        tb.addWidget(self.lbl_count)
        layout.addLayout(tb)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Date/Time", "Method", "Outcome", "Phone Used", "Notes"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().resizeSection(0, 130)
        self.table.horizontalHeader().resizeSection(1, 100)
        self.table.horizontalHeader().resizeSection(2, 160)
        self.table.horizontalHeader().resizeSection(3, 120)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(
            "QTableWidget{background:#080f1c;border:1px solid #1a2a40;font-size:11px;}"
            "QHeaderView::section{background:#0d1b2a;color:#4a6fa5;font-size:11px;}"
            "QTableWidget::item{padding:4px;}"
        )
        self.table.verticalHeader().setDefaultSectionSize(32)
        # Hide id column
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Date/Time", "Method", "Outcome", "Phone Used", "Notes", "id"]
        )
        self.table.setColumnHidden(5, True)
        layout.addWidget(self.table, 1)

    def set_student(self, student_id: int, phones: List[str] = None):
        self.student_id = student_id
        self.phones = phones or []
        self.refresh()

    def refresh(self):
        if not self.student_id:
            return
        contacts = get_contacts(self.conn, self.student_id)
        self.table.setRowCount(0)
        for c in contacts:
            r = self.table.rowCount()
            self.table.insertRow(r)

            dt = str(c.get("logged_at", ""))[:16]
            self.table.setItem(r, 0, QTableWidgetItem(dt))
            self.table.setItem(r, 1, QTableWidgetItem(c.get("method", "")))

            outcome = c.get("outcome", "")
            oi = QTableWidgetItem(outcome)
            colour = OUTCOME_COLOURS.get(outcome, "#c8d8f0")
            oi.setForeground(QColor(colour))
            self.table.setItem(r, 2, oi)

            self.table.setItem(r, 3, QTableWidgetItem(c.get("phone_used", "")))
            self.table.setItem(r, 4, QTableWidgetItem(c.get("summary", "")))
            self.table.setItem(r, 5, QTableWidgetItem(str(c["id"])))

        n = len(contacts)
        self.lbl_count.setText(
            f"{n} contact record{'s' if n != 1 else ''}" if n else "No contacts logged"
        )

    def _log_contact(self):
        if not self.student_id:
            return
        dlg = AddContactDialog(phones=self.phones, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            v = dlg.values()
            add_contact(
                self.conn, self.student_id,
                v["method"], v["outcome"], v["phone_used"], v["summary"]
            )
            self.refresh()
            self.contact_added.emit()

    def _delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        id_item = self.table.item(row, 5)
        if id_item:
            delete_contact(self.conn, int(id_item.text()))
            self.refresh()
