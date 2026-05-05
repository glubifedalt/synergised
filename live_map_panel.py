"""
live_map_panel.py – Synergy Teacher Dashboard
Replaces the external-Selenium live mapper with an embedded Chromium browser
(PyQt6 QtWebEngine). The teacher logs in, navigates to a student page, then
uses the built-in overlay to hover+press S to map each field.
"""

import json
from typing import List, Dict, Callable, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QObject, pyqtSlot, QTimer
from PyQt6.QtGui import QColor

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import (
        QWebEngineSettings, QWebEnginePage, QWebEngineScript
    )
    from PyQt6.QtWebChannel import QWebChannel
    WEBENGINE_OK = True
except ImportError:
    WEBENGINE_OK = False

from scraper import FIELD_LABELS

# ── JavaScript injected into every page ───────────────────────────────────
# Communicates back to Python via Qt WebChannel (window.pyBridge.onMapping)
_BRIDGE_JS = r"""
new QWebChannel(qt.webChannelTransport, function(channel) {
    window.pyBridge = channel.objects.pyBridge;
});
"""

_OVERLAY_JS = r"""
(function(){
    if (window.__synToolActive) return;
    window.__synToolActive = true;

    // ── inject webchannel polyfill path set by Qt ──
    // (qwebchannel.js is served automatically by QtWebEngine)

    var FIELDS = FIELD_QUEUE_PLACEHOLDER;
    var fieldIdx = 0;
    var currentEl = null;
    window.__synMappings = {};

    // ── Overlay bar ──────────────────────────────────────────────────────
    var bar = document.createElement('div');
    bar.id = '__syn_bar';
    bar.style.cssText = [
        'position:fixed','top:0','left:0','right:0','z-index:2147483647',
        'background:linear-gradient(90deg,#0d1f3c,#1a3d7c)',
        'color:#e0e8ff','font:700 13px/1 "Segoe UI",sans-serif',
        'padding:10px 16px','display:flex','align-items:center',
        'gap:14px','box-shadow:0 2px 12px #0008',
        'border-bottom:2px solid #4a90d9'
    ].join(';');

    var logo = document.createElement('span');
    logo.style.cssText = 'color:#5b9bd5;letter-spacing:2px;font-size:11px;font-weight:900;';
    logo.textContent = 'SYNERGY MAP';
    bar.appendChild(logo);

    var divider = document.createElement('span');
    divider.style.cssText = 'color:#1e3a6e;font-size:18px;';
    divider.textContent = '|';
    bar.appendChild(divider);

    var instruction = document.createElement('span');
    instruction.style.cssText = 'color:#8ab0d8;font-size:12px;';
    instruction.innerHTML = 'Hover over a field then press <kbd style="background:#1e3a6e;border-radius:3px;padding:1px 6px;color:#7eb8ff">S</kbd> to map it';
    bar.appendChild(instruction);

    var fieldPill = document.createElement('span');
    fieldPill.id = '__syn_field_pill';
    fieldPill.style.cssText = [
        'margin-left:auto','background:#ffd700','color:#0a1628',
        'border-radius:20px','padding:3px 14px',
        'font-size:12px','font-weight:800','letter-spacing:.5px'
    ].join(';');
    bar.appendChild(fieldPill);

    var doneBtn = document.createElement('button');
    doneBtn.textContent = '✓ Done';
    doneBtn.style.cssText = [
        'background:#0e3a1a','color:#4dd88a','border:1px solid #1a6a30',
        'border-radius:6px','padding:4px 14px','font:700 12px "Segoe UI"',
        'cursor:pointer','margin-left:8px'
    ].join(';');
    doneBtn.onclick = function(){ finishMapping(); };
    bar.appendChild(doneBtn);

    document.body.prepend(bar);
    document.body.style.marginTop = '44px';

    // ── Highlight ghost ──────────────────────────────────────────────────
    var ghost = document.createElement('div');
    ghost.id = '__syn_ghost';
    ghost.style.cssText = [
        'position:fixed','pointer-events:none','z-index:2147483646',
        'background:rgba(74,144,217,.12)','border:2px solid #4a90d9',
        'border-radius:4px','transition:all .08s ease','display:none'
    ].join(';');
    document.body.appendChild(ghost);

    function updatePill(){
        if (fieldIdx < FIELDS.length){
            fieldPill.style.background = '#ffd700';
            fieldPill.style.color = '#0a1628';
            fieldPill.textContent = '▸ Next: ' + FIELDS[fieldIdx];
        } else {
            fieldPill.style.background = '#0e3a1a';
            fieldPill.style.color = '#4dd88a';
            fieldPill.textContent = '✅ All fields mapped — press Done';
        }
    }
    updatePill();

    // ── CSS path generator ───────────────────────────────────────────────
    function cssPath(el){
        var path = [];
        while(el && el.nodeType === 1){
            var sel = el.nodeName.toLowerCase();
            if(el.id){ sel += '#' + CSS.escape(el.id); path.unshift(sel); break; }
            var siblings = el.parentNode ? Array.from(el.parentNode.children) : [];
            var sameTag  = siblings.filter(function(s){ return s.nodeName === el.nodeName; });
            if(sameTag.length > 1){
                sel += ':nth-of-type(' + (sameTag.indexOf(el) + 1) + ')';
            }
            path.unshift(sel);
            el = el.parentNode;
        }
        return path.join(' > ');
    }

    // ── Mouse tracking ───────────────────────────────────────────────────
    document.addEventListener('mouseover', function(e){
        var t = e.target;
        if(t.id && t.id.startsWith('__syn')) return;
        currentEl = t;
        var r = t.getBoundingClientRect();
        ghost.style.left   = (r.left   - 2 + window.scrollX) + 'px';
        ghost.style.top    = (r.top    - 2 + window.scrollY) + 'px';
        ghost.style.width  = (r.width  + 4) + 'px';
        ghost.style.height = (r.height + 4) + 'px';
        ghost.style.position = 'absolute';
        ghost.style.display = 'block';
    }, true);

    // ── Key handler ──────────────────────────────────────────────────────
    document.addEventListener('keydown', function(e){
        if(e.key === 's' || e.key === 'S'){
            if(!currentEl || fieldIdx >= FIELDS.length) return;
            e.preventDefault();

            var field   = FIELDS[fieldIdx];
            var sel     = cssPath(currentEl);
            var sample  = (currentEl.innerText || currentEl.textContent || '').trim().substring(0,200);

            window.__synMappings[field] = {selector: sel, sample: sample};
            fieldIdx++;
            updatePill();

            // Flash confirmation
            var old = currentEl.style.outline;
            currentEl.style.outline = '3px solid #4dd88a';
            currentEl.style.transition = 'outline .3s';
            var captured = currentEl;
            setTimeout(function(){ captured.style.outline = old; }, 700);

            // Send to Python bridge
            try {
                window.pyBridge.receiveMapping(JSON.stringify({
                    field: field, selector: sel, sample: sample
                }));
            } catch(err) { console.warn('bridge not ready:', err); }
        }
    }, true);

    // ── Done ─────────────────────────────────────────────────────────────
    function finishMapping(){
        try {
            window.pyBridge.mappingsDone(JSON.stringify(window.__synMappings));
        } catch(err) { console.warn('bridge error:', err); }
        bar.remove();
        ghost.remove();
        document.body.style.marginTop = '';
        window.__synToolActive = false;
    }
})();
"""


