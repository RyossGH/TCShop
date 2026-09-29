from pathlib import Path

APP_NAME = "TCShop"
APP_VERSION = "2.4.0"
APP_TAGLINE = "Jeux, TCG & collection"
APP_ID = "TCShop.Boutique"  # identifiant Windows (barre des tâches)

RESOURCES = Path(__file__).resolve().parent / "resources"


def resource(name: str) -> str:
    return str(RESOURCES / name)
