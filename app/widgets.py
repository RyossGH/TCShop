"""Composants d'interface réutilisables."""
from __future__ import annotations

import hashlib
from pathlib import Path
import urllib.request
from typing import Callable

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QObject, QRunnable, QSortFilterProxyModel, Qt, QThreadPool, QTimer, Signal,
)
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QSizePolicy,
    QTableView, QVBoxLayout, QWidget,
)

from . import theme
from .api import UA
from .constants import STATUS_COLORS
from .db import CACHE_DIR, DATA_DIR


# ------------------------------------------------------------------ formatage
def money(v) -> str:
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        v = 0.0
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} €"


def fdate(s: str | None, with_time: bool = True) -> str:
    if not s:
        return ""
    d, _, t = s.partition(" ")
    parts = d.split("-")
    out = f"{parts[2]}/{parts[1]}/{parts[0]}" if len(parts) == 3 else d
    return f"{out} {t[:5]}" if with_time and t else out


# ------------------------------------------------------------------ asynchrone
class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn: Callable):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn()
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(str(e) or e.__class__.__name__)
            return
        self.signals.done.emit(result)


_alive: set = set()


def run_async(fn: Callable, on_done: Callable | None = None, on_error: Callable | None = None):
    """Exécute fn() dans un thread ; les callbacks sont appelés dans le thread de l'interface."""
    task = _Task(fn)
    task.setAutoDelete(False)
    _alive.add(task)

    def _release(*_):
        QTimer.singleShot(0, lambda: _alive.discard(task))

    def _safe(cb):
        def inner(arg):
            try:
                cb(arg)
            except RuntimeError:  # widget détruit entre-temps
                pass
        return inner

    if on_done:
        task.signals.done.connect(_safe(on_done))
    if on_error:
        task.signals.failed.connect(_safe(on_error))
    task.signals.done.connect(_release)
    task.signals.failed.connect(_release)
    QThreadPool.globalInstance().start(task)


# ------------------------------------------------------------------ images
_pix_cache: dict[str, QPixmap] = {}


def load_pixmap(url: str, callback: Callable[[QPixmap], None]):
    if not url:
        return
    if url in _pix_cache:
        callback(_pix_cache[url])
        return
    if not url.lower().startswith(("http://", "https://")):  # image locale (photo du produit)
        local = Path(url) if Path(url).is_absolute() else DATA_DIR / url
        pm = QPixmap(str(local))
        if not pm.isNull():
            _pix_cache[url] = pm
        callback(pm)
        return
    path = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".img")

    def ready(p):
        pm = QPixmap(str(p))
        if not pm.isNull():
            if len(_pix_cache) > 800:
                _pix_cache.clear()
            _pix_cache[url] = pm
        callback(pm)

    if path.exists():
        ready(path)
        return

    def download():
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    run_async(download, ready, lambda _e: None)


class ImageLabel(QLabel):
    def __init__(self, w: int = 230, h: int = 320, parent=None):
        super().__init__(parent)
        self._url = ""
        self._w, self._h = w, h
        self.setFixedSize(w, h)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("Muted")
        self.setStyleSheet(f"border: 1px dashed {theme.c('border')}; border-radius: 10px;")
        self.setText("Aucune image")

    def set_url(self, url: str):
        self._url = url or ""
        self.setPixmap(QPixmap())
        self.setText("Chargement…" if url else "Aucune image")
        if url:
            load_pixmap(url, lambda pm, u=url: self._show(pm, u))

    def _show(self, pm: QPixmap, url: str):
        if url != self._url:
            return
        if pm.isNull():
            self.setText("Image indisponible")
            return
        self.setText("")
        self.setPixmap(pm.scaled(self._w - 4, self._h - 4, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation))


# ------------------------------------------------------------------ tableaux
class RecordModel(QAbstractTableModel):
    """Modèle générique : columns = [(clé, titre, type)] ; type ∈ text,int,qty,money,pct,date,bool,status."""

    NUMERIC = {"int", "qty", "money", "pct"}

    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows: list[dict] = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = [dict(r) for r in rows]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.columns[section][1]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key, _title, kind = self.columns[index.column()]
        v = row.get(key)
        if role == Qt.ItemDataRole.DisplayRole:
            if kind == "money":
                return money(v)
            if kind == "pct":
                return f"{float(v or 0):.1f} %"
            if kind == "date":
                return fdate(v)
            if kind == "bool":
                return "✔" if v else ""
            if kind == "qty" and row.get("track_stock") == 0:
                return "∞"  # prestation sans stock
            if kind in ("int", "qty"):
                return "" if v is None else str(int(v))
            if kind == "delta":
                return f"{int(v):+d}" if v is not None else ""
            return "" if v is None else str(v)
        if role == Qt.ItemDataRole.UserRole:  # tri
            if kind in self.NUMERIC or kind in ("bool", "delta"):
                try:
                    return float(v or 0)
                except (TypeError, ValueError):
                    return 0.0
            return str(v or "").lower()
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if kind in self.NUMERIC or kind == "delta":
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if kind == "bool":
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            if kind == "qty" and row.get("track_stock") != 0:
                q = int(v or 0)
                if q <= 0:
                    return QColor(theme.c("danger"))
                if row.get("min_stock") and q <= int(row["min_stock"]):
                    return QColor(theme.c("warning"))
            if kind == "delta" and v is not None:
                return QColor(theme.c("success") if int(v) > 0 else theme.c("danger"))
            if kind == "status":
                return QColor(theme.c(STATUS_COLORS.get(str(v), "text")))
            if kind == "bool" and v:
                return QColor(theme.c("success"))
        if role == Qt.ItemDataRole.FontRole and kind in ("status", "qty"):
            from PySide6.QtGui import QFont
            f = QFont()
            f.setBold(True)
            return f
        return None


