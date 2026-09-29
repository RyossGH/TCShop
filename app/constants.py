"""Listes de référence utilisées dans toute l'application."""

GAMES = [
    "Pokémon",
    "Magic: The Gathering",
    "Yu-Gi-Oh!",
    "One Piece",
    "Lorcana",
    "Dragon Ball Super",
    "Flesh and Blood",
    "Digimon",
    "Star Wars Unlimited",
    "Autre",
]

# Familles de produits d'une boutique de jeux indépendante → catégories
CATEGORY_FAMILIES: dict[str, list[str]] = {
    "Cartes à l'unité": ["Carte"],
    "TCG scellé": ["Booster", "Display", "ETB / Coffret", "Deck", "Lot"],
    "Accessoires": ["Sleeves / Protège-cartes", "Classeur / Cahier", "Deckbox", "Tapis de jeu",
                    "Toploader / Protection", "Dés & jetons", "Rangement / Boîte", "Accessoire"],
    "Jeux": ["Jeu de société", "Extension de jeu", "Jeu de rôle", "Figurines / Wargame", "Peinture & modélisme",
             "Puzzle"],
    "Épicerie": ["Boisson", "Snack / Confiserie"],
    "Services & événements": ["Tournoi / Événement", "Location de table", "Service"],
    "Autre": ["Goodies / Produits dérivés", "Autre"],
}
FAMILY_ICONS = {
    "Cartes à l'unité": "🃏", "TCG scellé": "📦", "Accessoires": "🛡️", "Jeux": "🎲", "Épicerie": "🥤",
    "Services & événements": "🏆", "Autre": "🎁",
}
CATEGORIES = [c for cats in CATEGORY_FAMILIES.values() for c in cats]
FAMILY_OF = {c: fam for fam, cats in CATEGORY_FAMILIES.items() for c in cats}


def family_of(category: str) -> str:
    return FAMILY_OF.get(category or "", "Autre")


# Champs « carte » (extension, n°, rareté, état, finition) : seulement pour les cartes à l'unité.
# Jeu / extension / langue : aussi pour le TCG scellé.
CARD_CATEGORIES = {"Carte"}
TCG_FAMILIES = {"Cartes à l'unité", "TCG scellé"}
# Catégories sans suivi de stock par défaut (prestations)
NO_STOCK_CATEGORIES = {"Tournoi / Événement", "Location de table", "Service"}
# TVA par défaut (France) quand elle diffère du taux normal réglé dans les paramètres
# (ventes à emporter ; à ajuster produit par produit si besoin, ex. livre de jeu de rôle à 5,5 %)
DEFAULT_VAT_BY_CATEGORY = {"Boisson": 5.5, "Snack / Confiserie": 5.5}
VAT_RATES = [20.0, 10.0, 5.5, 2.1, 0.0]

# Colonne SQL « détail » lisible pour tout type d'article : extension + n° (cartes) ou marque + variante
DETAIL_SQL = """TRIM(
    COALESCE(NULLIF(set_name, ''), '')
    || CASE WHEN COALESCE(number, '') != '' THEN ' #' || number ELSE '' END
    || CASE WHEN COALESCE(brand, '') != '' THEN ' ' || brand ELSE '' END
    || CASE WHEN COALESCE(variant, '') != '' THEN ' · ' || variant ELSE '' END) AS detail"""

LANGUAGES = ["FR", "EN", "JP", "DE", "IT", "ES", "PT", "KR", "CN"]

# Échelle Cardmarket + facteur appliqué au prix de rachat
CONDITIONS = ["MT", "NM", "EX", "GD", "LP", "PL", "PO", "Scellé"]
CONDITION_LABELS = {
    "MT": "Mint",
    "NM": "Near Mint",
    "EX": "Excellent",
    "GD": "Good",
    "LP": "Light Played",
    "PL": "Played",
    "PO": "Poor",
    "Scellé": "Produit scellé",
}
CONDITION_FACTORS = {"MT": 1.0, "NM": 1.0, "EX": 0.85, "GD": 0.70, "LP": 0.60, "PL": 0.45, "PO": 0.30, "Scellé": 1.0}

FINISHES = ["Normale", "Holo", "Reverse", "Foil", "Full Art", "Alt Art", "Gold / Secret", "1ère édition"]

ORDER_STATUSES = ["À préparer", "Préparée", "Expédiée", "Livrée", "Annulée"]
CHANNELS = ["Site web", "Cardmarket", "eBay", "Vinted", "Téléphone", "Autre"]

PAYOUTS = ["Espèces", "Crédit boutique", "Virement", "Wero"]

STOCK_REASONS = ["Inventaire", "Correction", "Casse / Perte", "Vol", "Retour client", "Transfert", "Usage interne", "Réception fournisseur"]

STATUS_COLORS = {
    "Validée": "success",
    "Remboursée": "danger",
    "À préparer": "warning",
    "Préparée": "info",
    "Expédiée": "accent",
    "Livrée": "success",
    "Annulée": "muted",
}
