"""Logique métier : stock, ventes, rachats, commandes, clients."""
from __future__ import annotations

from datetime import datetime

from .barcode import normalize_scan
from .constants import DEFAULT_VAT_BY_CATEGORY, NO_STOCK_CATEGORIES
from .db import Database, now


class Services:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------ utils
    def next_number(self, prefix: str) -> str:
        key = f"counter_{prefix}"
        n = int(self.db.setting(key, "0")) + 1
        self.db.set_setting(key, n)
        return f"{prefix}{datetime.now():%y%m}-{n:05d}"

    # ------------------------------------------------------------------ stock
    def adjust_stock(self, product_id: int, delta: int, reason: str, ref: str = "", date: str | None = None):
        if not product_id or not delta:
            return
        p = self.db.one("SELECT name, set_name, variant, track_stock FROM products WHERE id = ?", (product_id,))
        if p and p["track_stock"] == 0:
            return  # prestation (tournoi, service…) : pas de stock
        extra = (p["set_name"] or p["variant"]) if p else ""
        name = f"{p['name']} ({extra})" if p and extra else (p["name"] if p else "?")
        with self.db.tx():
            self.db.exec(
                "UPDATE products SET quantity = quantity + ?, updated_at = ? WHERE id = ?",
                (delta, now(), product_id),
            )
            self.db.insert(
                "movements",
                dict(date=date or now(), product_id=product_id, product_name=name, delta=delta, reason=reason, ref=ref),
            )

    def save_product(self, data: dict, product_id: int | None = None) -> int:
        data = dict(data)
        data["updated_at"] = now()
        with self.db.tx():
            if product_id:
                old = self.db.one("SELECT quantity, market_price FROM products WHERE id = ?", (product_id,))
                new_qty = data.pop("quantity", None)
                self.db.update("products", product_id, data)
                if new_qty is not None and old and int(new_qty) != int(old["quantity"]):
                    self.adjust_stock(product_id, int(new_qty) - int(old["quantity"]), "Correction", "Fiche produit")
                if old and data.get("market_price") and abs(float(data["market_price"]) - float(old["market_price"] or 0)) > 0.001:
                    self.log_price(product_id, float(data["market_price"]))
                return product_id
            qty = int(data.pop("quantity", 0) or 0)
            data["quantity"] = 0
            data["created_at"] = now()
            if "track_stock" not in data:
                data["track_stock"] = 0 if data.get("category") in NO_STOCK_CATEGORIES else 1
            pid = self.db.insert("products", data)
            if not data.get("sku"):
                self.db.exec("UPDATE products SET sku = ? WHERE id = ?", (f"TCG{pid:06d}", pid))
            if qty:
                self.adjust_stock(pid, qty, "Création", "Fiche produit")
            if data.get("market_price"):
                self.log_price(pid, float(data["market_price"]))
            return pid

    def vat_for(self, product: dict | None) -> float:
        """Taux de TVA d'un article : le sien, sinon celui de sa catégorie, sinon le taux normal."""
        if product and product.get("vat_rate") is not None:
            return float(product["vat_rate"])
        if product and product.get("category") in DEFAULT_VAT_BY_CATEGORY:
            return DEFAULT_VAT_BY_CATEGORY[product["category"]]
        return self.db.setting_float("vat_rate", 20)

    def log_price(self, product_id: int, price: float):
        self.db.insert("price_history", dict(product_id=product_id, date=now(), market_price=price))

    def delete_product(self, product_id: int):
        self.db.exec("DELETE FROM products WHERE id = ?", (product_id,))

    def find_by_code(self, code: str) -> dict | None:
        """Retrouve un article par code-barres principal, code supplémentaire ou SKU."""
        raw = (code or "").strip()
        if not raw:
            return None
        for c in dict.fromkeys((raw, normalize_scan(raw))):
            p = self.db.one(
                """SELECT * FROM products WHERE barcode = ? COLLATE NOCASE OR sku = ? COLLATE NOCASE
                   OR id = (SELECT product_id FROM barcodes WHERE code = ?) LIMIT 1""", (c, c, c))
            if p:
                return p
        return None

    def barcode_owner(self, code: str, exclude_id: int | None = None) -> dict | None:
        """Article qui utilise déjà ce code (principal, supplémentaire ou SKU), hors exclude_id."""
        code = (code or "").strip()
        if not code:
            return None
        return self.db.one(
            """SELECT id, name, set_name FROM products WHERE id != ? AND (barcode = ? COLLATE NOCASE
               OR sku = ? COLLATE NOCASE OR id = (SELECT product_id FROM barcodes WHERE code = ?)) LIMIT 1""",
            (exclude_id or 0, code, code, code))

    def product_codes(self, product_id: int) -> list[str]:
        p = self.db.one("SELECT barcode FROM products WHERE id = ?", (product_id,))
        extra = [r["code"] for r in self.db.q("SELECT code FROM barcodes WHERE product_id = ? ORDER BY created_at",
                                                (product_id,))]
        return ([p["barcode"]] if p and p["barcode"] else []) + extra

    def link_barcode(self, product_id: int, code: str) -> None:
        """Associe un code à un article : devient le code principal s'il n'en a pas, sinon code supplémentaire."""
        code = normalize_scan(code)
        if not code:
            raise ValueError("Code vide.")
        owner = self.barcode_owner(code, product_id)
        if owner:
            raise ValueError(f"Ce code est déjà associé à « {owner['name']} ».")
        if code.lower() in (c.lower() for c in self.product_codes(product_id)):
            return
        p = self.db.one("SELECT barcode FROM products WHERE id = ?", (product_id,))
        with self.db.tx():
            if not p["barcode"]:
                self.db.exec("UPDATE products SET barcode = ?, updated_at = ? WHERE id = ?", (code, now(), product_id))
            else:
                self.db.insert("barcodes", dict(code=code, product_id=product_id, created_at=now()))

    def unlink_barcode(self, product_id: int, code: str) -> None:
        with self.db.tx():
            p = self.db.one("SELECT barcode FROM products WHERE id = ?", (product_id,))
            if p and p["barcode"].lower() == code.lower():
                # le premier code supplémentaire devient le code principal
                nxt = self.db.one("SELECT code FROM barcodes WHERE product_id = ? ORDER BY created_at LIMIT 1",
                                  (product_id,))
                self.db.exec("UPDATE products SET barcode = ? WHERE id = ?", (nxt["code"] if nxt else "", product_id))
                if nxt:
                    self.db.exec("DELETE FROM barcodes WHERE code = ?", (nxt["code"],))
            else:
                self.db.exec("DELETE FROM barcodes WHERE code = ? AND product_id = ?", (code, product_id))

    # ------------------------------------------------------------------ clients
    def save_customer(self, data: dict, customer_id: int | None = None) -> int:
        if customer_id:
            self.db.update("customers", customer_id, data)
            return customer_id
        data = dict(data)
        data["created_at"] = now()
        return self.db.insert("customers", data)

    def adjust_credit(self, customer_id: int, delta: float):
        self.db.exec("UPDATE customers SET credit = ROUND(credit + ?, 2) WHERE id = ?", (delta, customer_id))

    def convert_points(self, customer_id: int) -> float:
        """Convertit les points fidélité en crédit boutique. Renvoie le montant crédité."""
        c = self.db.one("SELECT points FROM customers WHERE id = ?", (customer_id,))
        per_euro = max(1, int(self.db.setting_float("points_for_euro", 20)))
        euros = (c["points"] // per_euro) if c else 0
        if euros <= 0:
            return 0.0
        with self.db.tx():
            self.db.exec("UPDATE customers SET points = points - ? WHERE id = ?", (euros * per_euro, customer_id))
            self.adjust_credit(customer_id, float(euros))
        return float(euros)

    # ------------------------------------------------------------------ ventes
    def create_sale(
        self,
        lines: list[dict],
        customer_id: int | None,
        discount: float,
        paid_cash: float = 0.0,
        paid_card: float = 0.0,
        paid_credit: float = 0.0,
        cash_given: float = 0.0,
        channel: str = "Boutique",
        paid_other: float = 0.0,
        other_label: str = "Virement",
        notes: str = "",
        date: str | None = None,
    ) -> int:
        subtotal = round(sum(l["qty"] * l["unit_price"] for l in lines), 2)
        total = round(max(0.0, subtotal - discount), 2)
        cost_total = round(sum(l["qty"] * (l.get("unit_cost") or 0) for l in lines), 2)
        parts = [n for n, v in (("Espèces", paid_cash), ("Carte", paid_card), ("Crédit", paid_credit),
                                (other_label, paid_other)) if v > 0.004]
        payment = " + ".join(parts) if parts else "—"
        change = round(max(0.0, cash_given - paid_cash), 2) if cash_given else 0.0
        points = 0
        if customer_id:
            points = int(total * self.db.setting_float("points_per_euro", 1))
        number = self.next_number("V")
        with self.db.tx():
            sid = self.db.insert(
                "sales",
                dict(
                    number=number, date=date or now(), customer_id=customer_id, channel=channel,
                    subtotal=subtotal, discount=round(discount, 2), total=total, cost_total=cost_total,
                    payment=payment, paid_cash=round(paid_cash, 2), paid_card=round(paid_card, 2),
                    paid_credit=round(paid_credit, 2), cash_given=round(cash_given, 2), change_given=change,
                    paid_other=round(paid_other, 2), other_label=other_label if paid_other > 0.004 else "",
                    points_earned=points, status="Validée", notes=notes,
                ),
            )
            for l in lines:
                self.db.insert(
                    "sale_items",
                    dict(sale_id=sid, product_id=l.get("product_id"), name=l["name"], qty=l["qty"],
                         unit_price=l["unit_price"], unit_cost=l.get("unit_cost") or 0,
                         vat_rate=l["vat_rate"] if l.get("vat_rate") is not None else self.vat_for(
                             self.db.one("SELECT * FROM products WHERE id = ?", (l.get("product_id"),))
                             if l.get("product_id") else None)),
                )
                if l.get("product_id"):
                    self.adjust_stock(l["product_id"], -int(l["qty"]), "Vente", number, date)
            if customer_id:
                if paid_credit > 0:
                    self.adjust_credit(customer_id, -paid_credit)
                if points:
                    self.db.exec("UPDATE customers SET points = points + ? WHERE id = ?", (points, customer_id))
        return sid

    def refund_sale(self, sale_id: int):
        s = self.db.one("SELECT * FROM sales WHERE id = ?", (sale_id,))
        if not s or s["status"] != "Validée":
            raise ValueError("Cette vente ne peut pas être remboursée.")
        with self.db.tx():
            for it in self.db.q("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)):
                if it["product_id"]:
                    self.adjust_stock(it["product_id"], int(it["qty"]), "Retour client", s["number"])
            if s["customer_id"]:
                if s["paid_credit"]:
                    self.adjust_credit(s["customer_id"], s["paid_credit"])
                if s["points_earned"]:
                    self.db.exec(
                        "UPDATE customers SET points = MAX(0, points - ?) WHERE id = ?",
                        (s["points_earned"], s["customer_id"]),
                    )
            self.db.exec("UPDATE sales SET status = 'Remboursée' WHERE id = ?", (sale_id,))

    # ------------------------------------------------------------------ rachats
    def create_buy(
        self,
        lines: list[dict],
        customer_id: int | None,
        payout: str,
        notes: str = "",
        date: str | None = None,
    ) -> int:
        """lines : {product_id | None, product (dict pour création), name, game, set_name, condition,
        qty, market_price, offer_price}"""
        total = round(sum(l["qty"] * l["offer_price"] for l in lines), 2)
        market_total = round(sum(l["qty"] * l["market_price"] for l in lines), 2)
        cust = self.db.one("SELECT * FROM customers WHERE id = ?", (customer_id,)) if customer_id else None
        number = self.next_number("R")
        with self.db.tx():
            bid = self.db.insert(
                "buys",
                dict(
                    number=number, date=date or now(), customer_id=customer_id,
                    customer_name=cust["name"] if cust else "", id_type=cust["id_type"] if cust else "",
                    id_number=cust["id_number"] if cust else "", payout=payout, total=total,
                    market_total=market_total, notes=notes,
                ),
            )
            for l in lines:
                pid = l.get("product_id")
                if not pid:
                    pdata = dict(l.get("product") or {})
                    pdata.setdefault("name", l["name"])
                    pdata["quantity"] = 0
                    pdata["cost"] = l["offer_price"]
                    pid = self.save_product(pdata)
                else:
                    # prix de revient moyen pondéré
                    p = self.db.one("SELECT quantity, cost FROM products WHERE id = ?", (pid,))
                    q0 = max(0, int(p["quantity"] or 0))
                    new_cost = (q0 * float(p["cost"] or 0) + l["qty"] * l["offer_price"]) / max(1, q0 + l["qty"])
                    self.db.exec("UPDATE products SET cost = ? WHERE id = ?", (round(new_cost, 2), pid))
                self.db.insert(
                    "buy_items",
                    dict(buy_id=bid, product_id=pid, name=l["name"], game=l.get("game", ""),
                         set_name=l.get("set_name", ""), condition=l.get("condition", ""), qty=l["qty"],
                         market_price=l["market_price"], offer_price=l["offer_price"]),
                )
                self.adjust_stock(pid, int(l["qty"]), "Rachat", number, date)
            if customer_id and payout == "Crédit boutique":
                self.adjust_credit(customer_id, total)
        return bid

    # ------------------------------------------------------------------ commandes
    def create_order(self, header: dict, lines: list[dict], date: str | None = None) -> int:
        items_total = sum(l["qty"] * l["unit_price"] for l in lines)
        total = round(items_total + float(header.get("shipping") or 0), 2)
        cost_total = round(sum(l["qty"] * (l.get("unit_cost") or 0) for l in lines), 2)
        number = self.next_number("C")
        with self.db.tx():
            oid = self.db.insert(
                "orders",
                dict(
                    number=number, external_ref=header.get("external_ref", ""), date=date or now(),
                    channel=header.get("channel", "Site web"), customer_id=header.get("customer_id"),
                    customer_name=header.get("customer_name", ""), address=header.get("address", ""),
                    status=header.get("status", "À préparer"), shipping=float(header.get("shipping") or 0),
                    total=total, cost_total=cost_total, tracking=header.get("tracking", ""),
                    notes=header.get("notes", ""), updated_at=date or now(),
                ),
            )
            for l in lines:
                self.db.insert(
                    "order_items",
                    dict(order_id=oid, product_id=l.get("product_id"), name=l["name"], qty=l["qty"],
                         unit_price=l["unit_price"], unit_cost=l.get("unit_cost") or 0),
                )
                if l.get("product_id"):
                    self.adjust_stock(l["product_id"], -int(l["qty"]), "Commande en ligne", number, date)
        return oid

    def set_order_status(self, order_id: int, status: str, tracking: str | None = None):
        o = self.db.one("SELECT * FROM orders WHERE id = ?", (order_id,))
        if not o:
            return
        with self.db.tx():
            if status == "Annulée" and o["status"] != "Annulée":
                for it in self.db.q("SELECT * FROM order_items WHERE order_id = ?", (order_id,)):
                    if it["product_id"]:
                        self.adjust_stock(it["product_id"], int(it["qty"]), "Annulation commande", o["number"])
            elif o["status"] == "Annulée" and status != "Annulée":
                for it in self.db.q("SELECT * FROM order_items WHERE order_id = ?", (order_id,)):
                    if it["product_id"]:
                        self.adjust_stock(it["product_id"], -int(it["qty"]), "Commande en ligne", o["number"])
            data = dict(status=status, updated_at=now())
            if tracking is not None:
                data["tracking"] = tracking
            self.db.update("orders", order_id, data)

    # ------------------------------------------------------------------ fournisseurs / réassort
    def reorder_suggestions(self) -> list[dict]:
        """Articles sous le stock minimum, avec quantité conseillée et fournisseur."""
        rows = self.db.q("""
            SELECT p.*, COALESCE(s.name, '') supplier_name FROM products p
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE p.track_stock = 1 AND p.min_stock > 0 AND p.quantity <= p.min_stock
            ORDER BY supplier_name, p.category, p.name""")
        pending = {r["product_id"]: r["q"] for r in self.db.q(
            """SELECT pi.product_id, SUM(pi.qty - pi.received_qty) q FROM purchase_items pi
               JOIN purchase_orders po ON po.id = pi.po_id WHERE po.status IN ('Brouillon', 'Commandée')
               GROUP BY pi.product_id""")}
        out = []
        for r in rows:
            r["pending"] = pending.get(r["id"], 0) or 0
            base = r["reorder_qty"] or max(r["min_stock"] * 2 - r["quantity"], 1)
            r["suggested"] = max(0, base - r["pending"])
            if r["suggested"] > 0:
                out.append(r)
        return out

    def save_po(self, supplier_id: int | None, lines: list[dict], notes: str = "", po_id: int | None = None,
                status: str = "Brouillon") -> int:
        total = round(sum(l["qty"] * l["unit_cost"] for l in lines), 2)
        with self.db.tx():
            if po_id:
                self.db.update("purchase_orders", po_id, dict(supplier_id=supplier_id, total=total, notes=notes,
                                                              status=status))
                self.db.exec("DELETE FROM purchase_items WHERE po_id = ?", (po_id,))
            else:
                po_id = self.db.insert("purchase_orders", dict(number=self.next_number("F"), supplier_id=supplier_id,
                                                               date=now(), status=status, total=total, notes=notes))
            for l in lines:
                self.db.insert("purchase_items", dict(po_id=po_id, product_id=l.get("product_id"), name=l["name"],
                                                      qty=l["qty"], unit_cost=l["unit_cost"],
                                                      received_qty=l.get("received_qty", 0)))
        return po_id

    def receive_po(self, po_id: int, received: dict[int, int]) -> int:
        """Réceptionne une commande fournisseur. received = {purchase_item_id: quantité reçue maintenant}.
        Met à jour le stock et le prix d'achat moyen pondéré. Renvoie le nombre d'unités entrées."""
        po = self.db.one("SELECT * FROM purchase_orders WHERE id = ?", (po_id,))
        units = 0
        with self.db.tx():
            for it in self.db.q("SELECT * FROM purchase_items WHERE po_id = ?", (po_id,)):
                q = int(received.get(it["id"], 0) or 0)
                if q <= 0:
                    continue
                if it["product_id"]:
                    p = self.db.one("SELECT quantity, cost FROM products WHERE id = ?", (it["product_id"],))
                    if p:
                        q0 = max(0, int(p["quantity"] or 0))
                        cost = (q0 * float(p["cost"] or 0) + q * it["unit_cost"]) / max(1, q0 + q)
                        self.db.exec("UPDATE products SET cost = ? WHERE id = ?", (round(cost, 2), it["product_id"]))
                        self.adjust_stock(it["product_id"], q, "Réception fournisseur", po["number"])
                self.db.exec("UPDATE purchase_items SET received_qty = received_qty + ? WHERE id = ?", (q, it["id"]))
                units += q
            left = self.db.val("SELECT COALESCE(SUM(MAX(qty - received_qty, 0)), 0) FROM purchase_items WHERE po_id = ?",
                               (po_id,), 0)
            self.db.update("purchase_orders", po_id, dict(status="Reçue" if left == 0 else "Commandée",
                                                          received_at=now()))
        return units
