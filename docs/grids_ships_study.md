# Étude : Grilles cargo des vaisseaux Star Citizen

## Contexte

Les vaisseaux Star Citizen ont une capacité cargo totale en SCU, mais cette capacité
**n'est pas entièrement utilisable** selon la taille des caisses disponibles au terminal.
La grille physique 3D du cargo hold impose des contraintes de hauteur par zone.

### Exemple concret — M2 Hercules (522 SCU)

Un terminal comme **Orbituary** ne vend que des caisses de 8 SCU minimum.
Une caisse de 8 SCU occupe **2 cellules de hauteur**.

Le M2 a deux zones :
- Zone principale (hauteur = 2 cellules) → **320 SCU** (10 × 32 SCU) → accepte des 8 SCU
- Zone rampe / bords (hauteur = 1 cellule) → **202 SCU** → seulement des 1 SCU

→ Avec des caisses de 8 SCU minimum, la capacité **effective** n'est que **320 SCU** au lieu de 522.

Le **C2 Hercules** a une hauteur de 4 cellules sur toute sa grille → on peut empiler
deux couches de caisses 8 SCU → toute la capacité est utilisable.

---

## Sources de données identifiées

### Sources visuelles / communautaires

| Source | Format | Contenu |
|---|---|---|
| [sc-cargo.space](https://sc-cargo.space/#/v1/viewer) | WebGL 3D | Visualiseur interactif, tous les vaisseaux flyables. Pas d'API publique. |
| [ratjack.net/Star-Citizen/Cargo-Grids/](https://ratjack.net/Star-Citizen/Cargo-Grids/) | PDF + images | Grilles isométriques par fabricant, PDF téléchargeable. Auteur : Erec. |
| [RSI Community Hub — Cargo Grid Reference Guide](https://robertsspaceindustries.com/community-hub/post/cargo-grid-reference-guide-vqkv5cQI8ZCLC) | Images isométriques | Guide de référence complet, mis à jour par patch. Inclut véhicules sol + freight elevators. |
| [RSI Community Hub — sc-cargo.space](https://robertsspaceindustries.com/community-hub/post/cargo-grid-viewer-https-sc-cargo-space-eKzoGhJn1IMn3) | Post | Annonce du viewer, pas de données structurées. |
| [GitHub — frosty024/Cargo_Grid_Reference_Guide](https://github.com/frosty024/Cargo_Grid_Reference_Guide) | PDF (fork) | Fork du guide d'Erec, releases par version du jeu. |

### Sources de données machine-readable

| Source | Format | Capacité cargo |
|---|---|---|
| [UEX Corp API 2.0](https://uexcorp.space/api/2.0/) | JSON/REST | SCU total uniquement (`/vehicles`). Pas de dimensions de grille. |
| [starcitizen-api.com](https://starcitizen-api.com/api.php) | JSON/REST | SCU total, dimensions physiques globales. Pas de grille. |
| [Star Citizen Wiki — Module:Vehicle/data.json](https://starcitizen.tools/Module:Vehicle/data.json) | JSON | Champ `API_cargo_capacity` (SCU total). Pas de grille. |
| [GitHub — StarCitizenWiki/scunpacked](https://github.com/StarCitizenWiki/scunpacked) | JSON extrait | Données fichiers jeu converties. Structure cargo non documentée publiquement. |
| [GitHub — Dymerz/StarCitizen-GameData](https://github.com/Dymerz/StarCitizen-GameData) | JSON/SQL | XML jeu → JSON (versions 3.6 à 3.10 seulement, obsolète). |

### Source de vérité : fichiers jeu (.p4k)

sc-cargo.space et les guides visuels tirent leurs données des fichiers DataForge du jeu.
Outils d'extraction :

| Outil | Langage | Rôle |
|---|---|---|
| [scdatatools](https://pypi.org/project/scdatatools/) | Python | Lib complète : extraire p4k, convertir CryXML → JSON, parser DataForge |
| [unp4k](https://github.com/dolkensp/unp4k) | C# | Décompresser + déchiffrer le .p4k (archive Zip + chiffrement CryEngine) |
| [StarBreaker](https://github.com/diogotr7/StarBreaker) | C# | Reverse engineering p4k, dcb, chf — le plus récent |
| unforge (inclus dans unp4k) | C# | Convertir CryXML sérialisé → XML standard |

Les grilles cargo sont définies dans les entités véhicules en CryXML, avec les coordonnées
précises de chaque "port" de cargo (position X/Y/Z, dimensions en mètres).

---

## Modèle de données proposé (table statique)

### Principe

Plutôt que de stocker les dimensions exactes en cellules (L×W×H), on modélise chaque
vaisseau comme une **liste de zones** caractérisées par leur hauteur disponible et leur
capacité SCU. Simple, suffisant pour calculer la capacité effective.

### Hauteur physique des caisses (en cellules de 1 SCU)

> Valeurs partiellement vérifiées — à confirmer sur les images des guides.

| Taille caisse | Hauteur (cellules) | Notes |
|---|---|---|
| 1 SCU | 1 | Confirmé |
| 2 SCU | 1 | À vérifier |
| 4 SCU | 1 | À vérifier |
| 8 SCU | 2 | Confirmé par exemple M2 |
| 16 SCU | 2 | À vérifier |
| 32 SCU | 2 | Cohérent avec exemple M2 (10 × 32 SCU dans zone h=2) |
| 96 SCU | 3 | À vérifier |
| 128 SCU | 4 | À vérifier |

### Structure Python envisagée

```python
# uexinfo/data/cargo_grids.py

# Hauteur physique (cellules) par taille de caisse
CONTAINER_HEIGHT: dict[int, int] = {
    1:   1,
    2:   1,
    4:   1,
    8:   2,
    16:  2,
    32:  2,
    96:  3,
    128: 4,
}

# Par vaisseau : [(hauteur_dispo, scu_dans_cette_zone), ...]
# Zones triées par hauteur décroissante
SHIP_CARGO_ZONES: dict[str, list[tuple[int, int]]] = {
    "Crusader_M2_Hercules": [(2, 320), (1, 202)],
    "Crusader_C2_Hercules": [(4, 696)],
    # À compléter...
}

def effective_scu(ship_name: str, min_container_scu: int) -> int | None:
    """
    Retourne le SCU effectivement chargeable si le terminal impose
    des caisses de taille >= min_container_scu.
    Retourne None si le vaisseau n'est pas dans la table.
    """
    zones = SHIP_CARGO_ZONES.get(ship_name)
    if zones is None:
        return None
    min_h = CONTAINER_HEIGHT.get(min_container_scu, 1)
    return sum(scu for h, scu in zones if h >= min_h)
```

### Exemple d'utilisation

```python
# Terminal qui vend minimum 8 SCU
effective_scu("Crusader_M2_Hercules", 8)  # → 320
effective_scu("Crusader_C2_Hercules", 8)  # → 696

# Terminal qui vend minimum 1 SCU (pas de contrainte)
effective_scu("Crusader_M2_Hercules", 1)  # → 522
```

---

## Plan de remplissage de la table

La méthode la plus rapide sans extraire les fichiers jeu :

1. **Source primaire** : images isométriques du [guide ratjack.net](https://ratjack.net/Star-Citizen/Cargo-Grids/)
   et du [RSI Community Hub](https://robertsspaceindustries.com/community-hub/post/cargo-grid-reference-guide-vqkv5cQI8ZCLC).
   Elles montrent clairement le nombre de couches par zone.

2. **Source secondaire** : [sc-cargo.space](https://sc-cargo.space/#/v1/viewer) pour les vaisseaux
   manquants ou ambigus — la vue 3D permet de compter les hauteurs.

3. **Priorité** : commencer par les vaisseaux cargo courants :
   - Hercules M2 / C2 / A2
   - Caterpillar
   - Hull A / B / C
   - RAFT
   - Freelancer / MAX / MIS
   - Cutlass Black / Steel
   - Constellation Taurus
   - Carrack

4. **Intégration dans uexinfo** : afficher un avertissement dans `/trade` et `/info ship`
   quand la capacité effective < capacité totale pour le terminal sélectionné.

---

## Notes complémentaires

- Les **freight elevators** ont aussi des grilles avec contraintes de hauteur (important
  pour la livraison manuelle depuis un hangar).
- Les zones **off-grid** (ex. Vulture, Corsair, C1) ne sont pas standardisées et dépendent
  d'emplacements hors de la grille officielle — sc-cargo.space les visualise séparément.
- La capacité SCU d'un vaisseau dans l'API UEX (`/vehicles`) correspond à la capacité
  **totale théorique**, pas à la capacité effective avec des caisses standard.
- Le terme "SCU" dans ce contexte = une cellule de cargo de 1,25m × 1,25m × 1,25m environ.
