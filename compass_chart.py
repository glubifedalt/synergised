"""
compass_chart.py – Synergy Teacher Dashboard
Matplotlib behaviour compass:
  X axis : sanction score (none=left, high=right)
  Y axis : year group (7 at bottom = newer; 13 at top = longer at school)
Bubble colour = praise ratio (red → amber → green)
Bubble size    = total behaviour points
Interactive: hover tooltip, click to highlight student.
"""

from typing import List, Dict, Optional
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.colors as mcolors

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QToolTip
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QCursor


class CompassChart(QWidget):
    student_clicked = pyqtSignal(int)   # emits student_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._students: List[Dict] = []
        self._selected_id: Optional[int] = None
        self._scatter = None
        self._xs = np.array([])
        self._ys = np.array([])
        self._ids: List[int] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()
        self.lbl_title = QLabel("Behaviour Compass")
        self.lbl_title.setStyleSheet(
            "font-size:13px;font-weight:700;color:#e0e8ff;letter-spacing:1px;"
        )
        toolbar.addWidget(self.lbl_title)
        toolbar.addStretch()

        self.lbl_hint = QLabel("Hover bubble for details • Click to select student")
        self.lbl_hint.setStyleSheet("color:#2a5298;font-size:10px;font-style:italic;")
        toolbar.addWidget(self.lbl_hint)

        btn_refresh = QPushButton("⟳")
        btn_refresh.setFixedSize(28, 28)
        btn_refresh.setStyleSheet(
            "QPushButton{background:#1e3a6e;color:#7eb8ff;border:1px solid #2a5298;"
            "border-radius:14px;font-size:13px;}"
            "QPushButton:hover{background:#2a5298;}"
        )
        btn_refresh.clicked.connect(self.render)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        # Legend row
        legend = QHBoxLayout()
        for colour, text in [
            ("#2ecc71", "More praise"), ("#f39c12", "Balanced"), ("#e74c3c", "More sanctions"),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{colour};font-size:16px;")
            lbl = QLabel(text)
            lbl.setStyleSheet("color:#4a6fa5;font-size:10px;")
            legend.addWidget(dot)
            legend.addWidget(lbl)
            legend.addSpacing(12)
        legend.addStretch()
        layout.addLayout(legend)

        # Figure
        self.figure = Figure(figsize=(9, 5.2), facecolor="#0d1b2a")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet("background:#0d1b2a;border-radius:8px;")
        self.canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.canvas.mpl_connect("button_press_event", self._on_click)
        layout.addWidget(self.canvas, 1)

        # Tooltip label (styled, shown above canvas)
        self.tooltip_lbl = QLabel("", self.canvas)
        self.tooltip_lbl.setStyleSheet(
            "background:#0e2140;color:#e0e8ff;border:1px solid #4a90d9;"
            "border-radius:6px;padding:6px 10px;font-size:11px;line-height:160%;"
        )
        self.tooltip_lbl.hide()
        self.tooltip_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def load_students(self, students: List[Dict]):
        self._students = students
        self.render()

    def render(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111, facecolor="#0d1b2a")

        if not self._students:
            ax.text(0.5, 0.5,
                    "No student data yet.\nAdd students to see the compass.",
                    ha="center", va="center", color="#4a6fa5", fontsize=12,
                    transform=ax.transAxes, style="italic")
            self._style_axes(ax)
            self.canvas.draw()
            return

        xs, ys, labels, ratios, sizes, ids = [], [], [], [], [], []

        for s in self._students:
            sanc   = float(s.get("sanctions", 0))
            praise = float(s.get("praise", 0))
            year   = float(s.get("year_group", 7))
            xs.append(sanc)
            ys.append(year)
            labels.append(s.get("name", "?"))
            ids.append(s.get("id", -1))
            total = sanc + praise
            ratio = praise / total if total > 0 else 0.5
            ratios.append(ratio)
            sizes.append(max(90, min(700, total * 18 + 90)))

        self._xs  = np.array(xs)
        self._ys  = np.array(ys)
        self._ids = ids
        ratios_arr = np.array(ratios)
        sizes_arr  = np.array(sizes)

        cmap = mcolors.LinearSegmentedColormap.from_list(
            "bcompass", ["#e74c3c", "#f39c12", "#2ecc71"]
        )

        # Draw unselected bubbles
        self._scatter = ax.scatter(
            self._xs, self._ys,
            c=ratios_arr, cmap=cmap,
            s=sizes_arr, alpha=0.80,
            edgecolors="#ffffff22", linewidths=0.8,
            zorder=3,
        )

        # Highlight selected student
        if self._selected_id is not None:
            for i, sid in enumerate(ids):
                if sid == self._selected_id:
                    ax.scatter(
                        [xs[i]], [ys[i]],
                        s=[sizes[i] * 1.6],
                        facecolors="none",
                        edgecolors="#ffd700",
                        linewidths=3,
                        zorder=5,
                    )

        # Labels
        for x, y, name in zip(xs, ys, labels):
            short = name.split()[-1] if " " in name else name
            ax.annotate(
                short, (x, y),
                fontsize=7.5, color="#ddeeff",
                ha="center", va="bottom",
                xytext=(0, 8), textcoords="offset points",
                path_effects=[pe.withStroke(linewidth=2, foreground="#0d1b2a")],
                zorder=4,
            )

        # Danger zone shading
        if len(xs) and max(xs) > 0:
            xmax = max(xs) * 1.15
            ax.axvspan(max(xs) * 0.65, xmax, alpha=0.04, color="#e74c3c", zorder=1)

        # Colourbar
        cb = self.figure.colorbar(self._scatter, ax=ax, fraction=0.022, pad=0.02)
        cb.set_label("← More sanctions  |  More praise →", color="#7eb8ff", fontsize=8)
        cb.ax.yaxis.set_tick_params(color="#7eb8ff", labelcolor="#7eb8ff", labelsize=7)
        cb.outline.set_edgecolor("#2a4a7f")

        self._style_axes(ax, np.array(xs))
        self.canvas.draw()

    def _style_axes(self, ax, xs=None):
        ax.set_facecolor("#0d1b2a")
        ax.grid(True, color="#1e3a6e", linewidth=0.5, alpha=0.6, zorder=0)
        for spine in ax.spines.values():
            spine.set_color("#1e3a6e")

        ax.set_xlabel("Sanction points  (none ← → more concerns)",
                      color="#7eb8ff", fontsize=10, labelpad=8)
        ax.tick_params(colors="#7eb8ff", labelsize=8)

        xmax = float(xs.max()) * 1.18 if xs is not None and len(xs) else 10
        ax.set_xlim(-0.8, max(xmax, 5))

        ax.set_xticks([0])
        ax.set_xticklabels(["None"], color="#2ecc71", fontsize=8)
        ax.text(1.0, -0.07, "Highest concern →", transform=ax.transAxes,
                ha="right", va="top", color="#e74c3c", fontsize=8)

        ax.set_ylabel("Year group  (time at school)",
                      color="#7eb8ff", fontsize=10, labelpad=8)
        yticks = list(range(7, 14))
        ax.set_yticks(yticks)
        ax.set_yticklabels([f"Yr {y}" for y in yticks], color="#7eb8ff", fontsize=8)
        ax.set_ylim(6.3, 13.7)

        ax.set_title("Behaviour Compass", color="#e0e8ff", fontsize=13,
                     fontweight="bold", pad=10, loc="left")
        self.figure.tight_layout(pad=1.4)

    # ── Interactivity ──────────────────────────────────────────────────────

    def _find_nearest(self, event) -> Optional[int]:
        """Return index of nearest data point within pick radius, or None."""
        if event.xdata is None or event.ydata is None or len(self._xs) == 0:
            return None
        # Convert data coords to display coords for distance
        ax = self.figure.axes[0]
        try:
            disp_pts = ax.transData.transform(
                np.column_stack([self._xs, self._ys])
            )
            ex, ey = ax.transData.transform([[event.xdata, event.ydata]])[0]
            dists = np.hypot(disp_pts[:, 0] - ex, disp_pts[:, 1] - ey)
            idx = int(np.argmin(dists))
            if dists[idx] < 30:
                return idx
        except Exception:
            pass
        return None

    def _on_hover(self, event):
        idx = self._find_nearest(event)
        if idx is None:
            self.tooltip_lbl.hide()
            return

        s = self._students[idx]
        name      = s.get("name", "?")
        praise    = s.get("praise", 0)
        sanctions = s.get("sanctions", 0)
        year      = s.get("year_group", "?")
        form      = s.get("form_class", "") or ""

        self.tooltip_lbl.setText(
            f"<b>{name}</b><br>"
            f"Year {year}  {form}<br>"
            f"✅ Praise: <b>{praise}</b> pts<br>"
            f"⚠ Sanctions: <b>{sanctions}</b> pts"
        )
        self.tooltip_lbl.adjustSize()

        # Position tooltip near cursor but keep inside canvas
        cx = int(event.x)
        cy = int(self.canvas.height() - event.y)
        tx = min(cx + 14, self.canvas.width() - self.tooltip_lbl.width() - 4)
        ty = max(cy - self.tooltip_lbl.height() - 8, 4)
        self.tooltip_lbl.move(tx, ty)
        self.tooltip_lbl.show()
        self.tooltip_lbl.raise_()

    def _on_click(self, event):
        idx = self._find_nearest(event)
        if idx is None:
            return
        sid = self._ids[idx]
        self._selected_id = sid
        self.render()
        self.student_clicked.emit(sid)
