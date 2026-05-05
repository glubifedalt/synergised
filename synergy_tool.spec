# synergy_tool.spec  –  PyInstaller 6+ compatible
# Usage:  cd path/to/synergy_tool   &&   pyinstaller synergy_tool.spec
# Output: dist/SynergyDashboard.exe  (Windows)
#         dist/SynergyDashboard      (macOS / Linux)

import sys
import os

# Always resolve paths relative to THIS spec file so it works
# regardless of where pyinstaller is invoked from.
HERE = os.path.abspath(os.path.dirname(SPEC))   # SPEC is set by PyInstaller

a = Analysis(
    [os.path.join(HERE, 'main.py')],
    pathex=[HERE],
    binaries=[],
    datas=[
        # Uncomment to bundle Tesseract language data (Windows example):
        # ('C:/Program Files/Tesseract-OCR/tessdata', 'tessdata'),
    ],
    hiddenimports=[
        # Matplotlib
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_agg',
        'matplotlib.figure',
        'matplotlib.patheffects',
        'matplotlib.colors',
        # Qt
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebChannel',
        # OCR (optional – won't break if not installed)
        'PIL',
        'PIL.Image',
        'pytesseract',
        # Web
        'bs4',
        'requests',
        # Stdlib
        'sqlite3',
        'json',
        'csv',
        'webbrowser',
        'collections',
        're',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['selenium', 'tkinter', 'wx'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SynergyDashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,           # single portable file
    # icon=os.path.join(HERE, 'icon.ico'),  # uncomment if you have an icon
)
