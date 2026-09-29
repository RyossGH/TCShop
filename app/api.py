"""Recherche de cartes et de prix via les bases publiques gratuites (sans clé API).

- Pokémon : api.tcgdex.net (noms français, prix Cardmarket)
- Magic   : api.scryfall.com (prix EUR)
- Yu-Gi-Oh: db.ygoprodeck.com (prix Cardmarket)

Toutes les fonctions sont bloquantes : les appeler depuis un thread (voir widgets.run_async).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "TCShop/2.0 (logiciel de boutique de jeux)"
API_GAMES = ["Pokémon", "Magic: The Gathering", "Yu-Gi-Oh!"]


def _get(url: str, params: dict | None = None, timeout: int = 30, retries: int = 2):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(1.0 + attempt)
                continue
            raise RuntimeError(f"Le service a répondu une erreur {e.code}. Réessayez dans un instant.") from e
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(1.0)
                continue
            raise RuntimeError(f"Connexion impossible ({e.reason}). Vérifiez votre accès Internet.") from e
    return None


def _f(v) -> float:
    try:
        return round(float(v), 2) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def num_key(number: str) -> tuple:
    m = re.search(r"\d+", number or "")
    return (int(m.group()) if m else 99999, number or "")


# ---------------------------------------------------------------- Magic
SCRY = "https://api.scryfall.com"


def _mtg_card(c: dict) -> dict:
    img = (c.get("image_uris") or {}).get("normal", "")
    if not img and c.get("card_faces"):
        img = (c["card_faces"][0].get("image_uris") or {}).get("normal", "")
    prices = c.get("prices") or {}
    return dict(
        game="Magic: The Gathering",
        name=c.get("printed_name") or c.get("name", ""),
        set_name=c.get("set_name", ""),
        set_code=(c.get("set") or "").upper(),
        number=c.get("collector_number", ""),
        rarity=(c.get("rarity") or "").capitalize(),
        image_url=img,
        market_price=_f(prices.get("eur")) or _f(prices.get("eur_foil")),
        external_id=c.get("id", ""),
        language=(c.get("lang") or "en").upper(),
    )


def _mtg_search(q: str) -> list[dict]:
    d = _get(f"{SCRY}/cards/search", {"q": q, "unique": "prints", "order": "released"})
    return [_mtg_card(c) for c in (d or {}).get("data", [])][:150]


def _mtg_sets() -> list[tuple]:
    d = _get(f"{SCRY}/sets") or {}
    return [
        (s["code"].upper(), s["name"], s.get("released_at", ""))
        for s in d.get("data", [])
        if s.get("card_count", 0) > 0 and not s.get("digital")
    ]


def _mtg_set_cards(code: str) -> list[dict]:
    out: list[dict] = []
    d = _get(f"{SCRY}/cards/search", {"q": f"set:{code.lower()}", "unique": "prints", "order": "set"})
    while d:
        out += [_mtg_card(c) for c in d.get("data", [])]
        if d.get("has_more") and d.get("next_page"):
            time.sleep(0.1)
            d = _get(d["next_page"])
        else:
            break
    return out


def _mtg_price(eid: str):
    d = _get(f"{SCRY}/cards/{eid}")
    return _mtg_card(d)["market_price"] if d else None


# ---------------------------------------------------------------- Pokémon (TCGdex : noms FR + prix Cardmarket)
TCGDEX = "https://api.tcgdex.net/v2"


def _pkm_img(base: str) -> str:
    return f"{base}/low.png" if base else ""


def _pkm_card(c: dict, lang: str = "fr") -> dict:
    cm = (c.get("pricing") or {}).get("cardmarket") or {}
    price = next((_f(cm.get(k)) for k in ("trend", "avg30", "avg", "trend-holo", "avg30-holo") if _f(cm.get(k))), 0.0)
    s = c.get("set") or {}
    return dict(
        game="Pokémon",
        name=c.get("name", ""),
        set_name=s.get("name", ""),
        set_code=(s.get("id") or "").upper(),
        number=c.get("localId", ""),
        rarity=c.get("rarity") or "",
        image_url=_pkm_img(c.get("image", "")),
        market_price=price,
        external_id=c.get("id", ""),
        language=lang.upper(),
    )


def _pkm_details(briefs: list[dict], lang: str, set_name: str = "") -> list[dict]:
    """Récupère le détail (prix, rareté, extension) de plusieurs cartes en parallèle."""
    def one(b):
        try:
            d = _get(f"{TCGDEX}/{lang}/cards/{urllib.parse.quote(b['id'])}")
            if d:
                return _pkm_card(d, lang)
        except RuntimeError:
            pass
        return dict(game="Pokémon", name=b.get("name", ""), set_name=set_name, set_code="", number=b.get("localId", ""),
                    rarity="", image_url=_pkm_img(b.get("image", "")), market_price=0.0,
                    external_id=b.get("id", ""), language=lang.upper())

    with ThreadPoolExecutor(max_workers=12) as ex:
        return list(ex.map(one, briefs))


def _pkm_search(q: str) -> list[dict]:
    q = q.strip()
    for lang in ("fr", "en"):  # « Dracaufeu » comme « Charizard »
        d = _get(f"{TCGDEX}/{lang}/cards", {"name": q}) or []
        if d:
            d = d[::-1][:60]  # les plus récentes d'abord
            return _pkm_details(d, lang)
    return []


def _pkm_sets() -> list[tuple]:
    d = _get(f"{TCGDEX}/fr/sets") or []
    return [(s["id"], s["name"], "") for s in reversed(d)]


def _pkm_set_cards(code: str) -> list[dict]:
    s = _get(f"{TCGDEX}/fr/sets/{urllib.parse.quote(code)}") or {}
    out = _pkm_details(s.get("cards", []), "fr", s.get("name", ""))
    out.sort(key=lambda c: num_key(c["number"]))
    return out


def _pkm_price(eid: str):
    for lang in ("fr", "en"):
        d = _get(f"{TCGDEX}/{lang}/cards/{urllib.parse.quote(eid)}")
        if d:
            return _pkm_card(d, lang)["market_price"] or None
    return None


# ---------------------------------------------------------------- Yu-Gi-Oh!
YGO = "https://db.ygoprodeck.com/api/v7"


def _ygo_cards(c: dict, only_set: str | None = None) -> list[dict]:
    img = (c.get("card_images") or [{}])[0].get("image_url_small", "")
    price = _f((c.get("card_prices") or [{}])[0].get("cardmarket_price"))
    out = []
    for s in c.get("card_sets") or [{}]:
        if only_set and s.get("set_name") != only_set:
            continue
        code = s.get("set_code", "")
        out.append(dict(
            game="Yu-Gi-Oh!",
            name=c.get("name", ""),
            set_name=s.get("set_name", ""),
            set_code=code.split("-")[0] if code else "",
            number=code,
            rarity=s.get("set_rarity", ""),
            image_url=img,
            market_price=price,
            external_id=str(c.get("id", "")),
            language="EN",
        ))
    return out


def _ygo_search(q: str) -> list[dict]:
    d = _get(f"{YGO}/cardinfo.php", {"fname": q}) or {}
    out: list[dict] = []
    for c in d.get("data", [])[:40]:
        out += _ygo_cards(c)
    return out[:200]


def _ygo_sets() -> list[tuple]:
    d = _get(f"{YGO}/cardsets.php") or []
    rows = [(s["set_name"], f"{s['set_name']} ({s.get('set_code', '')})", s.get("tcg_date") or "") for s in d]
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows


def _ygo_set_cards(name: str) -> list[dict]:
    d = _get(f"{YGO}/cardinfo.php", {"cardset": name}) or {}
    out: list[dict] = []
    for c in d.get("data", []):
        out += _ygo_cards(c, only_set=name)
    out.sort(key=lambda c: num_key(c["number"].split("-")[-1] if c["number"] else ""))
    return out


def _ygo_price(eid: str):
    d = _get(f"{YGO}/cardinfo.php", {"id": eid})
    if d and d.get("data"):
        return _f((d["data"][0].get("card_prices") or [{}])[0].get("cardmarket_price"))
    return None


# ---------------------------------------------------------------- façade
_PROVIDERS = {
    "Pokémon": (_pkm_search, _pkm_sets, _pkm_set_cards, _pkm_price),
    "Magic: The Gathering": (_mtg_search, _mtg_sets, _mtg_set_cards, _mtg_price),
    "Yu-Gi-Oh!": (_ygo_search, _ygo_sets, _ygo_set_cards, _ygo_price),
}


def _prov(game: str):
    if game not in _PROVIDERS:
        raise RuntimeError(f"Aucune base en ligne disponible pour « {game} ».")
    return _PROVIDERS[game]


def search_cards(game: str, query: str) -> list[dict]:
    return _prov(game)[0](query)


def list_sets(game: str) -> list[tuple]:
    """Renvoie [(code, nom, date_sortie)] du plus récent au plus ancien."""
    return _prov(game)[1]()


def set_cards(game: str, code: str) -> list[dict]:
    return _prov(game)[2](code)


def fetch_price(game: str, external_id: str):
    return _prov(game)[3](external_id)
