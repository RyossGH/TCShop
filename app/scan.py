"""Scanner de codes-barres : détection globale, codes inconnus, poste de scan et impression d'étiquettes."""
from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QEvent, QMarginsF, QObject, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPageLayout, QPageSize, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget,
)

from .barcode import code_font, draw_code128, normalize_scan
from .dialogs import CardSearchDialog, ProductDialog, ProductPickerDialog, combo
from .widgets import Card, DataTable, ImageLabel, ask, button, info, label, money, warn


# ====================================================================== détection globale
class ScannerFilter(QObject):
    """Un scanner USB se comporte comme un clavier qui tape très vite puis appuie sur Entrée.

    Quand le curseur n'est pas dans un champ de saisie, on intercepte ces frappes rapides et on émet
    `scanned(code)` : l'utilisateur peut scanner à tout moment, sans cliquer nulle part."""

    scanned = Signal(str)
    MAX_GAP = 0.06   # secondes max entre deux caractères d'un scan
    MIN_LEN = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buf = ""
        self.last = 0.0
        self.fast = True
        self.enabled = True

    @staticmethod
    def _is_text_input(w) -> bool:
        return isinstance(w, (QLineEdit, QAbstractSpinBox, QPlainTextEdit, QTextEdit)) or (
            isinstance(w, QComboBox) and w.isEditable())

    def eventFilter(self, obj, ev):
        if not self.enabled or ev.type() != QEvent.Type.KeyPress:
            return False
        if QApplication.activeModalWidget() is not None:
            return False  # les boîtes de dialogue gèrent leur propre champ de scan
        focus = QApplication.focusWidget()
        target = focus or QApplication.activeWindow()
        if obj is not target or self._is_text_input(focus):
            return False
        now = time.monotonic()
        key = ev.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            code, fast = self.buf, self.fast and (now - self.last) < 0.3
            self.buf = ""
            if len(code) >= self.MIN_LEN and fast:
                self.scanned.emit(code)
                return True
            return False
        text = ev.text()
        if text and text.isprintable() and not (ev.modifiers() & (Qt.KeyboardModifier.ControlModifier |
                                                                   Qt.KeyboardModifier.AltModifier)):
            if now - self.last > self.MAX_GAP:
                # pause entre deux frappes : ce n'était pas un scan, on repart de zéro
                self.buf, self.fast = "", True
            self.buf += text
            self.last = now
            return True
        return False


# ====================================================================== code inconnu
class UnknownCodeDialog(QDialog):
    LINK, CREATE, CREATE_DB = 1, 2, 3

    def __init__(self, code: str, parent=None):
        super().__init__(parent)
        self.choice = 0
        self.setWindowTitle("Code-barres inconnu")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Ce code-barres n'est associé à aucun article :", "Muted"))
        big = label(code, "H1")
        big.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(big)
        for text, choice, kind in (
            ("🔗  Associer à un article existant", self.LINK, "primary"),
            ("🔎  Créer l'article depuis la base de cartes", self.CREATE_DB, None),
            ("+  Créer un nouvel article (saisie manuelle)", self.CREATE, None),
        ):
            b = button(text, lambda _=False, c=choice: self._choose(c), kind)
            b.setMinimumHeight(40)
            lay.addWidget(b)
        lay.addWidget(button("Annuler", self.reject))

    def _choose(self, c):
        self.choice = c
        self.accept()


