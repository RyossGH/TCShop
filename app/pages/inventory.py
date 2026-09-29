"""Inventaire : tout le magasin — cartes à l'unité, TCG scellé, accessoires, jeux, épicerie, services."""
from __future__ import annotations

import csv
import time
import unicodedata

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLineEdit, QMenu, QProgressBar, QTabBar, QVBoxLayout,
    QWidget,
)

from .. import api
from ..constants import (
    CATEGORY_FAMILIES, CONDITIONS, DETAIL_SQL, FAMILY_ICONS, GAMES, TCG_FAMILIES, family_of,
)
from ..db import now
from ..dialogs import CardSearchDialog, ProductDialog, StockAdjustDialog
from ..widgets import (
    Card, DataTable, ImageLabel, PageHeader, ask, button, fdate, info, label, money, page_layout, warn,
)

# colonnes affichées selon l'onglet (famille) choisi
COLUMNS_CARDS = [
    ("sku", "SKU", "text"), ("name", "Nom", "text"), ("game", "Jeu", "text"),
    ("set_name", "Extension", "text"), ("number", "N°", "text"), ("rarity", "Rareté", "text"),
    ("language", "Lang.", "text"), ("condition", "État", "text"), ("finish", "Finition", "text"),
    ("location", "Emplacement", "text"), ("quantity", "Stock", "qty"), ("price", "Prix vente", "money"),
    ("market_price", "Marché", "money"), ("cost", "Achat", "money"), ("online", "En ligne", "bool"),
]
COLUMNS_SEALED = [
    ("sku", "SKU", "text"), ("name", "Nom", "text"), ("game", "Jeu", "text"), ("category", "Catégorie", "text"),
    ("set_name", "Extension", "text"), ("language", "Lang.", "text"), ("location", "Emplacement", "text"),
    ("quantity", "Stock", "qty"), ("min_stock", "Mini", "int"), ("price", "Prix vente", "money"),
    ("market_price", "Marché", "money"), ("cost", "Achat", "money"), ("online", "En ligne", "bool"),
]
COLUMNS_SHOP = [
    ("sku", "SKU", "text"), ("name", "Nom", "text"), ("category", "Catégorie", "text"), ("brand", "Marque", "text"),
    ("variant", "Variante", "text"), ("supplier_name", "Fournisseur", "text"), ("location", "Emplacement", "text"),
    ("quantity", "Stock", "qty"), ("min_stock", "Mini", "int"), ("price", "Prix vente", "money"),
    ("cost", "Achat", "money"), ("favorite", "Rapide", "bool"), ("online", "En ligne", "bool"),
]
COLUMNS_ALL = [
    ("sku", "SKU", "text"), ("name", "Nom", "text"), ("category", "Catégorie", "text"), ("detail", "Détail", "text"),
    ("location", "Emplacement", "text"), ("quantity", "Stock", "qty"), ("price", "Prix vente", "money"),
    ("cost", "Achat", "money"), ("favorite", "Rapide", "bool"), ("online", "En ligne", "bool"),
]
FAMILIES = list(CATEGORY_FAMILIES)

EXPORT_FIELDS = ["id", "sku", "barcode", "name", "category", "brand", "variant", "supplier", "game", "set_name",
                 "set_code", "number", "rarity", "language", "condition", "finish", "location", "quantity", "min_stock",
                 "reorder_qty", "cost", "price", "market_price", "vat_rate", "track_stock", "favorite", "online",
                 "image_url", "external_id", "notes"]

