"""Boîtes de dialogue partagées."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QSpinBox,
    QTextBrowser, QVBoxLayout, QWidget,
)

from . import api
from .barcode import normalize_scan
from .constants import (
    CARD_CATEGORIES, CATEGORY_FAMILIES, CONDITIONS, CONDITION_LABELS, FAMILY_ICONS, FINISHES, GAMES, LANGUAGES,
    DETAIL_SQL, NO_STOCK_CATEGORIES, STOCK_REASONS, TCG_FAMILIES, VAT_RATES, family_of,
)
from .db import DATA_DIR, now
from .widgets import DataTable, ImageLabel, button, label, money, run_async, warn

IMAGES_DIR = DATA_DIR / "images"  # photos de produits choisies sur l'ordinateur


def spin_money(maximum: float = 1_000_000) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, maximum)
    s.setDecimals(2)
    s.setSuffix(" €")
    s.setSingleStep(0.5)
    s.setAlignment(Qt.AlignmentFlag.AlignRight)
    return s


def combo(items, editable: bool = False, current: str | None = None) -> QComboBox:
    c = QComboBox()
    c.addItems(list(items))
    c.setEditable(editable)
    if current:
        i = c.findText(current)
        if i >= 0:
            c.setCurrentIndex(i)
        elif editable:
            c.setEditText(current)
    return c


# ------------------------------------------------------------------ recherche base de cartes
class CardSearchDialog(QDialog):
    """Recherche une carte dans les bases publiques. Résultat : self.result_card (dict)."""

    def __init__(self, parent=None, game: str = "Pokémon", query: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Rechercher une carte dans la base en ligne")
        self.resize(1100, 640)
        self.result_card: dict | None = None
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.game = combo(api.API_GAMES, current=game if game in api.API_GAMES else None)
        self.query = QLineEdit(query)
        self.query.setObjectName("Search")
        self.query.setPlaceholderText("Nom de la carte (ex. Dracaufeu → « Charizard », Black Lotus, Blue-Eyes…)")
        self.query.returnPressed.connect(self.search)
        top.addWidget(self.game)
        top.addWidget(self.query, 1)
        top.addWidget(button("Rechercher", self.search, "primary"))
        lay.addLayout(top)
        hint = label("Astuce : Pokémon accepte les noms français (Dracaufeu) ou anglais ; Magic et Yu-Gi-Oh! en anglais. Magic accepte la syntaxe Scryfall (ex. « set:mh3 t:dragon »).",
                     "Muted")
        lay.addWidget(hint)

        body = QHBoxLayout()
        self.table = DataTable([
            ("name", "Nom", "text"), ("set_name", "Extension", "text"), ("set_code", "Code", "text"),
            ("number", "N°", "text"), ("rarity", "Rareté", "text"), ("language", "Langue", "text"),
            ("market_price", "Prix marché", "money"),
        ], stretch="name")
        self.table.selection_changed_record.connect(self._preview)
        self.table.record_activated.connect(lambda _r: self.accept_selection())
        body.addWidget(self.table, 1)
        right = QVBoxLayout()
        self.image = ImageLabel(250, 350)
        right.addWidget(self.image)
        self.details = label("", "Muted", wrap=True)
        self.details.setFixedWidth(250)
        right.addWidget(self.details)
        right.addStretch(1)
        body.addLayout(right)
        lay.addLayout(body, 1)

        bottom = QHBoxLayout()
        self.status = label("", "Muted")
        bottom.addWidget(self.status, 1)
        bottom.addWidget(button("Annuler", self.reject))
        self.ok = button("Utiliser cette carte", self.accept_selection, "primary")
        bottom.addWidget(self.ok)
        lay.addLayout(bottom)
        if query:
            QTimer.singleShot(50, self.search)

    def search(self):
        q = self.query.text().strip()
        if not q:
            return
        game = self.game.currentText()
        self.status.setText("Recherche en cours…")
        self.table.set_rows([])

        def done(rows):
            self.table.set_rows(rows)
            self.status.setText(f"{len(rows)} résultat(s)" if rows else "Aucun résultat.")
            if rows:
                self.table.selectRow(0)

        run_async(lambda: api.search_cards(game, q), done, lambda e: self.status.setText(f"Erreur : {e}"))

    def _preview(self, rec):
        if not rec:
            return
        self.image.set_url(rec.get("image_url", ""))
        self.details.setText(
            f"<b>{rec['name']}</b><br>{rec['set_name']} · {rec['number']}<br>{rec['rarity']}<br>"
            f"Prix marché : <b>{money(rec['market_price'])}</b>"
        )

    def accept_selection(self):
        rec = self.table.selected()
        if not rec:
            return
        self.result_card = rec
        self.accept()


# ------------------------------------------------------------------ fiche produit
def category_combo(current: str | None = None, with_all: str | None = None) -> QComboBox:
    """Liste des catégories regroupées par famille (en-têtes non sélectionnables)."""
    c = QComboBox()
    model = QStandardItemModel(c)
    if with_all:
        it = QStandardItem(with_all)
        it.setData("", Qt.ItemDataRole.UserRole)
        model.appendRow(it)
    for fam, cats in CATEGORY_FAMILIES.items():
        head = QStandardItem(f"{FAMILY_ICONS.get(fam, '')}  {fam.upper()}")
        head.setFlags(Qt.ItemFlag.NoItemFlags)
        f = head.font()
        f.setBold(True)
        head.setFont(f)
        model.appendRow(head)
        for cat in cats:
            it = QStandardItem(f"      {cat}")
            it.setData(cat, Qt.ItemDataRole.UserRole)
            model.appendRow(it)
    c.setModel(model)
    c.setMaxVisibleItems(25)
    select_category(c, current or ("" if with_all else "Carte"))
    return c


def select_category(c: QComboBox, cat: str):
    i = c.findData(cat, Qt.ItemDataRole.UserRole)
    if i < 0 and cat:  # ancienne catégorie inconnue : on l'ajoute pour ne rien perdre
        c.model().appendRow(QStandardItem(f"      {cat}"))
        i = c.count() - 1
        c.model().item(i).setData(cat, Qt.ItemDataRole.UserRole)
    if i >= 0:
        c.setCurrentIndex(i)


def current_category(c: QComboBox) -> str:
    return c.currentData(Qt.ItemDataRole.UserRole) or ""


class ProductDialog(QDialog):
    """Fiche article universelle : carte à l'unité, TCG scellé, accessoire, jeu, boisson, prestation…"""

    def __init__(self, ctx, product: dict | None = None, parent=None, preset: dict | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.product = product
        self.setWindowTitle("Modifier l'article" if product else "Nouvel article")
        self.resize(1180, 720)
        p = dict(product or {})
        if preset:
            p.update(preset)
        self._vat_touched = product is not None and product.get("vat_rate") is not None

        db = ctx.db
        locations = [r["location"] for r in db.q("SELECT DISTINCT location FROM products WHERE location != '' ORDER BY 1")]
        brands = [r["brand"] for r in db.q("SELECT DISTINCT brand FROM products WHERE brand != '' ORDER BY 1")]

        # --- champs
        self.name = QLineEdit(p.get("name", ""))
        self.name.setPlaceholderText("Nom de l'article (obligatoire)")
        self.short_name = QLineEdit(p.get("short_name", "") or "")
        self.short_name.setPlaceholderText("Facultatif — ex. « Sleeves DS noir » (imprimé sur les étiquettes)")
        self.short_name.setMaxLength(40)
        self.category = category_combo(p.get("category") or "Carte")
        self.brand = combo([""] + brands, editable=True, current=p.get("brand", ""))
        self.brand.lineEdit().setPlaceholderText("Dragon Shield, Ultra Pro, Asmodee…")
        self.variant = QLineEdit(p.get("variant", ""))
        self.variant.setPlaceholderText("Couleur, taille, format… (ex. Noir mat, 100 pochettes)")
        self.supplier = QComboBox()
        self._load_suppliers(p.get("supplier_id"))

        self.game = combo(GAMES, editable=True, current=p.get("game") or "Pokémon")
        self.set_name = QLineEdit(p.get("set_name", ""))
        self.set_code = QLineEdit(p.get("set_code", ""))
        self.language = combo(LANGUAGES, editable=True, current=p.get("language", "FR"))
        self.number = QLineEdit(p.get("number", ""))
        self.rarity = QLineEdit(p.get("rarity", ""))
        self.condition = combo(CONDITIONS, current=p.get("condition") or "NM")
        for i, cond in enumerate(CONDITIONS):
            self.condition.setItemData(i, CONDITION_LABELS[cond], Qt.ItemDataRole.ToolTipRole)
        self.finish = combo(FINISHES, editable=True, current=p.get("finish", "Normale"))
        self.external_id = QLineEdit(p.get("external_id", ""))

        self.qty = QSpinBox()
        self.qty.setRange(-9999, 999999)
        self.qty.setValue(int(p.get("quantity", 1 if not product else 0) or 0))
        self.min_stock = QSpinBox()
        self.min_stock.setRange(0, 99999)
        self.min_stock.setValue(int(p.get("min_stock", 0) or 0))
        self.min_stock.setToolTip("Alerte et suggestion de réassort quand le stock descend à ce niveau")
        self.reorder_qty = QSpinBox()
        self.reorder_qty.setRange(0, 99999)
        self.reorder_qty.setSpecialValueText("auto")
        self.reorder_qty.setValue(int(p.get("reorder_qty", 0) or 0))
        self.reorder_qty.setToolTip("Quantité commandée habituellement au fournisseur (auto = 2 × stock mini − stock)")
        self.location = combo([""] + locations, editable=True, current=p.get("location", ""))
        self.cost = spin_money()
        self.cost.setValue(float(p.get("cost", 0) or 0))
        self.market = spin_money()
        self.market.setValue(float(p.get("market_price", 0) or 0))
        self.price = spin_money()
        self.price.setValue(float(p.get("price", 0) or 0))
        self.vat = QComboBox()
        self.vat.addItem("", None)
        for r in VAT_RATES:
            self.vat.addItem(f"{r:g} %".replace(".", ","), r)
        if p.get("vat_rate") is not None:
            i = self.vat.findData(float(p["vat_rate"]))
            self.vat.setCurrentIndex(max(0, i))
        self.vat.currentIndexChanged.connect(lambda _i: setattr(self, "_vat_touched", True))
        self.track = QCheckBox("Suivre le stock")
        self.track.setChecked(bool(p.get("track_stock", 0 if p.get("category") in NO_STOCK_CATEGORIES else 1)))
        self.track.setToolTip("Décochez pour une prestation (tournoi, location de table…) : pas de stock à gérer")
        self.track.toggled.connect(self._update_visibility)
        self.favorite = QCheckBox("⭐ Touche rapide en caisse")
        self.favorite.setChecked(bool(p.get("favorite", 0)))
        self.online = QCheckBox("Publié en ligne")
        self.online.setChecked(bool(p.get("online", 1)))

        self.sku = QLineEdit(p.get("sku", ""))
        self.sku.setPlaceholderText("Généré automatiquement si vide")
        self.barcode = QLineEdit(p.get("barcode", ""))
        self.barcode.setPlaceholderText("Cliquez ici puis scannez")
        self.barcode.returnPressed.connect(self._barcode_scanned)
        self.codes_btn = button("Autres codes…", self._manage_codes,
                                tip="Associer plusieurs codes-barres à cet article (EAN fabricant, étiquette boutique…)")
        self.codes_btn.setVisible(bool(product))
        self.image_url = QLineEdit(p.get("image_url", ""))
        self.image_url.setPlaceholderText("Adresse web de l'image ou photo locale")
        self.image_url.editingFinished.connect(lambda: self.image.set_url(self.image_url.text().strip()))
        self.notes = QPlainTextEdit(p.get("notes", ""))
        self.notes.setFixedHeight(70)
        self.margin_lbl = label("", "Muted")
        for w in (self.cost, self.price):
            w.valueChanged.connect(self._update_margin)

        # --- mise en page
        root = QHBoxLayout(self)
        col1 = QVBoxLayout()
        g_art = QGroupBox("Article")
        f = QFormLayout(g_art)
        f.addRow("Nom *", self.name)
        f.addRow("Nom court", self.short_name)
        f.addRow("Catégorie", self.category)
        f.addRow("Marque / éditeur", self.brand)
        f.addRow("Variante", self.variant)
        sup_row = QHBoxLayout()
        sup_row.addWidget(self.supplier, 1)
        sup_row.addWidget(button("+", self._new_supplier, tip="Nouveau fournisseur"))
        f.addRow("Fournisseur", sup_row)
        col1.addWidget(g_art)

        self.g_tcg = QGroupBox("Jeu de cartes")
        f2 = QFormLayout(self.g_tcg)
        f2.addRow("Jeu", self.game)
        f2.addRow("Extension", self.set_name)
        f2.addRow("Code extension", self.set_code)
        f2.addRow("Langue", self.language)
        self.card_rows = [("Numéro", self.number), ("Rareté", self.rarity), ("État", self.condition),
                          ("Finition", self.finish), ("ID base en ligne", self.external_id)]
        for lbl, w in self.card_rows:
            f2.addRow(lbl, w)
        self._tcg_form = f2
        col1.addWidget(self.g_tcg)
        col1.addWidget(label("Notes", "Muted"))
        col1.addWidget(self.notes)
        col1.addStretch(1)
        root.addLayout(col1, 1)

        col2 = QVBoxLayout()
        g_stock = QGroupBox("Stock et prix")
        f3 = QFormLayout(g_stock)
        f3.addRow("", self.track)
        self.stock_rows = [("Quantité en stock", self.qty), ("Stock minimum", self.min_stock),
                           ("Qté de réassort", self.reorder_qty), ("Emplacement", self.location)]
        for lbl, w in self.stock_rows:
            f3.addRow(lbl, w)
        f3.addRow("Prix d'achat HT (PMP)", self.cost)
        f3.addRow("Prix marché", self.market)
        f3.addRow("Prix de vente TTC", self.price)
        f3.addRow("TVA", self.vat)
        f3.addRow("", self.margin_lbl)
        coef_btn = button("Prix de vente = marché × coef.", self._apply_coef, tip="Coefficient défini dans les paramètres")
        f3.addRow("", coef_btn)
        self._stock_form = f3
        self._market_widgets = [self.market, coef_btn]
        col2.addWidget(g_stock)
        g_id = QGroupBox("Identification et visibilité")
        f4 = QFormLayout(g_id)
        f4.addRow("SKU", self.sku)
        bc = QHBoxLayout()
        bc.addWidget(self.barcode, 1)
        bc.addWidget(self.codes_btn)
        f4.addRow("Code-barres", bc)
        img_row = QHBoxLayout()
        img_row.addWidget(self.image_url, 1)
        img_row.addWidget(button("📁", self._pick_image, tip="Choisir une photo sur l'ordinateur"))
        f4.addRow("Image", img_row)
        f4.addRow("", self.favorite)
        f4.addRow("", self.online)
        col2.addWidget(g_id)
        col2.addStretch(1)
        root.addLayout(col2, 1)

        col3 = QVBoxLayout()
        self.image = ImageLabel(250, 350)
        col3.addWidget(self.image)
        self.lookup_btn = button("🔎 Remplir depuis la base de cartes", self._lookup)
        col3.addWidget(self.lookup_btn)
        col3.addStretch(1)
        col3.addWidget(button("Annuler", self.reject))
        col3.addWidget(button("Enregistrer", self._save, "primary"))
        root.addLayout(col3)

        self.category.currentIndexChanged.connect(self._category_changed)
        self.image.set_url(p.get("image_url", ""))
        self._update_margin()
        self._refresh_codes_btn()
        self._category_changed(initial=True)
        self.saved_id: int | None = None

    # ---------------------------------------------------------------- dynamique
    def _category_changed(self, *_, initial=False):
        cat = current_category(self.category)
        if not initial and not self.product:
            self.track.setChecked(cat not in NO_STOCK_CATEGORIES)
        if not self._vat_touched:
            self.vat.blockSignals(True)
            self.vat.setCurrentIndex(0)
            self.vat.blockSignals(False)
        default = self.ctx.svc.vat_for({"category": cat, "vat_rate": None})
        self.vat.setItemText(0, f"Par défaut ({default:g} %)".replace(".", ","))
        self._update_visibility()

    def _update_visibility(self, *_):
        cat = current_category(self.category)
        fam = family_of(cat)
        is_card = cat in CARD_CATEGORIES
        self.g_tcg.setVisible(fam in TCG_FAMILIES)
        for _lbl, w in self.card_rows:
            self._tcg_form.setRowVisible(w, is_card)
        for w in self._market_widgets:
            self._stock_form.setRowVisible(w, fam in TCG_FAMILIES)
        for _lbl, w in self.stock_rows:
            self._stock_form.setRowVisible(w, self.track.isChecked())
        self.lookup_btn.setVisible(is_card)

    def _load_suppliers(self, select_id=None):
        self.supplier.clear()
        self.supplier.addItem("— Aucun —", None)
        for s in self.ctx.db.q("SELECT id, name FROM suppliers ORDER BY name"):
            self.supplier.addItem(s["name"], s["id"])
        if select_id:
            self.supplier.setCurrentIndex(max(0, self.supplier.findData(select_id)))

    def _new_supplier(self):
        dlg = TextInputDialog("Nouveau fournisseur", "Nom du fournisseur :", parent=self)
        if dlg.exec() and dlg.value():
            sid = self.ctx.db.insert("suppliers", dict(name=dlg.value(), created_at=now()))
            self._load_suppliers(sid)

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une photo", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        dest = IMAGES_DIR / f"{uuid.uuid4().hex[:12]}{Path(path).suffix.lower()}"
        shutil.copyfile(path, dest)
        rel = str(dest.relative_to(DATA_DIR)).replace("\\", "/")
        self.image_url.setText(rel)
        self.image.set_url(rel)

    # ---------------------------------------------------------------- codes-barres
    def _barcode_scanned(self):
        """Lecture scanner dans le champ : on corrige la saisie et on vérifie le doublon tout de suite."""
        code = normalize_scan(self.barcode.text())
        self.barcode.setText(code)
        owner = self.ctx.svc.barcode_owner(code, self.product["id"] if self.product else None)
        if owner:
            warn(self, "Code-barres déjà utilisé", f"Ce code est déjà associé à « {owner['name']} ».")
            self.barcode.selectAll()
            return
        self.focusNextChild()

    def _refresh_codes_btn(self):
        if self.product:
            n = self.ctx.db.val("SELECT COUNT(*) FROM barcodes WHERE product_id = ?", (self.product["id"],), 0)
            self.codes_btn.setText(f"Autres codes ({n})…" if n else "Autres codes…")

    def _manage_codes(self):
        if self.product:
            BarcodesDialog(self.ctx, self.product["id"], self).exec()
            p = self.ctx.db.one("SELECT barcode FROM products WHERE id = ?", (self.product["id"],))
            self.barcode.setText(p["barcode"])
            self._refresh_codes_btn()

    # ---------------------------------------------------------------- prix
    def _update_margin(self):
        c, pr = self.cost.value(), self.price.value()
        if pr > 0:
            vat = self._vat_value()
            ht = pr / (1 + vat / 100)
            self.margin_lbl.setText(f"Marge unitaire : {money(ht - c)} HT ({(ht - c) / ht * 100:.0f} %)")
        else:
            self.margin_lbl.setText("")

    def _vat_value(self) -> float:
        v = self.vat.currentData()
        if v is None:
            return self.ctx.svc.vat_for({"category": current_category(self.category), "vat_rate": None})
        return float(v)

    def _apply_coef(self):
        coef = self.ctx.db.setting_float("price_coef", 1.0)
        if self.market.value() > 0:
            self.price.setValue(round(self.market.value() * coef, 2))

    # ---------------------------------------------------------------- base de cartes
    def _lookup(self):
        dlg = CardSearchDialog(self, self.game.currentText(), self.name.text().strip())
        if dlg.exec() and dlg.result_card:
            self.fill_from_card(dlg.result_card)

    def fill_from_card(self, c: dict):
        self.name.setText(c.get("name", ""))
        self.set_name.setText(c.get("set_name", ""))
        self.set_code.setText(c.get("set_code", ""))
        self.number.setText(str(c.get("number", "")))
        self.rarity.setText(c.get("rarity", ""))
        self.image_url.setText(c.get("image_url", ""))
        self.external_id.setText(c.get("external_id", ""))
        self.game.setEditText(c.get("game", ""))
        select_category(self.category, "Carte")
        if c.get("market_price"):
            self.market.setValue(c["market_price"])
            if self.price.value() == 0:
                self._apply_coef()
        self.image.set_url(c.get("image_url", ""))

    # ---------------------------------------------------------------- enregistrement
    def _save(self):
        name = self.name.text().strip()
        if not name:
            warn(self, "Champ manquant", "Le nom de l'article est obligatoire.")
            return
        cat = current_category(self.category)
        fam = family_of(cat)
        is_card = cat in CARD_CATEGORIES
        data = dict(
            name=name, short_name=self.short_name.text().strip(),
            category=cat, brand=self.brand.currentText().strip(), variant=self.variant.text().strip(),
            supplier_id=self.supplier.currentData(),
            game=self.game.currentText().strip() if fam in TCG_FAMILIES else "",
            set_name=self.set_name.text().strip() if fam in TCG_FAMILIES else "",
            set_code=self.set_code.text().strip() if fam in TCG_FAMILIES else "",
            language=self.language.currentText().strip() if fam in TCG_FAMILIES else "",
            number=self.number.text().strip() if is_card else "",
            rarity=self.rarity.text().strip() if is_card else "",
            condition=self.condition.currentText() if is_card else ("Scellé" if fam == "TCG scellé" else ""),
            finish=self.finish.currentText().strip() if is_card else "",
            external_id=self.external_id.text().strip() if is_card else "",
            location=self.location.currentText().strip(), quantity=self.qty.value(),
            min_stock=self.min_stock.value(), reorder_qty=self.reorder_qty.value(), cost=self.cost.value(),
            price=self.price.value(), market_price=self.market.value() if fam in TCG_FAMILIES else 0.0,
            vat_rate=self.vat.currentData(), track_stock=int(self.track.isChecked()),
            favorite=int(self.favorite.isChecked()), online=int(self.online.isChecked()),
            sku=self.sku.text().strip(), barcode=normalize_scan(self.barcode.text()),
            image_url=self.image_url.text().strip(), notes=self.notes.toPlainText().strip(),
        )
        if not self.track.isChecked():
            data["quantity"] = 0 if not self.product else self.product["quantity"]
        pid = self.product["id"] if self.product else None
        for key, what in (("barcode", "Ce code-barres"), ("sku", "Ce SKU")):
            dup = self.ctx.svc.barcode_owner(data[key], pid) if data[key] else None
            if dup:
                warn(self, "Code déjà utilisé", f"{what} est déjà attribué à « {dup['name']} ».")
                return
        if pid and data["barcode"]:
            # si le nouveau code principal était un code supplémentaire du même article, on l'y retire
            self.ctx.db.exec("DELETE FROM barcodes WHERE code = ? AND product_id = ?", (data["barcode"], pid))
        self.saved_id = self.ctx.svc.save_product(data, pid)
        self.accept()


# ------------------------------------------------------------------ codes-barres d'un article
class BarcodesDialog(QDialog):
    """Liste des codes-barres d'un article : ajout par scan, suppression, choix du code principal."""

    def __init__(self, ctx, product_id: int, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.pid = product_id
        p = ctx.db.one("SELECT name, set_name, sku FROM products WHERE id = ?", (product_id,))
        self.setWindowTitle("Codes-barres de l'article")
        self.resize(460, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"<b>{p['name']}</b>" + (f" — {p['set_name']}" if p["set_name"] else ""), wrap=True))
        lay.addWidget(label(f"Le SKU <b>{p['sku']}</b> est toujours scannable (c'est lui qui figure sur les étiquettes "
                            "imprimées par l'application).", "Muted", wrap=True))
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setObjectName("Search")
        self.input.setPlaceholderText("📷  Scannez un code à ajouter puis Entrée")
        self.input.returnPressed.connect(self._add)
        row.addWidget(self.input, 1)
        row.addWidget(button("Ajouter", self._add, "primary"))
        lay.addLayout(row)
        self.status = label("", wrap=True)
        lay.addWidget(self.status)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        row2 = QHBoxLayout()
        row2.addWidget(button("★ Définir comme principal", self._primary))
        row2.addWidget(button("Retirer", self._remove, "danger"))
        row2.addStretch(1)
        row2.addWidget(button("Fermer", self.accept))
        lay.addLayout(row2)
        self._fill()
        self.input.setFocus()

    def _fill(self):
        self.list.clear()
        for i, code in enumerate(self.ctx.svc.product_codes(self.pid)):
            it = QListWidgetItem(f"{code}   ★ principal" if i == 0 else code)
            it.setData(Qt.ItemDataRole.UserRole, code)
            self.list.addItem(it)
        if not self.list.count():
            self.list.addItem(QListWidgetItem("Aucun code-barres associé pour l'instant."))

    def _add(self):
        code = normalize_scan(self.input.text())
        self.input.clear()
        if not code:
            return
        try:
            self.ctx.svc.link_barcode(self.pid, code)
            self.status.setText(f"<span style='color:#22c55e'>✔ {code} associé.</span>")
        except ValueError as e:
            self.status.setText(f"<span style='color:#ef4444'>✖ {e}</span>")
        self._fill()
        self.input.setFocus()

    def _selected(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _remove(self):
        code = self._selected()
        if code:
            self.ctx.svc.unlink_barcode(self.pid, code)
            self._fill()

    def _primary(self):
        code = self._selected()
        if not code:
            return
        cur = self.ctx.db.val("SELECT barcode FROM products WHERE id = ?", (self.pid,), "")
        if cur.lower() == code.lower():
            return
        with self.ctx.db.tx():
            self.ctx.db.exec("DELETE FROM barcodes WHERE code = ?", (code,))
            self.ctx.db.exec("UPDATE products SET barcode = ? WHERE id = ?", (code, self.pid))
            if cur:
                self.ctx.db.insert("barcodes", dict(code=cur, product_id=self.pid, created_at=now()))
        self._fill()


# ------------------------------------------------------------------ sélection d'un article du stock
class ProductPickerDialog(QDialog):
    def __init__(self, ctx, parent=None, title="Choisir un article du stock", in_stock_only=False, hint: str = ""):
        super().__init__(parent)
        self.ctx = ctx
        self.in_stock_only = in_stock_only
        self.setWindowTitle(title)
        self.resize(980, 560)
        self.result_product: dict | None = None
        lay = QVBoxLayout(self)
        if hint:
            lay.addWidget(label(hint, wrap=True))
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Rechercher par nom, extension, SKU ou code-barres…")
        lay.addWidget(self.search)
        self.table = DataTable([
            ("name", "Nom", "text"), ("category", "Catégorie", "text"), ("detail", "Détail", "text"),
            ("condition", "État", "text"), ("language", "Langue", "text"),
            ("quantity", "Stock", "qty"), ("price", "Prix", "money"),
        ], stretch="name")
        self.table.record_activated.connect(self._pick)
        lay.addWidget(self.table, 1)
        b = QHBoxLayout()
        b.addStretch(1)
        b.addWidget(button("Annuler", self.reject))
        b.addWidget(button("Choisir", lambda: self._pick(self.table.selected()), "primary"))
        lay.addLayout(b)
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self._timer.start())
        self.search.returnPressed.connect(self._enter)
        self.refresh()

    def refresh(self):
        t = f"%{self.search.text().strip()}%"
        where = ("(name LIKE ? OR set_name LIKE ? OR sku LIKE ? OR barcode LIKE ? OR brand LIKE ? OR variant LIKE ? "
                 "OR category LIKE ? OR id IN (SELECT product_id FROM barcodes WHERE code LIKE ?))")
        if self.in_stock_only:
            where += " AND (quantity > 0 OR track_stock = 0)"
        self.table.set_rows(self.ctx.db.q(f"SELECT *, {DETAIL_SQL} FROM products WHERE {where} ORDER BY name LIMIT 500",
                                          (t,) * 8))

    def _enter(self):
        p = self.ctx.svc.find_by_code(self.search.text())
        if p:
            self._pick(p)
        elif len(self.table.rows()) == 1:
            self._pick(self.table.rows()[0])

    def _pick(self, rec):
        if rec:
            self.result_product = rec
            self.accept()


# ------------------------------------------------------------------ clients
class CustomerDialog(QDialog):
    def __init__(self, ctx, customer: dict | None = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.customer = customer
        self.saved_id: int | None = None
        self.setWindowTitle("Modifier le client" if customer else "Nouveau client")
        self.resize(480, 420)
        c = customer or {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.f = {k: QLineEdit(c.get(k, "") or "") for k in ("name", "email", "phone", "id_number")}
        self.id_type = combo(["", "Carte d'identité", "Passeport", "Permis de conduire", "Titre de séjour"],
                             current=c.get("id_type", ""))
        self.address = QPlainTextEdit(c.get("address", "") or "")
        self.address.setFixedHeight(60)
        self.notes = QPlainTextEdit(c.get("notes", "") or "")
        self.notes.setFixedHeight(50)
        form.addRow("Nom complet *", self.f["name"])
        form.addRow("E-mail", self.f["email"])
        form.addRow("Téléphone", self.f["phone"])
        form.addRow("Adresse", self.address)
        form.addRow("Pièce d'identité", self.id_type)
        form.addRow("N° de pièce", self.f["id_number"])
        form.addRow("Notes", self.notes)
        lay.addLayout(form)
        lay.addWidget(label("La pièce d'identité est requise pour les rachats (registre des objets mobiliers).",
                            "Muted", wrap=True))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        name = self.f["name"].text().strip()
        if not name:
            warn(self, "Champ manquant", "Le nom du client est obligatoire.")
            return
        data = {k: w.text().strip() for k, w in self.f.items()}
        data.update(id_type=self.id_type.currentText(), address=self.address.toPlainText().strip(),
                    notes=self.notes.toPlainText().strip())
        self.saved_id = self.ctx.svc.save_customer(data, self.customer["id"] if self.customer else None)
        self.accept()


class CustomerPicker(QWidget):
    """Sélecteur de client avec recherche + bouton de création."""
    changed = Signal(object)

    def __init__(self, ctx, parent=None, allow_none_label="— Client de passage —"):
        super().__init__(parent)
        self.ctx = ctx
        self.none_label = allow_none_label
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.combo.currentIndexChanged.connect(lambda _i: self._emit())
        row.addWidget(self.combo, 1)
        row.addWidget(button("+", self._new, tip="Nouveau client"))
        lay.addLayout(row)
        self.info = label("", "Muted")
        lay.addWidget(self.info)
        self.reload()

    def reload(self, select_id=None):
        cur = select_id if select_id is not None else (self.customer() or {}).get("id")
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(self.none_label, None)
        for c in self.ctx.db.q("SELECT id, name, phone FROM customers ORDER BY name"):
            self.combo.addItem(f"{c['name']}" + (f"  ·  {c['phone']}" if c["phone"] else ""), c["id"])
        idx = self.combo.findData(cur) if cur else 0
        self.combo.setCurrentIndex(max(0, idx))
        self.combo.blockSignals(False)
        self._emit()

    def customer(self) -> dict | None:
        if not hasattr(self, "combo"):
            return None
        idx = self.combo.findText(self.combo.currentText())
        cid = self.combo.itemData(idx) if idx >= 0 else None
        return self.ctx.db.one("SELECT * FROM customers WHERE id = ?", (cid,)) if cid else None

    def set_none(self):
        self.combo.setCurrentIndex(0)

    def _emit(self):
        c = self.customer()
        self.info.setText(f"Crédit : {money(c['credit'])} · Points : {c['points']}" if c else "")
        self.changed.emit(c)

    def _new(self):
        dlg = CustomerDialog(self.ctx, parent=self)
        if dlg.exec():
            self.reload(dlg.saved_id)


# ------------------------------------------------------------------ ajustement de stock
class StockAdjustDialog(QDialog):
    def __init__(self, product: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajuster le stock")
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"<b>{product['name']}</b> — stock actuel : <b>{product['quantity']}</b>"))
        form = QFormLayout()
        self.mode = combo(["Ajouter / retirer (±)", "Fixer la quantité à"])
        self.value = QSpinBox()
        self.value.setRange(-99999, 99999)
        self.value.setValue(1)
        self.reason = combo(STOCK_REASONS, editable=True)
        self.note = QLineEdit()
        form.addRow("Mode", self.mode)
        form.addRow("Valeur", self.value)
        form.addRow("Motif", self.reason)
        form.addRow("Référence / note", self.note)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.current = int(product["quantity"])

    def delta(self) -> int:
        return self.value.value() if self.mode.currentIndex() == 0 else self.value.value() - self.current


# ------------------------------------------------------------------ choix d'une extension
class SetPickerDialog(QDialog):
    def __init__(self, parent=None, game="Pokémon"):
        super().__init__(parent)
        self.setWindowTitle("Importer une extension complète")
        self.resize(620, 560)
        self.result_set: tuple | None = None
        self._sets: list[tuple] = []
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.game = combo(api.API_GAMES, current=game if game in api.API_GAMES else None)
        self.game.currentIndexChanged.connect(self.load)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtrer les extensions…")
        self.filter.textChanged.connect(self._fill)
        top.addWidget(self.game)
        top.addWidget(self.filter, 1)
        lay.addLayout(top)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._ok())
        lay.addWidget(self.list, 1)
        self.status = label("", "Muted")
        lay.addWidget(self.status)
        b = QHBoxLayout()
        b.addStretch(1)
        b.addWidget(button("Annuler", self.reject))
        b.addWidget(button("Importer", self._ok, "primary"))
        lay.addLayout(b)
        self.load()

    def load(self):
        self.status.setText("Chargement des extensions…")
        self.list.clear()
        game = self.game.currentText()

        def done(rows):
            self._sets = rows
            self._fill()
            self.status.setText(f"{len(rows)} extensions")

        run_async(lambda: api.list_sets(game), done, lambda e: self.status.setText(f"Erreur : {e}"))

    def _fill(self):
        t = self.filter.text().lower().strip()
        self.list.clear()
        for code, name, date in self._sets:
            if t and t not in name.lower() and t not in code.lower():
                continue
            it = QListWidgetItem(f"{name}   ·   {code}   ·   {date[:4]}")
            it.setData(Qt.ItemDataRole.UserRole, (code, name))
            self.list.addItem(it)

    def _ok(self):
        it = self.list.currentItem()
        if it:
            self.result_set = (self.game.currentText(),) + tuple(it.data(Qt.ItemDataRole.UserRole))
            self.accept()


# ------------------------------------------------------------------ aperçu/impression
class DocumentDialog(QDialog):
    def __init__(self, title: str, html: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 720)
        self.html = html
        lay = QVBoxLayout(self)
        view = QTextBrowser()
        view.setStyleSheet("background: white; color: #111; border-radius: 8px;")
        view.setHtml(html)
        lay.addWidget(view, 1)
        b = QHBoxLayout()
        b.addStretch(1)
        b.addWidget(button("Enregistrer en PDF", self._pdf))
        b.addWidget(button("🖨  Imprimer", self._print, "primary"))
        b.addWidget(button("Fermer", self.accept))
        lay.addLayout(b)

    def _doc(self) -> QTextDocument:
        d = QTextDocument()
        d.setHtml(self.html)
        return d

    def _print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(printer, self).exec():
            self._doc().print_(printer)

    def _pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer en PDF", f"{self.windowTitle()}.pdf", "PDF (*.pdf)")
        if path:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)
            self._doc().print_(printer)


class TextInputDialog(QDialog):
    def __init__(self, title: str, prompt: str, value: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(prompt))
        self.edit = QLineEdit(value)
        lay.addWidget(self.edit)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def value(self) -> str:
        return self.edit.text().strip()
