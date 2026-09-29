"""Accès à la base SQLite locale."""
from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# Données dans le profil utilisateur : un programme installé ne peut pas écrire dans son propre dossier.
# (variable TCSHOP_DATA pour choisir un autre emplacement, ex. un dossier synchronisé)
DATA_DIR = Path(os.environ.get("TCSHOP_DATA") or Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TCShop")
LEGACY_DATA_DIR = BASE_DIR / "data"  # emplacement utilisé par les versions « TCG Manager » 1.x
CACHE_DIR = DATA_DIR / "cache"
BACKUP_DIR = DATA_DIR / "backups"
DB_PATH = DATA_DIR / "tcg.db"


def migrate_legacy_data() -> bool:
    """Au premier lancement de TCShop, reprend les données de l'ancien dossier « data » (base, photos, sauvegardes)."""
    old_db = LEGACY_DATA_DIR / "tcg.db"
    if DB_PATH.exists() or not old_db.exists():
        return False
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(old_db))
    dst = sqlite3.connect(str(DB_PATH))
    with dst:
        src.backup(dst)  # copie cohérente, même avec un journal WAL en cours
    src.close()
    dst.close()
    for sub in ("images", "backups", "cache"):
        if (LEGACY_DATA_DIR / sub).is_dir():
            shutil.copytree(LEGACY_DATA_DIR / sub, DATA_DIR / sub, dirs_exist_ok=True)
    return True

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT DEFAULT '', barcode TEXT DEFAULT '',
    name TEXT NOT NULL, game TEXT DEFAULT '', category TEXT DEFAULT 'Carte',
    set_name TEXT DEFAULT '', set_code TEXT DEFAULT '', number TEXT DEFAULT '', rarity TEXT DEFAULT '',
    language TEXT DEFAULT 'FR', condition TEXT DEFAULT 'NM', finish TEXT DEFAULT 'Normale',
    location TEXT DEFAULT '', quantity INTEGER DEFAULT 0, min_stock INTEGER DEFAULT 0,
    cost REAL DEFAULT 0, price REAL DEFAULT 0, market_price REAL DEFAULT 0,
    online INTEGER DEFAULT 1, image_url TEXT DEFAULT '', external_id TEXT DEFAULT '', notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);

-- codes-barres supplémentaires (le code principal est products.barcode)
CREATE TABLE IF NOT EXISTS barcodes (
    code TEXT PRIMARY KEY COLLATE NOCASE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_barcodes_product ON barcodes(product_id);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, email TEXT DEFAULT '', phone TEXT DEFAULT '', address TEXT DEFAULT '',
    id_type TEXT DEFAULT '', id_number TEXT DEFAULT '',
    credit REAL DEFAULT 0, points INTEGER DEFAULT 0, notes TEXT DEFAULT '', created_at TEXT
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT, date TEXT, customer_id INTEGER, channel TEXT DEFAULT 'Boutique',
    subtotal REAL DEFAULT 0, discount REAL DEFAULT 0, total REAL DEFAULT 0, cost_total REAL DEFAULT 0,
    payment TEXT DEFAULT '', paid_cash REAL DEFAULT 0, paid_card REAL DEFAULT 0, paid_credit REAL DEFAULT 0,
    cash_given REAL DEFAULT 0, change_given REAL DEFAULT 0, points_earned INTEGER DEFAULT 0,
    status TEXT DEFAULT 'Validée', notes TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(date);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER REFERENCES sales(id) ON DELETE CASCADE,
    product_id INTEGER, name TEXT, qty INTEGER, unit_price REAL, unit_cost REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS buys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT, date TEXT, customer_id INTEGER, customer_name TEXT DEFAULT '',
    id_type TEXT DEFAULT '', id_number TEXT DEFAULT '',
    payout TEXT, total REAL DEFAULT 0, market_total REAL DEFAULT 0, notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS buy_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buy_id INTEGER REFERENCES buys(id) ON DELETE CASCADE,
    product_id INTEGER, name TEXT, game TEXT DEFAULT '', set_name TEXT DEFAULT '', condition TEXT DEFAULT '',
    qty INTEGER, market_price REAL DEFAULT 0, offer_price REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT, external_ref TEXT DEFAULT '', date TEXT, channel TEXT, customer_id INTEGER,
    customer_name TEXT DEFAULT '', address TEXT DEFAULT '', status TEXT DEFAULT 'À préparer',
    shipping REAL DEFAULT 0, total REAL DEFAULT 0, cost_total REAL DEFAULT 0,
    tracking TEXT DEFAULT '', notes TEXT DEFAULT '', updated_at TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER, name TEXT, qty INTEGER, unit_price REAL, unit_cost REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT, product_id INTEGER, product_name TEXT, delta INTEGER, reason TEXT, ref TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_movements_date ON movements(date);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, game TEXT DEFAULT '', description TEXT DEFAULT '', created_at TEXT
);

CREATE TABLE IF NOT EXISTS collection_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
    name TEXT, set_name TEXT DEFAULT '', number TEXT DEFAULT '', rarity TEXT DEFAULT '',
    image_url TEXT DEFAULT '', external_id TEXT DEFAULT '', market_price REAL DEFAULT 0,
    owned INTEGER DEFAULT 0, sort_key INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, contact TEXT DEFAULT '', email TEXT DEFAULT '', phone TEXT DEFAULT '',
    website TEXT DEFAULT '', account_ref TEXT DEFAULT '', min_order REAL DEFAULT 0, notes TEXT DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT, supplier_id INTEGER REFERENCES suppliers(id), date TEXT,
    status TEXT DEFAULT 'Brouillon', total REAL DEFAULT 0, notes TEXT DEFAULT '', received_at TEXT
);