# alias d'en-têtes acceptés à l'import
HEADER_ALIASES = {
    "nom": "name", "name": "name", "carte": "name", "produit": "name",
    "jeu": "game", "game": "game", "categorie": "category", "category": "category",
    "extension": "set_name", "set": "set_name", "set_name": "set_name", "edition": "set_name",
    "code": "set_code", "set_code": "set_code", "numero": "number", "number": "number", "n°": "number",
    "rarete": "rarity", "rarity": "rarity", "langue": "language", "language": "language",
    "etat": "condition", "condition": "condition", "finition": "finish", "finish": "finish",
    "emplacement": "location", "location": "location", "quantite": "quantity", "quantity": "quantity",
    "qte": "quantity", "qty": "quantity", "stock": "quantity", "prix": "price", "price": "price",
    "prix_vente": "price", "prix de vente": "price", "cout": "cost", "cost": "cost", "prix_achat": "cost",
    "prix d'achat": "cost", "marche": "market_price", "market_price": "market_price", "prix_marche": "market_price",
    "sku": "sku", "barcode": "barcode", "ean": "barcode", "code-barres": "barcode", "code_barres": "barcode",
    "image_url": "image_url", "image": "image_url", "external_id": "external_id", "notes": "notes",
    "min_stock": "min_stock", "stock_min": "min_stock", "online": "online", "en_ligne": "online",
    "marque": "brand", "brand": "brand", "editeur": "brand", "variante": "variant", "variant": "variant",
    "couleur": "variant", "fournisseur": "supplier", "supplier": "supplier", "tva": "vat_rate", "vat_rate": "vat_rate",
    "track_stock": "track_stock", "favorite": "favorite", "reorder_qty": "reorder_qty",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.strip().lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _num(v, default=0.0):
    try:
        return float(str(v).replace("€", "").replace(" ", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ mise à jour des prix
class PriceWorker(QThread):
    progress = Signal(int, int, str)
    finished_prices = Signal(list)

    def __init__(self, products):
        super().__init__()
        self.products = products
        self.stop = False

    def run(self):
        out = []
        for i, p in enumerate(self.products, 1):
            if self.stop:
                break
            self.progress.emit(i, len(self.products), p["name"])
            try:
                price = api.fetch_price(p["game"], p["external_id"])
                if price:
                    out.append((p["id"], price))
            except Exception:  # noqa: BLE001 - on continue sur les autres cartes
                pass
            time.sleep(0.12)
        self.finished_prices.emit(out)


class PriceUpdateDialog(QDialog):
    def __init__(self, ctx, products, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Mise à jour des prix marché")
        self.resize(520, 220)
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"{len(products)} carte(s) liée(s) à une base en ligne seront mises à jour.", wrap=True))
        self.align = QCheckBox("Aligner aussi le prix de vente sur « marché × coefficient »")
        self.only_up = QCheckBox("… uniquement si le nouveau prix est plus élevé")
        lay.addWidget(self.align)
        lay.addWidget(self.only_up)
        self.bar = QProgressBar()
        self.bar.setMaximum(max(1, len(products)))
        lay.addWidget(self.bar)
        self.status = label("", "Muted")
        lay.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = button("Fermer", self._close)
        self.start_btn = button("Démarrer", self._start, "primary")
        row.addWidget(self.cancel_btn)
        row.addWidget(self.start_btn)
        lay.addLayout(row)
        self.worker = PriceWorker(products)
        self.worker.progress.connect(self._progress)
        self.worker.finished_prices.connect(self._done)

    def _start(self):
        self.start_btn.setEnabled(False)
        self.cancel_btn.setText("Arrêter")
        self.worker.start()

    def _progress(self, i, n, name):
        self.bar.setValue(i)
        self.status.setText(f"{i}/{n} · {name}")

    def _done(self, prices):
        coef = self.ctx.db.setting_float("price_coef", 1.0)
        changed = 0
        with self.ctx.db.tx():
            for pid, price in prices:
                p = self.ctx.db.one("SELECT market_price, price FROM products WHERE id = ?", (pid,))
                if not p:
                    continue
                data = {"market_price": price}
                if self.align.isChecked():
                    new_sale = round(price * coef, 2)
                    if not self.only_up.isChecked() or new_sale > (p["price"] or 0):
                        data["price"] = new_sale
                if abs((p["market_price"] or 0) - price) > 0.001 or "price" in data:
                    self.ctx.db.update("products", pid, data)
                    self.ctx.svc.log_price(pid, price)
                    changed += 1
        self.status.setText(f"Terminé : {len(prices)} prix récupérés, {changed} article(s) modifié(s).")
        self.cancel_btn.setText("Fermer")

    def _close(self):
        if self.worker.isRunning():
            self.worker.stop = True
            return
        self.accept()

    def closeEvent(self, e):
        if self.worker.isRunning():
            self.worker.stop = True
            self.worker.wait(3000)
        super().closeEvent(e)


# ------------------------------------------------------------------ page
class InventoryPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = page_layout(self)
        header = PageHeader("Inventaire", "Tout le magasin, un seul stock boutique + en ligne")
        header.add(button("⇩ Importer CSV", self.import_csv))
        header.add(button("⇧ Exporter CSV", self.export_csv))
        header.add(button("💱 Maj prix marché", self.update_prices))
        header.add(button("🔎 Ajouter depuis la base", self.add_from_db))
        header.add(button("+ Nouvel article", self.add, "primary"))
        lay.addWidget(header)

        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.addTab("🏪  Tout")
        for fam in FAMILIES:
            self.tabs.addTab(f"{FAMILY_ICONS.get(fam, '')}  {fam}".replace("&", "&&"))  # « & » = raccourci Qt
        lay.addWidget(self.tabs)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("🔍  Rechercher : nom, marque, extension, SKU, code-barres, emplacement…")
        self.game = QComboBox()
        self.game.addItems(["Tous les jeux"] + GAMES)
        self.cat = QComboBox()
        self.cond = QComboBox()
        self.cond.addItems(["Tous états"] + CONDITIONS)
        self.stock = QComboBox()
        self.stock.addItems(["Tout le stock", "En stock", "Stock bas", "Rupture", "En ligne uniquement"])
        filters.addWidget(self.search, 1)
        for w in (self.game, self.cat, self.cond, self.stock):
            filters.addWidget(w)
            w.currentIndexChanged.connect(self.refresh)
        filters.addWidget(button("📷 Mode scan", self.scan_station,
                                 tip="Consulter, réceptionner ou inventorier en scannant les articles"))
        filters.addWidget(button("🏷 Étiquettes", self.print_labels,
                                 tip="Imprimer des étiquettes code-barres pour les articles sélectionnés"))
        lay.addLayout(filters)
        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self._timer.start())
        self.search.returnPressed.connect(self._search_enter)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.table = DataTable(COLUMNS_ALL, stretch="name")
        self.table.record_activated.connect(self.edit)
        self.table.selection_changed_record.connect(self._show_detail)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        body.addWidget(self.table, 1)

        side = Card()
        side.setFixedWidth(290)
        self.image = ImageLabel(258, 360)
        side.lay.addWidget(self.image)
        self.d_title = label("Sélectionnez un article", "H2", wrap=True)
        self.d_info = label("", "Muted", wrap=True)
        self.d_price = label("", wrap=True)
        side.lay.addWidget(self.d_title)
        side.lay.addWidget(self.d_info)
        side.lay.addWidget(self.d_price)
        side.lay.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(button("Modifier", lambda: self.edit(self.table.selected())))
        row.addWidget(button("± Stock", self.adjust))
        side.lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(button("Dupliquer", self.duplicate, tip="Créer une variante (autre état, langue, couleur…)"))
        row2.addWidget(button("Supprimer", self.delete, "danger"))
        side.lay.addLayout(row2)
        row3 = QHBoxLayout()
        row3.addWidget(button("▦ Codes-barres", self.manage_codes, tip="Associer / retirer des codes-barres"))
        row3.addWidget(button("🏷 Étiquette", self.print_labels))
        side.lay.addLayout(row3)
        body.addWidget(side)
        lay.addLayout(body, 1)

        self.footer = label("", "Muted")
        lay.addWidget(self.footer)
        self._pending_select = None
        self._family_changed(0, refresh=False)
        self.tabs.currentChanged.connect(self._family_changed)

    # ------------------------------------------------------------------
    def refresh(self, select_id=None):
        where, params = ["1=1"], []
        t = self.search.text().strip()
        if t:
            for word in t.split():
                where.append("(name LIKE ? OR set_name LIKE ? OR set_code LIKE ? OR number LIKE ? OR sku LIKE ? "
                             "OR barcode LIKE ? OR location LIKE ? OR rarity LIKE ? OR brand LIKE ? OR variant LIKE ? "
                             "OR category LIKE ? OR id IN (SELECT product_id FROM barcodes WHERE code LIKE ?))")
                params += [f"%{word}%"] * 12
        fam = self._family()
        if fam == "Autre":  # inclut aussi les catégories inconnues (anciennes données)
            known = [c for f, cs in CATEGORY_FAMILIES.items() if f != "Autre" for c in cs]
            where.append(f"category NOT IN ({','.join('?' * len(known))})")
            params += known
        elif fam:
            cats = CATEGORY_FAMILIES[fam]
            where.append(f"category IN ({','.join('?' * len(cats))})")
            params += cats
        if not self.game.isHidden() and self.game.currentIndex() > 0:
            where.append("game = ?")
            params.append(self.game.currentText())
        if self.cat.currentIndex() > 0:
            where.append("category = ?")
            params.append(self.cat.currentText())
        if not self.cond.isHidden() and self.cond.currentIndex() > 0:
            where.append("condition = ?")
            params.append(self.cond.currentText())
        where.append(["1=1", "(quantity > 0 OR track_stock = 0)",
                      "track_stock = 1 AND min_stock > 0 AND quantity <= min_stock",
                      "track_stock = 1 AND quantity <= 0",
                      "online = 1 AND (quantity > 0 OR track_stock = 0)"][self.stock.currentIndex()])
        rows = self.ctx.db.q(f"""SELECT *, {DETAIL_SQL},
            (SELECT name FROM suppliers WHERE suppliers.id = products.supplier_id) AS supplier_name
            FROM products WHERE {' AND '.join(where)} ORDER BY name, set_name""", params)
        self.table.set_rows(rows)
        sel = select_id if isinstance(select_id, int) else self._pending_select
        if sel:
            self.table.select_id(sel)
            self._pending_select = None
        stocked = [r for r in rows if r["track_stock"] != 0]
        qty = sum(max(0, r["quantity"]) for r in stocked)
        val = sum(max(0, r["quantity"]) * r["price"] for r in stocked)
        cost = sum(max(0, r["quantity"]) * r["cost"] for r in stocked)
        self.footer.setText(f"{len(rows)} références · {qty} articles · valeur de vente {money(val)} · "
                            f"valeur d'achat {money(cost)} · marge potentielle {money(val - cost)}")

    # ------------------------------------------------------------------ familles
    def _family(self) -> str:
        i = self.tabs.currentIndex()
        return FAMILIES[i - 1] if i > 0 else ""

    def _family_changed(self, _i=0, refresh=True):
        fam = self._family()
        self.table.set_columns({"": COLUMNS_ALL, "Cartes à l'unité": COLUMNS_CARDS,
                                "TCG scellé": COLUMNS_SEALED}.get(fam, COLUMNS_SHOP))
        cats = CATEGORY_FAMILIES.get(fam) or [c for cs in CATEGORY_FAMILIES.values() for c in cs]
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItems(["Toutes catégories"] + cats)
        self.cat.blockSignals(False)
        self.cat.setVisible(len(cats) > 1)
        tcg = fam in TCG_FAMILIES or not fam
        self.game.setVisible(tcg)
        self.cond.setVisible(fam == "Cartes à l'unité" or not fam)
        if refresh:
            self.refresh()

    def on_navigate(self, select_id=None, search=None, **_):
        if select_id:
            self.select(select_id)
        elif search is not None:
            self.stock.setCurrentIndex(0)
            self.search.setText(search)
            self.refresh()

    # ------------------------------------------------------------------ codes-barres
    def _codes_text(self, pid) -> str:
        codes = self.ctx.svc.product_codes(pid)
        if not codes:
            return "<br><span style='color:#f59e0b'>▦ Aucun code-barres (scannez-en un pour l'associer)</span>"
        return "<br>▦ " + ", ".join(codes)

    def on_scan(self, code: str) -> bool:
        p = self.ctx.svc.find_by_code(code)
        if not p:
            sel = self.table.selected()
            if sel and not self.ctx.svc.product_codes(sel["id"]) and ask(
                    self, "Associer le code-barres",
                    f"Code inconnu : {code}\n\nL'associer à l'article sélectionné « {sel['name']} » ?"):
                try:
                    self.ctx.svc.link_barcode(sel["id"], code)
                    p = sel
                    self.ctx.window.flash(f"Code associé à « {sel['name']} »")
                except ValueError as e:
                    warn(self, "Association impossible", str(e))
                    return True
            else:
                from ..scan import resolve_unknown
                p = resolve_unknown(self.ctx, code, self)
        if p:
            self.select(p["id"])
        return True

    def _search_enter(self):
        text = self.search.text().strip()
        if not text:
            return
        p = self.ctx.svc.find_by_code(text)
        if p:
            self.select(p["id"])
        elif " " not in text and len(text) >= 6 and not self.table.rows():
            self.search.clear()
            self.on_scan(text)

    def manage_codes(self):
        p = self.table.selected()
        if p:
            from ..dialogs import BarcodesDialog
            BarcodesDialog(self.ctx, p["id"], self).exec()
            self.refresh(p["id"])

    def print_labels(self):
        sel = self.table.selected_all()
        if not sel:
            info(self, "Étiquettes", "Sélectionnez un ou plusieurs articles dans la liste (Ctrl+clic / Maj+clic).")
            return
        from ..scan import LabelDialog
        LabelDialog(self.ctx, sel, self).exec()

    def scan_station(self):
        from ..scan import ScanStationDialog
        ScanStationDialog(self.ctx, self).exec()
        self.refresh()

    def select(self, product_id):
        self._pending_select = product_id
        self.search.clear()
        self.stock.setCurrentIndex(0)
        if self.tabs.currentIndex() != 0:
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(0)
            self.tabs.blockSignals(False)
            self._family_changed(0, refresh=False)
        self.refresh(product_id)

    def _show_detail(self, p):
        if not p:
            return
        self.image.set_url(p.get("image_url", ""))
        self.d_title.setText(p["name"])
        fam = family_of(p["category"])
        if fam in TCG_FAMILIES:
            bits = [x for x in (p["game"], p["set_name"], f"n° {p['number']}" if p["number"] else "", p["rarity"]) if x]
            line2 = " · ".join(x for x in ((p["condition"], p["language"], p["finish"]) if p["category"] == "Carte"
                                           else (p["category"], p["language"])) if x)
        else:
            bits = [x for x in (p["category"], p["brand"], p["variant"]) if x]
            line2 = f"Fournisseur : {p.get('supplier_name') or '—'}"
        vat = self.ctx.svc.vat_for(p)
        stock_txt = "Prestation sans stock" if p["track_stock"] == 0 else f"📍 {p['location'] or 'Emplacement non défini'}"
        self.d_info.setText(" · ".join(bits) + f"<br>{line2}"
                            f"<br>{stock_txt}<br>TVA {vat:g} % · SKU {p['sku']}"
                            + self._codes_text(p["id"]))
        margin = p["price"] / (1 + vat / 100) - p["cost"]  # marge HT (prix d'achat saisi HT)
        hist = self.ctx.db.q("SELECT date, market_price FROM price_history WHERE product_id = ? "
                             "ORDER BY date DESC LIMIT 4", (p["id"],)) if fam in TCG_FAMILIES else []
        hist_txt = "<br>".join(f"<span style='color:gray'>{fdate(h['date'], False)} : {money(h['market_price'])}</span>"
                               for h in hist)
        stock = "∞" if p["track_stock"] == 0 else p["quantity"]
        market = f"Marché {money(p['market_price'])} · " if fam in TCG_FAMILIES else ""
        self.d_price.setText(
            f"<b style='font-size:15pt'>{money(p['price'])}</b> &nbsp; stock <b>{stock}</b><br>"
            f"{market}achat {money(p['cost'])} HT<br>"
            f"Marge unitaire <b>{money(margin)}</b> HT" + (f"<br><br>Historique prix :<br>{hist_txt}" if hist else ""))

    def _menu(self, pos):
        p = self.table.selected()
        if not p:
            return
        m = QMenu(self)
        m.addAction("Modifier…", lambda: self.edit(p))
        m.addAction("Ajuster le stock…", self.adjust)
        m.addAction("Dupliquer (variante)", self.duplicate)
        m.addAction("Vendre en caisse", lambda: self.ctx.window.goto("pos", add_product=p["id"]))
        m.addAction("Voir les mouvements", lambda: self.ctx.window.goto("movements", search=p["name"]))
        m.addSeparator()
        m.addAction("Codes-barres associés…", self.manage_codes)
        m.addAction("Imprimer des étiquettes…", self.print_labels)
        m.addSeparator()
        m.addAction("Supprimer", self.delete)
        m.exec(self.table.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ actions
    def add(self):
        fam = self._family()
        preset = {"category": CATEGORY_FAMILIES[fam][0]} if fam else None
        dlg = ProductDialog(self.ctx, parent=self, preset=preset)
        if dlg.exec():
            self.refresh(dlg.saved_id)

    def add_from_db(self):
        dlg = CardSearchDialog(self)
        if dlg.exec() and dlg.result_card:
            c = dlg.result_card
            coef = self.ctx.db.setting_float("price_coef", 1.0)
            preset = {k: c.get(k, "") for k in ("name", "game", "set_name", "set_code", "number", "rarity",
                                                "image_url", "external_id")}
            preset.update(category="Carte", market_price=c.get("market_price", 0),
                          price=round((c.get("market_price") or 0) * coef, 2), quantity=1)
            existing = self.ctx.db.one(
                "SELECT * FROM products WHERE external_id = ? AND external_id != '' AND condition = 'NM' LIMIT 1",
                (c.get("external_id", ""),))
            if existing and ask(self, "Déjà en stock",
                                f"« {existing['name']} » ({existing['set_name']}) existe déjà "
                                f"(stock {existing['quantity']}).\nAjouter 1 exemplaire à cet article ?"):
                self.ctx.svc.adjust_stock(existing["id"], 1, "Réception fournisseur")
                self.refresh(existing["id"])
                return
            d = ProductDialog(self.ctx, parent=self, preset=preset)
            if d.exec():
                self.refresh(d.saved_id)

    def edit(self, p):
        if not p:
            return
        dlg = ProductDialog(self.ctx, self.ctx.db.one("SELECT * FROM products WHERE id = ?", (p["id"],)), self)
        if dlg.exec():
            self.refresh(p["id"])

    def duplicate(self):
        p = self.table.selected()
        if not p:
            return
        preset = {k: v for k, v in p.items() if k not in ("id", "sku", "barcode", "created_at", "updated_at")}
        preset["quantity"] = 1
        dlg = ProductDialog(self.ctx, parent=self, preset=preset)
        if dlg.exec():
            self.refresh(dlg.saved_id)

    def adjust(self):
        p = self.table.selected()
        if not p:
            return
        dlg = StockAdjustDialog(p, self)
        if dlg.exec() and dlg.delta():
            self.ctx.svc.adjust_stock(p["id"], dlg.delta(), dlg.reason.currentText(), dlg.note.text())
            self.refresh(p["id"])

    def delete(self):
        sel = self.table.selected_all()
        if not sel:
            return
        if ask(self, "Supprimer", f"Supprimer définitivement {len(sel)} article(s) ?\n"
                                  "L'historique des ventes est conservé."):
            with self.ctx.db.tx():
                for p in sel:
                    self.ctx.svc.delete_product(p["id"])
            self.refresh()

    def update_prices(self):
        sel = self.table.selected_all()
        base = sel if len(sel) > 1 else self.table.rows()
        products = [p for p in base if p["external_id"] and p["game"] in api.API_GAMES]
        if not products:
            info(self, "Aucune carte liée",
                 "Aucun article affiché n'est lié à une base en ligne.\n"
                 "Utilisez « Ajouter depuis la base » ou « Remplir depuis la base de cartes » dans la fiche.")
            return
        PriceUpdateDialog(self.ctx, products, self).exec()
        self.refresh()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter l'inventaire", "inventaire.csv", "CSV (*.csv)")
        if not path:
            return
        rows = self.table.rows()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=EXPORT_FIELDS, delimiter=";", extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(dict(r, supplier=r.get("supplier_name") or ""))
        info(self, "Export terminé", f"{len(rows)} article(s) exporté(s) vers :\n{path}")

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importer un inventaire", "", "CSV (*.csv *.txt)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
                except csv.Error:
                    class dialect(csv.excel):  # noqa: N801
                        delimiter = ";"
                reader = csv.DictReader(f, dialect=dialect)
                mapping = {h: HEADER_ALIASES.get(_norm(h)) for h in (reader.fieldnames or [])}
                if "name" not in mapping.values():
                    warn(self, "Import impossible", "Colonne « nom » / « name » introuvable dans le fichier.")
                    return
                created = updated = 0
                with self.ctx.db.tx():
                    for raw in reader:
                        d = {mapping[k]: (v or "").strip() for k, v in raw.items() if k and mapping.get(k)}
                        if not d.get("name"):
                            continue
                        for k in ("price", "cost", "market_price"):
                            if k in d:
                                d[k] = _num(d[k])
                        for k in ("quantity", "min_stock", "reorder_qty", "track_stock", "favorite"):
                            if k in d:
                                d[k] = int(_num(d[k]))
                        if "vat_rate" in d:
                            d["vat_rate"] = _num(d["vat_rate"]) if str(d["vat_rate"]).strip() else None
                        if "supplier" in d:
                            sname = d.pop("supplier")
                            if sname:
                                s = self.ctx.db.one("SELECT id FROM suppliers WHERE name = ? COLLATE NOCASE", (sname,))
                                d["supplier_id"] = s["id"] if s else self.ctx.db.insert(
                                    "suppliers", dict(name=sname, created_at=now()))
                        if "online" in d:
                            d["online"] = 0 if _norm(str(d["online"])) in ("0", "non", "no", "false", "") else 1
                        existing = None
                        if d.get("sku"):
                            existing = self.ctx.db.one("SELECT id FROM products WHERE sku = ?", (d["sku"],))
                        if existing:
                            self.ctx.svc.save_product(d, existing["id"])
                            updated += 1
                        else:
                            self.ctx.svc.save_product(d)
                            created += 1
        except Exception as e:  # noqa: BLE001
            warn(self, "Erreur d'import", str(e))
            return
        self.refresh()
        info(self, "Import terminé", f"{created} article(s) créé(s), {updated} mis à jour (même SKU).")
