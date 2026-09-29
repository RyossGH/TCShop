"""Génération des documents imprimables (tickets, bons de rachat, bons de préparation)."""
from __future__ import annotations

from html import escape

from .db import Database
from .widgets import fdate, money

_CSS = """
<style>
body { font-family: 'Segoe UI', Arial; font-size: 10pt; color: #111; }
h1 { font-size: 15pt; margin: 0; }
h2 { font-size: 12pt; margin: 10px 0 4px 0; }
.muted { color: #555; font-size: 9pt; }
table { border-collapse: collapse; width: 100%; margin-top: 8px; }
th { text-align: left; border-bottom: 1px solid #333; padding: 4px; font-size: 9pt; }
td { padding: 4px; border-bottom: 1px solid #ddd; font-size: 9.5pt; }
.r { text-align: right; }
.tot td { border: none; font-size: 10.5pt; }
.big td { font-size: 13pt; font-weight: bold; }
.center { text-align: center; }
</style>
"""


def _shop_header(db: Database) -> str:
    lines = [f"<h1>{escape(db.setting('shop_name'))}</h1>"]
    for key in ("shop_address", "shop_phone", "shop_email"):
        v = db.setting(key)
        if v:
            lines.append(f"<div class='muted'>{escape(v).replace(chr(10), '<br>')}</div>")
    if db.setting("shop_siret"):
        lines.append(f"<div class='muted'>SIRET : {escape(db.setting('shop_siret'))}</div>")
    return "\n".join(lines)


def _pct(rate: float) -> str:
    return f"{rate:g} %".replace(".", ",")


