"""Association de TCShop Mobile : QR codes Android et iPhone, état du serveur, appareils connus."""
from __future__ import annotations

import secrets

import segno
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from .sync_server import iphone_guide_url, local_ips, pairing_uri
from .widgets import DataTable, ask, button, label


def qr_pixmap(text: str, size: int = 280) -> QPixmap:
    qr = segno.make(text, error="m")
    matrix = list(qr.matrix)
    n = len(matrix) + 8  # zone blanche de 4 modules autour
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    cell = size / n
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("black"))
    for y, row in enumerate(matrix):
        for x, v in enumerate(row):
            if v:
                p.drawRect(QRectF((x + 4) * cell, (y + 4) * cell, cell + 0.5, cell + 0.5))
    p.end()
    return QPixmap.fromImage(img)


def _qr_tab(steps: str) -> tuple[QWidget, QLabel]:
    w = QWidget()
    lay = QVBoxLayout(w)
    qr = QLabel()
    qr.setFixedSize(280, 280)
    lay.addWidget(qr, 0, Qt.AlignmentFlag.AlignHCenter)
    lay.addWidget(label(steps, wrap=True))
    lay.addStretch(1)
    return w, qr


class PairingDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("TCShop Mobile — associer un téléphone")
        self.resize(860, 620)
        lay = QHBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.setFixedWidth(360)
        w_android, self.qr_android = _qr_tab(
            "Dans l'appli <b>TCShop Mobile</b> (APK) : « Scanner le QR code ».")
        w_iphone, self.qr_iphone = _qr_tab(
            "Scannez avec l'<b>appareil photo</b> de l'iPhone, ouvrez le lien dans <b>Safari</b> "
            "et suivez les 4 étapes affichées (certificat, activation, ouverture, écran d'accueil).")
        self.tabs.addTab(w_iphone, "  iPhone")
        self.tabs.addTab(w_android, "  Android")
        lay.addWidget(self.tabs)

        right = QVBoxLayout()
        right.addWidget(label("Associer TCShop Mobile", "H2"))
        right.addWidget(label(
            "Le téléphone et ce PC doivent être sur le <b>même Wi-Fi</b>. Ensuite la synchro est automatique.<br><br>"
            "<span style='color:gray'>Au premier démarrage, Windows peut demander d'autoriser TCShop sur le réseau : "
            "cochez <b>Réseaux privés</b> puis « Autoriser ».<br>Astuce : réservez l'adresse IP du PC dans votre box "
            "internet pour que l'appli iPhone la retrouve toujours.</span>", wrap=True))
        self.addr = label("", "Muted", wrap=True)
        right.addWidget(self.addr)
        right.addWidget(label("Appareils associés", "Muted"))
        self.devices = DataTable([("name", "Appareil", "text"), ("last_sync", "Dernière synchro", "date"),
                                  ("ops", "Opérations reçues", "int")], stretch="name")
        right.addWidget(self.devices, 1)
        row = QHBoxLayout()
        row.addWidget(button("Nouvelle clé (déconnecte tous les téléphones)", self._reset, "danger"))
        row.addStretch(1)
        row.addWidget(button("Fermer", self.accept, "primary"))
        right.addLayout(row)
        lay.addLayout(right, 1)
        self._refresh()

    def _refresh(self):
        db = self.ctx.db
        self.qr_android.setPixmap(qr_pixmap(pairing_uri(db)))
        self.qr_iphone.setPixmap(qr_pixmap(iphone_guide_url(db)))
        srv = getattr(self.ctx.window, "sync", None)
        port = int(db.setting_float("sync_port", 8765))
        state = "✔ Synchro active" if srv and srv.running else f"✖ Synchro arrêtée {srv.error if srv else ''}"
        https = ""
        if srv and srv.running:
            https = (f"<br>✔ iPhone (HTTPS) : port {srv.https_port}" if srv.httpsd else f"<br>✖ {srv.https_error}")
        self.addr.setText(f"{state}{https}<br>Adresse du PC : {', '.join(f'{ip}:{port}' for ip in local_ips())}")
        self.devices.set_rows(db.q("""SELECT d.*, (SELECT COUNT(*) FROM sync_ops o WHERE o.device_id = d.id) ops
                                      FROM sync_devices d ORDER BY last_sync DESC"""))

    def _reset(self):
        if ask(self, "Nouvelle clé", "Les téléphones déjà associés ne pourront plus se synchroniser tant qu'ils n'auront "
                                     "pas rescanné le nouveau QR code. Continuer ?"):
            self.ctx.db.set_setting("sync_token", secrets.token_urlsafe(18))
            win = self.ctx.window
            if win.sync.running:
                win.sync.stop()
                win.sync.start()
            self._refresh()
