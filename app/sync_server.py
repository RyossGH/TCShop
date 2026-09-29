"""Synchronisation avec TCShop Mobile (Android) sur le réseau Wi-Fi local.

- HTTP (port 8765 par défaut), protégé par une clé secrète transmise au téléphone via QR code.
- Découverte automatique : le téléphone envoie « TCSHOP_DISCOVER » en diffusion UDP (port 8766),
  le PC répond avec son port, ce qui permet de le retrouver même si son adresse IP a changé.
- Le téléphone travaille hors ligne et envoie un journal d'opérations (ventes, commandes, mouvements de stock).
  Chaque opération a un identifiant unique : renvoyée deux fois, elle n'est appliquée qu'une fois.
  Le stock est synchronisé par mouvements (−2, +5…), jamais par quantité absolue : aucune vente ne se perd.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import socket
import ssl
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, Signal

from . import APP_NAME, APP_VERSION
from .constants import CHANNELS, ORDER_STATUSES
from .db import DATA_DIR, Database, now
from .services import Services

DEFAULT_PORT = 8765
DISCOVERY_PORT = 8766
MOBILE_PAYMENTS = ("Espèces", "Virement", "Wero")
MOBILE_PAYOUTS = ("Espèces", "Virement", "Wero", "Crédit boutique")  # règlement des rachats
STOCK_REASONS_MOBILE = {"reception": "Réception fournisseur", "out": "Sortie (mobile)", "count": "Inventaire",
                        "correction": "Correction"}


def local_ips() -> list[str]:
    """Adresses IPv4 du PC sur le réseau local (la principale en premier)."""
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # aucun paquet n'est envoyé : sert à connaître l'interface par défaut
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def ensure_token(db: Database) -> str:
    tok = db.setting("sync_token", "")
    if not tok:
        tok = secrets.token_urlsafe(18)
        db.set_setting("sync_token", tok)
    return tok


def pairing_uri(db: Database) -> str:
    ip = local_ips()[0]
    port = int(db.setting_float("sync_port", DEFAULT_PORT))
    return f"tcshop://pair?h={ip}&p={port}&t={ensure_token(db)}"


# ====================================================================== logique de synchro
class SyncLogic:
    """Traite les requêtes du téléphone. Utilise sa propre connexion SQLite (thread du serveur)."""

    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self.svc = Services(self.db)

    # ---------------------------------------------------------------- catalogue
    def catalog(self) -> dict:
        db = self.db
        products = db.q("""SELECT id, sku, barcode, name, short_name, category, brand, variant, game, set_name, number,
                                  rarity, language, condition, finish, location, quantity, min_stock, price, cost,
                                  market_price, track_stock, favorite, image_url, updated_at
                           FROM products ORDER BY name""")
        orders = db.q("""SELECT id, number, external_ref, date, channel, customer_name, address, status, shipping, total,
                                tracking, notes FROM orders
                         WHERE status IN ('À préparer', 'Préparée', 'Expédiée') OR date >= date('now', '-30 days')
                         ORDER BY date DESC""")
        items = db.q("""SELECT order_id, product_id, name, qty, unit_price FROM order_items
                        WHERE order_id IN (SELECT id FROM orders WHERE status IN ('À préparer', 'Préparée', 'Expédiée')
                                           OR date >= date('now', '-30 days'))""")
        by_order: dict[int, list] = {}
        for it in items:
            by_order.setdefault(it["order_id"], []).append(it)
        for o in orders:
            o["items"] = by_order.get(o["id"], [])
        channels = list(dict.fromkeys(CHANNELS + [r["channel"] for r in db.q(
            "SELECT DISTINCT channel FROM orders WHERE channel != ''")]))
        return dict(
            server_time=now(), app=APP_NAME, version=APP_VERSION,
            shop=dict(name=db.setting("shop_name"), address=db.setting("shop_address"),
                      phone=db.setting("shop_phone")),
            products=products,
            barcodes=db.q("SELECT code, product_id FROM barcodes"),
            customers=db.q("SELECT id, name, phone, credit, (id_number != '') AS has_id FROM customers ORDER BY name"),
            orders=orders, channels=channels, order_statuses=ORDER_STATUSES, payments=list(MOBILE_PAYMENTS),
            payouts=list(MOBILE_PAYOUTS),
            settings=dict(buy_rate_cash=db.setting_float("buy_rate_cash", 50),
                          buy_rate_credit=db.setting_float("buy_rate_credit", 65),
                          price_coef=db.setting_float("price_coef", 1.0)),
            collections=db.q("""SELECT c.id, c.name, c.game, c.description,
                  (SELECT COUNT(*) FROM collection_cards WHERE collection_id = c.id) total,
                  (SELECT COUNT(*) FROM collection_cards WHERE collection_id = c.id AND owned > 0) owned_count
                FROM collections c ORDER BY c.name"""),
            collection_cards=db.q("""SELECT id, collection_id, name, set_name, number, rarity, image_url, external_id,
                  market_price, owned, sort_key FROM collection_cards ORDER BY collection_id, sort_key, id"""),
        )

    # ---------------------------------------------------------------- opérations
    def apply_ops(self, device_id: str, device_name: str, ops: list[dict]) -> dict:
        db = self.db
        db.exec("""INSERT INTO sync_devices(id, name, created_at, last_sync) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name = excluded.name, last_sync = excluded.last_sync""",
                (device_id, device_name, now(), now()))
        results, summary = [], {}
        for op in ops:
            uid = str(op.get("uuid") or "")
            if not uid:
                continue
            done = db.one("SELECT ref FROM sync_ops WHERE uuid = ?", (uid,))
            if done:
                results.append(dict(uuid=uid, ok=True, ref=done["ref"], duplicate=True))
                continue
            try:
                with db.tx():
                    ref = self._apply(op["type"], op.get("data") or {}, op.get("date") or now())
                    db.insert("sync_ops", dict(uuid=uid, device_id=device_id, type=op["type"], ref=str(ref or ""),
                                               applied_at=now()))
                results.append(dict(uuid=uid, ok=True, ref=ref))
                summary[op["type"]] = summary.get(op["type"], 0) + 1
            except Exception as e:  # noqa: BLE001 - une opération invalide ne bloque pas les autres
                results.append(dict(uuid=uid, ok=False, error=str(e)))
        return dict(results=results, summary=summary)

    def _ref(self, uuid) -> int | None:
        """Identifiant PC d'un objet créé sur le téléphone (collection, carte…) à partir de l'uuid de son opération."""
        r = self.db.one("SELECT ref FROM sync_ops WHERE uuid = ?", (uuid,)) if uuid else None
        return int(r["ref"]) if r and r["ref"] else None

    def _product(self, pid):
        return self.db.one("SELECT * FROM products WHERE id = ?", (pid,)) if pid else None

    def _lines(self, raw_lines) -> list[dict]:
        lines = []
        for l in raw_lines:
            p = self._product(l.get("product_id"))
            lines.append(dict(product_id=p["id"] if p else None, name=str(l.get("name") or (p and p["name"]) or "Article"),
                              qty=max(1, int(l.get("qty") or 1)), unit_price=round(float(l.get("unit_price") or 0), 2),
                              unit_cost=p["cost"] if p else 0.0))
        if not lines:
            raise ValueError("Aucune ligne")
        return lines

    def _apply(self, kind: str, d: dict, date: str):
        svc = self.svc
        if kind == "sale":
            lines = self._lines(d.get("lines") or [])
            total = round(max(0.0, sum(l["qty"] * l["unit_price"] for l in lines) - float(d.get("discount") or 0)), 2)
            pay = d.get("payment") if d.get("payment") in MOBILE_PAYMENTS else "Espèces"
            sid = svc.create_sale(
                lines, d.get("customer_id") or None, float(d.get("discount") or 0),
                paid_cash=total if pay == "Espèces" else 0.0,
                paid_other=total if pay != "Espèces" else 0.0, other_label=pay,
                channel="Hors boutique (mobile)", notes=str(d.get("notes") or ""), date=date)
            return sid
        if kind == "order":
            lines = self._lines(d.get("lines") or [])
            header = dict(channel=str(d.get("channel") or "Autre"), external_ref=str(d.get("external_ref") or ""),
                          customer_name=str(d.get("customer_name") or ""), address=str(d.get("address") or ""),
                          shipping=float(d.get("shipping") or 0), notes=str(d.get("notes") or ""),
                          status=d.get("status") if d.get("status") in ORDER_STATUSES else "À préparer",
                          tracking=str(d.get("tracking") or ""))
            return svc.create_order(header, lines, date=date)
        if kind == "order_status":
            oid = d.get("order_id")
            if not oid and d.get("order_uuid"):  # commande créée sur le téléphone, pas encore connue par son id
                r = self.db.one("SELECT ref FROM sync_ops WHERE uuid = ?", (d["order_uuid"],))
                oid = int(r["ref"]) if r and r["ref"] else None
            if not oid:
                raise ValueError("Commande introuvable")
            status = d.get("status")
            if status not in ORDER_STATUSES:
                raise ValueError("Statut invalide")
            svc.set_order_status(int(oid), status, d.get("tracking"))
            return oid
        if kind == "stock":
            p = self._product(d.get("product_id"))
            if not p:
                raise ValueError("Article introuvable")
            delta = int(d.get("delta") or 0)
            svc.adjust_stock(p["id"], delta, STOCK_REASONS_MOBILE.get(d.get("reason"), "Correction"), "Mobile", date)
            return p["id"]
        # ---------------------------------------------------------- collections
        if kind == "collection_create":
            name = str(d.get("name") or "").strip()
            if not name:
                raise ValueError("Nom de collection vide")
            return self.db.insert("collections", dict(name=name, game=str(d.get("game") or ""),
                                                      description=str(d.get("description") or ""), created_at=date))
        if kind == "collection_add_card":
            cid = d.get("collection_id") or self._ref(d.get("collection_uuid"))
            if not cid or not self.db.one("SELECT id FROM collections WHERE id = ?", (cid,)):
                raise ValueError("Collection introuvable")
            n = self.db.val("SELECT COALESCE(MAX(sort_key), 0) FROM collection_cards WHERE collection_id = ?", (cid,), 0)
            return self.db.insert("collection_cards", dict(
                collection_id=cid, name=str(d.get("name") or "Carte"), set_name=str(d.get("set_name") or ""),
                number=str(d.get("number") or ""), rarity=str(d.get("rarity") or ""),
                image_url=str(d.get("image_url") or ""), external_id=str(d.get("external_id") or ""),
                market_price=float(d.get("market_price") or 0), owned=max(0, int(d.get("owned") or 0)),
                sort_key=int(n) + 1))
        if kind == "collection_owned":
            card = d.get("card_id") or self._ref(d.get("card_uuid"))
            if not card:
                raise ValueError("Carte introuvable")
            self.db.exec("UPDATE collection_cards SET owned = MAX(0, owned + ?) WHERE id = ?",
                         (int(d.get("delta") or 0), card))
            return card
        if kind == "collection_import_set":  # le PC télécharge l'extension complète (prix, raretés…)
            from . import api
            game, code, name = str(d.get("game") or ""), str(d.get("code") or ""), str(d.get("name") or "")
            cards = api.set_cards(game, code)
            if not cards:
                raise ValueError(f"Extension « {name} » introuvable")
            cid = self.db.insert("collections", dict(name=name or code, game=game, created_at=date,
                                                     description=f"Extension complète ({len(cards)} cartes)"))
            for i, c in enumerate(cards):
                self.db.insert("collection_cards", dict(
                    collection_id=cid, name=c["name"], set_name=c["set_name"], number=c["number"], rarity=c["rarity"],
                    image_url=c["image_url"], external_id=c["external_id"], market_price=c["market_price"], owned=0,
                    sort_key=i))
            return cid
        # ---------------------------------------------------------- rachats (conventions)
        if kind == "buy":
            cust_id = d.get("customer_id")
            new = d.get("customer") or {}
            if not cust_id and str(new.get("name") or "").strip():
                cust_id = svc.save_customer({k: str(new.get(k) or "").strip() for k in
                                             ("name", "phone", "email", "address", "id_type", "id_number")})
            elif cust_id and (new.get("id_number") or new.get("id_type")):
                # pièce d'identité saisie sur le téléphone pour un client existant
                self.db.update("customers", int(cust_id), {k: str(new.get(k) or "") for k in ("id_type", "id_number")
                                                           if new.get(k)})
            payout = d.get("payout") if d.get("payout") in MOBILE_PAYOUTS else "Espèces"
            if payout == "Crédit boutique" and not cust_id:
                raise ValueError("Crédit boutique impossible sans client")
            coef = self.db.setting_float("price_coef", 1.0)
            lines = []
            for l in d.get("lines") or []:
                p = self._product(l.get("product_id"))
                market = round(float(l.get("market_price") or 0), 2)
                line = dict(product_id=p["id"] if p else None, name=str(l.get("name") or (p and p["name"]) or "Article"),
                            game=str(l.get("game") or (p and p["game"]) or ""),
                            set_name=str(l.get("set_name") or (p and p["set_name"]) or ""),
                            condition=str(l.get("condition") or "NM"), qty=max(1, int(l.get("qty") or 1)),
                            market_price=market, offer_price=round(float(l.get("offer_price") or 0), 2))
                if not p:  # nouvelle fiche article créée à la réception du rachat
                    line["product"] = dict(
                        name=line["name"], game=line["game"], set_name=line["set_name"],
                        set_code=str(l.get("set_code") or ""), number=str(l.get("number") or ""),
                        rarity=str(l.get("rarity") or ""), image_url=str(l.get("image_url") or ""),
                        external_id=str(l.get("external_id") or ""), language=str(l.get("language") or "FR"),
                        category=str(l.get("category") or "Carte"), condition=line["condition"],
                        market_price=market, price=round(market * coef, 2))
                lines.append(line)
            if not lines:
                raise ValueError("Rachat vide")
            notes = "Rachat hors boutique (mobile)" + (f" · {d['notes']}" if d.get("notes") else "")
            return svc.create_buy(lines, int(cust_id) if cust_id else None, payout, notes, date=date)
        raise ValueError(f"Opération inconnue : {kind}")


# ====================================================================== serveur HTTP / HTTPS
WEBAPP_DIR = Path(__file__).resolve().parent / "resources" / "webapp"
HTTPS_PORT = 8443
_CTYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".json": "application/json",
           ".wasm": "application/wasm", ".png": "image/png", ".ttf": "font/ttf", ".otf": "font/otf",
           ".css": "text/css", ".ico": "image/x-icon", ".frag": "text/plain", ".bin": "application/octet-stream"}

GUIDE_HTML = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>TCShop sur iPhone</title>
<style>body{{font-family:-apple-system,sans-serif;background:#0E1120;color:#e7e9f5;margin:0;padding:22px;line-height:1.45}}
h1{{color:#8f72ff}}.step{{background:#161a2e;border-radius:14px;padding:16px;margin:14px 0}}
.n{{display:inline-block;background:#7c5cff;border-radius:50%;width:28px;height:28px;text-align:center;line-height:28px;
margin-right:8px;font-weight:bold}}a.btn{{display:block;background:#7c5cff;color:#fff;text-align:center;padding:14px;
border-radius:12px;text-decoration:none;font-weight:bold;margin-top:12px}}small{{color:#8b91b0}}</style></head><body>
<h1>TCShop sur iPhone</h1><p><small>À faire une seule fois, dans <b>Safari</b>.</small></p>
<div class="step"><span class="n">1</span><b>Installer le certificat de sécurité</b>
<a class="btn" href="/ca.crt">Télécharger le certificat TCShop</a>
<p><small>Safari demande d'autoriser le téléchargement du profil : touchez « Autoriser ».</small></p></div>
<div class="step"><span class="n">2</span><b>L'activer</b><p>Réglages → <b>Profil téléchargé</b> → Installer.<br>
Puis Réglages → Général → Informations → <b>Réglages des certificats</b> → activez « TCShop ».</p></div>
<div class="step"><span class="n">3</span><b>Ouvrir TCShop</b><a class="btn" href="{app_url}">Ouvrir TCShop</a></div>
<div class="step"><span class="n">4</span><b>L'ajouter à l'écran d'accueil</b><p>Dans Safari : bouton Partager → <b>Sur l'écran
d'accueil</b>. Ouvrez ensuite TCShop depuis son icône.</p></div></body></html>"""


