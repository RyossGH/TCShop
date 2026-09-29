"""Génère les icônes de TCShop (PNG + ICO multi-tailles) à partir de app/resources/tcshop.svg.

Usage :  .venv\\Scripts\\python.exe tools\\make_icon.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "app" / "resources"
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def render(renderer: QSvgRenderer, size: int) -> Image.Image:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(p)
    p.end()
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(ba))).convert("RGBA")


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    renderer = QSvgRenderer(str(RES / "tcshop.svg"))
    if not renderer.isValid():
        raise SystemExit("SVG invalide")
    # rendu en grand puis réduction : meilleur lissage aux petites tailles
    big = render(renderer, 1024)
    images = [big.resize((s, s), Image.Resampling.LANCZOS) for s in SIZES]
    images[-1].save(RES / "tcshop.png")
    big.resize((512, 512), Image.Resampling.LANCZOS).save(RES / "tcshop_512.png")
    images[-1].save(RES / "tcshop.ico", sizes=[(s, s) for s in SIZES], append_images=images[:-1])

    # visuels de l'assistant d'installation (Inno Setup, format BMP)
    pack = ROOT / "packaging"
    small = Image.new("RGB", (110, 110), "white")
    small.paste(big.resize((100, 100), Image.Resampling.LANCZOS), (5, 5), big.resize((100, 100)))
    small.save(pack / "wizard_small.bmp")
    w, h = 328, 628
    large = Image.new("RGB", (w, h))
    top, bottom = (143, 114, 255), (40, 22, 120)
    for y in range(h):
        t = y / (h - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        large.paste(c, (0, y, w, y + 1))
    logo = big.resize((230, 230), Image.Resampling.LANCZOS)
    large.paste(logo, ((w - 230) // 2, 150), logo)
    large.save(pack / "wizard_large.bmp")
    print("icônes générées dans", RES)


if __name__ == "__main__":
    main()