def resolve_unknown(ctx, code: str, parent=None) -> dict | None:
    """Propose d'associer un code inconnu à un article (existant ou nouveau). Renvoie l'article ou None."""
    code = normalize_scan(code)
    QApplication.beep()
    dlg = UnknownCodeDialog(code, parent)
    if not dlg.exec():
        return None
    pid = None
    if dlg.choice == UnknownCodeDialog.LINK:
        picker = ProductPickerDialog(ctx, parent, "Associer le code-barres à un article",
                                     hint=f"Choisissez l'article qui correspond au code <b>{code}</b> "
                                          "(double-clic ou Entrée).")
        if picker.exec() and picker.result_product:
            try:
                ctx.svc.link_barcode(picker.result_product["id"], code)
            except ValueError as e:
                warn(parent, "Association impossible", str(e))
                return None
            pid = picker.result_product["id"]
            ctx.window.flash(f"Code {code} associé à « {picker.result_product['name']} »")
    elif dlg.choice == UnknownCodeDialog.CREATE_DB:
        search = CardSearchDialog(parent)
        if search.exec() and search.result_card:
            c = search.result_card
            coef = ctx.db.setting_float("price_coef", 1.0)
            preset = {k: c.get(k, "") for k in ("name", "game", "set_name", "set_code", "number", "rarity",
                                                "image_url", "external_id")}
            preset.update(category="Carte", market_price=c.get("market_price", 0), barcode=code, quantity=0,
                          price=round((c.get("market_price") or 0) * coef, 2))
            pd = ProductDialog(ctx, parent=parent, preset=preset)
            if pd.exec():
                pid = pd.saved_id
    elif dlg.choice == UnknownCodeDialog.CREATE:
        pd = ProductDialog(ctx, parent=parent, preset=dict(barcode=code, quantity=0, category="Booster"))
        if pd.exec():
            pid = pd.saved_id
    return ctx.db.one("SELECT * FROM products WHERE id = ?", (pid,)) if pid else None


# ====================================================================== poste de scan
MODES = ["🔍 Consulter", "📥 Réception : ajouter au stock", "📤 Sortie : retirer du stock", "🧮 Comptage d'inventaire"]


class ScanStationDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.counts: dict[int, int] = {}
        self.log: list[dict] = []
        self.setWindowTitle("Mode scan")
        self.resize(1150, 680)
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setObjectName("Search")
        self.input.setPlaceholderText("📷  Scannez un article (le curseur doit rester ici)…")
        self.input.returnPressed.connect(self._scan)
        self.mode = combo(MODES)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.qty = QSpinBox()
        self.qty.setRange(1, 9999)
        self.qty.setPrefix("× ")
        self.qty.setToolTip("Quantité appliquée à chaque scan")
        top.addWidget(self.input, 1)
        top.addWidget(self.mode)
        top.addWidget(self.qty)
        lay.addLayout(top)
        self.help = label("", "Muted", wrap=True)
        lay.addWidget(self.help)

        body = QHBoxLayout()
        self.table = DataTable([
            ("time", "Heure", "text"), ("code", "Code scanné", "text"), ("name", "Article", "text"),
            ("action", "Action", "text"), ("stock", "Stock", "qty"), ("counted", "Compté", "int"),
        ], stretch="name")
        self.table.setSortingEnabled(False)
        body.addWidget(self.table, 1)
        side = Card()
        side.setFixedWidth(290)
        self.image = ImageLabel(258, 330)
        side.lay.addWidget(self.image)
        self.p_title = label("En attente d'un scan…", "H2", wrap=True)
        self.p_info = label("", "Muted", wrap=True)
        self.p_price = label("", wrap=True)
        side.lay.addWidget(self.p_title)
        side.lay.addWidget(self.p_info)
        side.lay.addWidget(self.p_price)
        side.lay.addStretch(1)
        body.addWidget(side)
        lay.addLayout(body, 1)

        bottom = QHBoxLayout()
        self.summary = label("", "Muted")
        bottom.addWidget(self.summary, 1)
        self.apply_btn = button("✔ Appliquer l'inventaire", self._apply_count, "success")
        bottom.addWidget(self.apply_btn)
        bottom.addWidget(button("Fermer", self.accept))
        lay.addLayout(bottom)
        self._mode_changed()
        self.input.setFocus()

    def _mode_changed(self, *_):
        i = self.mode.currentIndex()
        self.help.setText([
            "Scannez pour afficher la fiche, le stock et le prix d'un article.",
            "Chaque scan ajoute la quantité choisie au stock (motif « Réception fournisseur »).",
            "Chaque scan retire la quantité choisie du stock (motif « Sortie scan »).",
            "Scannez tous les exemplaires d'un rayon puis cliquez « Appliquer l'inventaire » : le stock des articles "
            "scannés sera remplacé par la quantité comptée.",
        ][i])
        self.apply_btn.setVisible(i == 3)
        self.input.setFocus()

    def _scan(self):
        raw = self.input.text()
        self.input.clear()
        code = normalize_scan(raw)
        if not code:
            return
        p = self.ctx.svc.find_by_code(code)
        if not p:
            p = resolve_unknown(self.ctx, code, self)
        if not p:
            self._add_log(code, None, "Code inconnu — ignoré")
            self.input.setFocus()
            return
        mode, q = self.mode.currentIndex(), self.qty.value()
        action = "Consultation"
        if mode == 1:
            self.ctx.svc.adjust_stock(p["id"], q, "Réception fournisseur", "Scan")
            action = f"+{q} en stock"
        elif mode == 2:
            self.ctx.svc.adjust_stock(p["id"], -q, "Sortie scan", "Scan")
            action = f"−{q} du stock"
        elif mode == 3:
            self.counts[p["id"]] = self.counts.get(p["id"], 0) + q
            action = f"Compté +{q}"
        p = self.ctx.db.one("SELECT * FROM products WHERE id = ?", (p["id"],))
        self._add_log(code, p, action)
        self._show(p)
        self.input.setFocus()

    def _add_log(self, code, p, action):
        self.log.insert(0, dict(time=datetime.now().strftime("%H:%M:%S"), code=code,
                                name=(p["name"] + (f" — {p['set_name']}" if p["set_name"] else "")) if p else "—",
                                action=action, stock=p["quantity"] if p else None,
                                counted=self.counts.get(p["id"]) if p else None, id=p["id"] if p else None))
        self.table.set_rows(self.log)
        units = sum(self.counts.values())
        self.summary.setText(f"{len(self.log)} scan(s)" + (f" · comptage : {len(self.counts)} article(s), {units} unité(s)"
                                                          if self.counts else ""))

    def _show(self, p):
        self.image.set_url(p["image_url"])
        self.p_title.setText(p["name"])
        self.p_info.setText(" · ".join(x for x in (p["game"], p["set_name"], p["number"], p["condition"], p["language"])
                                       if x) + f"<br>📍 {p['location'] or 'Emplacement non défini'}")
        counted = self.counts.get(p["id"])
        self.p_price.setText(f"<b style='font-size:16pt'>{money(p['price'])}</b><br>Stock : <b>{p['quantity']}</b>"
                             + (f"<br>Compté : <b>{counted}</b>" if counted is not None else ""))

    def _apply_count(self):
        if not self.counts:
            return
        diffs = []
        for pid, n in self.counts.items():
            cur = self.ctx.db.val("SELECT quantity FROM products WHERE id = ?", (pid,), 0)
            if cur != n:
                diffs.append((pid, n - cur))
        if not diffs:
            info(self, "Inventaire", "Aucun écart : le stock correspond au comptage 👍")
            return
        if not ask(self, "Appliquer l'inventaire",
                   f"{len(diffs)} article(s) ont un écart avec le stock enregistré.\nMettre le stock à jour ?"):
            return
        with self.ctx.db.tx():
            for pid, d in diffs:
                self.ctx.svc.adjust_stock(pid, d, "Inventaire", "Comptage scan")
        self.counts.clear()
        info(self, "Inventaire appliqué", f"Stock corrigé pour {len(diffs)} article(s).")
        self.input.setFocus()


