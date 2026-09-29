"""Collections : suivi de complétion d'extensions (master sets, classeurs clients, objectifs boutique)."""
from __future__ import annotations

import csv

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMenu, QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget,
)

from .. import api, theme
from ..constants import GAMES
from ..dialogs import CardSearchDialog, ProductDialog, SetPickerDialog, combo
from ..widgets import Card, PageHeader, ask, button, info, label, load_pixmap, money, page_layout, run_async, warn

THUMB = QSize(150, 209)


def _faded(pm: QPixmap) -> QPixmap:
    img = pm.toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setOpacity(0.35)
    p.drawImage(0, 0, img)
    p.end()
    return out


def _placeholder(text: str, owned: bool) -> QPixmap:
    pm = QPixmap(THUMB)
    pm.fill(QColor(theme.c("panel2")))
    p = QPainter(pm)
    p.setPen(QColor(theme.c("text") if owned else theme.c("muted")))
    p.drawRect(0, 0, THUMB.width() - 1, THUMB.height() - 1)
    p.drawText(pm.rect().adjusted(8, 8, -8, -8), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
    p.end()
    return pm


class CollectionDialog(QDialog):
    def __init__(self, coll=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Collection")
        c = coll or {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(c.get("name", ""))
        self.game = combo(GAMES, editable=True, current=c.get("game", "Pokémon"))
        self.desc = QPlainTextEdit(c.get("description", ""))
        self.desc.setFixedHeight(70)
        form.addRow("Nom *", self.name)
        form.addRow("Jeu", self.game)
        form.addRow("Description", self.desc)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(lambda: self.name.text().strip() and self.accept())
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def data(self):
        return dict(name=self.name.text().strip(), game=self.game.currentText(), description=self.desc.toPlainText())


class CollectionsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._gen = 0
        self._cards: list[dict] = []
        lay = page_layout(self)
        header = PageHeader("Collections", "Suivez la complétion d'extensions entières — pour la boutique ou pour vos clients")
        header.add(button("📥 Importer une extension", self._import_set, "primary"))
        header.add(button("+ Collection vide", self._new))
        lay.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(12)
        left = Card()
        left.setFixedWidth(300)
        left.lay.addWidget(label("Mes collections", "H2"))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(lambda _r: self._load_cards())
        left.lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(button("Renommer", self._edit))
        row.addWidget(button("Supprimer", self._delete, "danger"))
        left.lay.addLayout(row)
        body.addWidget(left)

        right = Card()
        top = QHBoxLayout()
        col = QVBoxLayout()
        self.title = label("Aucune collection", "H2")
        self.sub = label("Importez une extension complète depuis la base en ligne pour démarrer.", "Muted")
        col.addWidget(self.title)
        col.addWidget(self.sub)
        top.addLayout(col, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setFormat("%p %")
        top.addWidget(self.progress)
        right.lay.addLayout(top)

        f = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrer par nom ou numéro…")
        self.search.textChanged.connect(self._fill_grid)
        self.filter = QComboBox()
        self.filter.addItems(["Toutes les cartes", "Possédées", "Manquantes", "Manquantes disponibles en boutique"])
        self.filter.currentIndexChanged.connect(self._fill_grid)
        f.addWidget(self.search, 1)
        f.addWidget(self.filter)
        f.addWidget(button("+ Carte", self._add_card))
        f.addWidget(button("⇧ Liste des manquantes", self._export_missing))
        right.lay.addLayout(f)

        self.grid = QListWidget()
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setIconSize(THUMB)
        self.grid.setGridSize(QSize(THUMB.width() + 22, THUMB.height() + 52))
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setWordWrap(True)
        self.grid.setUniformItemSizes(True)
        self.grid.setSpacing(6)
        self.grid.itemDoubleClicked.connect(lambda it: self._change(it, +1))
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._menu)
        right.lay.addWidget(self.grid, 1)
        right.lay.addWidget(label("Double-clic : +1 exemplaire · Clic droit : plus d'options", "Muted"))
        body.addWidget(right, 1)
        lay.addLayout(body, 1)

    # ---------------------------------------------------------------- données
    def _current(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def refresh(self, select_id=None):
        cur = select_id or self._current()
        self.list.blockSignals(True)
        self.list.clear()
        rows = self.ctx.db.q("""SELECT c.*, COUNT(cc.id) total, SUM(CASE WHEN cc.owned > 0 THEN 1 ELSE 0 END) owned
            FROM collections c LEFT JOIN collection_cards cc ON cc.collection_id = c.id GROUP BY c.id ORDER BY c.name""")
        for r in rows:
            pct = (r["owned"] or 0) / r["total"] * 100 if r["total"] else 0
            it = QListWidgetItem(f"{r['name']}\n{r['game']} · {r['owned'] or 0}/{r['total']} ({pct:.0f} %)")
            it.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.list.addItem(it)
            if r["id"] == cur:
                self.list.setCurrentItem(it)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self._load_cards()

    def _load_cards(self):
        cid = self._current()
        if not cid:
            self._cards = []
            self.title.setText("Aucune collection")
            self.progress.setValue(0)
            self._fill_grid()
            return
        c = self.ctx.db.one("SELECT * FROM collections WHERE id = ?", (cid,))
        self._cards = self.ctx.db.q("SELECT * FROM collection_cards WHERE collection_id = ? ORDER BY sort_key, id", (cid,))
        # disponibilité en boutique : même id externe, ou même nom + extension
        stock = self.ctx.db.q("SELECT external_id, name, set_name, SUM(quantity) q FROM products WHERE quantity > 0 "
                              "GROUP BY external_id, name, set_name")
        by_ext = {s["external_id"]: s["q"] for s in stock if s["external_id"]}
        by_name = {(s["name"].lower(), s["set_name"].lower()): s["q"] for s in stock}
        for card in self._cards:
            card["in_stock"] = by_ext.get(card["external_id"]) or by_name.get(
                (card["name"].lower(), (card["set_name"] or "").lower()), 0)
        self.title.setText(c["name"])
        self._update_header(c)
        self._fill_grid()

    def _update_header(self, c=None):
        c = c or self.ctx.db.one("SELECT * FROM collections WHERE id = ?", (self._current(),))
        total = len(self._cards)
        owned = sum(1 for x in self._cards if x["owned"] > 0)
        v_owned = sum(x["market_price"] for x in self._cards if x["owned"] > 0)
        v_missing = sum(x["market_price"] for x in self._cards if x["owned"] <= 0)
        dispo = sum(1 for x in self._cards if x["owned"] <= 0 and x["in_stock"])
        self.sub.setText(f"{c['game']} · {owned}/{total} cartes · valeur possédée {money(v_owned)} · "
                         f"coût pour compléter ≈ {money(v_missing)} · {dispo} manquante(s) dispo en boutique"
                         + (f"<br>{c['description']}" if c["description"] else ""))
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(owned)

    def _fill_grid(self):
        self._gen += 1
        gen = self._gen
        self.grid.clear()
        t = self.search.text().strip().lower()
        mode = self.filter.currentIndex()
        for card in self._cards:
            if t and t not in card["name"].lower() and t not in (card["number"] or "").lower():
                continue
            owned = card["owned"] > 0
            if (mode == 1 and not owned) or (mode == 2 and owned) or (mode == 3 and (owned or not card["in_stock"])):
                continue
            badge = f"✔ ×{card['owned']}" if owned else ("🟢 en boutique" if card["in_stock"] else "manquante")
            it = QListWidgetItem(f"#{card['number']} {card['name']}\n{badge} · {money(card['market_price'])}")
            it.setData(Qt.ItemDataRole.UserRole, card["id"])
            it.setIcon(_placeholder(card["name"], owned))
            it.setToolTip(f"{card['name']} — {card['set_name']} #{card['number']}\n{card['rarity']}\n"
                          f"Possédées : {card['owned']} · Prix marché : {money(card['market_price'])}")
            if not owned:
                it.setForeground(QColor(theme.c("muted")))
            self.grid.addItem(it)
            if card["image_url"]:
                load_pixmap(card["image_url"], lambda pm, it=it, owned=owned, g=gen: self._set_icon(it, pm, owned, g))

    def _set_icon(self, it, pm, owned, gen):
        if gen != self._gen or pm.isNull():
            return
        pm = pm.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        it.setIcon(pm if owned else _faded(pm))

    # ---------------------------------------------------------------- actions cartes
    def _card_of(self, it):
        cid = it.data(Qt.ItemDataRole.UserRole)
        return next((c for c in self._cards if c["id"] == cid), None)

    def _change(self, it, delta=None, value=None):
        card = self._card_of(it)
        if not card:
            return
        new = max(0, value if value is not None else card["owned"] + delta)
        self.ctx.db.exec("UPDATE collection_cards SET owned = ? WHERE id = ?", (new, card["id"]))
        card["owned"] = new
        row = self.grid.row(it)
        self._fill_grid()
        self._update_header()
        if 0 <= row < self.grid.count():
            self.grid.setCurrentRow(row)
        self._refresh_list_label()

    def _refresh_list_label(self):
        it = self.list.currentItem()
        if not it:
            return
        c = self.ctx.db.one("SELECT * FROM collections WHERE id = ?", (self._current(),))
        owned = sum(1 for x in self._cards if x["owned"] > 0)
        total = len(self._cards)
        it.setText(f"{c['name']}\n{c['game']} · {owned}/{total} ({owned / total * 100 if total else 0:.0f} %)")

    def _menu(self, pos):
        it = self.grid.itemAt(pos)
        if not it:
            return
        card = self._card_of(it)
        m = QMenu(self)
        m.addAction("+1 exemplaire", lambda: self._change(it, +1))
        m.addAction("−1 exemplaire", lambda: self._change(it, -1))
        m.addAction("Marquer manquante (0)", lambda: self._change(it, value=0))
        m.addSeparator()
        m.addAction("Chercher dans l'inventaire", lambda: self.ctx.window.goto("inventory", search=card["name"]))
        m.addAction("Ajouter au stock de la boutique…", lambda: self._to_stock(card))
        m.addSeparator()
        m.addAction("Retirer de la collection", lambda: self._remove_card(card))
        m.exec(self.grid.viewport().mapToGlobal(pos))

    def _to_stock(self, card):
        c = self.ctx.db.one("SELECT game FROM collections WHERE id = ?", (self._current(),))
        coef = self.ctx.db.setting_float("price_coef", 1.0)
        preset = dict(name=card["name"], game=c["game"], set_name=card["set_name"], number=card["number"],
                      rarity=card["rarity"], image_url=card["image_url"], external_id=card["external_id"],
                      market_price=card["market_price"], price=round(card["market_price"] * coef, 2), quantity=1)
        ProductDialog(self.ctx, parent=self, preset=preset).exec()
        self._load_cards()

    def _remove_card(self, card):
        self.ctx.db.exec("DELETE FROM collection_cards WHERE id = ?", (card["id"],))
        self._load_cards()
        self._refresh_list_label()

    def _add_card(self):
        cid = self._current()
        if not cid:
            warn(self, "Aucune collection", "Créez d'abord une collection.")
            return
        c = self.ctx.db.one("SELECT game FROM collections WHERE id = ?", (cid,))
        dlg = CardSearchDialog(self, c["game"])
        if dlg.exec() and dlg.result_card:
            r = dlg.result_card
            self.ctx.db.insert("collection_cards", dict(
                collection_id=cid, name=r["name"], set_name=r["set_name"], number=r["number"], rarity=r["rarity"],
                image_url=r["image_url"], external_id=r["external_id"], market_price=r["market_price"], owned=1,
                sort_key=len(self._cards) + 1))
            self.refresh()

    # ---------------------------------------------------------------- actions collections
    def _new(self):
        dlg = CollectionDialog(parent=self)
        if dlg.exec():
            d = dlg.data()
            d["created_at"] = self.ctx.db.val("SELECT datetime('now','localtime')")
            self.refresh(self.ctx.db.insert("collections", d))

    def _edit(self):
        cid = self._current()
        if not cid:
            return
        dlg = CollectionDialog(self.ctx.db.one("SELECT * FROM collections WHERE id = ?", (cid,)), self)
        if dlg.exec():
            self.ctx.db.update("collections", cid, dlg.data())
            self.refresh(cid)

    def _delete(self):
        cid = self._current()
        if cid and ask(self, "Supprimer", "Supprimer cette collection et son suivi ?"):
            self.ctx.db.exec("DELETE FROM collections WHERE id = ?", (cid,))
            self.refresh()

    def _import_set(self):
        dlg = SetPickerDialog(self)
        if not dlg.exec() or not dlg.result_set:
            return
        game, code, name = dlg.result_set
        self.sub.setText(f"Import de « {name} » en cours…")

        def done(cards):
            if not cards:
                warn(self, "Import", "Aucune carte trouvée pour cette extension.")
                return
            with self.ctx.db.tx():
                cid = self.ctx.db.insert("collections", dict(
                    name=name, game=game, description=f"Extension complète ({len(cards)} cartes)",
                    created_at=self.ctx.db.val("SELECT datetime('now','localtime')")))
                for i, c in enumerate(cards):
                    self.ctx.db.insert("collection_cards", dict(
                        collection_id=cid, name=c["name"], set_name=c["set_name"], number=c["number"],
                        rarity=c["rarity"], image_url=c["image_url"], external_id=c["external_id"],
                        market_price=c["market_price"], owned=0, sort_key=i))
            self.refresh(cid)
            info(self, "Import terminé", f"{len(cards)} cartes importées dans « {name} ».")

        run_async(lambda: api.set_cards(game, code), done, lambda e: warn(self, "Erreur d'import", e))

    def _export_missing(self):
        miss = [c for c in self._cards if c["owned"] <= 0]
        if not miss:
            info(self, "Rien à exporter", "Aucune carte manquante 🎉")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Liste des manquantes", "cartes_manquantes.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Numéro", "Nom", "Extension", "Rareté", "Prix marché", "Dispo en boutique"])
            for c in miss:
                w.writerow([c["number"], c["name"], c["set_name"], c["rarity"],
                            f"{c['market_price']:.2f}".replace(".", ","), c["in_stock"] or 0])
        info(self, "Export terminé", f"{len(miss)} carte(s) manquante(s) exportée(s).")
