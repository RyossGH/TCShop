"""Commandes en ligne (site web, Cardmarket, eBay…) partageant le stock de la boutique."""
from __future__ import annotations

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLineEdit,
    QPlainTextEdit, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..constants import CHANNELS, ORDER_STATUSES
from ..dialogs import CustomerPicker, DocumentDialog, ProductPickerDialog, TextInputDialog, combo, spin_money
from ..documents import picking_list
from ..widgets import Card, DataTable, PageHeader, ask, button, info, label, money, page_layout, warn

NEXT_STATUS = {"À préparer": "Préparée", "Préparée": "Expédiée", "Expédiée": "Livrée"}


class OrderDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.lines: list[dict] = []
        self.setWindowTitle("Nouvelle commande en ligne")
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        form = QFormLayout()
        self.channel = combo(CHANNELS)
        self.ext_ref = QLineEdit()
        self.ext_ref.setPlaceholderText("N° de commande Cardmarket / site…")
        self.customer = CustomerPicker(ctx, allow_none_label="— Client non enregistré —")
        self.customer.changed.connect(self._fill_customer)
        self.cust_name = QLineEdit()
        self.address = QPlainTextEdit()
        self.address.setFixedHeight(70)
        form.addRow("Canal", self.channel)
        form.addRow("Référence externe", self.ext_ref)
        form.addRow("Client", self.customer)
        form.addRow("Nom du destinataire *", self.cust_name)
        form.addRow("Adresse de livraison", self.address)
        top.addLayout(form, 3)
        form2 = QFormLayout()
        self.shipping = spin_money()
        self.shipping.valueChanged.connect(self._totals)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(70)
        form2.addRow("Frais de port", self.shipping)
        form2.addRow("Notes", self.notes)
        top.addLayout(form2, 2)
        lay.addLayout(top)

        row = QHBoxLayout()
        row.addWidget(button("+ Ajouter un article du stock", self._add, "primary"))
        row.addWidget(button("+ Article libre", self._add_free))
        row.addStretch(1)
        lay.addLayout(row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Article", "Qté", "Prix unit.", "Total", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, w in ((1, 80), (2, 110), (3, 100), (4, 36)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, w)
        lay.addWidget(self.table, 1)
        b = QHBoxLayout()
        self.total_lbl = label("", "H2")
        b.addWidget(self.total_lbl, 1)
        b.addWidget(button("Annuler", self.reject))
        b.addWidget(button("Créer la commande", self._save, "primary"))
        lay.addLayout(b)
        self._totals()
        self.saved_id = None

    def _fill_customer(self, c):
        if c:
            self.cust_name.setText(c["name"])
            self.address.setPlainText(c["address"] or "")

    def _add(self):
        dlg = ProductPickerDialog(self.ctx, self, in_stock_only=True)
        if dlg.exec() and dlg.result_product:
            p = dlg.result_product
            for l in self.lines:
                if l.get("product_id") == p["id"]:
                    l["qty"] += 1
                    break
            else:
                name = p["name"] + (f" — {p['set_name']}" if p["set_name"] else "") + \
                    (f" ({p['condition']} {p['language']})" if p["category"] == "Carte" else "")
                self.lines.append(dict(product_id=p["id"], name=name, qty=1, unit_price=p["price"],
                                       unit_cost=p["cost"], stock=p["quantity"]))
            self._render()

    def _add_free(self):
        dlg = TextInputDialog("Article libre", "Désignation :", parent=self)
        if dlg.exec() and dlg.value():
            self.lines.append(dict(product_id=None, name=dlg.value(), qty=1, unit_price=0.0, unit_cost=0.0, stock=9999))
            self._render()

    def _render(self):
        self.table.setRowCount(len(self.lines))
        for r, l in enumerate(self.lines):
            self.table.setItem(r, 0, QTableWidgetItem(l["name"]))
            q = QSpinBox()
            q.setRange(1, max(1, l["stock"]))
            q.setValue(l["qty"])
            q.valueChanged.connect(lambda v, l=l: self._set(l, "qty", v))
            self.table.setCellWidget(r, 1, q)
            p = spin_money()
            p.setValue(l["unit_price"])
            p.valueChanged.connect(lambda v, l=l: self._set(l, "unit_price", v))
            self.table.setCellWidget(r, 2, p)
            it = QTableWidgetItem(money(l["qty"] * l["unit_price"]))
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 3, it)
            self.table.setCellWidget(r, 4, button("✕", lambda _=False, l=l: self._rm(l), "flat"))
        self._totals()

    def _set(self, l, k, v):
        l[k] = v
        it = self.table.item(self.lines.index(l), 3)
        if it:
            it.setText(money(l["qty"] * l["unit_price"]))
        self._totals()

    def _rm(self, l):
        self.lines.remove(l)
        self._render()

    def _totals(self):
        items = sum(l["qty"] * l["unit_price"] for l in self.lines)
        self.total_lbl.setText(f"Total : {money(items + self.shipping.value())}  "
                               f"<span style='font-size:10pt;color:gray'>(articles {money(items)} + port "
                               f"{money(self.shipping.value())})</span>")

    def _save(self):
        if not self.lines:
            warn(self, "Commande vide", "Ajoutez au moins un article.")
            return
        if not self.cust_name.text().strip():
            warn(self, "Destinataire manquant", "Indiquez le nom du destinataire.")
            return
        c = self.customer.customer()
        header = dict(channel=self.channel.currentText(), external_ref=self.ext_ref.text().strip(),
                      customer_id=c["id"] if c else None, customer_name=self.cust_name.text().strip(),
                      address=self.address.toPlainText().strip(), shipping=self.shipping.value(),
                      notes=self.notes.toPlainText().strip())
        self.saved_id = self.ctx.svc.create_order(header, self.lines)
        self.accept()


class OrdersPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = page_layout(self)
        header = PageHeader("Commandes en ligne", "Le stock est réservé dès la création et restitué en cas d'annulation")
        header.add(button("⇧ Exporter le catalogue en ligne", self._export_catalog,
                          tip="CSV des articles publiés en ligne et en stock (pour votre site / Cardmarket)"))
        header.add(button("+ Nouvelle commande", self._new, "primary"))
        lay.addWidget(header)

        f = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("🔍  N° de commande, référence, client, suivi…")
        self.search.textChanged.connect(self.refresh)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Commandes en cours", "Toutes"] + ORDER_STATUSES)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.channel_filter = QComboBox()
        self.channel_filter.addItems(["Tous les canaux"] + CHANNELS)
        self.channel_filter.currentIndexChanged.connect(self.refresh)
        f.addWidget(self.search, 1)
        f.addWidget(self.status_filter)
        f.addWidget(self.channel_filter)
        lay.addLayout(f)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.table = DataTable([
            ("number", "N°", "text"), ("date", "Date", "date"), ("channel", "Canal", "text"),
            ("external_ref", "Réf. externe", "text"), ("customer_name", "Client", "text"),
            ("nb", "Articles", "int"), ("total", "Total", "money"), ("status", "Statut", "status"),
            ("tracking", "Suivi", "text"),
        ], stretch="customer_name")
        self.table.selection_changed_record.connect(self._detail)
        self.table.record_activated.connect(lambda _r: self._advance())
        body.addWidget(self.table, 3)

        side = Card()
        side.setFixedWidth(360)
        self.d_title = label("Sélectionnez une commande", "H2")
        self.d_info = label("", "Muted", wrap=True)
        side.lay.addWidget(self.d_title)
        side.lay.addWidget(self.d_info)
        self.items = DataTable([("name", "Article", "text"), ("qty", "Qté", "int"), ("location", "Empl.", "text")],
                               stretch="name")
        side.lay.addWidget(self.items, 1)
        self.next_btn = button("→ Étape suivante", self._advance, "primary")
        side.lay.addWidget(self.next_btn)
        row = QHBoxLayout()
        row.addWidget(button("🖨 Bon de préparation", self._picking))
        row.addWidget(button("🚚 N° de suivi", self._tracking))
        side.lay.addLayout(row)
        row2 = QHBoxLayout()
        self.status_combo = combo(ORDER_STATUSES)
        row2.addWidget(self.status_combo, 1)
        row2.addWidget(button("Appliquer", self._apply_status))
        side.lay.addLayout(row2)
        body.addWidget(side)
        lay.addLayout(body, 1)
        self.footer = label("", "Muted")
        lay.addWidget(self.footer)

    def refresh(self, *_):
        where, params = ["1=1"], []
        i = self.status_filter.currentIndex()
        if i == 0:
            where.append("status IN ('À préparer', 'Préparée', 'Expédiée')")
        elif i >= 2:
            where.append("status = ?")
            params.append(self.status_filter.currentText())
        if self.channel_filter.currentIndex() > 0:
            where.append("channel = ?")
            params.append(self.channel_filter.currentText())
        t = self.search.text().strip()
        if t:
            where.append("(number LIKE ? OR external_ref LIKE ? OR customer_name LIKE ? OR tracking LIKE ?)")
            params += [f"%{t}%"] * 4
        rows = self.ctx.db.q(f"""SELECT o.*, (SELECT COALESCE(SUM(qty),0) FROM order_items WHERE order_id = o.id) nb
            FROM orders o WHERE {' AND '.join(where)} ORDER BY
            CASE status WHEN 'À préparer' THEN 0 WHEN 'Préparée' THEN 1 WHEN 'Expédiée' THEN 2 ELSE 3 END, date DESC""",
                             params)
        self.table.set_rows(rows)
        counts = {r["status"]: r["n"] for r in self.ctx.db.q("SELECT status, COUNT(*) n FROM orders GROUP BY status")}
        self.footer.setText(" · ".join(f"{s} : {counts.get(s, 0)}" for s in ORDER_STATUSES))
        self._detail(self.table.selected())

    def _detail(self, o):
        if not o:
            self.d_title.setText("Sélectionnez une commande")
            self.d_info.setText("")
            self.items.set_rows([])
            self.next_btn.setEnabled(False)
            return
        self.d_title.setText(f"{o['number']} · {o['status']}")
        self.d_info.setText(
            f"{o['channel']}" + (f" · réf. {o['external_ref']}" if o["external_ref"] else "") +
            f"<br><b>{o['customer_name']}</b><br>{(o['address'] or '').replace(chr(10), '<br>')}"
            f"<br>Total {money(o['total'])} (port {money(o['shipping'])})"
            + (f"<br>Suivi : {o['tracking']}" if o["tracking"] else "")
            + (f"<br><i>{o['notes']}</i>" if o["notes"] else ""))
        self.items.set_rows(self.ctx.db.q("""SELECT oi.name, oi.qty, p.location FROM order_items oi
            LEFT JOIN products p ON p.id = oi.product_id WHERE oi.order_id = ?""", (o["id"],)))
        nxt = NEXT_STATUS.get(o["status"])
        self.next_btn.setEnabled(bool(nxt))
        self.next_btn.setText(f"→ Marquer « {nxt} »" if nxt else "Commande terminée")
        self.status_combo.setCurrentText(o["status"])

    def _new(self):
        dlg = OrderDialog(self.ctx, self)
        if dlg.exec():
            self.status_filter.setCurrentIndex(0)
            self.refresh()
            self.table.select_id(dlg.saved_id)

    def _advance(self):
        o = self.table.selected()
        if not o or o["status"] not in NEXT_STATUS:
            return
        nxt = NEXT_STATUS[o["status"]]
        tracking = None
        if nxt == "Expédiée" and not o["tracking"]:
            dlg = TextInputDialog("Expédition", "Numéro de suivi (facultatif) :", parent=self)
            if not dlg.exec():
                return
            tracking = dlg.value()
        self.ctx.svc.set_order_status(o["id"], nxt, tracking)
        self.refresh()
        self.table.select_id(o["id"])

    def _apply_status(self):
        o = self.table.selected()
        st = self.status_combo.currentText()
        if not o or st == o["status"]:
            return
        if st == "Annulée" and not ask(self, "Annuler la commande",
                                       f"Annuler {o['number']} ? Les articles seront remis en stock."):
            return
        self.ctx.svc.set_order_status(o["id"], st)
        self.refresh()
        self.table.select_id(o["id"])

    def _tracking(self):
        o = self.table.selected()
        if not o:
            return
        dlg = TextInputDialog("Numéro de suivi", "Numéro de suivi du colis :", o["tracking"] or "", self)
        if dlg.exec():
            self.ctx.db.update("orders", o["id"], {"tracking": dlg.value()})
            self.refresh()
            self.table.select_id(o["id"])

    def _picking(self):
        o = self.table.selected()
        if o:
            DocumentDialog(f"Préparation {o['number']}", picking_list(self.ctx.db, o["id"]), self).exec()

    def _export_catalog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le catalogue en ligne", "catalogue_en_ligne.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        rows = self.ctx.db.q("""SELECT sku, barcode, name, game, category, set_name, set_code, number, rarity, language,
            condition, finish, quantity, price, image_url FROM products WHERE online = 1 AND quantity > 0 ORDER BY game, name""")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            if rows:
                w.writerow(rows[0].keys())
            for r in rows:
                w.writerow([str(v).replace(".", ",") if isinstance(v, float) else v for v in r.values()])
        info(self, "Export terminé", f"{len(rows)} article(s) exporté(s) vers :\n{path}")
