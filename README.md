# TCShop

Logiciel de caisse et de gestion pour **boutique de jeux, TCG et collection** : cartes à l'unité (Pokémon, Magic,
Yu-Gi-Oh!, One Piece, Lorcana…), boosters, accessoires, jeux de société, épicerie, tournois.
Il gère l'achat et la revente, le stock, les rachats, les commandes en ligne, les fournisseurs et les collections.
Il fonctionne hors ligne, avec une base de données locale.

## Installer

Lancez **`dist\installer\TCShop-Setup-2.4.0.exe`**. Aucun droit administrateur n'est nécessaire.
L'installeur crée les raccourcis dans le menu Démarrer et, si vous le cochez, sur le Bureau.
Pour désinstaller : Paramètres Windows → Applications → TCShop.

Les données (base, photos, sauvegardes) sont enregistrées dans **`%LOCALAPPDATA%\TCShop`**.
Elles sont **conservées** en cas de désinstallation ou de mise à jour.
Au premier lancement, TCShop reprend automatiquement les données de l'ancien dossier `data` (version « TCG Manager »).

## Développement

- Lancer depuis les sources : **`Lancer TCShop.bat`**, ou `.venv\Scripts\python.exe main.py`.
- Reconstruire l'exe et l'installeur : **`packaging\build.bat`**. Il faut PyInstaller et Pillow dans le `.venv`, et Inno Setup 6 (`winget install JRSoftware.InnoSetup`).
- L'icône se modifie dans `app/resources/tcshop.svg`, puis `tools/make_icon.py` régénère les fichiers `.ico` et `.png`.

## Modules

| Touche | Module | Ce qu'il fait |
|---|---|---|
| F1 | **Tableau de bord** | CA du jour et sur 30 jours, marge, valeur du stock, graphiques (boutique / en ligne, ventes par jeu), meilleures ventes, alertes de stock |
| F2 | **Caisse** | Scan de codes-barres, recherche, panier, remise en % ou en €, paiement en espèces, carte, crédit boutique ou mixte, rendu monnaie, ticket imprimable ou PDF, historique et remboursements |
| F3 | **Inventaire** | Tout le magasin par familles (cartes, scellé, accessoires, jeux, épicerie, services), fiche avec image, prix d'achat moyen pondéré, mise à jour automatique des prix marché, import / export CSV |
| F4 | **Rachats** | Offre calculée à partir du prix marché × taux (espèces / crédit) × état, bon de rachat à signer, registre et export du **livre de police** |
| F5 | **Commandes en ligne** | Cardmarket, site web, eBay… : le stock est réservé dès la création, suivi des statuts, bon de préparation trié par emplacement, n° de suivi, export du catalogue en ligne |
| F6 | **Fournisseurs & réassort** | Articles sous le stock minimum, bons de commande par fournisseur (brouillon, commandée, reçue), montant minimum pour le franco de port, réception au scanner avec mise à jour du stock et du prix d'achat moyen |
| F7 | **Clients** | Fiches, pièce d'identité, crédit boutique, points de fidélité convertibles, historique |
| F8 | **Collections** | Import d'une extension complète, suivi de complétion en visuel, cartes manquantes disponibles en boutique, export de la liste des manquantes |
| F9 | **Mouvements** | Chaque entrée et sortie de stock est tracée : vente, rachat, commande, correction |
| F10 | **Paramètres** | Coordonnées de la boutique, TVA, taux de rachat, coefficient de prix, fidélité, thème clair / sombre, sauvegardes |

## Tout le magasin, pas seulement les cartes

Les articles sont classés par familles : **cartes à l'unité**, **TCG scellé** (boosters, displays, ETB), **accessoires** (sleeves, classeurs et cahiers, deckbox, tapis, dés…), **jeux** (jeux de société, jeux de rôle, figurines), **épicerie** (boissons, snacks), **services et événements** (tournois, location de table) et **autre**.

- La fiche article s'adapte au type de produit : extension, état et rareté pour une carte ; marque, variante (couleur, format) et fournisseur pour un accessoire ou un jeu.
- **TVA par article** : 20 % par défaut, 5,5 % pour les boissons et snacks, modifiable fiche par fiche. Le ticket détaille la TVA par taux.
- **Prestations sans stock** (inscription à un tournoi…) : elles se vendent sans jamais tomber en rupture.
- **Touches rapides en caisse** : cochez « ⭐ Touche rapide » sur les articles les plus vendus (sleeves, boosters, boissons…) pour les encaisser en un clic.
- **Photos de produits** : choisissez une photo sur l'ordinateur ; elle est copiée dans le dossier `images` des données.

## Scanner de codes-barres

Branchez le scanner en USB : il est reconnu comme un clavier, sans pilote à installer. Il fonctionne **partout** dans l'application, sans cliquer dans un champ :

- **Caisse** : l'article scanné s'ajoute au panier.
- **Inventaire** : la fiche de l'article s'ouvre.
- **Rachats** : une ligne est ajoutée au rachat.
- **Code inconnu** : l'application propose de l'associer à un article existant ou de créer l'article, depuis la base de cartes ou en saisie manuelle.

