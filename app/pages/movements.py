"""Journal des mouvements de stock (traçabilité complète)."""
from __future__ import annotations

import csv

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QLineEdit, QWidget

from ..widgets import DataTable, PageHeader, button, info, label, page_layout


class MovementsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = page_layout(self)
        header = PageHeader("Mouvements de stock", "Chaque entrée et sortie est tracée : ventes, rachats, commandes, corrections")
        header.add(button("⇧ Exporter CSV", self._export))
        lay.addWidget(header)
        f = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("🔍  Article ou référence (ticket, rachat, commande)…")
        self.search.textChanged.connect(self.refresh)
        self.reason = QComboBox()
        self.reason.currentIndexChanged.connect(self.refresh)
        self.d1 = QDateEdit(QDate.currentDate().addDays(-30))
        self.d2 = QDateEdit(QDate.currentDate())
        for d in (self.d1, self.d2):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
            d.dateChanged.connect(self.refresh)
        f.addWidget(self.search, 1)
        f.addWidget(self.reason)
        f.addWidget(label("Du"))
        f.addWidget(self.d1)
        f.addWidget(label("au"))
        f.addWidget(self.d2)
        lay.addLayout(f)
        self.table = DataTable([
            ("date", "Date", "date"), ("product_name", "Article", "text"), ("delta", "Mouvement", "delta"),
            ("reason", "Motif", "text"), ("ref", "Référence", "text"),
        ], stretch="product_name")
        self.table.record_activated.connect(
            lambda r: r["product_id"] and self.ctx.window.goto("inventory", select_id=r["product_id"]))
        lay.addWidget(self.table, 1)
        self.footer = label("", "Muted")
        lay.addWidget(self.footer)

    def on_navigate(self, search=None, **_):
        if search is not None:
            self.d1.setDate(QDate.currentDate().addYears(-5))
            self.search.setText(search)

    def refresh(self, *_):
        cur = self.reason.currentText()
        self.reason.blockSignals(True)
        self.reason.clear()
        self.reason.addItems(["Tous les motifs"] + [r["reason"] for r in self.ctx.db.q(
            "SELECT DISTINCT reason FROM movements ORDER BY reason")])
        i = self.reason.findText(cur)
        self.reason.setCurrentIndex(max(0, i))
        self.reason.blockSignals(False)
        where = ["date >= ?", "date < ?"]
        params = [self.d1.date().toString("yyyy-MM-dd"), self.d2.date().addDays(1).toString("yyyy-MM-dd")]
        t = self.search.text().strip()
        if t:
            where.append("(product_name LIKE ? OR ref LIKE ?)")
            params += [f"%{t}%"] * 2
        if self.reason.currentIndex() > 0:
            where.append("reason = ?")
            params.append(self.reason.currentText())
        rows = self.ctx.db.q(f"SELECT * FROM movements WHERE {' AND '.join(where)} ORDER BY date DESC, id DESC LIMIT 5000",
                             params)
        self.table.set_rows(rows)
        inn = sum(r["delta"] for r in rows if r["delta"] > 0)
        out = -sum(r["delta"] for r in rows if r["delta"] < 0)
        self.footer.setText(f"{len(rows)} mouvement(s) · entrées +{inn} · sorties −{out}")

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exporter les mouvements", "mouvements.csv", "CSV (*.csv)")
        if not path:
            return
        rows = self.table.rows()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Date", "Article", "Mouvement", "Motif", "Référence"])
            for r in rows:
                w.writerow([r["date"], r["product_name"], r["delta"], r["reason"], r["ref"]])
        info(self, "Export terminé", f"{len(rows)} mouvement(s) exporté(s).")
