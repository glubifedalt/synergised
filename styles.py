"""
styles.py – Synergy Teacher Dashboard
Single source of truth for the application stylesheet.
Import QSS from here instead of main_window to avoid circular imports.
"""

QSS = """
QMainWindow, QWidget {
    background: #0a1628;
    color: #c8d8f0;
    font-family: 'Segoe UI', 'SF Pro Display', Helvetica, Arial, sans-serif;
    font-size: 12px;
}
QSplitter::handle { background: #1e3a6e; width: 2px; height: 2px; }

/* Sidebar */
#sidebar {
    background: #0d1f3c;
    border-right: 1px solid #1e3a6e;
    min-width: 240px; max-width: 280px;
}
#sidebar QLabel#logo {
    color: #5b9bd5;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 18px 16px 4px 16px;
}
#sidebar QLabel#subtitle {
    color: #2a5298;
    font-size: 10px;
    letter-spacing: 2px;
    padding: 0 16px 14px 16px;
}

/* Search */
QLineEdit#search {
    background: #112244;
    border: 1px solid #1e3a6e;
    border-radius: 8px;
    padding: 7px 12px;
    color: #c8d8f0;
    font-size: 12px;
    margin: 0 10px;
}
QLineEdit#search:focus { border-color: #4a90d9; }

/* Student list */
QListWidget#student_list {
    background: transparent;
    border: none;
    padding: 4px 6px;
}
QListWidget#student_list::item {
    background: #0e2140;
    border: 1px solid #1a3358;
    border-radius: 8px;
    padding: 8px 10px;
    margin: 3px 0;
    color: #b0c8e8;
}
QListWidget#student_list::item:selected {
    background: #1a3d7c;
    border-color: #4a90d9;
    color: #ffffff;
}
QListWidget#student_list::item:hover {
    background: #162d58;
    border-color: #2a5298;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #1e3a6e;
    border-radius: 8px;
    background: #0d1b2a;
    padding: 4px;
}
QTabBar::tab {
    background: #0e2140;
    color: #4a6fa5;
    border: 1px solid #1e3a6e;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    padding: 7px 16px;
    margin-right: 3px;
    font-size: 11px;
    font-weight: 600;
}
QTabBar::tab:selected { background: #1a3d7c; color: #ffffff; border-color: #4a90d9; }
QTabBar::tab:hover:!selected { background: #162d58; color: #c0d8f8; }

/* Buttons */
QPushButton {
    background: #1a3d7c;
    color: #7eb8ff;
    border: 1px solid #2a5298;
    border-radius: 7px;
    padding: 7px 16px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton:hover { background: #2a5298; color: #ffffff; }
QPushButton:pressed { background: #0e2140; }
QPushButton#btn_danger  { background: #4a1020; color: #ff6b6b; border-color: #8b1a30; }
QPushButton#btn_danger:hover  { background: #8b1a30; color: #ffffff; }
QPushButton#btn_praise  { background: #0e3a1a; color: #4dd88a; border-color: #1a6a30; }
QPushButton#btn_praise:hover  { background: #1a6a30; }
QPushButton#btn_sanction{ background: #3a1a0e; color: #ff9944; border-color: #7a3010; }
QPushButton#btn_sanction:hover{ background: #7a3010; }
QPushButton#btn_sync    { background: #0e2a4a; color: #5b9bd5; border-color: #1e4a7e; padding: 8px 20px; }
QPushButton#btn_sync:hover    { background: #1e4a7e; }

/* Fields */
QLineEdit, QTextEdit, QSpinBox, QComboBox {
    background: #0e2140;
    border: 1px solid #1e3a6e;
    border-radius: 6px;
    padding: 6px 10px;
    color: #c8d8f0;
    font-size: 12px;
    selection-background-color: #2a5298;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #4a90d9;
    background: #112244;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #0e2140; color: #c8d8f0;
    selection-background-color: #1a3d7c;
    border: 1px solid #2a5298;
}

/* Table */
QTableWidget {
    background: #0d1b2a;
    border: 1px solid #1e3a6e;
    border-radius: 6px;
    gridline-color: #1a3050;
    color: #b0c8e8;
    font-size: 11px;
}
QHeaderView::section {
    background: #0e2140;
    color: #5b9bd5;
    border: none;
    border-bottom: 1px solid #1e3a6e;
    padding: 6px 10px;
    font-weight: 700;
    font-size: 11px;
}
QTableWidget::item:selected { background: #1a3d7c; color: #fff; }

/* Group boxes */
QGroupBox {
    border: 1px solid #1e3a6e;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 700;
    color: #5b9bd5;
    font-size: 11px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #5b9bd5;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #0a1628; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #1e3a6e; border-radius: 4px; min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #2a5298; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal {
    background: #0a1628; height: 8px; border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #1e3a6e; border-radius: 4px; min-width: 20px;
}

/* Status bar */
QStatusBar {
    background: #0d1b2a; color: #2a5298;
    font-size: 10px; border-top: 1px solid #1e3a6e;
}

/* Stat cards */
#card_praise   { background: #0a2218; border: 1px solid #1a5030; border-radius: 10px; padding: 8px 14px; }
#card_sanction { background: #221008; border: 1px solid #5a2808; border-radius: 10px; padding: 8px 14px; }
#card_phone    { background: #08182a; border: 1px solid #1a3050; border-radius: 10px; padding: 8px 14px; }

/* Dialog backgrounds */
QDialog { background: #0a1628; }
"""
