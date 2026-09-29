# -*- mode: python ; coding: utf-8 -*-
# Construction de TCShop.exe :  .venv\Scripts\pyinstaller packaging\tcshop.spec --noconfirm
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 (fourni par PyInstaller)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "app" / "resources"), "app/resources")],
    hiddenimports=["PySide6.QtCharts", "PySide6.QtPrintSupport", "PySide6.QtSvg"],
    excludes=["tkinter", "unittest", "pydoc", "PIL", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtQuick3D", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TCShop",
    icon=str(ROOT / "app" / "resources" / "tcshop.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
    console=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="TCShop", upx=False)