def iphone_guide_url(db: Database) -> str:
    port = int(db.setting_float("sync_port", DEFAULT_PORT))
    return f"http://{local_ips()[0]}:{port}/iphone?t={ensure_token(db)}"


class _Handler(BaseHTTPRequestHandler):
    server_version = "TCShopSync/1.0"
    logic: SyncLogic
    token: str
    https = False
    https_port = 8443
    on_synced = None

    def log_message(self, *_):  # pas de sortie console
        pass

    def _send(self, code: int, payload=None, raw: bytes | None = None, ctype="application/json; charset=utf-8",
              headers: dict | None = None):
        body = raw if raw is not None else json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, query) -> bool:
        tok = self.headers.get("X-TCShop-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(tok, self.token)

    def _static(self, rel: str):
        """Appli iPhone (Flutter web) servie en HTTPS sous /app/."""
        rel = rel or "index.html"
        p = (WEBAPP_DIR / rel).resolve()
        if WEBAPP_DIR.resolve() not in p.parents or not p.is_file():
            p = WEBAPP_DIR / "index.html"
        if not p.is_file():
            return self._send(404, dict(error="Appli iPhone absente de cette installation"))
        # pas de cache navigateur : c'est le service worker de l'appli qui gère le hors ligne (et les mises à jour)
        return self._send(200, raw=p.read_bytes(), ctype=_CTYPES.get(p.suffix.lower(), "application/octet-stream"),
                          headers={"Cache-Control": "no-cache"})

    def _remote_image(self, url: str):
        """Images des bases de cartes, relayées (et mises en cache) par le PC pour l'appli iPhone."""
        if not url.startswith(("http://", "https://")):
            return self._send(400, dict(error="URL invalide"))
        from .db import CACHE_DIR
        path = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".img")
        if not path.exists():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "TCShop/2.2", "Accept": "*/*"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = r.read()
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            except Exception:  # noqa: BLE001
                return self._send(404, dict(error="Image indisponible"))
        data = path.read_bytes()
        ctype = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
        return self._send(200, raw=data, ctype=ctype, headers={"Cache-Control": "max-age=86400"})

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if url.path == "/api/ping":
            return self._send(200, dict(app=APP_NAME, version=APP_VERSION, shop=self.logic.db.setting("shop_name")))
        if url.path == "/ca.crt":  # certificat public de l'autorité TCShop (à installer sur l'iPhone)
            from .certs import ca_der
            return self._send(200, raw=ca_der(), ctype="application/x-x509-ca-cert",
                              headers={"Content-Disposition": 'attachment; filename="TCShop.crt"'})
        if self.https and (url.path == "/app" or url.path.startswith("/app/")):
            if url.path == "/app":
                return self._send(301, raw=b"", headers={"Location": "/app/" + (f"?{url.query}" if url.query else "")})
            return self._static(url.path[len("/app/"):])
        if not self._authorized(q):
            return self._send(401, dict(error="Clé invalide : réassociez le téléphone (QR code)."))
        if url.path == "/iphone":  # page guide ouverte en scannant le QR code avec l'appareil photo de l'iPhone
            host = self.headers.get("Host", "").split(":")[0] or local_ips()[0]
            app_url = f"https://{host}:{self.https_port}/app/?t={self.token}"
            return self._send(200, raw=GUIDE_HTML.format(app_url=app_url).encode("utf-8"), ctype="text/html; charset=utf-8")
        if url.path == "/api/catalog":
            return self._send(200, self.logic.catalog())
        if url.path == "/api/image":
            if q.get("url"):
                return self._remote_image(q["url"][0])
            rel = (q.get("path") or [""])[0]  # photos locales des produits (dossier images des données)
            p = (DATA_DIR / rel).resolve()
            if DATA_DIR.resolve() in p.parents and p.is_file():
                ext = p.suffix.lower().lstrip(".")
                return self._send(200, raw=p.read_bytes(), ctype=f"image/{'jpeg' if ext == 'jpg' else ext}")
            return self._send(404, dict(error="Image introuvable"))
        self._send(404, dict(error="Inconnu"))

    def do_POST(self):  # noqa: N802
        url = urlparse(self.path)
        if not self._authorized(parse_qs(url.query)):
            return self._send(401, dict(error="Clé invalide : réassociez le téléphone (QR code)."))
        if url.path != "/api/sync":
            return self._send(404, dict(error="Inconnu"))
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            res = self.logic.apply_ops(str(data.get("device_id") or "?"), str(data.get("device_name") or "Téléphone"),
                                       data.get("ops") or [])
        except Exception as e:  # noqa: BLE001
            return self._send(400, dict(error=str(e)))
        if res["summary"] and self.on_synced:
            self.on_synced(str(data.get("device_name") or "Téléphone"), res["summary"])
        self._send(200, res)


