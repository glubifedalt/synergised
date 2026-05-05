"""
timetable_capture.py – Synergy Teacher Dashboard
Handles:
  - Injecting the region-selector JS overlay into the embedded browser
  - Waiting for page load + configurable settle time
  - Capturing a QWebEngineView screenshot cropped to the timetable region
  - Running Tesseract OCR on the image to extract text & teacher names
  - Saving PNG to ~/.synergy_tool/timetables/
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Callable

from PyQt6.QtCore import Qt, QTimer, QRect, QSize, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QPainter, QImage, QColor

APP_DIR  = Path.home() / ".synergy_tool"
IMG_DIR  = APP_DIR / "timetables"
IMG_DIR.mkdir(parents=True, exist_ok=True)

# ── OCR (optional – graceful fallback if tesseract missing) ───────────────
try:
    import pytesseract
    from PIL import Image as PILImage
    OCR_OK = True
except ImportError:
    OCR_OK = False

# ── Regex patterns for teacher name extraction ─────────────────────────────
# Common Synergy formats: "Mr J Smith", "Mrs Smith", "Miss A Jones", "Dr Brown"
_TITLE_PAT = r"\b(?:Mr|Mrs|Miss|Ms|Dr|Prof)\.?\s+[A-Z][a-zA-Z\-']{1,20}(?:\s+[A-Z][a-zA-Z\-']{1,20})?\b"
_INITIALS_PAT = r"\b[A-Z]{1,3}\s*[A-Z][a-z]{2,15}\b"   # "JD Smith" style codes

# ── JS injected to let user box the timetable region ─────────────────────
REGION_SELECTOR_JS = r"""
(function(){
    if(window.__synTTActive) return;
    window.__synTTActive = true;
    window.__synTTRegion = null;

    // Instruction bar
    var bar = document.createElement('div');
    bar.style.cssText = [
        'position:fixed','top:0','left:0','right:0','z-index:2147483647',
        'background:linear-gradient(90deg,#0d1f3c,#1a3d7c)',
        'color:#e0e8ff','font:700 13px/44px "Segoe UI",sans-serif',
        'padding:0 16px','display:flex','align-items:center','gap:14px',
        'box-shadow:0 2px 12px #0008','border-bottom:2px solid #ffd700'
    ].join(';');
    bar.innerHTML = '<span style="color:#ffd700;font-size:11px;letter-spacing:2px;">TIMETABLE SELECT</span>'
        + '<span style="color:#8ab0d8;font-size:12px;">Click and drag to draw a box around the timetable, then press <kbd style="background:#1e3a6e;border-radius:3px;padding:1px 6px;color:#7eb8ff">C</kbd> to capture</span>'
        + '<span id="__tt_status" style="margin-left:auto;background:#ffd700;color:#0a1628;border-radius:20px;padding:3px 14px;font-size:11px;font-weight:800;">Draw box</span>';
    document.body.prepend(bar);
    document.body.style.marginTop = '44px';

    // Selection box overlay
    var selBox = document.createElement('div');
    selBox.style.cssText = [
        'position:absolute','border:2px dashed #ffd700','pointer-events:none',
        'z-index:2147483646','background:rgba(255,215,0,0.08)',
        'display:none','box-sizing:border-box'
    ].join(';');
    document.body.appendChild(selBox);

    var startX=0,startY=0,drawing=false;
    var region = null;

    document.addEventListener('mousedown', function(e){
        if(e.target.closest && e.target.closest('[style*="z-index:2147483647"]')) return;
        drawing = true;
        startX = e.pageX; startY = e.pageY;
        selBox.style.left   = startX+'px';
        selBox.style.top    = startY+'px';
        selBox.style.width  = '0';
        selBox.style.height = '0';
        selBox.style.display = 'block';
        e.preventDefault();
    }, true);

    document.addEventListener('mousemove', function(e){
        if(!drawing) return;
        var x = Math.min(e.pageX, startX);
        var y = Math.min(e.pageY, startY);
        var w = Math.abs(e.pageX - startX);
        var h = Math.abs(e.pageY - startY);
        selBox.style.left   = x+'px';
        selBox.style.top    = y+'px';
        selBox.style.width  = w+'px';
        selBox.style.height = h+'px';
        document.getElementById('__tt_status').textContent = w+'×'+h+'px';
    }, true);

    document.addEventListener('mouseup', function(e){
        if(!drawing) return;
        drawing = false;
        var x = Math.min(e.pageX, startX);
        var y = Math.min(e.pageY, startY);
        var w = Math.abs(e.pageX - startX);
        var h = Math.abs(e.pageY - startY);
        region = {
            x: x, y: y, w: w, h: h,
            scrollX: window.scrollX, scrollY: window.scrollY,
            dpr: window.devicePixelRatio || 1
        };
        window.__synTTRegion = region;
        document.getElementById('__tt_status').textContent = 'Press C to capture';
        document.getElementById('__tt_status').style.background = '#4dd88a';
        document.getElementById('__tt_status').style.color = '#0a1628';
    }, true);

    document.addEventListener('keydown', function(e){
        if((e.key==='c'||e.key==='C') && window.__synTTRegion){
            try{
                window.pyBridge.receiveTimetableRegion(JSON.stringify(window.__synTTRegion));
            }catch(err){ console.warn('bridge err',err); }
            // Clean up
            bar.remove();
            selBox.remove();
            document.body.style.marginTop = '';
            window.__synTTActive = false;
        }
        if(e.key==='Escape'){
            bar.remove(); selBox.remove();
            document.body.style.marginTop = '';
            window.__synTTActive = false;
        }
    }, true);
})();
"""


# ── Capture engine ────────────────────────────────────────────────────────

class TimetableCapture(QObject):
    """
    Orchestrates:
      1. Inject region-selector JS
      2. Receive region from JS bridge
      3. Wait settle_ms for dynamic content
      4. Grab QWebEngineView, crop to region
      5. Save PNG, run OCR, return result
    """
    capture_done   = pyqtSignal(str, str, list)   # image_path, ocr_text, teachers
    capture_failed = pyqtSignal(str)              # error message
    status_update  = pyqtSignal(str)

    def __init__(self, browser_view, settle_ms: int = 800, parent=None):
        super().__init__(parent)
        self.view       = browser_view
        self.settle_ms  = settle_ms
        self._region: Optional[Dict] = None

    def start_region_select(self):
        """Inject the JS overlay so user can draw the timetable box."""
        self.status_update.emit("Draw a box around the timetable, then press C")
        self.view.page().runJavaScript(
            "if(!window.QWebChannel){"
            "var s=document.createElement('script');"
            "s.src='qrc:///qtwebchannel/qwebchannel.js';"
            "document.head.appendChild(s);}"
        )
        QTimer.singleShot(400, lambda: (
            self.view.page().runJavaScript(_BRIDGE_INIT_JS),
            QTimer.singleShot(300, lambda:
                self.view.page().runJavaScript(REGION_SELECTOR_JS)
            )
        ))

    def receive_region(self, region_json: str):
        """Called by the Qt bridge when user presses C."""
        try:
            self._region = json.loads(region_json)
        except Exception as e:
            self.capture_failed.emit(f"Region parse error: {e}")
            return
        self.status_update.emit(
            f"Region locked ({self._region['w']}×{self._region['h']}px) — "
            f"waiting {self.settle_ms}ms for page to settle…"
        )
        QTimer.singleShot(self.settle_ms, self._do_capture)

    def _do_capture(self):
        self.status_update.emit("Capturing screenshot…")
        try:
            # Grab the full widget as a pixmap
            full_px = self.view.grab()

            if self._region:
                r = self._region
                dpr = r.get("dpr", 1.0)
                scroll_y = r.get("scrollY", 0)
                # Toolbar offset (the browser's own toolbar is ~48px)
                toolbar_h = 48
                # Convert page coords → widget coords
                crop_x = int(r["x"] * dpr)
                crop_y = int((r["y"] - scroll_y + toolbar_h) * dpr)
                crop_w = int(r["w"] * dpr)
                crop_h = int(r["h"] * dpr)
                # Clamp to pixmap bounds
                pw, ph = full_px.width(), full_px.height()
                crop_x = max(0, min(crop_x, pw - 1))
                crop_y = max(0, min(crop_y, ph - 1))
                crop_w = min(crop_w, pw - crop_x)
                crop_h = min(crop_h, ph - crop_y)
                px = full_px.copy(QRect(crop_x, crop_y, crop_w, crop_h))
            else:
                px = full_px

            # Save
            fname = f"tt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            fpath = str(IMG_DIR / fname)
            px.save(fpath, "PNG")

            # OCR
            ocr_text, teachers = "", []
            if OCR_OK:
                self.status_update.emit("Running OCR to extract teacher names…")
                ocr_text, teachers = self._run_ocr(fpath)

            self.status_update.emit(
                f"✅ Timetable captured — {len(teachers)} teacher name(s) found"
            )
            self.capture_done.emit(fpath, ocr_text, teachers)

        except Exception as e:
            self.capture_failed.emit(f"Capture error: {e}")

    def _run_ocr(self, image_path: str) -> Tuple[str, List[str]]:
        try:
            img = PILImage.open(image_path)
            # Upscale for better OCR accuracy
            w, h = img.size
            if w < 1200:
                scale = 1200 / w
                img = img.resize((int(w*scale), int(h*scale)), PILImage.LANCZOS)

            text = pytesseract.image_to_string(img, config="--psm 6")
            teachers = self._extract_teachers(text)
            return text, teachers
        except Exception as e:
            return f"OCR error: {e}", []

    def _extract_teachers(self, text: str) -> List[str]:
        found = set()
        # Title + name pattern (Mr Smith, Mrs Jones etc.)
        for m in re.finditer(_TITLE_PAT, text):
            name = re.sub(r"\s+", " ", m.group(0)).strip()
            found.add(name)
        # Short codes often used in timetables: e.g. "SMI", "JON"
        # These appear in cells — capture 2-4 uppercase letter codes
        codes = re.findall(r"\b[A-Z]{2,4}\b", text)
        # Only keep codes that appear multiple times (likely a staff code)
        from collections import Counter
        code_counts = Counter(codes)
        for code, count in code_counts.items():
            if count >= 2 and code not in {"AM","PM","ICT","PE","RE","DT","MFL"}:
                found.add(code)
        return sorted(found)


# Minimal bridge init JS (re-used from live_map_panel but kept self-contained)
_BRIDGE_INIT_JS = """
new QWebChannel(qt.webChannelTransport, function(channel){
    window.pyBridge = channel.objects.pyBridge;
});
"""