# ── Qt WebChannel bridge object ───────────────────────────────────────────
class MappingBridge(QObject):
    """Exposed to JavaScript as window.pyBridge."""
    mapping_received    = pyqtSignal(str, str, str)   # field, selector, sample
    all_done            = pyqtSignal(dict)
    discovery_ready     = pyqtSignal(list)
    timetable_region_ready = pyqtSignal(str)          # region JSON string

    @pyqtSlot(str)
    def receiveMapping(self, json_str: str):
        try:
            d = json.loads(json_str)
            self.mapping_received.emit(d["field"], d["selector"], d.get("sample",""))
        except Exception as e:
            print(f"[bridge] receiveMapping error: {e}")

    @pyqtSlot(str)
    def mappingsDone(self, json_str: str):
        try:
            d = json.loads(json_str)
            self.all_done.emit(d)
        except Exception as e:
            print(f"[bridge] mappingsDone error: {e}")

    @pyqtSlot(str)
    def receiveDiscovery(self, json_str: str):
        try:
            candidates = json.loads(json_str)
            self.discovery_ready.emit(candidates)
        except Exception as e:
            print(f"[bridge] receiveDiscovery error: {e}")

    @pyqtSlot(str)
    def receiveTimetableRegion(self, json_str: str):
        self.timetable_region_ready.emit(json_str)


