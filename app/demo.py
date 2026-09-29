"""Données de démonstration pour découvrir l'application."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

PKM_IMG = "https://assets.tcgdex.net/{}/low.png"
MTG_IMG = "https://cards.scryfall.io/normal/front/{0}/{1}/{2}.jpg"
YGO_IMG = "https://images.ygoprodeck.com/images/cards_small/{}.jpg"

# nom, jeu, catégorie, extension, n°, rareté, langue, état, finition, empl., qté, min, achat, vente, marché, image, id ext
PRODUCTS = [
    ("Charizard", "Pokémon", "Carte", "Base", "4/102", "Rare Holo", "EN", "EX", "Holo", "Vitrine A", 1, 0, 180, 349.9, 330, PKM_IMG.format("fr/base/base1/4"), "base1-4"),
    ("Blastoise", "Pokémon", "Carte", "Base", "2/102", "Rare Holo", "EN", "GD", "Holo", "Vitrine A", 1, 0, 60, 119.9, 110, PKM_IMG.format("fr/base/base1/2"), "base1-2"),
    ("Venusaur", "Pokémon", "Carte", "Base", "15/102", "Rare Holo", "FR", "NM", "Holo", "Vitrine A", 2, 0, 50, 99.9, 95, PKM_IMG.format("fr/base/base1/15"), "base1-15"),
    ("Charizard ex", "Pokémon", "Carte", "151", "199/165", "Special Illustration Rare", "EN", "NM", "Full Art", "Vitrine B", 2, 1, 70, 129.9, 120, PKM_IMG.format("fr/sv/sv03.5/199"), "sv03.5-199"),
    ("Umbreon VMAX", "Pokémon", "Carte", "Evolving Skies", "215/203", "Rare Secret", "EN", "NM", "Alt Art", "Vitrine B", 1, 0, 600, 1049.0, 990, PKM_IMG.format("fr/swsh/swsh7/215"), "swsh7-215"),
    ("Booster Écarlate et Violet 151", "Pokémon", "Booster", "151", "", "", "FR", "Scellé", "Normale", "Comptoir", 36, 12, 3.2, 6.5, 6, "", ""),
    ("Display Évolutions Prismatiques", "Pokémon", "Display", "Évolutions Prismatiques", "", "", "FR", "Scellé", "Normale", "Réserve", 4, 2, 150, 219.9, 210, "", ""),
    ("ETB Mascarade Crépusculaire", "Pokémon", "ETB / Coffret", "Mascarade Crépusculaire", "", "", "FR", "Scellé", "Normale", "Rayon 1", 6, 3, 38, 59.9, 55, "", ""),
    ("Sol Ring", "Magic: The Gathering", "Carte", "Reality Fracture Commander", "21", "Uncommon", "EN", "NM", "Normale", "Classeur MTG-1", 8, 4, 0.6, 2.0, 1.5, MTG_IMG.format("8", "e", "8ee443cc-e17a-493b-9c93-1f9e141a30e4"), "8ee443cc-e17a-493b-9c93-1f9e141a30e4"),
    ("Lightning Bolt", "Magic: The Gathering", "Carte", "Marvel Super Heroes Commander", "806", "Common", "FR", "NM", "Normale", "Classeur MTG-1", 12, 4, 0.5, 1.5, 1.2, MTG_IMG.format("7", "6", "7673784e-db4b-43a1-8d55-1bb9fc1e284f"), "7673784e-db4b-43a1-8d55-1bb9fc1e284f"),
    ("The One Ring", "Magic: The Gathering", "Carte", "The Lord of the Rings", "246", "Mythic", "EN", "NM", "Normale", "Vitrine C", 1, 0, 35, 59.9, 55, MTG_IMG.format("d", "5", "d5806e68-1054-458e-866d-1f2470f682b2"), "d5806e68-1054-458e-866d-1f2470f682b2"),
    ("Ragavan, Nimble Pilferer", "Magic: The Gathering", "Carte", "Modern Horizons 2", "138", "Mythic", "EN", "EX", "Normale", "Vitrine C", 1, 0, 30, 49.9, 45, MTG_IMG.format("a", "9", "a9738cda-adb1-47fb-9f4c-ecd930228c4d"), "a9738cda-adb1-47fb-9f4c-ecd930228c4d"),
    ("Counterspell", "Magic: The Gathering", "Carte", "Duskmourn Commander", "114", "Common", "EN", "NM", "Normale", "Classeur MTG-1", 6, 2, 0.3, 1.0, 0.8, MTG_IMG.format("4", "f", "4f616706-ec97-4923-bb1e-11a69fbaa1f8"), "4f616706-ec97-4923-bb1e-11a69fbaa1f8"),
    ("Collector Booster Bloomburrow", "Magic: The Gathering", "Booster", "Bloomburrow", "", "", "EN", "Scellé", "Normale", "Comptoir", 10, 4, 18, 29.9, 27, "", ""),
    ("Blue-Eyes White Dragon", "Yu-Gi-Oh!", "Carte", "Legend of Blue Eyes White Dragon", "LOB-001", "Ultra Rare", "EN", "LP", "Normale", "Classeur YGO-1", 1, 0, 40, 79.9, 75, YGO_IMG.format("89631139"), "89631139"),
    ("Dark Magician", "Yu-Gi-Oh!", "Carte", "Legend of Blue Eyes White Dragon", "LOB-005", "Ultra Rare", "EN", "GD", "Normale", "Classeur YGO-1", 1, 0, 25, 49.9, 45, YGO_IMG.format("46986414"), "46986414"),
    ("Ash Blossom & Joyous Spring", "Yu-Gi-Oh!", "Carte", "Maximum Crisis", "MACR-EN036", "Secret Rare", "FR", "NM", "Gold / Secret", "Classeur YGO-1", 3, 1, 4, 9.9, 8, YGO_IMG.format("14558127"), "14558127"),
    ("Maxx \"C\"", "Yu-Gi-Oh!", "Carte", "Storm of Ragnarok", "STOR-EN084", "Rare", "EN", "NM", "Normale", "Classeur YGO-1", 2, 0, 8, 17.9, 16, YGO_IMG.format("23434538"), "23434538"),
    ("Booster One Piece OP-07", "One Piece", "Booster", "500 Years in the Future", "", "", "EN", "Scellé", "Normale", "Comptoir", 24, 12, 3.5, 6.9, 6, "", ""),
    ("Booster Lorcana Chapitre 5", "Lorcana", "Booster", "Ciel Scintillant", "", "", "FR", "Scellé", "Normale", "Comptoir", 30, 12, 3.3, 6.5, 6, "", ""),
    ("Sleeves Dragon Shield Mat (x100)", "", "Sleeves / Protège-cartes", "", "", "", "", "", "", "Rayon Accessoires", 25, 10, 6.5, 11.9, 11.9, "", ""),
    ("Toploader 35pt (x25)", "", "Toploader / Protection", "", "", "", "", "", "", "Rayon Accessoires", 40, 15, 1.8, 3.9, 3.9, "", ""),
    ("Classeur 9 cases Ultra Pro", "", "Classeur / Cahier", "", "", "", "", "", "", "Rayon Accessoires", 3, 5, 12, 24.9, 24.9, "", ""),
    ("Deck de combat Pokémon", "Pokémon", "Deck", "", "", "", "FR", "Scellé", "Normale", "Rayon 1", 0, 2, 9, 16.9, 15, "", ""),
]

SUPPLIERS = [  # nom, contact, e-mail, franco
    ("Asmodee", "Service pro", "pro@asmodee.example", 300.0),
    ("Blackfire", "Commandes", "orders@blackfire.example", 250.0),
    ("Distributeur TCG Europe", "Julie", "commandes@tcg-europe.example", 500.0),
    ("Grossiste Boissons", "", "", 80.0),
]

# nom, catégorie, marque, variante, fournisseur, qté, mini, achat HT, vente TTC, touche rapide, TVA
SHOP_PRODUCTS = [
    ("Sleeves Dragon Shield Matte", "Sleeves / Protège-cartes", "Dragon Shield", "Noir (x100)", "Blackfire", 18, 8, 6.5, 11.9, 1, None),
    ("Sleeves Dragon Shield Matte", "Sleeves / Protège-cartes", "Dragon Shield", "Bleu nuit (x100)", "Blackfire", 6, 8, 6.5, 11.9, 0, None),
    ("Sleeves Perfect Fit", "Sleeves / Protège-cartes", "Ultra Pro", "Transparent (x100)", "Blackfire", 30, 15, 2.2, 4.9, 1, None),
    ("Deckbox Boulder 100+", "Deckbox", "Ultimate Guard", "Onyx", "Blackfire", 7, 3, 7.5, 14.9, 1, None),
    ("Tapis de jeu Pokémon", "Tapis de jeu", "Ultra Pro", "Évoli", "Blackfire", 4, 2, 11, 24.9, 0, None),
    ("Cahier de rangement A4 18 pochettes", "Classeur / Cahier", "Ultra Pro", "Noir", "Blackfire", 9, 4, 8, 16.9, 1, None),
    ("Portfolio 4 cases Pokémon", "Classeur / Cahier", "Pokémon", "Écarlate et Violet", "Distributeur TCG Europe", 5, 3, 6, 12.9, 0, None),
    ("Set de dés D6 (x12)", "Dés & jetons", "Chessex", "Marbre bleu", "Blackfire", 10, 4, 5, 10.9, 0, None),
    ("Catan", "Jeu de société", "Kosmos", "Édition 2022", "Asmodee", 3, 2, 26, 44.9, 0, None),
    ("Dixit", "Jeu de société", "Libellud", "", "Asmodee", 2, 2, 19, 34.9, 0, None),
    ("Azul", "Jeu de société", "Next Move", "", "Asmodee", 4, 2, 23, 39.9, 0, None),
    ("Skyjo", "Jeu de société", "Magilano", "", "Asmodee", 8, 4, 10, 19.9, 1, None),
    ("Coca-Cola 33 cl", "Boisson", "Coca-Cola", "Canette", "Grossiste Boissons", 48, 24, 0.45, 1.5, 1, None),
    ("Eau minérale 50 cl", "Boisson", "Cristaline", "", "Grossiste Boissons", 30, 12, 0.2, 1.0, 1, None),
    ("Barre chocolatée", "Snack / Confiserie", "Kinder", "Bueno", "Grossiste Boissons", 36, 12, 0.55, 1.5, 1, None),
    ("Tournoi Pokémon du samedi", "Tournoi / Événement", "", "Inscription", "", 0, 0, 0, 5.0, 1, None),
    ("Tournoi Magic Commander", "Tournoi / Événement", "", "Inscription", "", 0, 0, 0, 8.0, 1, None),
    ("Location de table (2 h)", "Location de table", "", "", "", 0, 0, 0, 3.0, 0, None),
]

CUSTOMERS = [
    ("Lucas Martin", "lucas.martin@example.com", "06 12 34 56 78", "Carte d'identité", "X1A2B3C4D"),
    ("Emma Bernard", "emma.b@example.com", "06 98 76 54 32", "Passeport", "22AB33445"),
    ("Hugo Petit", "", "07 11 22 33 44", "", ""),
    ("Chloé Durand", "chloe.durand@example.com", "06 55 44 33 22", "Carte d'identité", "Z9Y8X7W6V"),
    ("Nathan Leroy", "nathan.l@example.com", "", "Permis de conduire", "1234567890"),
]


def load_demo(ctx) -> int:
    db, svc = ctx.db, ctx.svc
    rnd = random.Random(42)
    pids = []
    with db.tx():
        for (name, game, cat, set_name, number, rarity, lang, cond, finish, loc, qty, mini, cost, price, market,
             img, ext) in PRODUCTS:
            pids.append(svc.save_product(dict(
                name=name, game=game, category=cat, set_name=set_name, number=number, rarity=rarity, language=lang,
                condition=cond, finish=finish, location=loc, quantity=qty + 60, min_stock=mini, cost=cost, price=price,
                market_price=market, image_url=img, external_id=ext, online=1)))
        cids = [svc.save_customer(dict(name=n, email=e, phone=p, id_type=t, id_number=i)) for n, e, p, t, i in CUSTOMERS]
        svc.adjust_credit(cids[0], 25.0)

        sup = {n: db.insert("suppliers", dict(name=n, contact=c, email=e, min_order=m,
                                              created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
               for n, c, e, m in SUPPLIERS}
        db.exec("UPDATE products SET supplier_id = ? WHERE category IN ('Booster', 'Display', 'ETB / Coffret', 'Deck')",
                (sup["Distributeur TCG Europe"],))
        db.exec("UPDATE products SET supplier_id = ?, brand = 'Ultra Pro' WHERE category IN "
                "('Toploader / Protection', 'Classeur / Cahier')", (sup["Blackfire"],))
        db.exec("UPDATE products SET supplier_id = ?, brand = 'Dragon Shield', favorite = 1 WHERE category = "
                "'Sleeves / Protège-cartes'", (sup["Blackfire"],))
        db.exec("UPDATE products SET favorite = 1 WHERE name LIKE 'Booster%'")
        extra = []
        for name, cat, brand, variant, supplier, qty, mini, cost, price, fav, vat in SHOP_PRODUCTS:
            pid = svc.save_product(dict(
                name=name, category=cat, brand=brand, variant=variant, supplier_id=sup.get(supplier),
                quantity=qty + 60, min_stock=mini, cost=cost, price=price, favorite=fav, vat_rate=vat,
                condition="", language="", location="Comptoir" if cat in ("Boisson", "Snack / Confiserie")
                else ("Rayon jeux" if cat == "Jeu de société" else "Rayon accessoires"), online=int(cat != "Boisson")))
            extra.append((pid, qty))

        cheap = [pid for pid in pids if (db.val("SELECT price FROM products WHERE id = ?", (pid,)) or 0) < 70]
        cheap += [pid for pid, _q in extra]
        now = datetime.now()
        for day in range(30, -1, -1):
            for _ in range(rnd.randint(1, 6)):
                when = (now - timedelta(days=day)).replace(hour=rnd.randint(10, 18), minute=rnd.randint(0, 59))
                if when > now:
                    when = now
                lines = []
                for pid in rnd.sample(cheap, rnd.randint(1, 3)):
                    p = db.one("SELECT * FROM products WHERE id = ?", (pid,))
                    lines.append(dict(product_id=pid, name=p["name"], qty=rnd.randint(1, 2), unit_price=p["price"],
                                      unit_cost=p["cost"]))
                total = sum(l["qty"] * l["unit_price"] for l in lines)
                cust = rnd.choice([None, None] + cids)
                if rnd.random() < 0.55:
                    svc.create_sale(lines, cust, 0, paid_card=total, date=when.strftime("%Y-%m-%d %H:%M:%S"))
                else:
                    svc.create_sale(lines, cust, 0, paid_cash=total, date=when.strftime("%Y-%m-%d %H:%M:%S"))
            if day % 4 == 0:
                p = db.one("SELECT * FROM products WHERE id = ?", (rnd.choice(cheap),))
                when = (now - timedelta(days=day)).replace(hour=9, minute=30)
                svc.create_order(
                    dict(channel=rnd.choice(["Cardmarket", "Site web", "eBay"]), customer_name=rnd.choice(CUSTOMERS)[0],
                         address="12 rue des Cartes\n75000 Paris", shipping=3.5,
                         status="Livrée" if day > 6 else rnd.choice(["À préparer", "Préparée", "Expédiée"]),
                         external_ref=f"CM{rnd.randint(100000, 999999)}"),
                    [dict(product_id=p["id"], name=p["name"], qty=1, unit_price=p["price"], unit_cost=p["cost"])],
                    date=when.strftime("%Y-%m-%d %H:%M:%S"))
        svc.create_buy([
            dict(product_id=pids[8], name="Sol Ring", game="Magic: The Gathering", set_name="Reality Fracture Commander",
                 condition="NM", qty=4, market_price=1.5, offer_price=0.75),
            dict(product_id=pids[16], name="Ash Blossom & Joyous Spring", game="Yu-Gi-Oh!", set_name="Maximum Crisis",
                 condition="EX", qty=2, market_price=8, offer_price=3.4),
        ], cids[1], "Espèces", date=(now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"))
        svc.create_buy([
            dict(product_id=pids[3], name="Charizard ex", game="Pokémon", set_name="151", condition="NM", qty=1,
                 market_price=120, offer_price=78),
        ], cids[0], "Crédit boutique", date=(now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"))
        # inventaire de fin : on remet chaque article à sa quantité cible
        for pid, row in zip(pids, PRODUCTS):
            cur = db.val("SELECT quantity FROM products WHERE id = ?", (pid,), 0)
            svc.adjust_stock(pid, row[10] - cur, "Inventaire", "Démo")
        for pid, target in extra:
            cur = db.val("SELECT quantity FROM products WHERE id = ?", (pid,), 0)
            svc.adjust_stock(pid, target - cur, "Inventaire", "Démo")
    return len(PRODUCTS) + len(SHOP_PRODUCTS)
