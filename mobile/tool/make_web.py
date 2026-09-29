"""Après `flutter build web` : icônes, liste du cache hors ligne (sw.js), copie dans l'appli PC.

Usage (depuis mobile/) :  ..\\.venv\\Scripts\\python.exe tool\\make_web.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

MOBILE = Path(__file__).resolve().parent.parent
BUILD = MOBILE / "build" / "web"
DEST = MOBILE.parent / "app" / "resources" / "webapp"
LOGO = MOBILE.parent / "app" / "resources" / "tcshop_512.png"


def icons(target: Path):
    src = Image.open(LOGO).convert("RGBA")
    (target / "icons").mkdir(exist_ok=True)
    for size in (192, 512):
        src.resize((size, size), Image.Resampling.LANCZOS).save(target / "icons" / f"Icon-{size}.png")
        # « maskable » : logo réduit sur fond plein (Android découpe l'icône en cercle)
        bg = Image.new("RGBA", (size, size), (14, 17, 32, 255))
        inner = src.resize((int(size * 0.8),) * 2, Image.Resampling.LANCZOS)
        bg.alpha_composite(inner, (int(size * 0.1),) * 2)
        bg.save(target / "icons" / f"Icon-maskable-{size}.png")
    # iOS : icône d'écran d'accueil sans transparence
    solid = Image.new("RGB", (180, 180), (14, 17, 32))
    solid.paste(src.resize((180, 180), Image.Resampling.LANCZOS), (0, 0), src.resize((180, 180)))
    solid.save(target / "icons" / "apple-touch-icon.png")
    src.resize((32, 32), Image.Resampling.LANCZOS).save(target / "favicon.png")


def main():
    if not (BUILD / "main.dart.js").exists():
        raise SystemExit("Lancez d'abord : flutter build web --release --base-href /app/ --pwa-strategy=none "
                         "--no-web-resources-cdn")
    icons(BUILD)
    files = sorted(str(p.relative_to(BUILD)).replace("\\", "/") for p in BUILD.rglob("*")
                   if p.is_file() and p.name not in ("sw.js", ".last_build_id") and not p.name.endswith(".map"))
    digest = hashlib.sha1()
    for f in files:
        digest.update((BUILD / f).read_bytes())
    sw = (MOBILE / "web" / "sw.js").read_text(encoding="utf-8")
    sw = sw.replace("__VERSION__", digest.hexdigest()[:12]).replace("__FILES__", json.dumps(["./"] + files, indent=0))
    (BUILD / "sw.js").write_text(sw, encoding="utf-8")
    index = (BUILD / "index.html").read_text(encoding="utf-8")
    index = index.replace('href="icons/Icon-192.png">', 'href="icons/apple-touch-icon.png">', 1)
    (BUILD / "index.html").write_text(index, encoding="utf-8")
    if DEST.exists():
        shutil.rmtree(DEST)
    shutil.copytree(BUILD, DEST, ignore=shutil.ignore_patterns("*.map", ".last_build_id"))
    size = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())
    print(f"Appli web copiée dans {DEST} ({len(files)} fichiers, {size / 1e6:.1f} Mo)")


if __name__ == "__main__":
    main()
