"""Fournisseurs, réassort conseillé et commandes fournisseurs (bons de commande + réception)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLineEdit,
    QPlainTextEdit, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..db import now
from ..dialogs import DocumentDialog, ProductPickerDialog, spin_money
from ..documents import purchase_order
from ..widgets import Card, DataTable, PageHeader, ask, button, info, label, money, page_layout, warn


# ====================================================================== fournisseur
class SupplierDialog(QDialog):
    def __init__(self, ctx, supplier: dict | None = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.supplier = supplier
        self.saved_id = None
        self.setWindowTitle("Fournisseur")
        self.resize(460, 440)
        s = supplier or {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.f = {k: QLineEdit(str(s.get(k, "") or "")) for k in ("name", "contact", "email", "phone", "website",
                                                                  "account_ref")}
        self.min_order = spin_money()
        self.min_order.setValue(float(s.get("min_order") or 0))
        self.notes = QPlainTextEdit(s.get("notes", "") or "")
        self.notes.setFixedHeight(70)
        form.addRow("Nom *", self.f["name"])
        form.addRow("Contact", self.f["contact"])
        form.addRow("E-mail", self.f["email"])
        form.addRow("Téléphone", self.f["phone"])
        form.addRow("Site / portail pro", self.f["website"])
        form.addRow("N° de compte client", self.f["account_ref"])
        form.addRow("Franco / minimum de commande", self.min_order)
        form.addRow("Notes", self.notes)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        data = {k: w.text().strip() for k, w in self.f.items()}
        if not data["name"]:
            warn(self, "Champ manquant", "Le nom du fournisseur est obligatoire.")
            return
        data.update(min_order=self.min_order.value(), notes=self.notes.toPlainText().strip())
        if self.supplier:
            self.ctx.db.update("suppliers", self.supplier["id"], data)
            self.saved_id = self.supplier["id"]
        else:
            data["created_at"] = now()
            self.saved_id = self.ctx.db.insert("suppliers", data)
        self.accept()


def supplier_combo(ctx, current=None, none_label="— Sans fournisseur —") -> QComboBox:
    c = QComboBox()
    c.addItem(none_label, None)
    for s in ctx.db.q("SELECT id, name FROM suppliers ORDER BY name"):
        c.addItem(s["name"], s["id"])
    if current:
        c.setCurrentIndex(max(0, c.findData(current)))
    return c


# ====================================================================== bon de commande
class PurchaseOrderDialog(QDialog):
    def __init__(self, ctx, po: dict | None = None, parent=None, lines: list[dict] | None = None, supplier_id=None):
        super().__init__(parent)
        self.ctx = ctx
        self.po = po
        self.saved_id = None
        self.setWindowTitle(f"Commande fournisseur {po['number']}" if po else "Nouvelle commande fournisseur")
        self.resize(940, 620)
        if po:
            lines = ctx.db.q("SELECT * FROM purchase_items WHERE po_id = ?", (po["id"],))
        self.lines = [dict(l) for l in (lines or [])]
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(label("Fournisseur"))
        self.supplier = supplier_combo(ctx, po["supplier_id"] if po else supplier_id)
        self.supplier.currentIndexChanged.connect(self._totals)
        top.addWidget(self.supplier, 1)
        self.scan = QLineEdit()
        self.scan.setPlaceholderText("📷  Scanner un article pour l'ajouter…")
        self.scan.returnPressed.connect(self._scan)
        top.addWidget(self.scan, 1)
        top.addWidget(button("+ Article du stock", self._add, "primary"))
        top.addWidget(button("+ Articles sous le minimum", self._add_low,
                             tip="Ajoute les articles de ce fournisseur sous leur stock minimum"))
        lay.addLayout(top)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Article", "Qté", "Prix d'achat HT", "Total HT", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, w in ((1, 80), (2, 130), (3, 110), (4, 36)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, w)
        lay.addWidget(self.table, 1)
        self.notes = QPlainTextEdit(po["notes"] if po else "")
        self.notes.setPlaceholderText("Notes (conditions, référence de devis…)")
        self.notes.setFixedHeight(54)
        lay.addWidget(self.notes)
        bottom = QHBoxLayout()
        self.total_lbl = label("", "H2")
        bottom.addWidget(self.total_lbl, 1)
        bottom.addWidget(button("Annuler", self.reject))
        bottom.addWidget(button("Enregistrer le brouillon", lambda: self._save("Brouillon")))
        bottom.addWidget(button("✔ Enregistrer et marquer « commandée »", lambda: self._save("Commandée"), "primary"))
        lay.addLayout(bottom)
        self._render()

    def _add_line(self, p, qty=1):
        for l in self.lines:
            if l.get("product_id") == p["id"]:
                l["qty"] += qty
                break
        else:
            name = p["name"] + (f" — {p['variant']}" if p.get("variant") else "") + \
                (f" — {p['set_name']}" if p.get("set_name") else "")
            self.lines.append(dict(product_id=p["id"], name=name, qty=qty, unit_cost=p["cost"] or 0.0))
            if self.supplier.currentData() is None and p.get("supplier_id"):
                self.supplier.setCurrentIndex(max(0, self.supplier.findData(p["supplier_id"])))
        self._render()

    def _add(self):
        dlg = ProductPickerDialog(self.ctx, self, "Ajouter un article à la commande")
        if dlg.exec() and dlg.result_product:
            self._add_line(dlg.result_product)

    def _scan(self):
        code = self.scan.text()
        self.scan.clear()
        p = self.ctx.svc.find_by_code(code)
        if p:
            self._add_line(p)
        else:
            warn(self, "Code inconnu", f"Aucun article pour le code « {code} ».\n"
                                       "Associez-le d'abord depuis l'inventaire.")

    def _add_low(self):
        sid = self.supplier.currentData()
        rows = [r for r in self.ctx.svc.reorder_suggestions() if r["supplier_id"] == sid]
        if not rows:
            info(self, "Réassort", "Aucun article de ce fournisseur n'est sous son stock minimum.")
            return
        for r in rows:
            self._add_line(r, r["suggested"])

    def _render(self):
        self.table.setRowCount(len(self.lines))
        for r, l in enumerate(self.lines):
            self.table.setItem(r, 0, QTableWidgetItem(l["name"]))
            q = QSpinBox()
            q.setRange(1, 99999)
            q.setValue(int(l["qty"]))
            q.valueChanged.connect(lambda v, l=l: self._set(l, "qty", v))
            self.table.setCellWidget(r, 1, q)
            c = spin_money()
            c.setValue(float(l["unit_cost"]))
            c.valueChanged.connect(lambda v, l=l: self._set(l, "unit_cost", v))
            self.table.setCellWidget(r, 2, c)
            it = QTableWidgetItem(money(l["qty"] * l["unit_cost"]))
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(r, 3, it)
            self.table.setCellWidget(r, 4, button("✕", lambda _=False, l=l: self._rm(l), "flat"))
        self._totals()

    def _set(self, l, k, v):
        l[k] = v
        it = self.table.item(self.lines.index(l), 3)
        if it:
            it.setText(money(l["qty"] * l["unit_cost"]))
        self._totals()

    def _rm(self, l):
        self.lines.remove(l)
        self._render()

    def _totals(self, *_):
        total = sum(l["qty"] * l["unit_cost"] for l in self.lines)
        n = sum(l["qty"] for l in self.lines)
        txt = f"{n} unité(s) · total {money(total)} HT"
        s = self.ctx.db.one("SELECT min_order FROM suppliers WHERE id = ?", (self.supplier.currentData(),))
        if s and s["min_order"]:
            left = s["min_order"] - total
            txt += (f"  <span style='color:#f59e0b;font-size:10pt'>· encore {money(left)} pour le franco</span>"
                    if left > 0 else "  <span style='color:#22c55e;font-size:10pt'>· franco atteint ✔</span>")
        self.total_lbl.setText(txt)

    def _save(self, status):
        if not self.lines:
            warn(self, "Commande vide", "Ajoutez au moins un article.")
            return
        self.saved_id = self.ctx.svc.save_po(self.supplier.currentData(), self.lines, self.notes.toPlainText().strip(),
                                             self.po["id"] if self.po else None, status)
        self.accept()


class ReceiveDialog(QDialog):
    """Réception d'une commande fournisseur : quantités reçues (saisie ou scan article par article)."""

    def __init__(self, ctx, po: dict, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.po = po
        self.setWindowTitle(f"Réception — {po['number']}")
        self.resize(860, 560)
        self.items = ctx.db.q("SELECT * FROM purchase_items WHERE po_id = ?", (po["id"],))
        lay = QVBoxLayout(self)
        lay.addWidget(label("Vérifiez les quantités reçues. Vous pouvez aussi remettre à zéro puis scanner chaque "
                            "article du colis.", "Muted", wrap=True))
        row = QHBoxLayout()
        self.scan = QLineEdit()
        self.scan.setObjectName("Search")
        self.scan.setPlaceholderText("📷  Scanner un article reçu (+1)…")
        self.scan.returnPressed.connect(self._scan)
        row.addWidget(self.scan, 1)
        row.addWidget(button("Tout reçu", lambda: self._fill(True)))
        row.addWidget(button("Remettre à zéro", lambda: self._fill(False)))
        lay.addLayout(row)
        self.table = QTableWidget(len(self.items), 4)
        self.table.setHorizontalHeaderLabels(["Article", "Commandé", "Déjà reçu", "Reçu maintenant"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.spins = []
        for r, it in enumerate(self.items):
            self.table.setItem(r, 0, QTableWidgetItem(it["name"]))
            self.table.setItem(r, 1, QTableWidgetItem(str(it["qty"])))
            self.table.setItem(r, 2, QTableWidgetItem(str(it["received_qty"])))
            s = QSpinBox()
            s.setRange(0, 99999)
            self.table.setCellWidget(r, 3, s)
            self.spins.append(s)
        lay.addWidget(self.table, 1)
        self.status = label("", wrap=True)
        lay.addWidget(self.status)
        b = QHBoxLayout()
        b.addStretch(1)
        b.addWidget(button("Annuler", self.reject))
        b.addWidget(button("✔ Valider la réception (entrée en stock)", self._ok, "success"))
        lay.addLayout(b)
        self._fill(True)
        self.scan.setFocus()

    def _fill(self, full: bool):
        for it, s in zip(self.items, self.spins):
            s.setValue(max(0, it["qty"] - it["received_qty"]) if full else 0)
        self.scan.setFocus()

    def _scan(self):
        code = self.scan.text()
        self.scan.clear()
        p = self.ctx.svc.find_by_code(code)
        for r, (it, s) in enumerate(zip(self.items, self.spins)):
            if p and it["product_id"] == p["id"]:
                s.setValue(s.value() + 1)
                self.table.selectRow(r)
                self.status.setText(f"<span style='color:#22c55e'>✔ {it['name']} : {s.value()} reçu(s)</span>")
                return
        self.status.setText(f"<span style='color:#ef4444'>✖ « {code} » ne fait pas partie de cette commande.</span>")

    def _ok(self):
        received = {it["id"]: s.value() for it, s in zip(self.items, self.spins) if s.value() > 0}
        if not received:
            warn(self, "Réception", "Aucune quantité reçue.")
            return
        self.units = self.ctx.svc.receive_po(self.po["id"], received)
        self.accept()


# ====================================================================== page
class SuppliersPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = page_layout(self)
        lay.addWidget(PageHeader("Fournisseurs & réassort",
                                 "Ne tombez plus jamais en rupture de sleeves ou de boosters : suggestions de commande, "
                                 "bons de commande et réception"))
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_reorder(), "🔁  Réassort conseillé")
        self.tabs.addTab(self._build_orders(), "🧾  Commandes fournisseurs")
        self.tabs.addTab(self._build_suppliers(), "🏭  Fournisseurs")
        self.tabs.currentChanged.connect(lambda _i: self.refresh())
        lay.addWidget(self.tabs, 1)

    # ---------------------------------------------------------------- réassort
    def _build_reorder(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        row.addWidget(label("Articles à ou sous leur stock minimum (hors quantités déjà en commande). Réglez le stock "
                            "minimum et la quantité de réassort dans la fiche de chaque article.", "Muted", wrap=True), 1)
        row.addWidget(button("🧾 Créer les bons de commande", self._create_pos, "primary",
                             tip="Un brouillon par fournisseur (sélection, ou tout si rien n'est sélectionné)"))
        lay.addLayout(row)
        self.reorder = DataTable([
            ("supplier_name", "Fournisseur", "text"), ("name", "Article", "text"), ("category", "Catégorie", "text"),
            ("variant", "Variante", "text"), ("quantity", "Stock", "qty"), ("min_stock", "Mini", "int"),
            ("pending", "En commande", "int"), ("suggested", "À commander", "int"), ("cost", "Achat HT", "money"),
            ("est", "Total HT", "money"),
        ], stretch="name")
        lay.addWidget(self.reorder, 1)
        self.reorder_footer = label("", "Muted")
        lay.addWidget(self.reorder_footer)
        return w

    def _create_pos(self):
        rows = self.reorder.selected_all() or self.reorder.rows()
        if not rows:
            info(self, "Réassort", "Rien à commander pour le moment 👍")
            return
        groups: dict = {}
        for r in rows:
            groups.setdefault(r["supplier_id"], []).append(r)
        for sid, items in groups.items():
            self.ctx.svc.save_po(sid, [dict(product_id=r["id"], name=r["name"] + (f" — {r['variant']}" if r["variant"]
                                                                                  else ""),
                                            qty=r["suggested"], unit_cost=r["cost"] or 0) for r in items])
        info(self, "Bons de commande créés", f"{len(groups)} brouillon(s) créé(s). Vérifiez-les dans l'onglet "
                                             "« Commandes fournisseurs » avant de les envoyer.")
        self.tabs.setCurrentIndex(1)

    # ---------------------------------------------------------------- commandes
    def _build_orders(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        self.po_filter = QComboBox()
        self.po_filter.addItems(["En cours", "Toutes", "Brouillon", "Commandée", "Reçue", "Annulée"])
        self.po_filter.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.po_filter)
        row.addStretch(1)
        row.addWidget(button("+ Nouvelle commande", self._new_po, "primary"))
        row.addWidget(button("Modifier", self._edit_po))
        row.addWidget(button("📨 Marquer commandée", self._mark_ordered))
        row.addWidget(button("📥 Réceptionner", self._receive, "success"))
        row.addWidget(button("🖨 Bon de commande", self._print_po))
        row.addWidget(button("Annuler la commande", self._cancel_po, "danger"))
        lay.addLayout(row)
        body = QHBoxLayout()
        self.pos_table = DataTable([
            ("number", "N°", "text"), ("date", "Date", "date"), ("supplier_name", "Fournisseur", "text"),
            ("nb", "Unités", "int"), ("received", "Reçues", "int"), ("total", "Total HT", "money"),
            ("status", "Statut", "status"), ("received_at", "Réception", "date"),
        ], stretch="supplier_name")
        self.pos_table.record_activated.connect(lambda _r: self._edit_po())
        self.pos_table.selection_changed_record.connect(self._po_items)
        body.addWidget(self.pos_table, 3)
        self.po_lines = DataTable([("name", "Article", "text"), ("qty", "Qté", "int"),
                                   ("received_qty", "Reçu", "int"), ("unit_cost", "P.U. HT", "money")], stretch="name")
        body.addWidget(self.po_lines, 2)
        lay.addLayout(body, 1)
        return w

    def _po(self):
        return self.pos_table.selected()

    def _po_items(self, po):
        self.po_lines.set_rows(self.ctx.db.q("SELECT * FROM purchase_items WHERE po_id = ?", (po["id"],)) if po else [])

    def _new_po(self):
        dlg = PurchaseOrderDialog(self.ctx, parent=self)
        if dlg.exec():
            self.refresh()
            self.pos_table.select_id(dlg.saved_id)

    def _edit_po(self):
        po = self._po()
        if not po:
            return
        if po["status"] not in ("Brouillon", "Commandée"):
            DocumentDialog(f"Commande {po['number']}", purchase_order(self.ctx.db, po["id"]), self).exec()
            return
        if po["status"] == "Commandée" and self.ctx.db.val(
                "SELECT COUNT(*) FROM purchase_items WHERE po_id = ? AND received_qty > 0", (po["id"],), 0):
            warn(self, "Modification impossible", "Cette commande a déjà été partiellement réceptionnée.")
            return
        dlg = PurchaseOrderDialog(self.ctx, po, self)
        if dlg.exec():
            self.refresh()

    def _mark_ordered(self):
        po = self._po()
        if po and po["status"] == "Brouillon":
            self.ctx.db.update("purchase_orders", po["id"], dict(status="Commandée", date=now()))
            self.refresh()
            self.pos_table.select_id(po["id"])

    def _receive(self):
        po = self._po()
        if not po:
            return
        if po["status"] not in ("Brouillon", "Commandée"):
            warn(self, "Réception", "Cette commande est déjà reçue ou annulée.")
            return
        dlg = ReceiveDialog(self.ctx, po, self)
        if dlg.exec():
            self.ctx.window.flash(f"{dlg.units} unité(s) entrée(s) en stock ({po['number']})")
            self.refresh()
            self.pos_table.select_id(po["id"])

    def _print_po(self):
        po = self._po()
        if po:
            DocumentDialog(f"Commande {po['number']}", purchase_order(self.ctx.db, po["id"]), self).exec()

    def _cancel_po(self):
        po = self._po()
        if po and po["status"] in ("Brouillon", "Commandée") and ask(
                self, "Annuler", f"Annuler la commande {po['number']} ? (les quantités déjà reçues restent en stock)"):
            self.ctx.db.update("purchase_orders", po["id"], dict(status="Annulée"))
            self.refresh()

    # ---------------------------------------------------------------- fournisseurs
    def _build_suppliers(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("+ Nouveau fournisseur", self._new_supplier, "primary"))
        row.addWidget(button("Modifier", self._edit_supplier))
        row.addWidget(button("Supprimer", self._delete_supplier, "danger"))
        lay.addLayout(row)
        self.sup_table = DataTable([
            ("name", "Fournisseur", "text"), ("contact", "Contact", "text"), ("email", "E-mail", "text"),
            ("phone", "Téléphone", "text"), ("account_ref", "N° client", "text"), ("min_order", "Franco", "money"),
            ("products", "Articles", "int"), ("open_pos", "Commandes en cours", "int"),
        ], stretch="name")
        self.sup_table.record_activated.connect(lambda _r: self._edit_supplier())
        lay.addWidget(self.sup_table, 1)
        return w

    def _new_supplier(self):
        if SupplierDialog(self.ctx, parent=self).exec():
            self.refresh()

    def _edit_supplier(self):
        s = self.sup_table.selected()
        if s and SupplierDialog(self.ctx, self.ctx.db.one("SELECT * FROM suppliers WHERE id = ?", (s["id"],)),
                                self).exec():
            self.refresh()

    def _delete_supplier(self):
        s = self.sup_table.selected()
        if s and ask(self, "Supprimer", f"Supprimer le fournisseur {s['name']} ?\n"
                                        "Les articles liés seront simplement détachés."):
            with self.ctx.db.tx():
                self.ctx.db.exec("UPDATE products SET supplier_id = NULL WHERE supplier_id = ?", (s["id"],))
                self.ctx.db.exec("DELETE FROM suppliers WHERE id = ?", (s["id"],))
            self.refresh()

    # ---------------------------------------------------------------- données
    def refresh(self, *_):
        i = self.tabs.currentIndex()
        if i == 0:
            rows = self.ctx.svc.reorder_suggestions()
            for r in rows:
                r["supplier_name"] = r["supplier_name"] or "— Sans fournisseur —"
                r["est"] = r["suggested"] * (r["cost"] or 0)
            self.reorder.set_rows(rows)
            self.reorder_footer.setText(f"{len(rows)} article(s) à commander · estimation "
                                        f"{money(sum(r['est'] for r in rows))} HT")
        elif i == 1:
            f = self.po_filter.currentText()
            where = {"En cours": "po.status IN ('Brouillon', 'Commandée')", "Toutes": "1=1"}.get(f, "po.status = ?")
            params = () if f in ("En cours", "Toutes") else (f,)
            self.pos_table.set_rows(self.ctx.db.q(f"""
                SELECT po.*, COALESCE(s.name, '—') supplier_name,
                  (SELECT COALESCE(SUM(qty),0) FROM purchase_items WHERE po_id = po.id) nb,
                  (SELECT COALESCE(SUM(received_qty),0) FROM purchase_items WHERE po_id = po.id) received
                FROM purchase_orders po LEFT JOIN suppliers s ON s.id = po.supplier_id
                WHERE {where} ORDER BY po.date DESC""", params))
            self._po_items(self._po())
        else:
            self.sup_table.set_rows(self.ctx.db.q("""
                SELECT s.*, (SELECT COUNT(*) FROM products WHERE supplier_id = s.id) products,
                  (SELECT COUNT(*) FROM purchase_orders WHERE supplier_id = s.id
                     AND status IN ('Brouillon', 'Commandée')) open_pos
                FROM suppliers s ORDER BY s.name"""))
