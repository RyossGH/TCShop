"""TCShop — logiciel de caisse et de gestion pour boutique de jeux, TCG et collection.

Lancement :  python main.py
"""
from __future__ import annotations

import locale
import sys
import traceback

from PySide6.QtCore import QLocale
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_ID, APP_NAME, APP_VERSION, resource, theme
from app.db import DATA_DIR, Database
from app.main_window import MainWindow
from app.services import Services


class AppContext:
    def __init__(self):
        self.db = Database()
        self.svc = Services(self.db)
        self.window = None


def _excepthook(exc_type, exc, tb):
    msg = "".join(traceback.format_exception(exc_type, exc, tb))
    sys.stderr.write(msg) if sys.stderr else None
    try:
        QMessageBox.critical(None, "Erreur inattendue", f"{exc}\n\nDétails :\n{msg[-1500:]}")
    except Exception:  # noqa: BLE001
        pass


def main():
    try:
        locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
    except locale.Error:
        try:
            locale.setlocale(locale.LC_TIME, "French_France")
        except locale.Error:
            pass
    if sys.platform == "win32":
        try:  # icône TCShop dans la barre des tâches (et non celle de Python)
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:  # noqa: BLE001
            pass
    QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.France))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(resource("tcshop.ico")))
    app.setFont(QFont("Segoe UI", 10))
    sys.excepthook = _excepthook

    ctx = AppContext()
    try:
        ctx.db.backup()
    except Exception:  # noqa: BLE001 - une sauvegarde ratée ne doit pas bloquer le démarrage
        pass
    theme.apply_theme(app, ctx.db.setting("theme", "Sombre"))

    win = MainWindow(ctx)
    win.show()

    if not ctx.db.val("SELECT COUNT(*) FROM products", default=0) and not ctx.db.setting("demo_asked"):
        ctx.db.set_setting("demo_asked", "1")
        r = QMessageBox.question(
            win, "Bienvenue 👋",
            f"Bienvenue dans {APP_NAME} !\n\nVoulez-vous charger des données de démonstration "
            "(articles, clients, ventes) pour découvrir l'application ?\n\n"
            f"Vous pourrez repartir de zéro en supprimant le dossier :\n{DATA_DIR}")
        if r == QMessageBox.StandardButton.Yes:
            from app.demo import load_demo
            load_demo(ctx)
            win.goto("dashboard")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
