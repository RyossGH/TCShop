"""Rachats (achat de cartes aux clients) + registre des rachats / livre de police."""
from __future__ import annotations

import csv

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDateEdit, QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLineEdit, QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..constants import CONDITION_FACTORS, CONDITIONS
from ..dialogs import (
    CardSearchDialog, CustomerDialog, CustomerPicker, DocumentDialog, ProductPickerDialog, TextInputDialog, spin_money,
)
from ..documents import buy_receipt
from ..widgets import Card, DataTable, PageHeader, ask, button, info, label, money, page_layout, warn


class BuylistPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.lines: list[dict] = []
        lay = page_layout(self)
        lay.addWidget(PageHeader("Rachats", "Rachetez des cartes à vos clients : offre calculée selon l'état et le mode de paiement"))
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_new(), "🤝  Nouveau rachat")
        self.tabs.addTab(self._build_history(), "📒  Registre des rachats")
        self.tabs.currentChanged.connect(lambda i: self.refresh_history() if i == 1 else None)
        lay.addWidget(self.tabs, 1)

    # ---------------------------------------------------------------- UI
    def _build_new(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        top = QHBoxLayout()
        top.setSpacing(12)

        c1 = Card()
        c1.lay.addWidget(label("Vendeur (client)", "Muted"))
        self.customer = CustomerPicker(self.ctx, allow_none_label="— Choisir le vendeur —")
        self.customer.changed.connect(self._customer_changed)
        c1.lay.addWidget(self.customer)
        self.id_warning = label("", wrap=True)
        c1.lay.addWidget(self.id_warning)
        top.addWidget(c1, 2)

        c2 = Card()
        c2.lay.addWidget(label("Mode de règlement", "Muted"))
        row = QHBoxLayout()
        self.payout_group = QButtonGroup(self)
        self.rb_cash = QRadioButton()
        self.rb_credit = QRadioButton()
        self.rb_transfer = QRadioButton()
        self.rb_wero = QRadioButton()
        for i, rb in enumerate((self.rb_cash, self.rb_credit, self.rb_transfer, self.rb_wero)):
            self.payout_group.addButton(rb, i)
            row.addWidget(rb)
        self.rb_cash.setChecked(True)
        self.payout_group.idToggled.connect(lambda _i, checked: checked and self._apply_rate_all())
        c2.lay.addLayout(row)
        c2.lay.addWidget(label("Le taux s'applique au prix marché, puis un coefficient selon l'état "
                               "(NM 100 %, EX 85 %, GD 70 %, LP 60 %, PL 45 %, PO 30 %).", "Muted", wrap=True))
        top.addWidget(c2, 3)
        lay.addLayout(top)

        actions = QHBoxLayout()
        actions.addWidget(button("🔎 Carte depuis la base en ligne", self._add_from_db, "primary"))
        actions.addWidget(button("🗃️ Article déjà en stock", self._add_from_stock))
        actions.addWidget(button("✎ Ligne manuelle", self._add_manual))
        actions.addStretch(1)
        actions.addWidget(button("Vider", self._clear, "danger"))
        lay.addLayout(actions)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Article", "Extension", "État", "Qté", "Prix marché", "Taux %",
                                              "Offre unit.", "Total", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, wdt in ((1, 170), (2, 80), (3, 70), (4, 110), (5, 80), (6, 110), (7, 100), (8, 36)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, wdt)
        lay.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.summary = label("", "Muted")
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(label("À verser :", "H2"))
        self.total_lbl = label(money(0), "Total")
        bottom.addWidget(self.total_lbl)
        self.validate_btn = button("✔ Valider le rachat", self._validate, "success")
        self.validate_btn.setProperty("kind", "big")
        self.validate_btn.setStyleSheet("background: #22c55e; color: white; border: none;")
        bottom.addWidget(self.validate_btn)
        lay.addLayout(bottom)
        return w

    def _build_history(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        f = QHBoxLayout()
        self.h_from = QDateEdit(QDate.currentDate().addMonths(-3))
        self.h_to = QDateEdit(QDate.currentDate())
        for d in (self.h_from, self.h_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
            d.dateChanged.connect(self.refresh_history)
        self.h_search = QLineEdit()
        self.h_search.setPlaceholderText("N° ou vendeur…")
        self.h_search.textChanged.connect(self.refresh_history)
        f.addWidget(label("Du"))
        f.addWidget(self.h_from)
        f.addWidget(label("au"))
        f.addWidget(self.h_to)
        f.addWidget(self.h_search, 1)
        f.addWidget(button("Voir le bon", self._show_receipt))
        f.addWidget(button("⇧ Exporter le livre de police", self._export_police))
        lay.addLayout(f)
        body = QHBoxLayout()
        self.history = DataTable([
            ("number", "N°", "text"), ("date", "Date", "date"), ("customer_name", "Vendeur", "text"),
            ("id_type", "Pièce", "text"), ("id_number", "N° pièce", "text"), ("payout", "Règlement", "text"),
            ("market_total", "Valeur marché", "money"), ("total", "Versé", "money"),
        ], stretch="customer_name")
        self.history.record_activated.connect(lambda _r: self._show_receipt())
        self.history.selection_changed_record.connect(self._show_items)
        body.addWidget(self.history, 3)
        self.h_items = DataTable([("name", "Article", "text"), ("condition", "État", "text"), ("qty", "Qté", "int"),
                                  ("offer_price", "Prix", "money")], stretch="name")
        body.addWidget(self.h_items, 2)
        lay.addLayout(body, 1)
        self.h_footer = label("", "Muted")
        lay.addWidget(self.h_footer)
        return w

    # ---------------------------------------------------------------- données
    def refresh(self):
        cash = self.ctx.db.setting_float("buy_rate_cash", 50)
        credit = self.ctx.db.setting_float("buy_rate_credit", 65)
        self.rb_cash.setText(f"💶 Espèces ({cash:g} %)")
        self.rb_credit.setText(f"🎟️ Crédit boutique ({credit:g} %)")
        self.rb_transfer.setText(f"🏦 Virement ({cash:g} %)")
        self.rb_wero.setText(f"📱 Wero ({cash:g} %)")
        self.customer.reload()
        if self.tabs.currentIndex() == 1:
            self.refresh_history()
        self._render()

    def _rate(self) -> float:
        if self.rb_credit.isChecked():
            return self.ctx.db.setting_float("buy_rate_credit", 65)
        return self.ctx.db.setting_float("buy_rate_cash", 50)

    def _payout(self) -> str:
        return ["Espèces", "Crédit boutique", "Virement", "Wero"][max(0, self.payout_group.checkedId())]

    def _customer_changed(self, c):
        if not c:
            self.id_warning.setText("")
        elif not c["id_number"]:
            self.id_warning.setText("<span style='color:#f59e0b'>⚠ Pièce d'identité non renseignée "
                                    "(obligatoire pour le registre).</span>")
        else:
            self.id_warning.setText(f"<span style='color:#22c55e'>✔ {c['id_type']} n° {c['id_number']}</span>")

    # ---------------------------------------------------------------- lignes
    def _new_line(self, **kw):
        line = dict(product_id=None, product=None, name="", game="", set_name="", condition="NM", qty=1,
                    market_price=0.0, rate=self._rate(), offer_price=0.0)
        line.update(kw)
        line["offer_price"] = self._offer(line)
        self.lines.append(line)
        self._render()

    @staticmethod
    def _offer(line) -> float:
        return round(line["market_price"] * line["rate"] / 100 * CONDITION_FACTORS.get(line["condition"], 1.0), 2)

    def _add_from_db(self):
        dlg = CardSearchDialog(self)
        if dlg.exec() and dlg.result_card:
            c = dlg.result_card
            coef = self.ctx.db.setting_float("price_coef", 1.0)
            existing = self.ctx.db.one(
                "SELECT * FROM products WHERE external_id = ? AND external_id != '' AND condition = 'NM' "
                "AND language = ? LIMIT 1", (c.get("external_id", ""), c.get("language", "EN")))
            product = {k: c.get(k, "") for k in ("name", "game", "set_name", "set_code", "number", "rarity",
                                                 "image_url", "external_id", "language")}
            product.update(category="Carte", condition="NM", market_price=c.get("market_price", 0),
                           price=round((c.get("market_price") or 0) * coef, 2))
            self._new_line(product_id=existing["id"] if existing else None, product=product, name=c["name"],
                           game=c["game"], set_name=c["set_name"], market_price=c.get("market_price") or 0.0)

    def _add_from_stock(self):
        dlg = ProductPickerDialog(self.ctx, self, "Racheter un article déjà référencé")
        if dlg.exec() and dlg.result_product:
            self._add_product_line(dlg.result_product)

    def _add_product_line(self, p):
        for l in self.lines:  # même article scanné plusieurs fois : on incrémente la quantité
            if l["product_id"] == p["id"]:
                self._edit(l, "qty", l["qty"] + 1)
                self._render()
                return
        self._new_line(product_id=p["id"], name=p["name"], game=p["game"], set_name=p["set_name"],
                       condition=p["condition"] if p["condition"] in CONDITIONS else "NM",
                       market_price=p["market_price"] or p["price"])

    def on_scan(self, code: str) -> bool:
        """Scan d'un produit (ex. booster scellé) pendant un rachat : ajout d'une ligne."""
        self.tabs.setCurrentIndex(0)
        p = self.ctx.svc.find_by_code(code)
        if not p:
            from ..scan import resolve_unknown
            p = resolve_unknown(self.ctx, code, self)
        if p:
            self._add_product_line(p)
        return True

    def _add_manual(self):
        dlg = TextInputDialog("Ligne manuelle", "Désignation de l'article :", parent=self)
        if dlg.exec() and dlg.value():
            self._new_line(name=dlg.value(), product=dict(name=dlg.value(), category="Carte"))

    def _clear(self):
        if self.lines and ask(self, "Vider", "Supprimer toutes les lignes du rachat en cours ?"):
            self.lines.clear()
            self._render()

    def _apply_rate_all(self):
        r = self._rate()
        for l in self.lines:
            l["rate"] = r
            l["offer_price"] = self._offer(l)
        self._render()

    def _render(self):
        t = self.table
        t.setRowCount(len(self.lines))
        for r, l in enumerate(self.lines):
            name = QTableWidgetItem(l["name"] + ("" if l["product_id"] else "  (nouveau)"))
            name.setToolTip("Article existant : le stock sera incrémenté" if l["product_id"]
                            else "Nouvel article : une fiche sera créée à la validation")
            t.setItem(r, 0, name)
            t.setItem(r, 1, QTableWidgetItem(l["set_name"]))
            cond = QComboBox()
            cond.addItems(CONDITIONS)
            cond.setCurrentText(l["condition"])
            cond.currentTextChanged.connect(lambda v, l=l: self._edit(l, "condition", v))
            t.setCellWidget(r, 2, cond)
            q = QSpinBox()
            q.setRange(1, 9999)
            q.setValue(l["qty"])
            q.valueChanged.connect(lambda v, l=l: self._edit(l, "qty", v))
            t.setCellWidget(r, 3, q)
            m = spin_money()
            m.setValue(l["market_price"])
            m.valueChanged.connect(lambda v, l=l: self._edit(l, "market_price", v))
            t.setCellWidget(r, 4, m)
            rate = QDoubleSpinBox()
            rate.setRange(0, 200)
            rate.setDecimals(0)
            rate.setSuffix(" %")
            rate.setValue(l["rate"])
            rate.valueChanged.connect(lambda v, l=l: self._edit(l, "rate", v))
            t.setCellWidget(r, 5, rate)
            o = spin_money()
            o.setValue(l["offer_price"])
            o.valueChanged.connect(lambda v, l=l: self._edit(l, "offer_price", v))
            t.setCellWidget(r, 6, o)
            tot = QTableWidgetItem(money(l["qty"] * l["offer_price"]))
            tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(r, 7, tot)
            t.setCellWidget(r, 8, button("✕", lambda _=False, l=l: self._remove(l), "flat"))
        self._totals()

    def _edit(self, line, key, value):
        line[key] = value
        r = self.lines.index(line)
        if key in ("condition", "market_price", "rate"):
            line["offer_price"] = self._offer(line)
            w = self.table.cellWidget(r, 6)
            w.blockSignals(True)
            w.setValue(line["offer_price"])
            w.blockSignals(False)
        elif key == "offer_price":
            base = line["market_price"] * CONDITION_FACTORS.get(line["condition"], 1.0)
            if base > 0:
                line["rate"] = round(value / base * 100)
                w = self.table.cellWidget(r, 5)
                w.blockSignals(True)
                w.setValue(line["rate"])
                w.blockSignals(False)
        it = self.table.item(r, 7)
        if it:
            it.setText(money(line["qty"] * line["offer_price"]))
        self._totals()

    def _remove(self, line):
        self.lines.remove(line)
        self._render()

    def _totals(self):
        total = sum(l["qty"] * l["offer_price"] for l in self.lines)
        market = sum(l["qty"] * l["market_price"] for l in self.lines)
        n = sum(l["qty"] for l in self.lines)
        self.total_lbl.setText(money(total))
        self.summary.setText(f"{n} carte(s) · valeur marché {money(market)}" +
                             (f" · soit {total / market * 100:.0f} % de la valeur" if market else ""))
        self.validate_btn.setEnabled(bool(self.lines))

    # ---------------------------------------------------------------- validation
    def _validate(self):
        if not self.lines:
            return
        cust = self.customer.customer()
        payout = self._payout()
        if not cust:
            if payout == "Crédit boutique":
                warn(self, "Client requis", "Choisissez ou créez le client pour lui verser du crédit boutique.")
                return
            if not ask(self, "Vendeur non renseigné",
                       "Aucun vendeur sélectionné : le registre des rachats sera incomplet.\nContinuer quand même ?"):
                return
        elif not cust["id_number"]:
            r = ask(self, "Pièce d'identité manquante",
                    "La pièce d'identité du vendeur n'est pas renseignée.\nLa compléter maintenant ?")
            if r:
                dlg = CustomerDialog(self.ctx, cust, self)
                if dlg.exec():
                    self.customer.reload(cust["id"])
                    cust = self.customer.customer()
        total = sum(l["qty"] * l["offer_price"] for l in self.lines)
        if not ask(self, "Confirmer le rachat", f"Verser {money(total)} en « {payout} » "
                                                f"à {cust['name'] if cust else 'un vendeur anonyme'} ?"):
            return
        lines = []
        for l in self.lines:
            d = dict(l)
            if d.get("product"):
                d["product"] = dict(d["product"], condition=l["condition"])
            lines.append(d)
        try:
            bid = self.ctx.svc.create_buy(lines, cust["id"] if cust else None, payout)
        except Exception as e:  # noqa: BLE001
            warn(self, "Erreur", f"Le rachat n'a pas pu être enregistré :\n{e}")
            return
        self.lines.clear()
        self._render()
        self.customer.reload()
        self.ctx.window.flash(f"Rachat enregistré · {money(total)} ({payout})")
        b = self.ctx.db.one("SELECT number FROM buys WHERE id = ?", (bid,))
        DocumentDialog(f"Bon de rachat {b['number']}", buy_receipt(self.ctx.db, bid), self).exec()

    # ---------------------------------------------------------------- registre
    def _history_rows(self):
        d1 = self.h_from.date().toString("yyyy-MM-dd")
        d2 = self.h_to.date().addDays(1).toString("yyyy-MM-dd")
        t = f"%{self.h_search.text().strip()}%"
        return self.ctx.db.q("SELECT * FROM buys WHERE date >= ? AND date < ? AND (number LIKE ? OR customer_name LIKE ?)"
                             " ORDER BY date DESC", (d1, d2, t, t))

    def refresh_history(self):
        rows = self._history_rows()
        self.history.set_rows(rows)
        self.h_footer.setText(f"{len(rows)} rachat(s) · versé {money(sum(r['total'] for r in rows))} · "
                              f"valeur marché {money(sum(r['market_total'] for r in rows))}")

    def _show_items(self, b):
        self.h_items.set_rows(self.ctx.db.q("SELECT * FROM buy_items WHERE buy_id = ?", (b["id"],)) if b else [])

    def _show_receipt(self):
        b = self.history.selected()
        if b:
            DocumentDialog(f"Bon de rachat {b['number']}", buy_receipt(self.ctx.db, b["id"]), self).exec()

    def _export_police(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le livre de police", "livre_de_police.csv", "CSV (*.csv)")
        if not path:
            return
        ids = [r["id"] for r in self._history_rows()]
        if not ids:
            info(self, "Rien à exporter", "Aucun rachat sur la période.")
            return
        rows = self.ctx.db.q(f"""
            SELECT b.number, b.date, b.customer_name, c.address, b.id_type, b.id_number, b.payout,
                   i.name, i.game, i.set_name, i.condition, i.qty, i.offer_price, i.qty * i.offer_price AS total
            FROM buy_items i JOIN buys b ON b.id = i.buy_id LEFT JOIN customers c ON c.id = b.customer_id
            WHERE b.id IN ({','.join('?' * len(ids))}) ORDER BY b.date, b.number""", ids)
        headers = ["N° rachat", "Date", "Vendeur", "Adresse", "Type pièce", "N° pièce", "Règlement", "Désignation",
                   "Jeu", "Extension", "État", "Quantité", "Prix unitaire", "Total"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(headers)
            for r in rows:
                w.writerow([str(v).replace(".", ",") if isinstance(v, float) else (v or "") for v in r.values()])
        info(self, "Export terminé", f"{len(rows)} ligne(s) exportée(s) vers :\n{path}")
