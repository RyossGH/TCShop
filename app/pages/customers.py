"""Clients : fiches, crédit boutique, fidélité, historique."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit, QTabWidget, QVBoxLayout, QWidget

from ..dialogs import CustomerDialog, spin_money, combo
from ..widgets import Card, DataTable, PageHeader, ask, button, info, label, money, page_layout


class CreditDialog(QDialog):
    def __init__(self, customer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crédit boutique")
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"<b>{customer['name']}</b> — solde actuel {money(customer['credit'])}"))
        form = QFormLayout()
        self.mode = combo(["Créditer (+)", "Débiter (−)"])
        self.amount = spin_money()
        form.addRow("Opération", self.mode)
        form.addRow("Montant", self.amount)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def delta(self) -> float:
        return self.amount.value() * (1 if self.mode.currentIndex() == 0 else -1)


class CustomersPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = page_layout(self)
        header = PageHeader("Clients", "Fidélité, crédit boutique et historique d'achats / rachats")
        header.add(button("+ Nouveau client", self._new, "primary"))
        lay.addWidget(header)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("🔍  Nom, e-mail, téléphone…")
        self.search.textChanged.connect(self.refresh)
        lay.addWidget(self.search)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.table = DataTable([
            ("name", "Nom", "text"), ("phone", "Téléphone", "text"), ("email", "E-mail", "text"),
            ("credit", "Crédit", "money"), ("points", "Points", "int"), ("spent", "Total achats", "money"),
            ("sold", "Total rachats", "money"), ("last", "Dernière visite", "date"),
        ], stretch="name")
        self.table.selection_changed_record.connect(self._detail)
        self.table.record_activated.connect(lambda _r: self._edit())
        body.addWidget(self.table, 3)

        side = Card()
        side.setMinimumWidth(420)
        self.d_title = label("Sélectionnez un client", "H2")
        self.d_info = label("", "Muted", wrap=True)
        side.lay.addWidget(self.d_title)
        side.lay.addWidget(self.d_info)
        row = QHBoxLayout()
        row.addWidget(button("Modifier", self._edit))
        row.addWidget(button("🎟️ Crédit ±", self._credit))
        row.addWidget(button("⭐ Points → crédit", self._convert))
        side.lay.addLayout(row)
        tabs = QTabWidget()
        self.h_sales = DataTable([("date", "Date", "date"), ("number", "Ticket", "text"), ("total", "Total", "money"),
                                  ("status", "Statut", "status")], stretch="number")
        self.h_buys = DataTable([("date", "Date", "date"), ("number", "Rachat", "text"), ("payout", "Règlement", "text"),
                                 ("total", "Versé", "money")], stretch="number")
        self.h_orders = DataTable([("date", "Date", "date"), ("number", "Commande", "text"), ("total", "Total", "money"),
                                   ("status", "Statut", "status")], stretch="number")
        tabs.addTab(self.h_sales, "Achats")
        tabs.addTab(self.h_buys, "Rachats")
        tabs.addTab(self.h_orders, "Commandes")
        side.lay.addWidget(tabs, 1)
        side.lay.addWidget(button("Supprimer le client", self._delete, "danger"))
        body.addWidget(side, 2)
        lay.addLayout(body, 1)

    def refresh(self, *_):
        t = f"%{self.search.text().strip()}%"
        rows = self.ctx.db.q("""
            SELECT c.*,
              (SELECT COALESCE(SUM(total),0) FROM sales WHERE customer_id = c.id AND status = 'Validée') +
              (SELECT COALESCE(SUM(total),0) FROM orders WHERE customer_id = c.id AND status != 'Annulée') spent,
              (SELECT COALESCE(SUM(total),0) FROM buys WHERE customer_id = c.id) sold,
              (SELECT MAX(d) FROM (SELECT MAX(date) d FROM sales WHERE customer_id = c.id
                                   UNION ALL SELECT MAX(date) FROM buys WHERE customer_id = c.id)) last
            FROM customers c WHERE c.name LIKE ? OR c.email LIKE ? OR c.phone LIKE ? ORDER BY c.name""", (t, t, t))
        self.table.set_rows(rows)
        self._detail(self.table.selected())

    def _detail(self, c):
        if not c:
            self.d_title.setText("Sélectionnez un client")
            self.d_info.setText("")
            for t in (self.h_sales, self.h_buys, self.h_orders):
                t.set_rows([])
            return
        c = self.ctx.db.one("SELECT * FROM customers WHERE id = ?", (c["id"],))
        per = int(self.ctx.db.setting_float("points_for_euro", 20)) or 1
        self.d_title.setText(c["name"])
        self.d_info.setText(
            f"📞 {c['phone'] or '—'} · ✉ {c['email'] or '—'}<br>{(c['address'] or '').replace(chr(10), ', ')}"
            f"<br>🪪 {c['id_type'] or 'Pièce non renseignée'} {c['id_number'] or ''}"
            f"<br><br><span style='font-size:13pt'>Crédit <b>{money(c['credit'])}</b> · Points <b>{c['points']}</b></span>"
            f" <span>(≈ {money(c['points'] // per)} convertibles)</span>"
            + (f"<br><i>{c['notes']}</i>" if c["notes"] else ""))
        self.h_sales.set_rows(self.ctx.db.q("SELECT * FROM sales WHERE customer_id = ? ORDER BY date DESC", (c["id"],)))
        self.h_buys.set_rows(self.ctx.db.q("SELECT * FROM buys WHERE customer_id = ? ORDER BY date DESC", (c["id"],)))
        self.h_orders.set_rows(self.ctx.db.q("SELECT * FROM orders WHERE customer_id = ? ORDER BY date DESC", (c["id"],)))

    def _new(self):
        dlg = CustomerDialog(self.ctx, parent=self)
        if dlg.exec():
            self.refresh()
            self.table.select_id(dlg.saved_id)

    def _edit(self):
        c = self.table.selected()
        if c:
            dlg = CustomerDialog(self.ctx, self.ctx.db.one("SELECT * FROM customers WHERE id = ?", (c["id"],)), self)
            if dlg.exec():
                self.refresh()

    def _credit(self):
        c = self.table.selected()
        if not c:
            return
        dlg = CreditDialog(c, self)
        if dlg.exec() and dlg.delta():
            self.ctx.svc.adjust_credit(c["id"], dlg.delta())
            self.refresh()

    def _convert(self):
        c = self.table.selected()
        if not c:
            return
        amount = self.ctx.svc.convert_points(c["id"])
        if amount:
            info(self, "Points convertis", f"{money(amount)} ajoutés au crédit boutique de {c['name']}.")
            self.refresh()
        else:
            info(self, "Pas assez de points", "Le client n'a pas encore assez de points pour une conversion.")

    def _delete(self):
        c = self.table.selected()
        if not c:
            return
        if c["credit"] and abs(c["credit"]) > 0.001:
            info(self, "Impossible", "Ce client a encore du crédit boutique. Soldez-le avant de le supprimer.")
            return
        if ask(self, "Supprimer", f"Supprimer le client {c['name']} ? Son historique reste dans les ventes."):
            self.ctx.db.exec("DELETE FROM customers WHERE id = ?", (c["id"],))
            self.refresh()