# ── Embedded browser widget ───────────────────────────────────────────────
class LiveMapPanel(QWidget):
    """
    Full embedded Chromium panel.
    Emits:
      field_mapped(field, selector, sample)  – after each S keypress
      mapping_complete(dict)                 – after Done clicked
      discovery_ready(list)                  – after auto-discover runs
      timetable_region_ready(str)            – region JSON after user draws box
    """
    field_mapped            = pyqtSignal(str, str, str)
    mapping_complete        = pyqtSignal(dict)
    discovery_ready         = pyqtSignal(list)
    timetable_region_ready  = pyqtSignal(str)

    def __init__(self, fields: List[str] = None, parent=None):
        super().__init__(parent)
        self.fields = fields or FIELD_LABELS
        self.mappings: Dict[str, Dict] = {}
        self._map_mode_active = False

        if not WEBENGINE_OK:
            self._build_fallback_ui()
            return

        self._build_ui()

    # ── Fallback when QtWebEngine not installed ───────────────────────────
    def _build_fallback_ui(self):
        layout = QVBoxLayout(self)
        lbl = QLabel(
            "<b>QtWebEngine not installed.</b><br><br>"
            "To enable the embedded browser, run:<br>"
            "<code>pip install PyQt6-WebEngine</code><br><br>"
            "Then restart the application."
        )
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#ff9944;font-size:13px;padding:20px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

    # ── Main UI ───────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top toolbar ──────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet("background:#0d1f3c;border-bottom:1px solid #1e3a6e;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(8)

        self.le_url = QLineEdit()
        self.le_url.setPlaceholderText("Enter Synergy URL and press Go…")
        self.le_url.setStyleSheet(
            "background:#0a1628;border:1px solid #1e3a6e;border-radius:16px;"
            "padding:5px 14px;color:#c8d8f0;font-size:12px;"
        )
        self.le_url.returnPressed.connect(self._navigate)

        btn_go = QPushButton("Go")
        btn_go.setFixedWidth(48)
        btn_go.setFixedHeight(30)
        btn_go.clicked.connect(self._navigate)
        btn_go.setStyleSheet(
            "QPushButton{background:#1a3d7c;color:#7eb8ff;border:1px solid #2a5298;"
            "border-radius:15px;font-weight:700;font-size:11px;}"
            "QPushButton:hover{background:#2a5298;color:#fff;}"
        )

        btn_back = QPushButton("◀")
        btn_fwd  = QPushButton("▶")
        btn_reload = QPushButton("⟳")
        for b in (btn_back, btn_fwd, btn_reload):
            b.setFixedSize(30, 30)
            b.setStyleSheet(
                "QPushButton{background:#0e2140;color:#4a6fa5;border:none;border-radius:15px;font-size:13px;}"
                "QPushButton:hover{background:#1a3d7c;color:#7eb8ff;}"
            )
        btn_back.clicked.connect(lambda: self.browser.back())
        btn_fwd.clicked.connect(lambda:  self.browser.forward())
        btn_reload.clicked.connect(lambda: self.browser.reload())

        self.btn_map_toggle = QPushButton("🎯  Activate Map Mode")
        self.btn_map_toggle.setFixedHeight(30)
        self.btn_map_toggle.setStyleSheet(
            "QPushButton{background:#0e3a1a;color:#4dd88a;border:1px solid #1a6a30;"
            "border-radius:6px;font-weight:700;font-size:11px;padding:0 12px;}"
            "QPushButton:hover{background:#1a6a30;color:#fff;}"
            "QPushButton:checked{background:#4dd88a;color:#0a1628;}"
        )
        self.btn_map_toggle.setCheckable(True)
        self.btn_map_toggle.clicked.connect(self._toggle_map_mode)

        self.btn_discover = QPushButton("🔍  Discover Students")
        self.btn_discover.setFixedHeight(30)
        self.btn_discover.setStyleSheet(
            "QPushButton{background:#1a2a5a;color:#7eb8ff;border:1px solid #2a4a9a;"
            "border-radius:6px;font-weight:700;font-size:11px;padding:0 12px;}"
            "QPushButton:hover{background:#2a4a9a;color:#fff;}"
        )
        self.btn_discover.setToolTip(
            "Scan this page for student records and offer to import them"
        )
        self.btn_discover.clicked.connect(self._run_discovery)

        self.btn_timetable = QPushButton("📸  Capture Timetable")
        self.btn_timetable.setFixedHeight(30)
        self.btn_timetable.setStyleSheet(
            "QPushButton{background:#2a1a5a;color:#b09aff;border:1px solid #4a3a9a;"
            "border-radius:6px;font-weight:700;font-size:11px;padding:0 12px;}"
            "QPushButton:hover{background:#4a3a9a;color:#fff;}"
        )
        self.btn_timetable.setToolTip(
            "Navigate to a student's timetable page, then click this.\n"
            "Draw a box around the timetable and press C to capture."
        )
        self.btn_timetable.clicked.connect(self._start_timetable_capture)

        tb_layout.addWidget(btn_back)
        tb_layout.addWidget(btn_fwd)
        tb_layout.addWidget(btn_reload)
        tb_layout.addWidget(self.le_url, 1)
        tb_layout.addWidget(btn_go)
        tb_layout.addWidget(self.btn_map_toggle)
        tb_layout.addWidget(self.btn_discover)
        tb_layout.addWidget(self.btn_timetable)
        layout.addWidget(toolbar)

        # ── Splitter: browser left, mapping panel right ──────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(3)
        splitter.setStyleSheet("QSplitter::handle{background:#1e3a6e;}")

        # Browser
        self.browser = QWebEngineView()
        self.browser.setMinimumWidth(500)
        self._setup_webchannel()
        self.browser.urlChanged.connect(self._on_url_changed)
        self.browser.loadFinished.connect(self._on_load_finished)

        # Mapping sidebar
        self.map_sidebar = self._build_map_sidebar()

        splitter.addWidget(self.browser)
        splitter.addWidget(self.map_sidebar)
        splitter.setSizes([700, 280])
        layout.addWidget(splitter, 1)

        # ── Status bar ───────────────────────────────────────────────────
        self.lbl_status = QLabel("Ready  •  Navigate to Synergy, then activate Map Mode")
        self.lbl_status.setStyleSheet(
            "background:#060e1c;color:#2a5298;font-size:10px;"
            "padding:3px 12px;border-top:1px solid #1a2a40;"
        )
        layout.addWidget(self.lbl_status)

    def _build_map_sidebar(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#0d1b2a;")
        w.setMinimumWidth(240)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        lbl = QLabel("Field Mappings")
        lbl.setStyleSheet("color:#5b9bd5;font-weight:700;font-size:12px;letter-spacing:1px;")
        layout.addWidget(lbl)

        # Queue of remaining fields
        self.lbl_queue = QLabel()
        self.lbl_queue.setWordWrap(True)
        self.lbl_queue.setStyleSheet("color:#4a6fa5;font-size:10px;line-height:160%;")
        layout.addWidget(self.lbl_queue)
        self._refresh_queue_label()

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#1e3a6e;")
        layout.addWidget(sep)

        # Captured mappings table
        self.tbl_mapped = QTableWidget(0, 2)
        self.tbl_mapped.setHorizontalHeaderLabels(["Field", "Sample"])
        self.tbl_mapped.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_mapped.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_mapped.setStyleSheet(
            "QTableWidget{background:#080f1c;border:1px solid #1a2a40;font-size:10px;}"
            "QHeaderView::section{background:#0d1b2a;color:#4a6fa5;font-size:10px;}"
        )
        self.tbl_mapped.setMaximumHeight(220)
        layout.addWidget(self.tbl_mapped)

        # Field selector (for manual re-map)
        lbl2 = QLabel("Re-map a specific field:")
        lbl2.setStyleSheet("color:#4a6fa5;font-size:10px;margin-top:6px;")
        layout.addWidget(lbl2)
        self.cb_remap = QComboBox()
        self.cb_remap.addItems(self.fields)
        self.cb_remap.setStyleSheet(
            "background:#0e2140;border:1px solid #1e3a6e;border-radius:5px;"
            "color:#c8d8f0;padding:4px 8px;font-size:11px;"
        )
        layout.addWidget(self.cb_remap)
        btn_remap = QPushButton("🎯  Map this field next")
        btn_remap.setFixedHeight(28)
        btn_remap.setStyleSheet(
            "QPushButton{background:#0e2140;color:#5b9bd5;border:1px solid #1e3a6e;"
            "border-radius:5px;font-size:10px;}"
            "QPushButton:hover{background:#1a3d7c;color:#fff;}"
        )
        btn_remap.clicked.connect(self._remap_field)
        layout.addWidget(btn_remap)

        layout.addStretch()

        btn_done = QPushButton("✓  Save All Mappings")
        btn_done.setFixedHeight(34)
        btn_done.setStyleSheet(
            "QPushButton{background:#0e3a1a;color:#4dd88a;border:1px solid #1a6a30;"
            "border-radius:7px;font-weight:700;font-size:12px;}"
            "QPushButton:hover{background:#1a6a30;color:#fff;}"
        )
        btn_done.clicked.connect(self._finish_mapping)
        layout.addWidget(btn_done)

        btn_clear = QPushButton("🗑  Clear Mappings")
        btn_clear.setFixedHeight(28)
        btn_clear.setStyleSheet(
            "QPushButton{background:#1e0808;color:#ff6b6b;border:1px solid #5a1a1a;"
            "border-radius:5px;font-size:10px;}"
            "QPushButton:hover{background:#5a1a1a;color:#fff;}"
        )
        btn_clear.clicked.connect(self._clear_mappings)
        layout.addWidget(btn_clear)

        return w

    # ── WebChannel setup ──────────────────────────────────────────────────
    def _setup_webchannel(self):
        self.bridge = MappingBridge()
        self.bridge.mapping_received.connect(self._on_field_mapped)
        self.bridge.all_done.connect(self._on_all_done)
        self.bridge.discovery_ready.connect(self.discovery_ready)
        self.bridge.timetable_region_ready.connect(self.timetable_region_ready)

        self.channel = QWebChannel()
        self.channel.registerObject("pyBridge", self.bridge)
        self.browser.page().setWebChannel(self.channel)

    # ── Navigation ────────────────────────────────────────────────────────
    def navigate_to(self, url: str):
        if not url.startswith("http"):
            url = "https://" + url
        self.le_url.setText(url)
        self.browser.load(QUrl(url))

    def _navigate(self):
        url = self.le_url.text().strip()
        if url:
            self.navigate_to(url)

    def _on_url_changed(self, url: QUrl):
        self.le_url.setText(url.toString())

    def _on_load_finished(self, ok: bool):
        self.lbl_status.setText("✅ Page loaded" if ok else "⚠ Page load error")
        if ok and self._map_mode_active:
            self._inject_overlay()

    # ── Map mode ──────────────────────────────────────────────────────────
    def _toggle_map_mode(self, checked: bool):
        self._map_mode_active = checked
        if checked:
            self.btn_map_toggle.setText("🔴  Map Mode ON — hover + press S")
            self.lbl_status.setText("Map Mode active. Hover over a field on the page and press S")
            self._inject_overlay()
        else:
            self.btn_map_toggle.setText("🎯  Activate Map Mode")
            self.lbl_status.setText("Map Mode off")

    def _inject_overlay(self):
        """Inject qwebchannel.js then the overlay script."""
        # Step 1: inject qwebchannel.js (Qt provides it at qrc:///qtwebchannel/qwebchannel.js)
        self.browser.page().runJavaScript(
            "if(!window.QWebChannel){ var s=document.createElement('script');"
            "s.src='qrc:///qtwebchannel/qwebchannel.js';"
            "document.head.appendChild(s); }"
        )
        # Step 2: wait a tick then inject bridge init + overlay
        QTimer.singleShot(400, self._inject_overlay_step2)

    def _inject_overlay_step2(self):
        # Build remaining field queue from what hasn't been mapped yet
        remaining = [f for f in self.fields if f not in self.mappings]
        if not remaining:
            remaining = self.fields  # allow re-mapping everything

        js_fields = json.dumps(remaining)
        overlay = _OVERLAY_JS.replace("FIELD_QUEUE_PLACEHOLDER", js_fields)
        bridge_init = _BRIDGE_JS

        full_js = bridge_init + "\n\n" + overlay
        self.browser.page().runJavaScript(full_js)
        self.lbl_status.setText(f"Overlay injected — {len(remaining)} fields to map. Hover + press S")

    # ── Mapping events ────────────────────────────────────────────────────
    def _on_field_mapped(self, field: str, selector: str, sample: str):
        self.mappings[field] = {"selector": selector, "sample": sample}
        self._update_mapped_table()
        self._refresh_queue_label()
        self.lbl_status.setText(f"✅ Mapped: {field}  →  {selector[:50]}…")
        self.field_mapped.emit(field, selector, sample)

    def _on_all_done(self, mappings: dict):
        for field, data in mappings.items():
            self.mappings[field] = data
        self._update_mapped_table()
        self._finish_mapping()

    def _finish_mapping(self):
        self.mapping_complete.emit(self.mappings)
        self._map_mode_active = False
        self.btn_map_toggle.setChecked(False)
        self.btn_map_toggle.setText("🎯  Activate Map Mode")
        self.lbl_status.setText(f"✅ {len(self.mappings)} mappings saved")

    def _run_discovery(self):
        """Inject the discovery JS into the current page."""
        from discovery import DISCOVERY_JS
        # Make sure webchannel bridge is ready first
        self.browser.page().runJavaScript(
            "if(!window.QWebChannel){ var s=document.createElement('script');"
            "s.src='qrc:///qtwebchannel/qwebchannel.js';"
            "document.head.appendChild(s); }"
        )
        QTimer.singleShot(400, lambda: (
            self.browser.page().runJavaScript(_BRIDGE_JS),
            QTimer.singleShot(300, lambda:
                self.browser.page().runJavaScript(DISCOVERY_JS)
            )
        ))
        self.lbl_status.setText(
            "🔍 Scanning page for students… results will appear shortly"
        )

    def _start_timetable_capture(self):
        """Inject the region-selector overlay so the user can draw a box."""
        from timetable_capture import REGION_SELECTOR_JS
        self.browser.page().runJavaScript(
            "if(!window.QWebChannel){ var s=document.createElement('script');"
            "s.src='qrc:///qtwebchannel/qwebchannel.js';"
            "document.head.appendChild(s); }"
        )
        QTimer.singleShot(400, lambda: (
            self.browser.page().runJavaScript(_BRIDGE_JS),
            QTimer.singleShot(300, lambda:
                self.browser.page().runJavaScript(REGION_SELECTOR_JS)
            )
        ))
        self.lbl_status.setText(
            "📸 Draw a box around the timetable, then press C to capture"
        )

    def _clear_mappings(self):
        self.mappings.clear()
        self.tbl_mapped.setRowCount(0)
        self._refresh_queue_label()

    def _remap_field(self):
        field = self.cb_remap.currentText()
        if field in self.mappings:
            del self.mappings[field]
        # Put it at the front of the inject queue
        remaining = [field] + [f for f in self.fields if f not in self.mappings]
        js_fields = json.dumps(remaining)
        overlay = _OVERLAY_JS.replace("FIELD_QUEUE_PLACEHOLDER", js_fields)
        self.browser.page().runJavaScript(_BRIDGE_JS + "\n\n" + overlay)
        self._map_mode_active = True
        self.btn_map_toggle.setChecked(True)
        self.btn_map_toggle.setText("🔴  Map Mode ON — hover + press S")
        self.lbl_status.setText(f"Re-mapping: {field} — hover over it and press S")

    # ── UI helpers ────────────────────────────────────────────────────────
    def _update_mapped_table(self):
        self.tbl_mapped.setRowCount(0)
        for field, data in self.mappings.items():
            r = self.tbl_mapped.rowCount()
            self.tbl_mapped.insertRow(r)
            fi = QTableWidgetItem(field)
            fi.setForeground(QColor("#4dd88a"))
            si = QTableWidgetItem(data.get("sample","")[:40])
            si.setForeground(QColor("#8ab0d8"))
            self.tbl_mapped.setItem(r, 0, fi)
            self.tbl_mapped.setItem(r, 1, si)

    def _refresh_queue_label(self):
        remaining = [f for f in self.fields if f not in self.mappings]
        if not remaining:
            self.lbl_queue.setText("✅ All fields mapped!")
            self.lbl_queue.setStyleSheet("color:#4dd88a;font-size:10px;")
        else:
            lines = "\n".join(f"  • {f}" for f in remaining)
            self.lbl_queue.setText(f"Fields to map:\n{lines}")
            self.lbl_queue.setStyleSheet("color:#4a6fa5;font-size:10px;line-height:160%;")

    def get_mappings(self) -> Dict:
        return dict(self.mappings)

    def load_existing_mappings(self, mappings: Dict):
        """Pre-populate from saved DB mappings."""
        self.mappings = {k: v for k, v in mappings.items()}
        self._update_mapped_table()
        self._refresh_queue_label()