def sale_ticket(db: Database, sale_id: int) -> str:
    s = db.one("SELECT * FROM sales WHERE id = ?", (sale_id,))
    items = db.q("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,))
    cust = db.one("SELECT * FROM customers WHERE id = ?", (s["customer_id"],)) if s["customer_id"] else None
    # TVA ventilée par taux (la remise globale est répartie au prorata des lignes)
    ratio = (s["total"] / s["subtotal"]) if s["subtotal"] else 0
    by_rate: dict[float, float] = {}
    for i in items:
        rate = float(i["vat_rate"] if i.get("vat_rate") is not None else db.setting_float("vat_rate", 20))
        by_rate[rate] = by_rate.get(rate, 0) + i["qty"] * i["unit_price"] * ratio
    vat_rows = "".join(
        f"<tr class='tot'><td colspan='3' class='muted'>TVA {_pct(rate)} sur {money(ttc / (1 + rate / 100))} HT</td>"
        f"<td class='r muted'>{money(ttc - ttc / (1 + rate / 100))}</td></tr>"
        for rate, ttc in sorted(by_rate.items(), reverse=True) if ttc)
    rows = "".join(
        f"<tr><td>{escape(i['name'])}</td><td class='r'>{i['qty']}</td>"
        f"<td class='r'>{money(i['unit_price'])}</td><td class='r'>{money(i['qty'] * i['unit_price'])}</td></tr>"
        for i in items
    )
    pay = []
    for label, key in (("Espèces", "paid_cash"), ("Carte bancaire", "paid_card"), ("Crédit boutique", "paid_credit")):
        if s[key]:
            pay.append(f"<tr class='tot'><td colspan='3'>{label}</td><td class='r'>{money(s[key])}</td></tr>")
    if s.get("paid_other"):
        pay.append(f"<tr class='tot'><td colspan='3'>{escape(s['other_label'] or 'Autre')}</td>"
                   f"<td class='r'>{money(s['paid_other'])}</td></tr>")
    if s["cash_given"]:
        pay.append(f"<tr class='tot'><td colspan='3'>Espèces remises</td><td class='r'>{money(s['cash_given'])}</td></tr>")
        pay.append(f"<tr class='tot'><td colspan='3'><b>Rendu monnaie</b></td><td class='r'><b>{money(s['change_given'])}</b></td></tr>")
    status = "<h2 style='color:#b91c1c'>VENTE REMBOURSÉE</h2>" if s["status"] == "Remboursée" else ""
    cust_html = ""
    if cust:
        cust_html = (f"<div>Client : <b>{escape(cust['name'])}</b></div>"
                     f"<div class='muted'>Points gagnés : {s['points_earned']} · Solde points : {cust['points']}"
                     f" · Crédit boutique : {money(cust['credit'])}</div>")
    return f"""<html><head>{_CSS}</head><body>
{_shop_header(db)}
<hr>
<div><b>Ticket {escape(s['number'])}</b> — {fdate(s['date'])}</div>
{cust_html}{status}
<table><tr><th>Article</th><th class='r'>Qté</th><th class='r'>P.U.</th><th class='r'>Total</th></tr>{rows}</table>
<table>
<tr class='tot'><td colspan='3'>Sous-total</td><td class='r'>{money(s['subtotal'])}</td></tr>
{"<tr class='tot'><td colspan='3'>Remise</td><td class='r'>- " + money(s['discount']) + "</td></tr>" if s['discount'] else ""}
<tr class='big'><td colspan='3'>TOTAL TTC</td><td class='r'>{money(s['total'])}</td></tr>
{vat_rows}
{''.join(pay)}
</table>
<p class='center'>{escape(db.setting('ticket_footer'))}</p>
</body></html>"""


def buy_receipt(db: Database, buy_id: int) -> str:
    b = db.one("SELECT * FROM buys WHERE id = ?", (buy_id,))
    items = db.q("SELECT * FROM buy_items WHERE buy_id = ?", (buy_id,))
    rows = "".join(
        f"<tr><td>{escape(i['name'])}</td><td>{escape(i['set_name'] or '')}</td><td>{escape(i['condition'] or '')}</td>"
        f"<td class='r'>{i['qty']}</td><td class='r'>{money(i['offer_price'])}</td>"
        f"<td class='r'>{money(i['qty'] * i['offer_price'])}</td></tr>"
        for i in items
    )
    ident = ""
    if b["id_type"] or b["id_number"]:
        ident = f"<div>Pièce d'identité : {escape(b['id_type'])} n° {escape(b['id_number'])}</div>"
    return f"""<html><head>{_CSS}</head><body>
{_shop_header(db)}
<hr>
<h2>Bon de rachat {escape(b['number'])}</h2>
<div>Date : {fdate(b['date'])}</div>
<div>Vendeur : <b>{escape(b['customer_name'] or 'Non renseigné')}</b></div>
{ident}
<div>Mode de règlement : <b>{escape(b['payout'])}</b></div>
<table><tr><th>Article</th><th>Extension</th><th>État</th><th class='r'>Qté</th><th class='r'>Prix</th><th class='r'>Total</th></tr>{rows}</table>
<table><tr class='big'><td>TOTAL VERSÉ</td><td class='r'>{money(b['total'])}</td></tr></table>
<p class='muted'>Le vendeur certifie être le propriétaire légitime des articles cédés et que ceux-ci ne proviennent
d'aucune activité illicite. Les articles sont acquis en l'état.</p>
<br><table><tr><td>Signature du vendeur :<br><br><br></td><td>Signature de la boutique :<br><br><br></td></tr></table>
</body></html>"""


def picking_list(db: Database, order_id: int) -> str:
    o = db.one("SELECT * FROM orders WHERE id = ?", (order_id,))
    items = db.q(
        """SELECT oi.*, p.location, p.set_name, p.number, p.condition, p.language
           FROM order_items oi LEFT JOIN products p ON p.id = oi.product_id WHERE oi.order_id = ?
           ORDER BY p.location, oi.name""",
        (order_id,),
    )
    rows = "".join(
        f"<tr><td>☐</td><td>{escape(i['location'] or '—')}</td><td>{escape(i['name'])}</td>"
        f"<td>{escape(i['set_name'] or '')} {escape(i['number'] or '')}</td>"
        f"<td>{escape(i['condition'] or '')} {escape(i['language'] or '')}</td><td class='r'>{i['qty']}</td></tr>"
        for i in items
    )
    return f"""<html><head>{_CSS}</head><body>
{_shop_header(db)}
<hr>
<h2>Bon de préparation — commande {escape(o['number'])}</h2>
<div>Canal : {escape(o['channel'] or '')} {('· Réf. ' + escape(o['external_ref'])) if o['external_ref'] else ''}</div>
<div>Date : {fdate(o['date'])}</div>
<h2>Destinataire</h2>
<div><b>{escape(o['customer_name'] or '')}</b></div>
<div>{escape(o['address'] or '').replace(chr(10), '<br>')}</div>
<table><tr><th></th><th>Emplacement</th><th>Article</th><th>Extension</th><th>État / Langue</th><th class='r'>Qté</th></tr>{rows}</table>
<p class='muted'>Notes : {escape(o['notes'] or '')}</p>
</body></html>"""


def purchase_order(db: Database, po_id: int) -> str:
    po = db.one("SELECT * FROM purchase_orders WHERE id = ?", (po_id,))
    sup = db.one("SELECT * FROM suppliers WHERE id = ?", (po["supplier_id"],)) if po["supplier_id"] else None
    items = db.q("""SELECT pi.*, p.sku, p.barcode, p.brand, p.variant FROM purchase_items pi
                    LEFT JOIN products p ON p.id = pi.product_id WHERE pi.po_id = ? ORDER BY pi.name""", (po_id,))
    rows = "".join(
        f"<tr><td>{escape(i['barcode'] or i['sku'] or '')}</td><td>{escape(i['name'])}</td>"
        f"<td class='r'>{i['qty']}</td><td class='r'>{money(i['unit_cost'])}</td>"
        f"<td class='r'>{money(i['qty'] * i['unit_cost'])}</td></tr>"
        for i in items)
    sup_html = ""
    if sup:
        sup_html = (f"<div><b>{escape(sup['name'])}</b></div>"
                    + "".join(f"<div class='muted'>{escape(v)}</div>" for v in
                              (sup["contact"], sup["email"], sup["phone"]) if v)
                    + (f"<div class='muted'>Notre n° de compte : {escape(sup['account_ref'])}</div>"
                       if sup["account_ref"] else ""))
    return f"""<html><head>{_CSS}</head><body>
{_shop_header(db)}
<hr>
<h2>Bon de commande {escape(po['number'])}</h2>
<div>Date : {fdate(po['date'], False)} · Statut : {escape(po['status'])}</div>
<h2>Fournisseur</h2>
{sup_html or "<div class='muted'>Non renseigné</div>"}
<table><tr><th>Réf. / EAN</th><th>Article</th><th class='r'>Qté</th><th class='r'>P.U. HT</th><th class='r'>Total HT</th></tr>
{rows}</table>
<table><tr class='big'><td>TOTAL HT</td><td class='r'>{money(po['total'])}</td></tr></table>
<p class='muted'>{escape(po['notes'] or '')}</p>
</body></html>"""