# ====================================================================== étiquettes
LABEL_FORMATS = {
    "Étiquette 50 × 25 mm (imprimante d'étiquettes)": dict(w=50, h=25),
    "Étiquette 40 × 30 mm (imprimante d'étiquettes)": dict(w=40, h=30),
    "Étiquette 62 × 29 mm (Brother DK-11209)": dict(w=62, h=29),
    "Planche A4 — 3 × 8 étiquettes (70 × 37 mm)": dict(w=70, h=37, cols=3, rows=8),
    "Planche A4 — 4 × 10 étiquettes (48,5 × 25,4 mm)": dict(w=48.5, h=25.4, cols=4, rows=10),
    "Planche A4 — 5 × 13 petites étiquettes prix (38 × 21 mm)": dict(w=38.1, h=21.2, cols=5, rows=13),
}
MODE_PRICE, MODE_BARCODE = 0, 1
LABEL_MODES = ["🏷  Nom + prix (étiquette prix)", "▦  Code-barres + nom + prix"]


def label_code(p: dict) -> str:
    """Code imprimé : le code-barres principal s'il existe, sinon le SKU."""
    return (p.get("barcode") or p.get("sku") or "").strip()


def label_name(p: dict) -> str:
    """Nom imprimé : le nom court s'il est renseigné, sinon le nom (+ variante)."""
    if p.get("short_name"):
        return p["short_name"]
    return p.get("name", "") + (f" {p['variant']}" if p.get("variant") else "")


