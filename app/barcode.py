"""Codes-barres : génération Code 128 (étiquettes) et normalisation des lectures scanner."""
from __future__ import annotations

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter

# Motifs Code 128 (largeurs barre/espace alternées), index = valeur du symbole
PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112",
]
START_B, START_C, CODE_B, CODE_C, STOP = 104, 105, 100, 99, 106
QUIET = 10  # zone de silence (modules) de chaque côté


def _symbols(data: str) -> list[int]:
    """Encode en Code 128 B, avec passage en C pour les longues suites de chiffres (plus compact)."""
    if not data or any(ord(ch) < 32 or ord(ch) > 126 for ch in data):
        raise ValueError("Le code doit contenir uniquement des caractères ASCII imprimables.")
    out: list[int] = []
    i, n = 0, len(data)
    mode = None
    while i < n:
        run = len(re.match(r"\d*", data[i:]).group())
        # bloc numérique : tout le code, ou au moins 6 chiffres au milieu / 4 en fin
        use_c = (run >= 4 and (i == 0 and run == n)) or run >= 6 or (run >= 4 and i + run == n)
        if use_c:
            if run % 2:  # un chiffre isolé reste en B
                if mode is None:
                    out.append(START_B)
                    mode = "B"
                elif mode != "B":
                    out.append(CODE_B)
                    mode = "B"
                out.append(ord(data[i]) - 32)
                i += 1
                run -= 1
            if mode is None:
                out.append(START_C)
            elif mode != "C":
                out.append(CODE_C)
            mode = "C"
            for k in range(i, i + run, 2):
                out.append(int(data[k:k + 2]))
            i += run
        else:
            if mode is None:
                out.append(START_B)
            elif mode != "B":
                out.append(CODE_B)
            mode = "B"
            out.append(ord(data[i]) - 32)
            i += 1
    checksum = out[0] + sum(v * k for k, v in enumerate(out[1:], 1))
    out.append(checksum % 103)
    out.append(STOP)
    return out


def code128_modules(data: str) -> list[int]:
    """Liste des largeurs (en modules), en commençant par une barre."""
    widths: list[int] = []
    for s in _symbols(data):
        widths += [int(c) for c in PATTERNS[s]]
    return widths


def draw_code128(p: QPainter, rect: QRectF, data: str, crisp: bool = True) -> None:
    """Dessine le code-barres centré dans rect (unités du painter = pixels périphérique)."""
    widths = code128_modules(data)
    total = sum(widths) + 2 * QUIET
    mw = rect.width() / total
    if crisp and mw >= 1:
        mw = float(int(mw))  # module entier en points imprimante = barres nettes
    x = rect.x() + (rect.width() - mw * (total - 2 * QUIET)) / 2
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("black"))
    bar = True
    for w in widths:
        if bar:
            p.drawRect(QRectF(x, rect.y(), w * mw, rect.height()))
        x += w * mw
        bar = not bar
    p.restore()


# --------------------------------------------------------------------- lecture scanner
# Scanner configuré en QWERTY sur un PC AZERTY : « 3760123456789 » arrive en « "è^àé"'(-è_çà »…
_QWERTY_ON_AZERTY = str.maketrans({
    "&": "1", "é": "2", '"': "3", "'": "4", "(": "5", "-": "6", "§": "6", "è": "7", "_": "8", "!": "8",
    "ç": "9", "à": "0", ")": "-", "°": "_",
    "a": "q", "q": "a", "z": "w", "w": "z", "A": "Q", "Q": "A", "Z": "W", "W": "Z", ",": "m", "?": "M",
})
_CLEAN = re.compile(r"[0-9A-Za-z\-_./]+")


def normalize_scan(code: str) -> str:
    """Corrige une lecture faite par un scanner réglé en QWERTY sur un clavier AZERTY."""
    code = (code or "").strip()
    if not code or _CLEAN.fullmatch(code):
        return code
    fixed = code.translate(_QWERTY_ON_AZERTY)
    return fixed if _CLEAN.fullmatch(fixed) else code


def code_font(px: float) -> QFont:
    f = QFont("Consolas")
    f.setPixelSize(max(6, int(px)))
    return f
