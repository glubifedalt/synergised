"""
timetable_widget.py – Synergy Teacher Dashboard
Qt widget that:
  - Shows a student's captured timetable image(s)
  - Lets user switch between capture dates
  - Filters/highlights cells by teacher name (scanned via OCR)
  - Shows a searchable all-students timetable browser with teacher filter
"""

import os
import json
import re
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QComboBox, QFrame, QSplitter, QToolButton,
    QSizePolicy, QListWidget, QListWidgetItem, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
    QDialogButtonBox, QFileDialog, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import (
    QPixmap, QPainter, QPen, QColor, QBrush, QFont,
    QImage, QTransform
)

from styles import QSS


# ─────────────────────────────────────────────────────────────────────────────
#  Zoomable image label
# ─────────────────────────────────────────────────────────────────────────────
class ZoomableImage(QLabel):
    """A QLabel that supports mouse-wheel zoom and click-drag pan."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap_orig: Optional[QPixmap] = None
        self._scale = 1.0
        self._highlight_colour: Optional[str] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#060e1c;border-radius:6px;")

    def set_pixmap(self, px: QPixmap):
        self._pixmap_orig = px
        self._scale = 1.0
        self._render()

    def set_highlight(self, colour: Optional[str]):
        """Tint the image to visually flag a teacher filter is active."""
        self._highlight_colour = colour
        self._render()

    def _render(self):
        if not self._pixmap_orig:
            return
        w = int(self._pixmap_orig.width() * self._scale)
        h = int(self._pixmap_orig.height() * self._scale)
        scaled = self._pixmap_orig.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        if self._highlight_colour:
            overlay = QPixmap(scaled.size())
            overlay.fill(QColor(self._highlight_colour))
            painter = QPainter(scaled)
            painter.setOpacity(0.15)
            painter.drawPixmap(0, 0, overlay)
            painter.end()
        self.setPixmap(scaled)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if delta > 0:
            self._scale = min(self._scale * 1.15, 8.0)
        else:
            self._scale = max(self._scale / 1.15, 0.1)
        self._render()

    def zoom_fit(self):
        if not self._pixmap_orig:
            return
        vw = self.width() - 4
        vh = self.height() - 4
        pw = self._pixmap_orig.width()
        ph = self._pixmap_orig.height()
        if pw and ph:
            self._scale = min(vw / pw, vh / ph, 1.0)
            self._render()


# ─────────────────────────────────────────────────────────────────────────────
#  Per-student timetable panel (embedded in student detail)
# ─────────────────────────────────────────────────────────────────────────────
class StudentTimetablePanel(QWidget):
    """Shows timetables for one student with teacher filter."""

    capture_requested = pyqtSignal()   # tell main window to start capture

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._student_id: Optional[int] = None
        self._timetables: List[Dict] = []
        self._current_idx = 0
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── Toolbar ──
        tb = QHBoxLayout()

        self.btn_capture = QPushButton("📸  Capture Timetable")
        self.btn_capture.setFixedHeight(30)
        self.btn_capture.setStyleSheet(
            "QPushButton{background:#1a2a5a;color:#7eb8ff;border:1px solid #2a4a9a;"
            "border-radius:6px;font-weight:700;font-size:11px;padding:0 12px;}"
            "QPushButton:hover{background:#2a4a9a;color:#fff;}"
        )
        self.btn_capture.clicked.connect(self.capture_requested)

        # Date picker
        self.cb_date = QComboBox()
        self.cb_date.setFixedWidth(220)
        self.cb_date.setStyleSheet(
            "background:#0e2140;border:1px solid #1e3a6e;border-radius:5px;"
            "color:#c8d8f0;padding:4px 8px;font-size:11px;"
        )
        self.cb_date.currentIndexChanged.connect(self._on_date_changed)

        # Teacher filter
        self.cb_teacher = QComboBox()
        self.cb_teacher.setFixedWidth(180)
        self.cb_teacher.setEditable(True)
        self.cb_teacher.lineEdit().setPlaceholderText("Filter by teacher…")
        self.cb_teacher.setStyleSheet(
            "background:#0e2140;border:1px solid #1e3a6e;border-radius:5px;"
            "color:#c8d8f0;padding:4px 8px;font-size:11px;"
        )
        self.cb_teacher.currentTextChanged.connect(self._on_teacher_filter)

        btn_fit = QPushButton("⊞  Fit")
        btn_fit.setFixedSize(48, 28)
        btn_fit.setStyleSheet(
            "QPushButton{background:#0e2140;color:#5b9bd5;border:1px solid #1e3a6e;"
            "border-radius:5px;font-size:10px;}"
            "QPushButton:hover{background:#1a3d7c;}"
        )
        btn_fit.clicked.connect(self._fit_image)

        btn_del = QPushButton("🗑")
        btn_del.setFixedSize(28, 28)
        btn_del.setStyleSheet(
            "QPushButton{background:#1e0808;color:#ff6b6b;border:1px solid #5a1a1a;"
            "border-radius:5px;font-size:11px;}"
            "QPushButton:hover{background:#5a1a1a;}"
        )
        btn_del.setToolTip("Delete this timetable capture")
        btn_del.clicked.connect(self._delete_current)

        tb.addWidget(self.btn_capture)
        tb.addSpacing(6)
        tb.addWidget(QLabel("Capture:"))
        tb.addWidget(self.cb_date)
        tb.addSpacing(10)
        tb.addWidget(QLabel("Teacher:"))
        tb.addWidget(self.cb_teacher)
        tb.addStretch()
        tb.addWidget(btn_fit)
        tb.addWidget(btn_del)
        layout.addLayout(tb)

        # ── Image area ──
        self.img = ZoomableImage()
        scroll = QScrollArea()
        scroll.setWidget(self.img)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{background:#060e1c;border:1px solid #1a2a40;border-radius:8px;}"
        )
        layout.addWidget(scroll, 1)

        # ── OCR text strip ──
        self.lbl_ocr = QLabel("No timetable captured yet. "
                              "Navigate to the student's timetable page in Live Map, "
                              "then click 📸 Capture Timetable.")
        self.lbl_ocr.setWordWrap(True)
        self.lbl_ocr.setStyleSheet(
            "color:#4a6fa5;font-size:10px;padding:6px 10px;"
            "background:#060e1c;border-radius:5px;"
        )
        layout.addWidget(self.lbl_ocr)

    # ── Public ────────────────────────────────────────────────────────────

    def set_student(self, student_id: int):
        self._student_id = student_id
        self._current_idx = 0
        self.refresh()

    def refresh(self):
        if not self._student_id:
            return
        self._timetables = self.db.get_timetables(self._student_id)
        self.cb_date.blockSignals(True)
        self.cb_date.clear()
        for tt in self._timetables:
            label = tt.get("week_label") or tt.get("captured_at", "")[:16]
            self.cb_date.addItem(label)
        self.cb_date.blockSignals(False)

        # Refresh teacher filter from all timetables for this student
        all_teachers = set()
        for tt in self._timetables:
            for t in tt.get("teachers", []):
                if t.strip():
                    all_teachers.add(t.strip())
        self.cb_teacher.blockSignals(True)
        current = self.cb_teacher.currentText()
        self.cb_teacher.clear()
        self.cb_teacher.addItem("All teachers")
        for t in sorted(all_teachers):
            self.cb_teacher.addItem(t)
        idx = self.cb_teacher.findText(current)
        if idx >= 0:
            self.cb_teacher.setCurrentIndex(idx)
        self.cb_teacher.blockSignals(False)

        if self._timetables:
            self._show(0)
        else:
            self.img.clear()
            self.lbl_ocr.setText("No timetable captured yet. "
                                 "Navigate to the student's timetable page in Live Map, "
                                 "then click 📸 Capture Timetable.")

    def show_new_capture(self, image_path: str, ocr_text: str, teachers: list):
        """Called after a fresh capture is saved to DB."""
        self.refresh()
        if self._timetables:
            self._show(0)

    # ── Private ───────────────────────────────────────────────────────────

    def _show(self, idx: int):
        if idx < 0 or idx >= len(self._timetables):
            return
        self._current_idx = idx
        tt = self._timetables[idx]
        path = tt.get("image_path", "")
        if path and os.path.exists(path):
            px = QPixmap(path)
            self.img.set_pixmap(px)
            QTimer.singleShot(50, self.img.zoom_fit)
        else:
            self.img.clear()
            self.lbl_ocr.setText(f"Image file not found: {path}")
            return

        teachers = tt.get("teachers", [])
        ocr = tt.get("ocr_text", "") or ""
        excerpt = ocr[:300].replace("\n", " ") if ocr else "(OCR not available)"
        self.lbl_ocr.setText(
            f"<b>Teachers detected:</b> {', '.join(teachers) if teachers else 'None detected'}  "
            f"&nbsp;|&nbsp; <i>{excerpt}{'…' if len(ocr)>300 else ''}</i>"
        )
        self._apply_teacher_highlight()

    def _on_date_changed(self, idx: int):
        self._show(idx)

    def _on_teacher_filter(self, teacher: str):
        self._apply_teacher_highlight()

    def _apply_teacher_highlight(self):
        teacher = self.cb_teacher.currentText().strip()
        if not teacher or teacher == "All teachers":
            self.img.set_highlight(None)
            return
        # Check if the current timetable mentions this teacher
        if self._current_idx < len(self._timetables):
            tt = self._timetables[self._current_idx]
            teachers_here = tt.get("teachers", [])
            ocr_text = (tt.get("ocr_text", "") or "").lower()
            if teacher.lower() in ocr_text or teacher in teachers_here:
                self.img.set_highlight("#4a90d9")   # blue tint = found
            else:
                self.img.set_highlight("#ff4444")   # red tint = not in this one

    def _fit_image(self):
        self.img.zoom_fit()

    def _delete_current(self):
        if self._current_idx >= len(self._timetables):
            return
        tt = self._timetables[self._current_idx]
        if QMessageBox.question(
            self, "Delete timetable",
            f"Delete this timetable capture ({tt.get('captured_at','')[:16]})?"
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_timetable(tt["id"])
            self.refresh()


# ─────────────────────────────────────────────────────────────────────────────
#  Global timetable browser (all students, with teacher filter)
# ─────────────────────────────────────────────────────────────────────────────
class TimetableBrowserWidget(QWidget):
    """
    Shows all captured timetables across every student.
    Teacher dropdown filters to only show timetables containing that teacher.
    """
    student_selected = pyqtSignal(int)   # emit student_id when card clicked

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._all: List[Dict] = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── Top bar ──
        top = QHBoxLayout()
        top.addWidget(QLabel("All timetables"))

        self.cb_teacher_f = QComboBox()
        self.cb_teacher_f.setFixedWidth(220)
        self.cb_teacher_f.setEditable(True)
        self.cb_teacher_f.lineEdit().setPlaceholderText("Filter by teacher…")
        self.cb_teacher_f.setStyleSheet(
            "background:#0e2140;border:1px solid #1e3a6e;border-radius:5px;"
            "color:#c8d8f0;padding:4px 8px;font-size:11px;"
        )
        self.cb_teacher_f.currentTextChanged.connect(self._filter)

        self.le_student_f = QLineEdit()
        self.le_student_f.setPlaceholderText("Search student name…")
        self.le_student_f.setFixedWidth(180)
        self.le_student_f.setStyleSheet(
            "background:#0e2140;border:1px solid #1e3a6e;border-radius:5px;"
            "color:#c8d8f0;padding:4px 8px;font-size:11px;"
        )
        self.le_student_f.textChanged.connect(self._filter)

        btn_refresh = QPushButton("⟳")
        btn_refresh.setFixedSize(30, 30)
        btn_refresh.setStyleSheet(
            "QPushButton{background:#1e3a6e;color:#7eb8ff;border:none;border-radius:15px;font-size:13px;}"
            "QPushButton:hover{background:#2a5298;}"
        )
        btn_refresh.clicked.connect(self.refresh)

        top.addStretch()
        top.addWidget(QLabel("Teacher:"))
        top.addWidget(self.cb_teacher_f)
        top.addSpacing(8)
        top.addWidget(QLabel("Student:"))
        top.addWidget(self.le_student_f)
        top.addWidget(btn_refresh)
        layout.addLayout(top)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#1e3a6e;")
        layout.addWidget(sep)

        # ── Timetable grid (scroll area containing rows) ──
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            "QScrollArea{background:#080f1c;border:1px solid #1a2a40;border-radius:8px;}"
        )
        self.container = QWidget()
        self.grid_layout = QVBoxLayout(self.container)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        self.lbl_count = QLabel("No timetables captured yet")
        self.lbl_count.setStyleSheet("color:#4a6fa5;font-size:10px;")
        layout.addWidget(self.lbl_count)

    def refresh(self):
        self._all = self.db.get_all_timetables()
        # Rebuild teacher dropdown
        all_teachers = set()
        for tt in self._all:
            for t in tt.get("teachers", []):
                if t.strip():
                    all_teachers.add(t.strip())
        cur = self.cb_teacher_f.currentText()
        self.cb_teacher_f.blockSignals(True)
        self.cb_teacher_f.clear()
        self.cb_teacher_f.addItem("All teachers")
        for t in sorted(all_teachers):
            self.cb_teacher_f.addItem(t)
        idx = self.cb_teacher_f.findText(cur)
        self.cb_teacher_f.setCurrentIndex(max(0, idx))
        self.cb_teacher_f.blockSignals(False)
        self._filter()

    def _filter(self):
        teacher = self.cb_teacher_f.currentText().strip()
        student_q = self.le_student_f.text().strip().lower()

        filtered = []
        for tt in self._all:
            # Student name filter
            if student_q and student_q not in tt.get("student_name","").lower():
                continue
            # Teacher filter
            if teacher and teacher != "All teachers":
                ocr = (tt.get("ocr_text","") or "").lower()
                teachers_list = tt.get("teachers", [])
                if teacher.lower() not in ocr and teacher not in teachers_list:
                    continue
            filtered.append(tt)

        self._render_cards(filtered)

    def _render_cards(self, timetables: List[Dict]):
        # Clear old cards
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not timetables:
            lbl = QLabel("No matching timetables found")
            lbl.setStyleSheet("color:#4a6fa5;font-size:12px;padding:20px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid_layout.addWidget(lbl)
            self.lbl_count.setText(f"0 timetables")
            return

        for tt in timetables:
            card = self._make_card(tt)
            self.grid_layout.addWidget(card)

        self.grid_layout.addStretch()
        self.lbl_count.setText(f"{len(timetables)} timetable{'s' if len(timetables)!=1 else ''}")

    def _make_card(self, tt: Dict) -> QWidget:
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:#0d1b2a;border:1px solid #1e3a6e;border-radius:10px;}"
            "QFrame:hover{border-color:#4a90d9;}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(12)

        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(120, 80)
        thumb.setStyleSheet("background:#060e1c;border-radius:5px;")
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path = tt.get("image_path","")
        if path and os.path.exists(path):
            px = QPixmap(path).scaled(
                120, 80,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            thumb.setPixmap(px)
        else:
            thumb.setText("No image")
            thumb.setStyleSheet("color:#2a4a7f;font-size:10px;background:#060e1c;border-radius:5px;")
        lay.addWidget(thumb)

        # Info
        info = QVBoxLayout()
        name_lbl = QLabel(f"<b>{tt.get('student_name','?')}</b>")
        name_lbl.setStyleSheet("color:#e0e8ff;font-size:13px;")
        info.addWidget(name_lbl)

        meta_lbl = QLabel(
            f"Year {tt.get('year_group','')}  {tt.get('form_class','')}  "
            f"·  Captured {str(tt.get('captured_at',''))[:16]}"
        )
        meta_lbl.setStyleSheet("color:#4a6fa5;font-size:10px;")
        info.addWidget(meta_lbl)

        teachers = tt.get("teachers", [])
        t_lbl = QLabel(f"Teachers: {', '.join(teachers) if teachers else 'None detected'}")
        t_lbl.setStyleSheet("color:#7eb8ff;font-size:10px;")
        t_lbl.setWordWrap(True)
        info.addWidget(t_lbl)
        lay.addLayout(info, 1)

        # View button
        btn_view = QPushButton("View →")
        btn_view.setFixedSize(70, 28)
        btn_view.setStyleSheet(
            "QPushButton{background:#1a3d7c;color:#7eb8ff;border:1px solid #2a5298;"
            "border-radius:6px;font-size:10px;font-weight:700;}"
            "QPushButton:hover{background:#2a5298;color:#fff;}"
        )
        sid = tt.get("student_id")
        btn_view.clicked.connect(lambda _, s=sid: self.student_selected.emit(s))
        lay.addWidget(btn_view, alignment=Qt.AlignmentFlag.AlignVCenter)

        return card