class SyncServer(QObject):
    """Serveurs de synchro (HTTP pour Android, HTTPS pour l'iPhone), chacun dans son thread.
    Le signal `synced` est reçu dans le thread de l'interface."""

    synced = Signal(str, dict)
    status_changed = Signal(str)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.httpd: HTTPServer | None = None
        self.httpsd: HTTPServer | None = None
        self.udp: socket.socket | None = None
        self.error = ""
        self.https_error = ""
        self.https_port = HTTPS_PORT

    @property
    def running(self) -> bool:
        return self.httpd is not None

    def _make(self, port: int, token: str, https: bool, https_port: int) -> HTTPServer:
        # la logique (et sa connexion SQLite) est créée dans le thread du serveur, qui est mono-thread
        handler = type("Handler", (_Handler,), dict(
            logic=None, token=token, https=https, https_port=https_port,
            on_synced=staticmethod(lambda name, s: self.synced.emit(name, s))))
        return HTTPServer(("0.0.0.0", port), handler)

    def start(self) -> bool:
        if self.httpd:
            return True
        db = self.ctx.db
        port = int(db.setting_float("sync_port", DEFAULT_PORT))
        token = ensure_token(db)
        https_port = int(db.setting_float("sync_https_port", HTTPS_PORT))
        self.https_port = https_port
        try:
            self.httpd = self._make(port, token, https=False, https_port=https_port)
        except OSError as e:
            self.error = f"Port {port} indisponible ({e.strerror or e})"
            self.status_changed.emit(self.error)
            return False
        threading.Thread(target=self._serve, args=(self.httpd, db.path), daemon=True).start()
        # HTTPS pour l'appli iPhone (Safari exige HTTPS pour l'appareil photo et le mode hors ligne)
        try:
            from .certs import ensure_server_cert
            crt, key = ensure_server_cert(local_ips())
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(crt, key)
            self.httpsd = self._make(https_port, token, https=True, https_port=https_port)
            self.httpsd.socket = ssl_ctx.wrap_socket(self.httpsd.socket, server_side=True)
            threading.Thread(target=self._serve, args=(self.httpsd, db.path), daemon=True).start()
            self.https_error = ""
        except Exception as e:  # noqa: BLE001 - Android fonctionne même sans HTTPS
            self.httpsd = None
            self.https_error = f"HTTPS (iPhone) indisponible : {e}"
        # la réponse est préparée ici : le thread de découverte ne doit pas toucher à la base de l'interface
        reply = json.dumps(dict(app=APP_NAME, port=port, shop=db.setting("shop_name"))).encode()
        threading.Thread(target=self._discovery, args=(reply,), daemon=True).start()
        self.error = ""
        self.status_changed.emit(f"Actif sur {local_ips()[0]}:{port}")
        return True

    def _serve(self, server: HTTPServer, db_path):
        server.RequestHandlerClass.logic = SyncLogic(db_path)  # connexion SQLite créée dans ce thread
        try:
            server.serve_forever(poll_interval=0.5)
        except Exception:  # noqa: BLE001
            pass

    def _discovery(self, reply: bytes):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", DISCOVERY_PORT))
            self.udp = s
            while self.httpd:
                try:
                    data, addr = s.recvfrom(256)
                except OSError:
                    break
                if data.strip() == b"TCSHOP_DISCOVER":
                    s.sendto(reply, addr)
        except OSError:
            pass

    def stop(self):
        for attr in ("httpd", "httpsd"):
            srv = getattr(self, attr)
            if srv:
                setattr(self, attr, None)
                threading.Thread(target=srv.shutdown, daemon=True).start()
        if self.udp:
            try:
                self.udp.close()
            except OSError:
                pass
            self.udp = None
        self.status_changed.emit("Arrêté")