def _details(p: dict) -> str:
    if p.get("category") == "Carte":
        bits = [p.get("set_code") or p.get("set_name"), p.get("number"), p.get("condition"), p.get("language"),
                p.get("finish") if p.get("finish") not in ("", "Normale") else ""]
    elif p.get("brand"):  # accessoire, jeu, boisson…
        bits = [p.get("brand")]
    else:
        bits = [p.get("set_name"), p.get("language")]
    return " · ".join(b for b in bits if b)


def _fit_font(text: str, rect: QRectF, start_px: float, min_px: float, bold=True, wrap=False) -> QFont:
    """Plus grande police (≤ start_px) pour que le texte tienne dans rect."""
    f = QFont("Segoe UI")
    f.setBold(bold)
    size = start_px
    flags = int(Qt.AlignmentFlag.AlignCenter) | (int(Qt.TextFlag.TextWordWrap) if wrap else 0)
    while size > min_px:
        f.setPixelSize(max(5, int(size)))
        br = QFontMetrics(f).boundingRect(QRectF(rect).toRect(), flags, text)
        if br.width() <= rect.width() and br.height() <= rect.height():
            break
        size *= 0.92
    f.setPixelSize(max(5, int(size)))
    return f


def draw_label(painter: QPainter, rect: QRectF, p: dict, pxmm: float, show_price=True, show_details=True,
               crisp=True, mode=MODE_BARCODE):
    painter.save()
    painter.fillRect(rect, QColor("white"))
    pad = 1.5 * pxmm
    r = rect.adjusted(pad, pad, -pad, -pad)
    h = r.height()
    painter.setPen(QColor("black"))
    name = label_name(p)
    price_txt = money(p["price"]).replace(" ", " ") if show_price and p.get("price") else ""

    if mode == MODE_PRICE:
        # étiquette prix : nom en haut (2 lignes max), grand prix en bas
        y = r.y()
        det = _details(p) if show_details else ""
        if det:
            fdet = QFont("Segoe UI")
            fdet.setPixelSize(max(5, int(h * 0.13)))
            painter.setFont(fdet)
            painter.setPen(QColor("#444"))
            painter.drawText(QRectF(r.x(), y, r.width(), h * 0.16), Qt.AlignmentFlag.AlignCenter,
                             QFontMetrics(fdet).elidedText(det, Qt.TextElideMode.ElideRight, int(r.width())))
            painter.setPen(QColor("black"))
            y += h * 0.16
        name_h = (h * 0.44 if price_txt else r.bottom() - y) - (y - r.y()) * 0.5
        name_rect = QRectF(r.x(), y, r.width(), name_h)
        painter.setFont(_fit_font(name, name_rect, h * 0.24, h * 0.11, wrap=True))
        painter.drawText(name_rect, int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap), name)
        if price_txt:
            price_rect = QRectF(r.x(), y + name_h, r.width(), r.bottom() - (y + name_h))
            painter.setFont(_fit_font(price_txt, price_rect, h * 0.42, h * 0.15))
            painter.drawText(price_rect, Qt.AlignmentFlag.AlignCenter, price_txt)
        painter.restore()
        return

    # étiquette code-barres : nom + prix en haut, détails, code-barres
    fname = QFont("Segoe UI")
    fname.setPixelSize(max(6, int(h * 0.17)))
    fname.setBold(True)
    price_w = 0.0
    if price_txt:
        fprice = QFont("Segoe UI")
        fprice.setPixelSize(max(6, int(h * 0.21)))
        fprice.setBold(True)
        price_w = QFontMetrics(fprice).horizontalAdvance(price_txt) + pad
        painter.setFont(fprice)
        painter.drawText(QRectF(r.x(), r.y(), r.width(), h * 0.24),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, price_txt)
    painter.setFont(fname)
    painter.drawText(QRectF(r.x(), r.y(), r.width() - price_w, h * 0.22),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                     QFontMetrics(fname).elidedText(name, Qt.TextElideMode.ElideRight, int(r.width() - price_w)))
    y = r.y() + h * 0.23
    if show_details:
        fdet = QFont("Segoe UI")
        fdet.setPixelSize(max(5, int(h * 0.12)))
        painter.setFont(fdet)
        det = QFontMetrics(fdet).elidedText(_details(p), Qt.TextElideMode.ElideRight, int(r.width()))
        painter.drawText(QRectF(r.x(), y, r.width(), h * 0.15), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, det)
        y += h * 0.16
    code = label_code(p)
    text_h = h * 0.14
    bar_h = r.bottom() - text_h - y
    if code:
        try:
            draw_code128(painter, QRectF(r.x(), y, r.width(), bar_h), code, crisp)
        except ValueError:
            pass
        painter.setFont(code_font(text_h * 0.9))
        painter.drawText(QRectF(r.x(), r.bottom() - text_h, r.width(), text_h), Qt.AlignmentFlag.AlignCenter, code)
    painter.restore()