CREATE TABLE IF NOT EXISTS purchase_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id INTEGER REFERENCES purchase_orders(id) ON DELETE CASCADE,
    product_id INTEGER, name TEXT, qty INTEGER DEFAULT 1, unit_cost REAL DEFAULT 0, received_qty INTEGER DEFAULT 0
);

-- synchronisation avec TCShop Mobile
CREATE TABLE IF NOT EXISTS sync_devices (id TEXT PRIMARY KEY, name TEXT, created_at TEXT, last_sync TEXT);
CREATE TABLE IF NOT EXISTS sync_ops (
    uuid TEXT PRIMARY KEY, device_id TEXT, type TEXT, ref TEXT DEFAULT '', applied_at TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE, date TEXT, market_price REAL
);
"""

DEFAULT_SETTINGS = {
    "shop_name": "Ma Boutique TCG",
    "shop_address": "",
    "shop_phone": "",
    "shop_email": "",
    "shop_siret": "",
    "vat_rate": "20",
    "buy_rate_cash": "50",
    "buy_rate_credit": "65",
    "price_coef": "1.0",
    "points_per_euro": "1",
    "points_for_euro": "20",
    "theme": "Sombre",
    "ticket_footer": "Merci de votre visite et à bientôt !",
}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: Path = DB_PATH):
        if Path(path) == DB_PATH:
            migrate_legacy_data()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self._depth = 0
        self._migrate()
        for k, v in DEFAULT_SETTINGS.items():
            self.conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        self.conn.commit()

    def _migrate(self):
        """Ajoute les colonnes des nouvelles versions aux bases existantes (sans perte de données)."""
        added = {
            "products": [
                ("brand", "TEXT DEFAULT ''"),          # marque / éditeur
                ("variant", "TEXT DEFAULT ''"),        # couleur, taille, format…
                ("supplier_id", "INTEGER"),
                ("vat_rate", "REAL"),                  # NULL = taux par défaut
                ("track_stock", "INTEGER DEFAULT 1"),  # 0 = prestation sans stock
                ("favorite", "INTEGER DEFAULT 0"),     # touche rapide en caisse
                ("reorder_qty", "INTEGER DEFAULT 0"),  # quantité de réassort habituelle
                ("short_name", "TEXT DEFAULT ''"),     # nom court imprimé sur les étiquettes
            ],
            "sale_items": [("vat_rate", "REAL DEFAULT 20")],
            "sales": [("paid_other", "REAL DEFAULT 0"),      # virement, Wero…
                      ("other_label", "TEXT DEFAULT ''")],
        }
        for table, cols in added.items():
            existing = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
        self.conn.commit()

    # --- lecture ---
    def q(self, sql: str, params=()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params=()) -> dict | None:
        r = self.conn.execute(sql, params).fetchone()
        return dict(r) if r else None

    def val(self, sql: str, params=(), default=None):
        r = self.conn.execute(sql, params).fetchone()
        if r is None or r[0] is None:
            return default
        return r[0]

    # --- écriture ---
    def exec(self, sql: str, params=()) -> int:
        cur = self.conn.execute(sql, params)
        if self._depth == 0:
            self.conn.commit()
        return cur.lastrowid

    @contextmanager
    def tx(self):
        """Transaction imbriquable : commit uniquement au niveau le plus externe."""
        self._depth += 1
        try:
            yield
        except Exception:
            self._depth -= 1
            if self._depth == 0:
                self.conn.rollback()
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self.conn.commit()

    def insert(self, table: str, data: dict) -> int:
        keys = list(data.keys())
        sql = f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})"
        return self.exec(sql, [data[k] for k in keys])

    def update(self, table: str, row_id: int, data: dict):
        keys = list(data.keys())
        sql = f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in keys)} WHERE id = ?"
        self.exec(sql, [data[k] for k in keys] + [row_id])

    # --- paramètres ---
    def setting(self, key: str, default: str = "") -> str:
        v = self.val("SELECT value FROM settings WHERE key = ?", (key,))
        return default if v is None else v

    def setting_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(str(self.setting(key, str(default))).replace(",", "."))
        except ValueError:
            return default

    def set_setting(self, key: str, value) -> None:
        self.exec("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, str(value)))

    # --- sauvegardes ---
    def backup(self, dest: Path | None = None, keep: int = 15) -> Path:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        dest = Path(dest) if dest else BACKUP_DIR / f"tcg_{datetime.now():%Y%m%d_%H%M%S}.db"
        target = sqlite3.connect(str(dest))
        with target:
            self.conn.backup(target)
        target.close()
        if dest.parent == BACKUP_DIR:
            olds = sorted(BACKUP_DIR.glob("tcg_*.db"))
            for f in olds[:-keep]:
                f.unlink(missing_ok=True)
        return dest

    def restore(self, src: Path) -> None:
        self.conn.close()
        shutil.copyfile(src, self.path)
        for ext in ("-wal", "-shm"):
            Path(str(self.path) + ext).unlink(missing_ok=True)