class DataTable(QTableView):
    record_activated = Signal(dict)
    selection_changed_record = Signal(object)

    def __init__(self, columns, stretch: str | None = None, parent=None):
        super().__init__(parent)
        self.model_ = RecordModel(columns, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model_)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.setModel(self.proxy)
        self.setSortingEnabled(True)
        self.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(30)
        hh = self.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(False)
        self._stretch = stretch
        self.doubleClicked.connect(self._activated)
        self.selectionModel().selectionChanged.connect(lambda *_: self.selection_changed_record.emit(self.selected()))

    def set_columns(self, columns, stretch: str | None = None):
        """Change les colonnes affichées (ex. colonnes « carte » masquées pour les accessoires)."""
        if columns == self.model_.columns:
            return
        self.model_.beginResetModel()
        self.model_.columns = columns
        self.model_.endResetModel()
        hh = self.horizontalHeader()
        for i in range(len(columns)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        if stretch:
            self._stretch = stretch

    def set_rows(self, rows):
        sel = self.selected()
        self.model_.set_rows(rows)
        self.resizeColumnsToContents()
        hh = self.horizontalHeader()
        for i, (key, _t, _k) in enumerate(self.model_.columns):
            if self.columnWidth(i) > 320:
                self.setColumnWidth(i, 320)
            if key == self._stretch:
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        if sel and "id" in sel:
            self.select_id(sel["id"])

    def select_id(self, rid):
        for r, row in enumerate(self.model_.rows):
            if row.get("id") == rid:
                idx = self.proxy.mapFromSource(self.model_.index(r, 0))
                self.selectRow(idx.row())
                return

    def _activated(self, idx):
        self.record_activated.emit(self.model_.rows[self.proxy.mapToSource(idx).row()])

    def selected(self) -> dict | None:
        rows = self.selectionModel().selectedRows()
        if not rows:
            return None
        return self.model_.rows[self.proxy.mapToSource(rows[0]).row()]

    def selected_all(self) -> list[dict]:
        return [self.model_.rows[self.proxy.mapToSource(i).row()] for i in self.selectionModel().selectedRows()]

    def rows(self) -> list[dict]:
        return self.model_.rows


# ------------------------------------------------------------------ petits composants
def button(text: str, slot=None, kind: str | None = None, tip: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    # sinon, dans une boîte de dialogue, le « Entrée » envoyé par le scanner déclencherait ce bouton
    b.setAutoDefault(False)
    return b


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


class Card(QFrame):
    def __init__(self, parent=None, margins=16, spacing=10, horizontal=False):
        super().__init__(parent)
        self.setObjectName("Card")
        self.lay = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        self.lay.setContentsMargins(margins, margins, margins, margins)
        self.lay.setSpacing(spacing)


class KpiCard(Card):
    def __init__(self, title: str, icon: str = "", parent=None):
        super().__init__(parent, margins=14, spacing=2)
        self.title = label(f"{icon}  {title.upper()}" if icon else title.upper(), "KpiTitle")
        self.value = label("—", "KpiValue")
        self.sub = label("", "Muted")
        self.lay.addWidget(self.title)
        self.lay.addWidget(self.value)
        self.lay.addWidget(self.sub)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set(self, value: str, sub: str = "", color: str | None = None):
        self.value.setText(value)
        self.sub.setText(sub)
        self.value.setStyleSheet(f"color: {theme.c(color)};" if color else "")


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label(title, "H1"))
        if subtitle:
            col.addWidget(label(subtitle, "Muted"))
        lay.addLayout(col)
        lay.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)

    def add(self, w):
        self.actions.addWidget(w)
        return w


def page_layout(widget: QWidget) -> QVBoxLayout:
    widget.setObjectName("Page")
    lay = QVBoxLayout(widget)
    lay.setContentsMargins(24, 20, 24, 20)
    lay.setSpacing(14)
    return lay


def ask(parent, title: str, text: str) -> bool:
    r = QMessageBox.question(parent, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                             QMessageBox.StandardButton.No)
    return r == QMessageBox.StandardButton.Yes


def info(parent, title: str, text: str):
    QMessageBox.information(parent, title, text)


def warn(parent, title: str, text: str):
    QMessageBox.warning(parent, title, text)