class LabelDialog(QDialog):
    def __init__(self, ctx, products: list[dict], parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.products = [ctx.db.one("SELECT * FROM products WHERE id = ?", (p["id"],)) for p in products]
        self.setWindowTitle("Imprimer des étiquettes")
        self.resize(1020, 620)
        lay = QHBoxLayout(self)

        left = QVBoxLayout()
        self.table = QTableWidget(len(self.products), 4)
        self.table.setHorizontalHeaderLabels(["Article", "Nom sur l'étiquette ✎", "Prix", "Nb"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                   QAbstractItemView.EditTrigger.EditKeyPressed |
                                   QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 80)
        self.spins: list[QSpinBox] = []
        for r, p in enumerate(self.products):
            art = QTableWidgetItem(p["name"] + (f" — {p['variant'] or p['set_name']}" if (p["variant"] or p["set_name"])
                                                else ""))
            art.setFlags(art.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, art)
            nm = QTableWidgetItem(label_name(p))
            nm.setToolTip("Double-cliquez pour raccourcir le nom (mémorisé pour les prochaines fois)")
            self.table.setItem(r, 1, nm)
            pr = QTableWidgetItem(money(p["price"]))
            pr.setFlags(pr.flags() & ~Qt.ItemFlag.ItemIsEditable)
            pr.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 2, pr)
            s = QSpinBox()
            s.setRange(0, 999)
            s.setValue(1)
            s.valueChanged.connect(self._update_total)
            self.table.setCellWidget(r, 3, s)
            self.spins.append(s)
        self.table.itemChanged.connect(self._name_edited)
        self.table.currentCellChanged.connect(lambda *_: self._preview())
        left.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(button("1 par article", lambda: self._set_all(False)))
        row.addWidget(button("Autant que le stock", lambda: self._set_all(True)))
        row.addStretch(1)
        self.total = label("", "Muted")
        row.addWidget(self.total)
        left.addLayout(row)
        left.addWidget(label("✎ Double-cliquez sur un nom pour le raccourcir : il est mémorisé dans la fiche (« Nom "
                             "court »). Les articles sans code fabricant utilisent leur SKU comme code-barres.",
                             "Muted", wrap=True))
        lay.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(label("Type d'étiquette", "Muted"))
        self.mode = combo(LABEL_MODES)
        self.mode.setCurrentIndex(int(ctx.db.setting("label_mode", str(MODE_PRICE)) or 0))
        self.mode.currentIndexChanged.connect(self._preview)
        right.addWidget(self.mode)
        right.addWidget(label("Format", "Muted"))
        self.fmt = combo(LABEL_FORMATS)
        self.fmt.setCurrentIndex(max(0, self.fmt.findText(ctx.db.setting("label_format", ""))))
        self.fmt.currentIndexChanged.connect(self._preview)
        right.addWidget(self.fmt)
        self.show_price = QCheckBox("Afficher le prix")
        self.show_price.setChecked(True)
        self.show_details = QCheckBox("Afficher marque / extension / état")
        self.show_details.setChecked(ctx.db.setting("label_details", "1") == "1")
        for c in (self.show_price, self.show_details):
            c.toggled.connect(self._preview)
            right.addWidget(c)
        right.addWidget(label("Aperçu", "Muted"))
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(200)
        right.addWidget(self.preview)
        right.addStretch(1)
        right.addWidget(button("Enregistrer en PDF", self._pdf))
        right.addWidget(button("🖨  Imprimer", self._print, "primary"))
        right.addWidget(button("Fermer", self.reject))
        lay.addLayout(right, 2)
        if self.products:
            self.table.selectRow(0)
        self._update_total()
        self._preview()

    def _name_edited(self, item: QTableWidgetItem):
        if item.column() != 1:
            return
        p = self.products[item.row()]
        text = item.text().strip()
        default = p["name"] + (f" {p['variant']}" if p.get("variant") else "")
        short = "" if text == default else text[:40]
        if short != (p.get("short_name") or ""):
            self.ctx.db.exec("UPDATE products SET short_name = ? WHERE id = ?", (short, p["id"]))
            p["short_name"] = short
        self._preview()

    def _set_all(self, stock: bool):
        for p, s in zip(self.products, self.spins):
            s.setValue(max(0, int(p["quantity"])) if stock else 1)

    def _update_total(self):
        self.total.setText(f"{sum(s.value() for s in self.spins)} étiquette(s)")

    def _opts(self) -> dict:
        return dict(show_price=self.show_price.isChecked(), show_details=self.show_details.isChecked(),
                    mode=self.mode.currentIndex())

    def _preview(self, *_):
        if not self.products:
            return
        row = max(0, self.table.currentRow())
        f = LABEL_FORMATS[self.fmt.currentText()]
        scale = min(330 / f["w"], 190 / f["h"])
        pm = QPixmap(int(f["w"] * scale), int(f["h"] * scale))
        pm.fill(QColor("white"))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_label(painter, QRectF(0, 0, pm.width(), pm.height()), self.products[row], scale, crisp=False,
                   **self._opts())
        painter.setPen(QColor("#999"))
        painter.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
        painter.end()
        self.preview.setPixmap(pm)

    def _jobs(self) -> list[dict]:
        out = []
        for p, s in zip(self.products, self.spins):
            out += [p] * s.value()
        return out

    def _setup_printer(self, printer: QPrinter):
        f = LABEL_FORMATS[self.fmt.currentText()]
        if "cols" in f:
            size = QPageSize(QPageSize.PageSizeId.A4)
        else:
            size = QPageSize(QSizeF(f["w"], f["h"]), QPageSize.Unit.Millimeter, "Étiquette",
                             QPageSize.SizeMatchPolicy.ExactMatch)
        printer.setPageLayout(QPageLayout(size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0),
                                          QPageLayout.Unit.Millimeter))
        printer.setFullPage(True)

    def _render(self, printer: QPrinter):
        jobs = self._jobs()
        if not jobs:
            warn(self, "Aucune étiquette", "Indiquez au moins une étiquette à imprimer.")
            return False
        db = self.ctx.db
        db.set_setting("label_format", self.fmt.currentText())
        db.set_setting("label_mode", self.mode.currentIndex())
        db.set_setting("label_details", "1" if self.show_details.isChecked() else "0")
        f = LABEL_FORMATS[self.fmt.currentText()]
        painter = QPainter(printer)
        pxmm = printer.resolution() / 25.4
        opts = self._opts()
        if "cols" in f:
            cols, rows = f["cols"], f["rows"]
            x0 = (210 - cols * f["w"]) / 2
            y0 = (297 - rows * f["h"]) / 2
            per_page = cols * rows
            for i, p in enumerate(jobs):
                if i and i % per_page == 0:
                    printer.newPage()
                k = i % per_page
                x = (x0 + (k % cols) * f["w"]) * pxmm
                y = (y0 + (k // cols) * f["h"]) * pxmm
                draw_label(painter, QRectF(x, y, f["w"] * pxmm, f["h"] * pxmm), p, pxmm, **opts)
        else:
            for i, p in enumerate(jobs):
                if i:
                    printer.newPage()
                draw_label(painter, QRectF(0, 0, f["w"] * pxmm, f["h"] * pxmm), p, pxmm, **opts)
        painter.end()
        return True

    def _print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._setup_printer(printer)
        dlg = QPrintDialog(printer, self)
        if dlg.exec():
            self._setup_printer(printer)  # le choix d'imprimante peut réinitialiser le format
            if self._render(printer):
                self.ctx.window.flash(f"{len(self._jobs())} étiquette(s) envoyée(s) à l'imprimante")

    def _pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer les étiquettes", "etiquettes.pdf", "PDF (*.pdf)")
        if not path:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        self._setup_printer(printer)
        if self._render(printer):
            info(self, "PDF créé", f"Étiquettes enregistrées :\n{path}")
