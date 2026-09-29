"""Paramètres : boutique, tarifs, fidélité, apparence, sauvegardes."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QGridLayout, QHBoxLayout,
    QLineEdit, QPlainTextEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .. import theme
from ..db import BACKUP_DIR, DATA_DIR
from ..sync_server import local_ips


def srv_addr(ctx) -> str:
    return f"{local_ips()[0]}:{int(ctx.db.setting_float('sync_port', 8765))}"
from ..widgets import PageHeader, ask, button, info, label, page_layout, warn


def _dspin(lo, hi, dec=2, suffix=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSuffix(suffix)
    return s


class SettingsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        lay = page_layout(inner)
        header = PageHeader("Paramètres", "Configuration de la boutique")
        header.add(button("💾 Enregistrer", self.save, "primary"))
        lay.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(14)

        g1 = QGroupBox("Boutique (affiché sur les tickets et bons)")
        f1 = QFormLayout(g1)
        self.shop_name = QLineEdit()
        self.shop_address = QPlainTextEdit()
        self.shop_address.setFixedHeight(60)
        self.shop_phone = QLineEdit()
        self.shop_email = QLineEdit()
        self.shop_siret = QLineEdit()
        self.ticket_footer = QLineEdit()
        f1.addRow("Nom", self.shop_name)
        f1.addRow("Adresse", self.shop_address)
        f1.addRow("Téléphone", self.shop_phone)
        f1.addRow("E-mail", self.shop_email)
        f1.addRow("SIRET", self.shop_siret)
        f1.addRow("Pied de ticket", self.ticket_footer)
        grid.addWidget(g1, 0, 0)

        g2 = QGroupBox("Tarifs et rachats")
        f2 = QFormLayout(g2)
        self.vat = _dspin(0, 100, 1, " %")
        self.buy_cash = _dspin(0, 100, 0, " %")
        self.buy_credit = _dspin(0, 150, 0, " %")
        self.coef = _dspin(0.1, 5, 2, " ×")
        f2.addRow("TVA (prix TTC)", self.vat)
        f2.addRow("Taux de rachat en espèces", self.buy_cash)
        f2.addRow("Taux de rachat en crédit boutique", self.buy_credit)
        f2.addRow("Coefficient prix de vente / marché", self.coef)
        f2.addRow(label("Ex. coef 1,10 = prix de vente 10 % au-dessus du prix marché.", "Muted", wrap=True))
        grid.addWidget(g2, 0, 1)

        g3 = QGroupBox("Fidélité")
        f3 = QFormLayout(g3)
        self.pts_per_euro = _dspin(0, 100, 1, " pt / €")
        self.pts_for_euro = QSpinBox()
        self.pts_for_euro.setRange(1, 100000)
        self.pts_for_euro.setSuffix(" pts = 1 €")
        f3.addRow("Points gagnés", self.pts_per_euro)
        f3.addRow("Conversion", self.pts_for_euro)
        grid.addWidget(g3, 1, 0)

        g4 = QGroupBox("Apparence")
        f4 = QFormLayout(g4)
        self.theme = QComboBox()
        self.theme.addItems(list(theme.PALETTES))
        f4.addRow("Thème", self.theme)
        f4.addRow(label("Le thème s'applique immédiatement ; certains graphiques se mettent à jour à l'actualisation.",
                        "Muted", wrap=True))
        grid.addWidget(g4, 1, 1)

        g5 = QGroupBox("Données et sauvegardes")
        v5 = QVBoxLayout(g5)
        v5.addWidget(label(f"Base de données : {self.ctx.db.path}", "Muted", wrap=True))
        v5.addWidget(label("Une sauvegarde automatique est faite à chaque démarrage (15 dernières conservées).",
                           "Muted", wrap=True))
        r = QHBoxLayout()
        r.addWidget(button("💾 Sauvegarder maintenant", self._backup))
        r.addWidget(button("📁 Ouvrir le dossier des données", lambda: os.startfile(str(DATA_DIR))))
        r.addWidget(button("♻ Restaurer une sauvegarde…", self._restore, "danger"))
        r.addStretch(1)
        v5.addLayout(r)
        r2 = QHBoxLayout()
        r2.addWidget(button("🎲 Charger des données de démonstration", self._demo))
        r2.addWidget(button("🧹 Vider le cache d'images", self._clear_cache))
        r2.addStretch(1)
        v5.addLayout(r2)
        grid.addWidget(g5, 2, 0, 1, 2)

        g6 = QGroupBox("📱 TCShop Mobile (téléphone Android)")
        v6 = QVBoxLayout(g6)
        v6.addWidget(label("Vendez en convention, enregistrez vos commandes en ligne et faites l'inventaire avec votre "
                           "téléphone. Il travaille hors ligne et se synchronise tout seul dès qu'il est sur le même "
                           "Wi-Fi que ce PC.", "Muted", wrap=True))
        r3 = QHBoxLayout()
        self.sync_enabled = QCheckBox("Activer la synchronisation")
        self.sync_enabled.toggled.connect(self._toggle_sync)
        r3.addWidget(self.sync_enabled)
        self.sync_status = label("", "Muted")
        r3.addWidget(self.sync_status, 1)
        r3.addWidget(button("📱 Associer un téléphone (QR code)", self._pair, "primary"))
        v6.addLayout(r3)
        grid.addWidget(g6, 3, 0, 1, 2)
        lay.addLayout(grid)
        lay.addStretch(1)

    # ---------------------------------------------------------------- mobile
    def _sync_state_text(self):
        srv = self.ctx.window.sync
        return f"✔ Actif — {srv_addr(self.ctx)}" if srv.running else (f"✖ {srv.error}" if srv.error else "Désactivée")

    def _toggle_sync(self, on: bool):
        srv = self.ctx.window.sync
        self.ctx.db.set_setting("sync_enabled", "1" if on else "0")
        if on and not srv.running:
            srv.start()
        elif not on and srv.running:
            srv.stop()
        self.sync_status.setText(self._sync_state_text())

    def _pair(self):
        if not self.sync_enabled.isChecked():
            self.sync_enabled.setChecked(True)
        from ..mobile_pairing import PairingDialog
        PairingDialog(self.ctx, self).exec()

    def refresh(self):
        self.sync_enabled.blockSignals(True)
        self.sync_enabled.setChecked(self.ctx.window.sync.running)
        self.sync_enabled.blockSignals(False)
        self.sync_status.setText(self._sync_state_text())
        s = self.ctx.db.setting
        self.shop_name.setText(s("shop_name"))
        self.shop_address.setPlainText(s("shop_address"))
        self.shop_phone.setText(s("shop_phone"))
        self.shop_email.setText(s("shop_email"))
        self.shop_siret.setText(s("shop_siret"))
        self.ticket_footer.setText(s("ticket_footer"))
        f = self.ctx.db.setting_float
        self.vat.setValue(f("vat_rate", 20))
        self.buy_cash.setValue(f("buy_rate_cash", 50))
        self.buy_credit.setValue(f("buy_rate_credit", 65))
        self.coef.setValue(f("price_coef", 1.0))
        self.pts_per_euro.setValue(f("points_per_euro", 1))
        self.pts_for_euro.setValue(int(f("points_for_euro", 20)))
        self.theme.setCurrentText(s("theme", "Sombre"))

    def save(self):
        db = self.ctx.db
        with db.tx():
            db.set_setting("shop_name", self.shop_name.text().strip() or "Ma Boutique TCG")
            db.set_setting("shop_address", self.shop_address.toPlainText().strip())
            db.set_setting("shop_phone", self.shop_phone.text().strip())
            db.set_setting("shop_email", self.shop_email.text().strip())
            db.set_setting("shop_siret", self.shop_siret.text().strip())
            db.set_setting("ticket_footer", self.ticket_footer.text().strip())
            db.set_setting("vat_rate", self.vat.value())
            db.set_setting("buy_rate_cash", self.buy_cash.value())
            db.set_setting("buy_rate_credit", self.buy_credit.value())
            db.set_setting("price_coef", self.coef.value())
            db.set_setting("points_per_euro", self.pts_per_euro.value())
            db.set_setting("points_for_euro", self.pts_for_euro.value())
            db.set_setting("theme", self.theme.currentText())
        theme.apply_theme(QApplication.instance(), self.theme.currentText())
        self.ctx.window.update_brand()
        self.ctx.window.flash("Paramètres enregistrés")

    def _backup(self):
        path = self.ctx.db.backup()
        info(self, "Sauvegarde", f"Sauvegarde créée :\n{path}")

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "Restaurer une sauvegarde", str(BACKUP_DIR), "Base TCG (*.db)")
        if not path:
            return
        if not ask(self, "Restaurer", "La base actuelle sera remplacée par cette sauvegarde "
                                      "(une copie de sécurité est faite avant).\nL'application va se fermer. Continuer ?"):
            return
        self.ctx.db.backup()
        self.ctx.db.restore(path)
        info(self, "Restauration", "Sauvegarde restaurée. Relancez l'application.")
        QApplication.instance().quit()

    def _demo(self):
        if self.ctx.db.val("SELECT COUNT(*) FROM products", default=0) and not ask(
                self, "Données de démonstration", "Des articles existent déjà. Ajouter quand même les données de démo ?"):
            return
        from ..demo import load_demo
        try:
            n = load_demo(self.ctx)
        except Exception as e:  # noqa: BLE001
            warn(self, "Erreur", str(e))
            return
        info(self, "Démo chargée", f"{n} articles, des clients, ventes, rachats et commandes ont été ajoutés.")

    def _clear_cache(self):
        from ..db import CACHE_DIR
        n = 0
        for f in CACHE_DIR.glob("*.img"):
            f.unlink(missing_ok=True)
            n += 1
        info(self, "Cache vidé", f"{n} image(s) supprimée(s). Elles seront retéléchargées au besoin.")