Pour **relier vos articles existants** à leurs codes-barres : dans l'Inventaire, sélectionnez l'article puis scannez le produit, et l'application propose l'association.
Un article peut avoir **plusieurs codes** (EAN du fabricant, étiquette boutique…) : bouton **▦ Codes-barres**.

- **📷 Mode scan** (Inventaire) : consultation, réception (+ stock), sortie (− stock) et **comptage d'inventaire** par rayon.
- **🏷 Étiquettes** : impression Code 128 (nom, prix, extension / état) sur imprimante d'étiquettes (50 × 25, 40 × 30, Brother 62 × 29) ou sur planche A4.
  Les cartes à l'unité, qui n'ont pas de code fabricant, reçoivent une étiquette avec leur SKU, que le scanner reconnaît directement.
- Un scanner réglé en clavier **QWERTY** sur un PC **AZERTY** est corrigé automatiquement : « àààà&è » redevient « 000017 ».

## TCShop Mobile (Android)

L'appli Android **TCShop Mobile** sert à vendre en convention, à enregistrer des commandes en ligne et à faire l'inventaire avec l'appareil photo du téléphone.
Elle fonctionne **hors ligne** et se synchronise toute seule avec le PC dès que les deux sont sur le **même Wi-Fi**.

**Installation :**
1. Copiez `dist/mobile/TCShop-Mobile.apk` sur le téléphone (câble USB, e-mail, Google Drive…) et ouvrez-le.
   Android demande d'autoriser l'installation depuis cette source : acceptez.
2. Sur le PC : **Paramètres (F10) → TCShop Mobile → Associer un téléphone**.
   Au premier lancement, Windows peut demander d'autoriser TCShop sur le réseau : cochez **Réseaux privés**.
3. Dans l'appli, appuyez sur **Scanner le QR code**. L'association est faite.

**Installation sur iPhone** (même appli, servie par TCShop sur le PC, sans passer par l'App Store) :
1. Sur le PC : **Paramètres → TCShop Mobile → Associer un téléphone**, onglet **iPhone**.
2. Scannez le QR code avec l'**appareil photo** de l'iPhone et ouvrez le lien dans **Safari**. Une page guide s'affiche.
3. Suivez ses 4 étapes, à ne faire qu'une fois :
   - télécharger le certificat TCShop ;
   - l'installer (Réglages → Profil téléchargé) puis l'activer (Réglages → Général → Informations → Réglages des certificats) ;
   - ouvrir TCShop ;
   - Partager → **Sur l'écran d'accueil**.

L'appli iPhone fonctionne aussi **hors ligne** et se synchronise dès qu'elle est sur le même Wi-Fi que le PC.
Conseil : réservez l'adresse IP du PC dans votre box, car l'appli iPhone mémorise cette adresse.
Pour reconstruire l'appli iPhone : `mobile\build_web.bat`, puis reconstruire l'installeur PC.

**Dans l'appli** (5 onglets) :
- **Caisse** : scan en continu vers le panier, articles libres, prix modifiable. Paiement **espèces** (avec calcul du rendu), **virement** ou **Wero**.
- **Rachat** (conventions) :
  - vendeur existant ou nouveau, avec sa **pièce d'identité** pour le livre de police ;
  - règlement en espèces, virement, Wero ou crédit boutique ;
  - cartes ajoutées au scanner, depuis le stock, depuis la **base en ligne** (prix Cardmarket directement sur le téléphone en 4G) ou à la main ;
  - offre calculée automatiquement : prix marché × taux × état, modifiable ligne par ligne ;
  - le vendeur doit cocher sa certification.
- **Stock** : recherche, fiche article, réception, sortie et **comptage d'inventaire** au scanner.
- **Collections** : import d'une extension complète, collection vide, ajout de cartes depuis la base en ligne. Les cartes possédées sont en couleur, les manquantes en gris ; toucher = +1, appui long = détail et −1.
- **Plus** : **commandes en ligne** (tous canaux, avec suivi et n° de colis scanné) et **synchronisation** (automatique chaque minute et après chaque opération).

Le stock est synchronisé **par mouvements** (−2, +5…) et non par quantités : une vente faite hors ligne sur le téléphone et une vente faite sur le PC s'additionnent correctement.
Un rachat fait sur le téléphone crée, à la synchro, les fiches articles et le vendeur sur le PC ; le bon de rachat et le livre de police sont ensuite disponibles dans TCShop sur PC.

Pour reconstruire l'APK : `mobile\build_apk.bat`. Il faut Flutter et le SDK Android dans `C:\Android\Sdk`.

## Bases de cartes en ligne (gratuites, sans clé)

- **Pokémon** : [TCGdex](https://tcgdex.dev), avec les noms français et les prix Cardmarket en euros
- **Magic** : [Scryfall](https://scryfall.com), prix en euros
- **Yu-Gi-Oh!** : [YGOPRODeck](https://ygoprodeck.com), prix Cardmarket

Pour les autres jeux, la saisie est manuelle, avec import CSV possible.

## Données

Tout est enregistré dans `%LOCALAPPDATA%\TCShop` : la base `tcg.db`, les photos, le cache des images et les sauvegardes.
Une sauvegarde automatique est faite à chaque démarrage (les 15 dernières sont conservées).
Pour repartir de zéro, fermez l'application puis supprimez ce dossier.
