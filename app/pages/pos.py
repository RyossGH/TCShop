"""Caisse (point de vente) + historique des ventes."""
from __future__ import annotations

from PySide6.QtCore import QDate, QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout, QGridLayout,
    QHBoxLayout, QHeaderView, QLineEdit, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from ..constants import CARD_CATEGORIES, CATEGORY_FAMILIES, DETAIL_SQL, FAMILY_ICONS
from ..dialogs import CustomerPicker, DocumentDialog, TextInputDialog, spin_money
from ..documents import sale_ticket
from ..widgets import (
    Card, DataTable, PageHeader, ask, button, label, load_pixmap, money, page_layout, warn,
)

TILE = QSize(138, 92)
CHIP_NAMES = {"TCG scellé": "Scellé", "Services & événements": "Services"}


class ProductTile(QToolButton):
    """Touche rapide de caisse : image, nom, prix."""

    def __init__(self, p: dict, on_click):
        super().__init__()
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setFixedSize(TILE.width(), TILE.height() + 34)
        self.setIconSize(QSize(64, 64))
        name = p["name"] if len(p["name"]) <= 22 else p["name"][:21] + "…"
        extra = p.get("variant") or ""
        self.setText(f"{name}\n{money(p['price'])}" + (f" · {extra[:10]}" if extra else ""))
        stock = "∞" if p.get("track_stock") == 0 else p["quantity"]
        self.setToolTip(f"{p['name']} {extra}\nStock : {stock}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("Tile")
        if p.get("track_stock") != 0 and p["quantity"] <= 0:
            self.setProperty("empty", True)
        self.clicked.connect(lambda: on_click(p))
        if p.get("image_url"):
            load_pixmap(p["image_url"], lambda pm: (not pm.isNull()) and self.setIcon(QIcon(pm)))
        else:
            self.setIcon(QIcon())
            self.setText(f"{FAMILY_ICONS.get(p.get('family', ''), '')}\n" + self.text())


# ------------------------------------------------------------------ paiement
class PaymentDialog(QDialog):
    def __init__(self, total: float, customer: dict | None, mode: str, parent=None):
        super().__init__(parent)
        self.total = round(total, 2)
        self.setWindowTitle("Encaissement")
        self.resize(460, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Montant à encaisser", "Muted"))
        lay.addWidget(label(money(self.total), "Total"))
        form = QFormLayout()
        self.cash = spin_money()
        self.card = spin_money()
        self.credit = spin_money(customer["credit"] if customer else 0)
        self.credit.setEnabled(bool(customer and customer["credit"] > 0))
        self.given = spin_money()
        form.addRow("💶 Espèces", self.cash)
        form.addRow("💳 Carte bancaire", self.card)
        form.addRow(f"🎟️ Crédit boutique (dispo {money(customer['credit']) if customer else '0 €'})", self.credit)
        form.addRow("Espèces remises par le client", self.given)
        lay.addLayout(form)
        quick = QHBoxLayout()
        for v in (5, 10, 20, 50, 100):
            quick.addWidget(button(f"{v} €", lambda _=False, v=v: self.given.setValue(self.given.value() + v)))
        quick.addWidget(button("Exact", lambda: self.given.setValue(self.cash.value())))
        lay.addLayout(quick)
        self.remaining = label("", "H2")
        self.change = label("", "H2")
        lay.addWidget(self.remaining)
        lay.addWidget(self.change)
        lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Annuler", self.reject))
        self.ok = button("✔ Valider la vente", self.accept, "success")
        row.addWidget(self.ok)
        lay.addLayout(row)
        for s in (self.cash, self.card, self.credit, self.given):
            s.valueChanged.connect(self._update)

        if mode == "cash":
            self.cash.setValue(self.total)
        elif mode == "card":
            self.card.setValue(self.total)
        elif mode == "credit" and customer:
            c = min(self.total, customer["credit"])
            self.credit.setValue(c)
            self.card.setValue(round(self.total - c, 2))
        self._update()
        (self.given if mode == "cash" else self.ok).setFocus()

    def _update(self):
        paid = self.cash.value() + self.card.value() + self.credit.value()
        rest = round(self.total - paid, 2)
        if abs(rest) < 0.005:
            self.remaining.setText("✔ Montant couvert")
            self.remaining.setStyleSheet("color: #22c55e;")
        elif rest > 0:
            self.remaining.setText(f"Reste à payer : {money(rest)}")
            self.remaining.setStyleSheet("color: #f59e0b;")
        else:
            self.remaining.setText(f"Trop perçu : {money(-rest)}")
            self.remaining.setStyleSheet("color: #ef4444;")
        self.ok.setEnabled(abs(rest) < 0.005 and (self.given.value() == 0 or self.given.value() >= self.cash.value()))
        if self.given.value() > 0:
            self.change.setText(f"À rendre : {money(max(0, self.given.value() - self.cash.value()))}")
        else:
            self.change.setText("")


# ------------------------------------------------------------------ caisse
class PosPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.cart: list[dict] = []
        lay = page_layout(self)
        lay.addWidget(PageHeader("Caisse", "Scannez un code-barres ou recherchez un article · F2 pour revenir ici"))
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_register(), "🛒  Encaissement")
        self.tabs.addTab(self._build_history(), "🧾  Historique des ventes")
        self.tabs.currentChanged.connect(lambda i: self.refresh_history() if i == 1 else None)

    # ---------------------------------------------------------------- UI
    def _build_register(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(12)

        left = Card()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("📷  Scanner / rechercher un article puis Entrée…")
        self.search.returnPressed.connect(self._on_enter)
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._search)
        self.search.textChanged.connect(lambda: self._timer.start())
        left.lay.addWidget(self.search)

        self.left_tabs = QTabWidget()
        # --- touches rapides
        quick = QWidget()
        ql = QVBoxLayout(quick)
        ql.setContentsMargins(0, 6, 0, 0)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        for i, (key, text) in enumerate([("", "⭐ Favoris")] +
                                        [(f, f"{FAMILY_ICONS.get(f, '')} {CHIP_NAMES.get(f, f)}")
                                         for f in CATEGORY_FAMILIES if f != "Cartes à l'unité"]):
            b = button(text, kind="chip")
            b.setCheckable(True)
            b.setProperty("family", key)
            self.chip_group.addButton(b, i)
            chips.addWidget(b)
        chips.addStretch(1)
        self.chip_group.button(0).setChecked(True)
        self.chip_group.idClicked.connect(lambda _i: self._fill_tiles())
        ql.addLayout(chips)
        self.tiles_area = QScrollArea()
        self.tiles_area.setWidgetResizable(True)
        self.tiles_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.tiles_area.setStyleSheet("QScrollArea { background: transparent; }")
        self.tiles_area.viewport().setAutoFillBackground(False)
        self._tile_cols = 0
        self._resize_timer = QTimer(self, singleShot=True, interval=150)
        self._resize_timer.timeout.connect(self._maybe_reflow)
        ql.addWidget(self.tiles_area, 1)
        self.left_tabs.addTab(quick, "⭐  Touches rapides")
        # --- recherche
        self.results = DataTable([
            ("name", "Article", "text"), ("category", "Catégorie", "text"), ("detail", "Détail", "text"),
            ("condition", "État", "text"), ("location", "Empl.", "text"),
            ("quantity", "Stock", "qty"), ("price", "Prix", "money"),
        ], stretch="name")
        self.results.record_activated.connect(self.add_product)
        self.left_tabs.addTab(self.results, "🔍  Recherche")
        left.lay.addWidget(self.left_tabs, 1)
        row = QHBoxLayout()
        row.addWidget(label("Double-clic pour ajouter au panier", "Muted"), 1)
        row.addWidget(button("+ Article libre", self._free_item, tip="Service, article non référencé…"))
        row.addWidget(button("Ajouter au panier →", lambda: self.add_product(self.results.selected()), "primary"))
        left.lay.addLayout(row)
        lay.addWidget(left, 3)

        right = Card()
        right.setMinimumWidth(460)
        right.lay.addWidget(label("Client", "Muted"))
        self.customer = CustomerPicker(self.ctx)
        self.customer.changed.connect(lambda _c: self._update_totals())
        right.lay.addWidget(self.customer)

        self.cart_table = QTableWidget(0, 5)
        self.cart_table.setHorizontalHeaderLabels(["Article", "Qté", "P.U.", "Total", ""])
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.verticalHeader().setDefaultSectionSize(38)
        self.cart_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.cart_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self.cart_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, wdt in ((1, 70), (2, 100), (3, 90), (4, 36)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.cart_table.setColumnWidth(i, wdt)
        right.lay.addWidget(self.cart_table, 1)

        disc = QHBoxLayout()
        disc.addWidget(label("Remise"))
        self.discount = QDoubleSpinBox()
        self.discount.setRange(0, 100000)
        self.discount.setDecimals(2)
        self.discount_type = QComboBox()
        self.discount_type.addItems(["%", "€"])
        self.discount.valueChanged.connect(self._update_totals)
        self.discount_type.currentIndexChanged.connect(self._update_totals)
        disc.addWidget(self.discount)
        disc.addWidget(self.discount_type)
        disc.addStretch(1)
        self.subtotal_lbl = label("", "Muted")
        disc.addWidget(self.subtotal_lbl)
        right.lay.addLayout(disc)

        tot = QHBoxLayout()
        tot.addWidget(label("TOTAL", "H2"))
        tot.addStretch(1)
        self.total_lbl = label(money(0), "Total")
        tot.addWidget(self.total_lbl)
        right.lay.addLayout(tot)

        pay = QGridLayout()
        pay.setSpacing(8)
        self.btn_cash = button("💶  Espèces", lambda: self._checkout("cash"), "big")
        self.btn_card = button("💳  Carte", lambda: self._checkout("card"), "big")
        self.btn_credit = button("🎟️  Crédit boutique", lambda: self._checkout("credit"), "big")
        self.btn_mixed = button("➗  Paiement mixte", lambda: self._checkout("mixed"), "big")
        self.btn_cash.setProperty("kind", "primary")
        pay.addWidget(self.btn_cash, 0, 0)
        pay.addWidget(self.btn_card, 0, 1)
        pay.addWidget(self.btn_credit, 1, 0)
        pay.addWidget(self.btn_mixed, 1, 1)
        right.lay.addLayout(pay)
        right.lay.addWidget(button("🗑  Vider le panier", self.clear_cart, "danger"))
        lay.addWidget(right, 2)
        return w

    def _build_history(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        f = QHBoxLayout()
        self.h_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.h_to = QDateEdit(QDate.currentDate())
        for d in (self.h_from, self.h_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
            d.dateChanged.connect(self.refresh_history)
        self.h_search = QLineEdit()
        self.h_search.setPlaceholderText("N° de ticket ou client…")
        self.h_search.textChanged.connect(self.refresh_history)
        f.addWidget(label("Du"))
        f.addWidget(self.h_from)
        f.addWidget(label("au"))
        f.addWidget(self.h_to)
        f.addWidget(self.h_search, 1)
        f.addWidget(button("Voir le ticket", self._show_ticket))
        f.addWidget(button("↩ Rembourser", self._refund, "danger"))
        lay.addLayout(f)
        body = QHBoxLayout()
        self.history = DataTable([
            ("number", "Ticket", "text"), ("date", "Date", "date"), ("customer", "Client", "text"),
            ("nb", "Articles", "int"), ("payment", "Paiement", "text"), ("discount", "Remise", "money"),
            ("total", "Total", "money"), ("margin", "Marge", "money"), ("status", "Statut", "status"),
        ], stretch="customer")
        self.history.record_activated.connect(lambda _r: self._show_ticket())
        self.history.selection_changed_record.connect(self._show_items)
        body.addWidget(self.history, 3)
        self.h_items = DataTable([("name", "Article", "text"), ("qty", "Qté", "int"),
                                  ("unit_price", "P.U.", "money")], stretch="name")
        body.addWidget(self.h_items, 2)
        lay.addLayout(body, 1)
        self.h_footer = label("", "Muted")
        lay.addWidget(self.h_footer)
        return w

    # ---------------------------------------------------------------- navigation
    def refresh(self):
        self.customer.reload()
        self._search()
        self._fill_tiles()
        if self.tabs.currentIndex() == 1:
            self.refresh_history()
        QTimer.singleShot(0, self.search.setFocus)

    def on_navigate(self, add_product=None, **_):
        if add_product:
            p = self.ctx.db.one("SELECT * FROM products WHERE id = ?", (add_product,))
            self.tabs.setCurrentIndex(0)
            self.add_product(p)

    # ---------------------------------------------------------------- recherche
    def _fill_tiles(self):
        """Grille de touches rapides : favoris, ou articles d'une famille (hors cartes à l'unité)."""
        b = self.chip_group.checkedButton()
        fam = b.property("family") if b else ""
        if fam:
            cats = CATEGORY_FAMILIES[fam]
            rows = self.ctx.db.q(
                f"SELECT * FROM products WHERE category IN ({','.join('?' * len(cats))}) "
                "AND (quantity > 0 OR track_stock = 0) ORDER BY favorite DESC, name LIMIT 120", cats)
        else:
            rows = self.ctx.db.q("SELECT * FROM products WHERE favorite = 1 ORDER BY category, name LIMIT 120")
        from ..constants import family_of
        cols = self._cols()
        self._tile_cols = cols
        grid_w = QWidget()
        grid_w.setAutoFillBackground(False)
        grid_w.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, p in enumerate(rows):
            p["family"] = family_of(p["category"])
            grid.addWidget(ProductTile(p, self.add_product), i // cols, i % cols)
        if not rows:
            grid.addWidget(label("Aucune touche rapide ici.\nCochez « ⭐ Touche rapide en caisse » dans la fiche d'un "
                                 "article (sleeves, boosters, boissons…) pour l'afficher dans les Favoris.",
                                 "Muted", wrap=True), 0, 0)
        grid.setRowStretch(grid.rowCount(), 1)
        grid.setColumnStretch(cols, 1)
        self.tiles_area.setWidget(grid_w)

    def _cols(self) -> int:
        return max(2, (self.tiles_area.viewport().width() - 4) // (TILE.width() + 8))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._resize_timer.start()

    def _maybe_reflow(self):
        if self._cols() != self._tile_cols:
            self._fill_tiles()

    def _search(self):
        t = self.search.text().strip()
        if t:
            where, params = [], []
            for word in t.split():
                where.append("(name LIKE ? OR set_name LIKE ? OR number LIKE ? OR sku LIKE ? OR barcode LIKE ? "
                             "OR brand LIKE ? OR variant LIKE ? OR category LIKE ? "
                             "OR id IN (SELECT product_id FROM barcodes WHERE code LIKE ?))")
                params += [f"%{word}%"] * 9
            rows = self.ctx.db.q(f"SELECT *, {DETAIL_SQL} FROM products WHERE {' AND '.join(where)} "
                                 "ORDER BY (quantity <= 0 AND track_stock = 1), name LIMIT 300", params)
            if self.left_tabs.currentIndex() != 1:
                self.left_tabs.setCurrentIndex(1)
        else:
            rows = self.ctx.db.q(f"SELECT *, {DETAIL_SQL} FROM products WHERE quantity > 0 OR track_stock = 0 "
                                 "ORDER BY updated_at DESC LIMIT 100")
        self.results.set_rows(rows)

    def _on_enter(self):
        text = self.search.text().strip()
        if not text:
            return
        p = self.ctx.svc.find_by_code(text)
        if p:
            self.add_product(p)
            self.search.clear()
            return
        self._timer.stop()
        self._search()  # le scanner tape plus vite que la recherche différée
        rows = self.results.rows()
        if len(rows) == 1:
            self.add_product(rows[0])
            self.search.clear()
        elif rows:
            self.results.setFocus()
            self.results.selectRow(0)
        elif " " not in text and len(text) >= 6:
            self.search.clear()
            self.on_scan(text)

    def on_scan(self, code: str) -> bool:
        """Scan reçu alors que le curseur n'est pas dans un champ : ajout direct au panier."""
        self.tabs.setCurrentIndex(0)
        p = self.ctx.svc.find_by_code(code)
        if not p:
            from ..scan import resolve_unknown
            p = resolve_unknown(self.ctx, code, self)
            self._search()
        if p:
            self.add_product(p)
        self.search.setFocus()
        return True

    # ---------------------------------------------------------------- panier
    def add_product(self, p):
        if not p:
            return
        p = self.ctx.db.one("SELECT * FROM products WHERE id = ?", (p["id"],))
        in_cart = sum(l["qty"] for l in self.cart if l.get("product_id") == p["id"])
        if p["track_stock"] != 0 and in_cart + 1 > p["quantity"] and not ask(
                self, "Stock insuffisant",
                f"Stock disponible pour « {p['name']} » : {p['quantity']}.\nVendre quand même ?"):
            return
        for l in self.cart:
            if l.get("product_id") == p["id"]:
                l["qty"] += 1
                break
        else:
            desc = p["name"] + (f" — {p['set_name']}" if p["set_name"] else "")
            if p["variant"]:
                desc += f" — {p['variant']}"
            if p["category"] in CARD_CATEGORIES:
                desc += f" ({p['condition']} {p['language']})"
            self.cart.append(dict(product_id=p["id"], name=desc, qty=1, unit_price=p["price"], unit_cost=p["cost"],
                                  vat_rate=self.ctx.svc.vat_for(p)))
        self._render_cart()

    def _free_item(self):
        dlg = TextInputDialog("Article libre", "Désignation :", "Divers", self)
        if not dlg.exec() or not dlg.value():
            return
        self.cart.append(dict(product_id=None, name=dlg.value(), qty=1, unit_price=0.0, unit_cost=0.0))
        self._render_cart()

    def _render_cart(self):
        t = self.cart_table
        t.setRowCount(len(self.cart))
        for r, l in enumerate(self.cart):
            item = QTableWidgetItem(l["name"])
            item.setToolTip(l["name"])
            t.setItem(r, 0, item)
            q = QSpinBox()
            q.setRange(1, 9999)
            q.setValue(l["qty"])
            q.valueChanged.connect(lambda v, l=l: self._set_line(l, "qty", v))
            t.setCellWidget(r, 1, q)
            pr = spin_money()
            pr.setValue(l["unit_price"])
            pr.valueChanged.connect(lambda v, l=l: self._set_line(l, "unit_price", v))
            t.setCellWidget(r, 2, pr)
            tot = QTableWidgetItem(money(l["qty"] * l["unit_price"]))
            tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(r, 3, tot)
            rm = button("✕", lambda _=False, l=l: self._remove(l), "flat")
            t.setCellWidget(r, 4, rm)
        self._update_totals()

    def _set_line(self, line, key, value):
        line[key] = value
        r = self.cart.index(line)
        it = self.cart_table.item(r, 3)
        if it:
            it.setText(money(line["qty"] * line["unit_price"]))
        self._update_totals()

    def _remove(self, line):
        self.cart.remove(line)
        self._render_cart()

    def clear_cart(self):
        self.cart.clear()
        self.discount.setValue(0)
        self.customer.set_none()
        self._render_cart()

    def _amounts(self):
        subtotal = round(sum(l["qty"] * l["unit_price"] for l in self.cart), 2)
        d = self.discount.value()
        disc = subtotal * d / 100 if self.discount_type.currentText() == "%" else d
        disc = round(min(disc, subtotal), 2)
        return subtotal, disc, round(subtotal - disc, 2)

    def _update_totals(self):
        subtotal, disc, total = self._amounts()
        n = sum(l["qty"] for l in self.cart)
        self.subtotal_lbl.setText(f"{n} article(s) · sous-total {money(subtotal)}" +
                                  (f" · remise −{money(disc)}" if disc else ""))
        self.total_lbl.setText(money(total))
        has = bool(self.cart)
        c = self.customer.customer()
        for b in (self.btn_cash, self.btn_card, self.btn_mixed):
            b.setEnabled(has)
        self.btn_credit.setEnabled(has and bool(c and c["credit"] > 0))

    # ---------------------------------------------------------------- encaissement
    def _checkout(self, mode):
        if not self.cart:
            return
        subtotal, disc, total = self._amounts()
        cust = self.customer.customer()
        dlg = PaymentDialog(total, cust, mode, self)
        if not dlg.exec():
            return
        try:
            sid = self.ctx.svc.create_sale(
                [dict(l) for l in self.cart], cust["id"] if cust else None, disc,
                paid_cash=dlg.cash.value(), paid_card=dlg.card.value(), paid_credit=dlg.credit.value(),
                cash_given=dlg.given.value(),
            )
        except Exception as e:  # noqa: BLE001
            warn(self, "Erreur", f"La vente n'a pas pu être enregistrée :\n{e}")
            return
        change = max(0, dlg.given.value() - dlg.cash.value()) if dlg.given.value() else 0
        self.clear_cart()
        self._search()
        self.ctx.window.flash(f"Vente enregistrée · {money(total)}" + (f" · rendu {money(change)}" if change else ""))
        s = self.ctx.db.one("SELECT number FROM sales WHERE id = ?", (sid,))
        DocumentDialog(f"Ticket {s['number']}", sale_ticket(self.ctx.db, sid), self).exec()
        self.search.setFocus()

    # ---------------------------------------------------------------- historique
    def refresh_history(self):
        d1 = self.h_from.date().toString("yyyy-MM-dd")
        d2 = self.h_to.date().addDays(1).toString("yyyy-MM-dd")
        t = f"%{self.h_search.text().strip()}%"
        rows = self.ctx.db.q("""
            SELECT s.*, COALESCE(c.name, '') customer, s.total - s.cost_total margin,
                   (SELECT COALESCE(SUM(qty),0) FROM sale_items WHERE sale_id = s.id) nb
            FROM sales s LEFT JOIN customers c ON c.id = s.customer_id
            WHERE s.date >= ? AND s.date < ? AND (s.number LIKE ? OR COALESCE(c.name,'') LIKE ?)
            ORDER BY s.date DESC""", (d1, d2, t, t))
        self.history.set_rows(rows)
        ok = [r for r in rows if r["status"] == "Validée"]
        tot = sum(r["total"] for r in ok)
        cash = sum(r["paid_cash"] for r in ok)
        card = sum(r["paid_card"] for r in ok)
        credit = sum(r["paid_credit"] for r in ok)
        other = sum(r.get("paid_other") or 0 for r in ok)
        self.h_footer.setText(f"{len(ok)} vente(s) · total {money(tot)} · espèces {money(cash)} · carte {money(card)}"
                              f" · crédit {money(credit)} · virement/Wero {money(other)}"
                              f" · marge {money(sum(r['margin'] for r in ok))}")

    def _show_items(self, s):
        self.h_items.set_rows(self.ctx.db.q("SELECT * FROM sale_items WHERE sale_id = ?", (s["id"],)) if s else [])

    def _show_ticket(self):
        s = self.history.selected()
        if s:
            DocumentDialog(f"Ticket {s['number']}", sale_ticket(self.ctx.db, s["id"]), self).exec()

    def _refund(self):
        s = self.history.selected()
        if not s:
            return
        if s["status"] != "Validée":
            warn(self, "Impossible", "Cette vente est déjà remboursée.")
            return
        if ask(self, "Rembourser", f"Rembourser la vente {s['number']} ({money(s['total'])}) ?\n"
                                   "Les articles seront remis en stock et le crédit boutique utilisé restitué."):
            self.ctx.svc.refund_sale(s["id"])
            self.refresh_history()
