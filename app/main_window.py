"""Fenêtre principale : navigation latérale + pages."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
)

from . import APP_NAME, APP_TAGLINE, APP_VERSION, resource
from .barcode import normalize_scan
from .scan import ScannerFilter, resolve_unknown
from .sync_server import SyncServer
from .pages.buylist import BuylistPage
from .pages.collections import CollectionsPage
from .pages.customers import CustomersPage
from .pages.dashboard import DashboardPage
from .pages.inventory import InventoryPage
from .pages.movements import MovementsPage
from .pages.orders import OrdersPage
from .pages.pos import PosPage
from .pages.settings import SettingsPage
from .pages.suppliers import SuppliersPage
from .widgets import label, warn

PAGES = [
    ("dashboard", "📊   Tableau de bord", DashboardPage),
    ("pos", "🛒   Caisse", PosPage),
    ("inventory", "🗃️   Inventaire", InventoryPage),
    ("buylist", "🤝   Rachats", BuylistPage),
    ("orders", "📦   Commandes en ligne", OrdersPage),
    ("suppliers", "🚚   Fournisseurs & réassort", SuppliersPage),
    ("customers", "👥   Clients", CustomersPage),
    ("collections", "📚   Collections", CollectionsPage),
    ("movements", "🔁   Mouvements de stock", MovementsPage),
    ("settings", "⚙️   Paramètres", SettingsPage),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        ctx.window = self
        self.setWindowTitle(APP_NAME)
        self.resize(1480, 900)
        self.setMinimumSize(1150, 700)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(240)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 18, 0, 12)
        sl.setSpacing(4)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(18, 0, 0, 0)
        brand_row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QPixmap(resource("tcshop_512.png")).scaled(
            40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        brand_row.addWidget(logo)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand_col.addWidget(label(APP_NAME, "Brand"))
        brand_col.addWidget(label(APP_TAGLINE, "Muted"))
        brand_row.addLayout(brand_col)
        brand_row.addStretch(1)
        sl.addLayout(brand_row)
        sl.addSpacing(6)
        self.shop_lbl = label("", "Muted")
        self.shop_lbl.setContentsMargins(22, 0, 0, 10)
        sl.addWidget(self.shop_lbl)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sl.addWidget(self.nav, 1)
        self.alerts = label("", "Muted", wrap=True)
        self.alerts.setContentsMargins(20, 0, 12, 0)
        sl.addWidget(self.alerts)
        ver = label(f"v{APP_VERSION}", "Muted")
        ver.setContentsMargins(20, 6, 0, 0)
        sl.addWidget(ver)
        root.addWidget(side)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.pages: dict[str, QWidget] = {}
        self.keys: list[str] = []
        for i, (key, title, cls) in enumerate(PAGES):
            page = cls(ctx)
            self.pages[key] = page
            self.keys.append(key)
            self.stack.addWidget(page)
            it = QListWidgetItem(title)
            it.setToolTip(f"F{i + 1}")
            self.nav.addItem(it)
            QShortcut(QKeySequence(f"F{i + 1}"), self, activated=lambda i=i: self.nav.setCurrentRow(i))
        self.nav.currentRowChanged.connect(self._show)

        self.clock = QLabel()
        self.statusBar().addPermanentWidget(self.clock)
        self._tick()
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(30_000)

        self.update_brand()
        self.nav.setCurrentRow(0)

        # scanner de codes-barres utilisable partout dans l'application
        self.scanner = ScannerFilter(self)
        self.scanner.scanned.connect(self.handle_scan)
        QApplication.instance().installEventFilter(self.scanner)
        self.statusBar().addWidget(label("  📷 Scanner prêt — scannez un article à tout moment", "Muted"))

        # synchronisation avec TCShop Mobile (Wi-Fi local)
        self.sync = SyncServer(ctx, self)
        self.sync.synced.connect(self._on_mobile_sync)
        if ctx.db.setting("sync_enabled", "0") == "1":
            self.sync.start()

    def _on_mobile_sync(self, device: str, summary: dict):
        names = {"sale": "vente(s)", "order": "commande(s)", "order_status": "suivi(s) de commande",
                 "stock": "mouvement(s) de stock", "buy": "rachat(s)", "collection_owned": "carte(s) de collection",
                 "collection_add_card": "carte(s) ajoutée(s)", "collection_create": "collection(s) créée(s)",
                 "collection_import_set": "extension(s) importée(s)"}
        parts = [f"{n} {names.get(k, k)}" for k, n in summary.items()]
        self.flash(f"📱 {device} synchronisé : " + ", ".join(parts))
        page = self.stack.currentWidget()
        if hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception:  # noqa: BLE001
                pass

    def closeEvent(self, e):
        self.sync.stop()
        super().closeEvent(e)

    # ------------------------------------------------------------------
    def handle_scan(self, code: str):
        code = normalize_scan(code)
        page = self.stack.currentWidget()
        if hasattr(page, "on_scan") and page.on_scan(code):
            return
        # par défaut : on ouvre la fiche de l'article dans l'inventaire
        p = self.ctx.svc.find_by_code(code) or resolve_unknown(self.ctx, code, self)
        if p:
            self.goto("inventory", select_id=p["id"])

    def _show(self, row: int):
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        page = self.stack.widget(row)
        try:
            if hasattr(page, "refresh"):
                page.refresh()
        except Exception as e:  # noqa: BLE001
            warn(self, "Erreur", f"Impossible d'afficher la page :\n{e}")
        self._update_alerts()

    def goto(self, key: str, **kwargs):
        idx = self.keys.index(key)
        if self.nav.currentRow() != idx:
            self.nav.setCurrentRow(idx)
        else:
            self._show(idx)
        page = self.pages[key]
        if kwargs and hasattr(page, "on_navigate"):
            page.on_navigate(**kwargs)

    def flash(self, message: str):
        self.statusBar().showMessage("✔ " + message, 6000)
        self._update_alerts()

    def update_brand(self):
        self.shop_lbl.setText(self.ctx.db.setting("shop_name"))
        self.setWindowTitle(f"{APP_NAME} — {self.ctx.db.setting('shop_name')}")

    def _update_alerts(self):
        db = self.ctx.db
        low = db.val("SELECT COUNT(*) FROM products WHERE track_stock = 1 AND ((min_stock > 0 AND quantity <= min_stock) "
                     "OR quantity < 0)",
                     default=0)
        orders = db.val("SELECT COUNT(*) FROM orders WHERE status IN ('À préparer', 'Préparée')", default=0)
        bits = []
        if orders:
            bits.append(f"📦 {orders} commande(s) à traiter")
        if low:
            bits.append(f"⚠️ {low} alerte(s) de stock")
        self.alerts.setText("<br>".join(bits))

    def _tick(self):
        self.clock.setText(datetime.now().strftime("%A %d/%m/%Y  %H:%M  "))
