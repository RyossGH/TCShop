"""Thèmes visuels (feuille de style Qt)."""
from __future__ import annotations

from string import Template

PALETTES = {
    "Sombre": dict(
        bg="#0e1120", panel="#161a2e", panel2="#1d2239", border="#2a3052", text="#e7e9f5", muted="#8b91b0",
        accent="#7c5cff", accent_hover="#927aff", accent_text="#ffffff", sel="#2f2a63",
        success="#22c55e", warning="#f59e0b", danger="#ef4444", info="#38bdf8", input="#12162a",
    ),
    "Clair": dict(
        bg="#f3f4f9", panel="#ffffff", panel2="#eef0f7", border="#d9dcea", text="#1a1d2e", muted="#697090",
        accent="#6a48ff", accent_hover="#7d60ff", accent_text="#ffffff", sel="#e3dcff",
        success="#16a34a", warning="#d97706", danger="#dc2626", info="#0284c7", input="#ffffff",
    ),
}

_current = dict(PALETTES["Sombre"])


def c(name: str) -> str:
    """Couleur de la palette active."""
    if name == "muted":
        return _current["muted"]
    return _current.get(name, _current["text"])


QSS = Template("""
* { font-family: "Segoe UI", "Segoe UI Emoji"; font-size: 10pt; color: $text; }
QMainWindow, QDialog, QWidget#Page { background: $bg; }
QToolTip { background: $panel2; color: $text; border: 1px solid $border; padding: 4px; }

QFrame#Card { background: $panel; border: 1px solid $border; border-radius: 12px; }
QFrame#Sidebar { background: $panel; border-right: 1px solid $border; }
QLabel { background: transparent; }
QLabel#H1 { font-size: 19pt; font-weight: 700; }
QLabel#H2 { font-size: 12.5pt; font-weight: 650; }
QLabel#Muted { color: $muted; }
QLabel#Brand { font-size: 15pt; font-weight: 800; color: $accent; }
QLabel#KpiTitle { color: $muted; font-size: 9pt; font-weight: 600; }
QLabel#KpiValue { font-size: 18pt; font-weight: 750; }
QLabel#Total { font-size: 26pt; font-weight: 800; color: $accent; }
QLabel#Badge { background: $sel; color: $text; border-radius: 9px; padding: 2px 8px; font-weight: 600; }

QListWidget#Nav { background: transparent; border: none; outline: 0; }
QListWidget#Nav::item { padding: 10px 12px; margin: 2px 8px; border-radius: 8px; color: $muted; }
QListWidget#Nav::item:hover { background: $panel2; color: $text; }
QListWidget#Nav::item:selected { background: $accent; color: $accent_text; font-weight: 600; }

QPushButton { background: $panel2; border: 1px solid $border; border-radius: 8px; padding: 7px 14px; }
QPushButton:hover { border-color: $accent; }
QPushButton:pressed { background: $sel; }
QPushButton:disabled { color: $muted; background: $panel; }
QPushButton[kind="primary"] { background: $accent; border: 1px solid $accent; color: $accent_text; font-weight: 600; }
QPushButton[kind="primary"]:hover { background: $accent_hover; }
QPushButton[kind="danger"] { color: $danger; }
QPushButton[kind="danger"]:hover { border-color: $danger; }
QPushButton[kind="success"] { background: $success; border: 1px solid $success; color: white; font-weight: 600; }
QPushButton[kind="big"] { padding: 14px; font-size: 11.5pt; font-weight: 650; }
QPushButton[kind="flat"] { background: transparent; border: none; padding: 4px 8px; }
QPushButton[kind="flat"]:hover { color: $accent; }
QPushButton[kind="chip"] { border-radius: 14px; padding: 5px 12px; color: $muted; }
QPushButton[kind="chip"]:checked { background: $accent; border-color: $accent; color: $accent_text; font-weight: 600; }
QToolButton#Tile { background: $panel2; border: 1px solid $border; border-radius: 10px; padding: 6px;
    font-size: 9pt; font-weight: 600; }
QToolButton#Tile:hover { border-color: $accent; background: $sel; }
QToolButton#Tile:pressed { background: $accent; color: $accent_text; }
QToolButton#Tile[empty="true"] { color: $muted; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QPlainTextEdit, QTextEdit {
    background: $input; border: 1px solid $border; border-radius: 7px; padding: 5px 8px;
    selection-background-color: $accent; selection-color: white;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {
    border: 1px solid $accent;
}
QLineEdit#Search { padding: 8px 12px; font-size: 11pt; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $panel; border: 1px solid $border; selection-background-color: $sel; outline: 0; }
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button { width: 16px; border: none; }

QTableView, QListView, QTreeView, QTableWidget {
    background: $panel; alternate-background-color: $panel2; border: 1px solid $border; border-radius: 10px;
    gridline-color: transparent; selection-background-color: $sel; selection-color: $text; outline: 0;
}
QTableView::item { padding: 4px 6px; border: none; }
QHeaderView::section {
    background: $panel; color: $muted; border: none; border-bottom: 1px solid $border;
    padding: 7px 6px; font-weight: 600;
}
QTableCornerButton::section { background: $panel; border: none; }

QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: $muted; padding: 8px 16px; margin-right: 4px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: $text; border-bottom: 2px solid $accent; font-weight: 600; }
QTabBar::tab:hover { color: $text; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QProgressBar { background: $panel2; border: none; border-radius: 6px; height: 12px; text-align: center; font-size: 8pt; }
QProgressBar::chunk { background: $accent; border-radius: 6px; }
QCheckBox, QRadioButton { spacing: 6px; background: transparent; }
QGroupBox { border: 1px solid $border; border-radius: 10px; margin-top: 14px; padding: 12px 10px 10px 10px; background: $panel; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: $muted; font-weight: 600; }
QStatusBar { background: $panel; color: $muted; border-top: 1px solid $border; }
QMenu { background: $panel; border: 1px solid $border; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: $sel; }
QSplitter::handle { background: transparent; }
""")


def apply_theme(app, name: str) -> None:
    global _current
    _current = dict(PALETTES.get(name, PALETTES["Sombre"]))
    app.setStyleSheet(QSS.substitute(_current))
