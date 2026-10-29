# CONSIGNES — Claude Code Sonnet — Fin Mars 2026

Ce document guide le travail de Claude Code (Sonnet) sur le projet **uexinfo**.
Il découpe les chantiers, identifie les améliorations prioritaires et prépare
l'ajout de la sous-commande `/voyage tb` (tableau de bord).

---

## 0. Contexte projet

- **uexinfo** = REPL interactif Star Citizen (trading, missions, voyages).
- **3 interfaces** : CLI (REPL prompt_toolkit), TUI (Textual), Overlay (WebSocket).
- **Priorité absolue : Overlay.** CLI et TUI sont secondaires, potentiellement à purger.
- Toute l'UI est en **français**.
- Couleurs via `uexinfo/display/colors.py` — jamais de chaînes brutes.
- Persistance = **fichiers JSON** dans `~/.uexinfo/`.

---

## 1. Découpage CLI / TUI / Overlay

### 1.1 Overlay (PRIORITAIRE)

L'overlay (`overlay/server.py`, ~1050 lignes) est le mode principal.
Toute nouvelle fonctionnalité doit fonctionner en overlay d'abord.

**Actions :**
- Vérifier que chaque commande envoie ses résultats via `ctx._overlay_send_fn`
  en plus de l'affichage Rich console.
- Les "boutons" interactifs (ajouter au voyage, éditer, supprimer) doivent
  émettre des messages JSON structurés que le frontend JS peut interpréter.

### 1.2 CLI (secondaire, potentiellement à purger)

Le REPL (`cli/main.py`) fonctionne mais est lourd à maintenir en parallèle.

**Décision à prendre :** garder un mode CLI minimal (headless pour debug/test)
ou purger entièrement au profit de l'overlay ?

**Si on garde** : ne plus investir de temps UI sur le CLI — limiter au dispatch
des commandes et à l'affichage Rich de base.

### 1.3 TUI (à purger)

Le mode Textual (`app.py`, `widgets/`, `screens/`) est un doublon de l'overlay
avec plus de complexité. Les widgets sont lourds (~650 lignes pour prompt.py seul).

**Action recommandée :**
- Marquer le code TUI comme **deprecated** (commentaire en tête de `app.py`).
- Ne plus y investir de temps. Ne pas casser le code existant, mais ne pas
  l'adapter pour les nouvelles features.
- À terme : supprimer `app.py`, `widgets/`, `screens/` et le entry point
  `uexinfo-tui` de `pyproject.toml`.

---

## 2. Aide des commandes — Harmonisation

### 2.1 Problème actuel

Chaque commande gère son aide différemment :
- `/help` a un dict `_COMMANDS` + `_DETAILS` (statique, facile à oublier)
- Certaines commandes ont `_show_help()` interne (voyage, mission)
- D'autres n'ont aucune aide (`/explore`, `/auto`, `/undo`, `/calc`, `/debug`, `/dev`)
- Le `__doc__` des handlers n'est pas exploité

### 2.2 Solution proposée

**Convention unique** : chaque handler `cmd_xxx` **DOIT** avoir :

1. Un `__doc__` de 1 ligne (description courte, utilisée par `/help`)
2. Réagir à `args == ["help"]` ou `args == ["?"]` ou `args == ["--help"]`
   en affichant l'aide détaillée
3. L'aide détaillée est une fonction `_show_help()` locale qui affiche
   usage + sous-commandes + exemples

**Pattern à répliquer** (voir `/voyage calc` qui le fait bien) :

```python
@register("macommande", "mc")
def cmd_macommande(args: list[str], ctx) -> None:
    """Description courte affichée par /help."""
    if not args or args[0] in ("help", "?", "--help"):
        _show_help()
        return
    # ... dispatch sous-commandes
```

**Commandes à corriger** (aide manquante ou incomplète) :
- `/explore` — aucune aide
- `/auto` — aucune aide
- `/undo` — aucune aide
- `/calc` (`/=`) — aucune aide
- `/debug` — aucune aide
- `/dev` — aucune aide
- `/history` — aucune aide
- `/go` — aide incomplète
- `/select` — aide incomplète
- `/refresh` — aide incomplète

**Mettre à jour `_DETAILS` dans `help.py`** pour chaque commande corrigée.

---

## 3. Harmonisation des options

### 3.1 Problème actuel

Les conventions d'options varient entre commandes :
- `/voyage calc` utilise `--boucle`, `--station`, `--max:N`
- `/info commodity` utilise `--all`, `--Sys1,Sys2` (filter systèmes)
- `/nav` utilise des sous-commandes positionnelles
- `/scan` mélange sous-commandes et paramètres positionnels

### 3.2 Convention à adopter

| Type | Format | Exemple |
|------|--------|---------|
| Sous-commande | 1er argument, minuscule | `/trade buy copper` |
| Flag booléen | `--nom` | `--boucle`, `--all` |
| Option avec valeur | `--nom valeur` ou `--nom:valeur` | `--max 5`, `--max:5` |
| Référence par ID | `#N` ou `N` (nombre seul) | `/mission view 3` |
| Référence par nom | texte libre | `/voyage MonTrajet list` |
| Étape | `-N` (tiret + nombre) | `/voyage tb -3` |
| Filtre système | `--sys Stanton` | (remplacer `--Sys1,Sys2`) |

**Actions :**
- Normaliser `/info commodity --all --sys Stanton,Pyro` (au lieu de `--Stanton,Pyro`)
- Supporter `--help` partout (en plus de `help` et `?`)
- Unifier le parsing : extraire une mini-lib `cli/opts.py` avec :
  ```python
  def parse_flags(args: list[str]) -> tuple[dict, list[str]]:
      """Sépare flags (--xxx) et arguments positionnels."""
  ```

---

## 4. Optimisation du cache

### 4.1 Problème actuel

- `CacheManager` charge TOUT en mémoire au démarrage (tous les terminaux,
  toutes les commodités, tous les véhicules) → lent sur les premières requêtes.
- `PriceCache` est un dict simple `{key: (timestamp, data)}` sans LRU.
- Les fichiers JSON dans `~/.uexinfo/` sont réécrits intégralement à chaque `save()`.
- Le transport graph (`transport_network.json`) est rechargé/sauvé à chaque
  modification de route.

### 4.2 Améliorations suggérées

**Court terme (faible effort) :**
- Ajouter un **LRU** au `PriceCache` (max 200 entrées, éjecter les plus vieilles)
- Ne pas sauvegarder `voyages.json` à **chaque** opération — bufferiser et sauver
  en batch (toutes les 30s ou à la fermeture). Idem pour `missions.json`.
- Ajouter `__slots__` aux dataclasses `Commodity`, `Terminal`, `Vehicle` pour
  réduire l'empreinte mémoire (~30% de RAM en moins sur 5000+ terminaux).

**Moyen terme :**
- Lazy loading : ne charger `vehicles` que quand `/info ship` ou `/explore ship`
  est appelé. Les véhicules ne sont pas nécessaires au démarrage.
- Index inversé pour `LocationIndex` : stocker `{mot → [terminal_ids]}` plutôt
  que de scanner toute la liste à chaque recherche.

**Non recommandé :**
- SQLite : la complexité ajoutée n'en vaut pas la peine pour ce volume de données.
- Compression : les JSON font quelques Mo max, ça ne justifie pas gzip.

---

## 5. Simplifications du code

### 5.1 Fichiers trop gros

| Fichier | Lignes | Action |
|---------|--------|--------|
| `commands/info.py` | ~1200 | Découper : `info_terminal.py`, `info_commodity.py`, `info_ship.py` |
| `commands/voyage.py` | ~1350 | Découper : `voyage_calc.py` (l'algo TSP + propositions) |
| `overlay/server.py` | ~1050 | Extraire `overlay/handlers.py` (dispatch des messages WS) |
| `ocr/engine.py` | ~960 | OK pour l'instant, déjà bien structuré |

### 5.2 Complexité excessive

- **TSP brute-force** dans `voyage.py` (~200 lignes) : l'algo est correct mais
  le code mélange logique métier, UI (progress bar), et optimisation.
  → Extraire dans `uexinfo/algo/voyage_solver.py`.

- **`_resolve` dans voyage.py** : la résolution du voyage cible + sous-commande
  est complexe (flag `-n`, nom de voyage, sous-commande). Documenter clairement
  la grammaire acceptée en commentaire.

- **Sélecteur multi** (`cli/selector.py`) : utilisé par voyage et mission.
  Vérifier qu'il fonctionne bien en mode overlay (il semble conçu pour le REPL).

### 5.3 Code mort ou stub

- `sctrade_client.py` — stub vide. Le garder tel quel, Phase 4.
- `screens/` (info.py, trade.py, route.py) — screens Textual inutilisées si TUI purgé.
- `widgets/position_bar.py` — semble non utilisé, vérifier.

---

## 6. Nouvelle sous-commande : `/voyage tb` (Tableau de Bord)

### 6.1 Vue d'ensemble

Le **tableau de bord** est une vue interactive qui affiche les missions
disponibles au départ d'un lieu, regroupées par destination, pour aider le
joueur à construire son voyage étape par étape.

### 6.2 Alias et invocation

```
/voyage tb [options]
/voyage tableauBord [options]
/voyage dashboard [options]
/voyage db [options]
```

Ajouter ces alias dans `_SUBS` de `voyage.py`.

### 6.3 Arguments et options

| Argument | Description |
|----------|-------------|
| `<lieu>` | Lieu de départ (positional, optionnel) |
| `-N` | Étape suivante (`-1` = étape 1, `-2` = étape 2…) |
| `-X` ou `X` | Numéro d'étape spécifique |
| `list` | Lister toutes les étapes ou les missions d'une étape |
| `compact` | `/voyage tb compact` — purge les étapes vides |
| `graph` | `/voyage tb graph` — affichage arbre des étapes |
| `--scu` | Option graph : afficher SCU sur les traits |
| `--dist` | Option graph : afficher distances (défaut) |
| `--benef` | Option graph : afficher bénéfice |

### 6.4 Modèle de données — Étapes

Le modèle `Voyage` actuel n'a pas de notion d'**étape**. Il faut l'ajouter.

**Modification de `models/voyage.py` :**

```python
@dataclass
class VoyageStep:
    """Une étape dans un voyage."""
    number: int                          # Numéro d'étape (1, 2, 3…)
    departure: str | None = None         # Lieu de départ (déduit ou explicite)
    mission_ids: list[int] = field(default_factory=list)
    _empty_display_count: int = 0        # Compteur affichages vide (purge à 3)

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "VoyageStep": ...

@dataclass
class Voyage:
    id: int
    name: str
    steps: list[VoyageStep] = field(default_factory=list)  # REMPLACE mission_ids
    departure: str | None = None
    arrival: str | None = None
    # ... reste inchangé
```

**Migration** : à la lecture d'un ancien `voyages.json` sans `steps`,
convertir `mission_ids` en une seule étape `VoyageStep(number=1, mission_ids=...)`.

### 6.5 Logique de départ automatique

```
Si le joueur précise un lieu de départ → l'utiliser
Sinon si étape N > 1 :
    → Arrivée majoritaire de l'étape N-1
    (= destination la plus fréquente parmi les missions de l'étape précédente)
Sinon si étape 1 :
    → Position courante du joueur (ctx.player.location)
Sinon :
    → print_warn("Aucun point de départ évident, veuillez le préciser")
```

Implémenter dans une fonction :
```python
def _infer_step_departure(voyage: Voyage, step_number: int, ctx) -> str | None:
```

### 6.6 Affichage principal — Missions par destination

Quand on appelle `/voyage tb` ou `/voyage tb <lieu>` :

1. **Déterminer le lieu de départ** (voir 6.5)
2. **Chercher les missions** dont une source correspond au départ
3. **Grouper par destination**
4. **Trier par récompense décroissante** dans chaque groupe
5. **Afficher un tableau par groupe de destination**

```
═══ Tableau de bord — départ : Port Olisar ═══

── Destination : Lorville (12.3 Gm) ──────────
[+]  #  Nom                 SCU  Récomp.    ROI      Dist
[+]  5  Livraison urgente    16  45 000α   3 658/Gm  12.3Gm
[+]  8  Transport médical     8  22 000α   1 789/Gm  12.3Gm
[+] 12  Fret industriel      32  18 000α   1 463/Gm  12.3Gm

── Destination : Area 18 (8.7 Gm) ────────────
[+]  3  Composants électr.   24  38 000α   4 368/Gm   8.7Gm
[+]  9  Pièces détachées      8  12 000α   1 379/Gm   8.7Gm
```

**Colonnes requises :**
- `[+]` = bouton ajouter au voyage (assigne l'étape courante)
- `#` = ID mission
- `Nom` = nom de la mission
- `SCU` = volume total
- `Récomp.` = récompense en aUEC
- `ROI` = aUEC / Gm (récompense / distance)
- `Dist` = distance source → destination

### 6.7 Mode `list` — Lister les étapes

`/voyage tb list` → affiche toutes les étapes avec résumé :

```
═══ Étapes du voyage : mon-trajet ═══
Ét.  Départ         Missions  SCU   Récomp.    Dist.
 1   Port Olisar    3         56□   105 000α   12.3Gm
 2   Lorville       2         24□    58 000α    8.7Gm
 3   Area 18        1          8□    22 000α   15.1Gm
                    ─────────────────────────────────
                    6        88□   185 000α   36.1Gm
```

`/voyage tb list -2` → affiche les missions de l'étape 2 avec boutons :

```
═══ Étape 2 — Départ : Lorville ═══
[✎] [✕] [📷]  #5  Livraison urgente  16 SCU  45 000α  [Ét.1] [Ét.2●] [Ét.3] [+4]
[✎] [✕] [📷]  #8  Transport médical   8 SCU  22 000α  [Ét.1] [Ét.2●] [Ét.3] [+4]
```

**Boutons par mission :**
- `[✎]` = éditer la mission (`/mission edit <id>`)
- `[✕]` = supprimer du voyage (clic direct, pas de confirmation)
- `[📷]` = ouvrir le screenshot source (si disponible, via `source_raw`)
- `[Ét.N]` = déplacer la mission vers l'étape N (le `●` marque l'étape actuelle)
- `[+N]` = créer une nouvelle étape et y déplacer la mission

### 6.8 Mode `compact`

`/voyage tb compact` → supprime les étapes sans mission.
Équivalent de renuméroter les étapes non-vides.

Note : une étape vide disparaît automatiquement au bout de 3 affichages
(compteur `_empty_display_count` dans `VoyageStep`).

### 6.9 Mode `graph` — Arbre des étapes

`/voyage tb graph` → affichage en arbre (style `tree` de Rich) :

```
Voyage : mon-trajet
├── Ét.1 : Port Olisar
│   ├──[12.3 Gm]── Lorville
│   │   ├── #5 Livraison urgente (45 000α)
│   │   └── #8 Transport médical (22 000α)
│   └──[8.7 Gm]── Area 18
│       └── #3 Composants électr. (38 000α)
├── Ét.2 : Lorville
│   └──[15.1 Gm]── New Babbage
│       └── #12 Fret industriel (18 000α)
└── Ét.3 : Area 18
    └──[9.2 Gm]── Port Olisar
        └── #9 Pièces détachées (12 000α)
```

**Options d'affichage sur les traits :**
- Par défaut ou `--dist` : distance en Gm/Mm
- `--scu` : volume SCU total vers cette destination
- `--benef` : bénéfice total (somme récompenses) vers cette destination

Utiliser `rich.tree.Tree` pour le rendu.

### 6.10 Intégration overlay

Pour l'overlay, le tableau de bord doit émettre un message JSON :

```json
{
  "type": "voyage_dashboard",
  "departure": "Port Olisar",
  "step_number": 1,
  "groups": [
    {
      "destination": "Lorville",
      "distance_gm": 12.3,
      "missions": [
        {
          "id": 5,
          "name": "Livraison urgente",
          "scu": 16,
          "reward": 45000,
          "roi": 3658,
          "screenshot_path": "C:/Games/.../screenshot.jpg"
        }
      ]
    }
  ]
}
```

Le frontend JS interprète les boutons `[+]`, `[✎]`, `[✕]`, `[📷]`, `[Ét.N]`
comme des actions envoyées au serveur WebSocket.

### 6.11 Plan d'implémentation

**Phase A — Modèle (1h)**
1. Ajouter `VoyageStep` dans `models/voyage.py`
2. Modifier `Voyage` pour utiliser `steps` au lieu de `mission_ids`
3. Ajouter migration dans `VoyageManager._load()`
4. Mettre à jour `VoyageManager` : `add_mission_to_step()`, `move_mission()`,
   `remove_step()`, `compact_steps()`, `get_step_departure()`
5. Adapter tout le code existant de `voyage.py` qui utilise `mission_ids`

**Phase B — Sous-commande tb (2h)**
1. Ajouter les alias `tb`, `tableauBord`, `dashboard`, `db` dans `_SUBS`
2. Implémenter `_cmd_dashboard(args, voyage, ctx)`
3. Parser les options : lieu de départ, `-N`, `list`, `compact`, `graph`
4. Implémenter `_infer_step_departure()`
5. Implémenter `_dashboard_main()` — affichage groupé par destination
6. Implémenter `_dashboard_list()` — liste des étapes / missions d'une étape
7. Implémenter `_dashboard_compact()`
8. Implémenter `_dashboard_graph()` avec `rich.tree.Tree`

**Phase C — Overlay (1h)**
1. Émettre le JSON `voyage_dashboard` pour l'affichage principal
2. Émettre les actions interactives (boutons)
3. Gérer les messages retour du frontend (add, move, delete, edit)

**Phase D — Complétion et aide (30min)**
1. Ajouter les sous-commandes dans `completer.py`
2. Ajouter l'aide dans `_show_help()` de voyage
3. Mettre à jour `_DETAILS` dans `help.py`

---

## 7. Points d'attention

### 7.1 Ne pas casser l'existant

Le `/voyage calc` fonctionne et est utilisé. La migration vers les `steps`
doit être transparente — un voyage existant sans steps doit continuer à
fonctionner.

### 7.2 Performance du tableau de bord

Le tb va chercher les missions par source → besoin d'un **index inversé**
dans `MissionManager` :

```python
def missions_by_source(self, location: str) -> list[Mission]:
    """Retourne les missions dont une source correspond au lieu."""
```

Utiliser `LocationIndex.find()` pour le fuzzy matching des noms de lieux.

### 7.3 Distances

Le tableau de bord utilise beaucoup les distances. Pré-calculer la matrice
des distances entre les lieux courants et la cacher dans `ctx` pour éviter
des appels Dijkstra répétitifs (le code de `voyage calc` fait déjà ça).

### 7.4 Tests

Aucun test n'existe pour l'instant. Avant d'ajouter des features, ce serait
bien d'avoir au minimum :
- `tests/test_voyage_model.py` — sérialisation/désérialisation des Steps
- `tests/test_voyage_manager.py` — CRUD + migration
- `tests/test_dashboard.py` — logique d'inférence du départ

---

## 8. Scraping direct du site UEX Corp

### 8.1 Constat

Actuellement, **uexinfo n'accède à UEX que via l'API REST 2.0**
(`uex_client.py` → `https://uexcorp.space/api/2.0`).
Il n'existe **aucun module de scraping** du site web UEX.

Le `sctrade_client.py` est un stub pour sc-trade.tools (Phase 4), pas pour UEX.

### 8.2 Données manquantes (site web uniquement)

Certaines informations sont disponibles **uniquement sur le site web** UEX
et ne sont pas exposées par l'API 2.0 :

| Donnée | Page web UEX | Endpoint API | Statut |
|--------|--------------|--------------|--------|
| **Missions** (types, récompenses, factions, conditions) | Pages missions | ❌ Aucun | Critique pour `/voyage tb` |
| **Distances** entre lieux (Gm) | Fiches terminaux, routes | Partiel (`commodities_routes.distance`) | Incomplet |
| **Infos raffinerie** (temps, rendements, recettes) | Pages raffinerie | ❌ Aucun | Utile |
| **Événements / alertes** (Jumptown, NineTails, etc.) | Page d'accueil / events | ❌ Aucun | Bonus |
| **Réputation factions** (détails, missions par faction) | Pages factions | Partiel (`/factions` = liste seulement) | Utile |
| **Historique des prix** (graphiques, tendances) | Pages commodités | ❌ Aucun (seulement min/max/avg) | Bonus |
| **Grilles cargo détaillées** (par vaisseau) | Pages véhicules | ❌ Aucun (`/vehicles.scu` = total seulement) | Utile |

### 8.3 Architecture proposée : `uex_scraper.py`

Créer un nouveau module `uexinfo/api/uex_scraper.py` pour le scraping direct.

**Stratégie technique :**
- **BeautifulSoup + requests** en priorité (léger, pas de dépendance lourde)
- **Playwright** en fallback si le site charge les données en JS (XHR/fetch)
- Reprendre le pattern de `sctrade_client.py` (prévu pour Playwright en Phase 4)
- **Cache agressif** : les données scrapées changent rarement → TTL 24h minimum
- **Rate limiting** : 1 requête/seconde max, User-Agent identifié

**Structure du module :**

```python
"""Scraper direct du site web UEX Corp (complément à l'API REST)."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://uexcorp.space"
TIMEOUT = 15

class UEXScraper:
    """Accès aux données du site web UEX non disponibles via l'API."""

    def __init__(self, timeout: int = TIMEOUT):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "uexinfo-cli/0.1 (companion tool)",
        })
        self.timeout = timeout

    def _get_soup(self, path: str) -> BeautifulSoup:
        """Récupère et parse une page HTML."""
        url = f"{BASE_URL}/{path.lstrip('/')}"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")

    # ── Missions ─────────────────────────────────────────────────────
    def get_missions(self) -> list[dict]:
        """Liste des types de missions avec récompenses."""
        ...

    def get_mission_detail(self, slug: str) -> dict | None:
        """Détail d'une mission spécifique."""
        ...

    # ── Distances / Lieux ────────────────────────────────────────────
    def get_terminal_distances(self, terminal_slug: str) -> list[dict]:
        """Distances depuis un terminal vers les autres."""
        ...

    # ── Raffinerie ───────────────────────────────────────────────────
    def get_refinery_info(self, terminal_slug: str) -> dict | None:
        """Infos raffinerie : méthodes, durées, rendements."""
        ...

    # ── Grilles cargo ────────────────────────────────────────────────
    def get_vehicle_cargo_grid(self, vehicle_slug: str) -> dict | None:
        """Grille cargo détaillée d'un vaisseau."""
        ...
```

### 8.4 URLs connues du site UEX

> **Note** : ces URLs sont basées sur la structure actuelle du site.
> Le scraper devra être testé et ajusté — les sélecteurs CSS peuvent changer.
> Si les URLs ci-dessous ne sont plus valides, le user les fournira.

**Pages de référence :**
- Page d'accueil : `https://uexcorp.space/`
- Commodités : `https://uexcorp.space/commodities`
- Terminaux : `https://uexcorp.space/terminals`
- Véhicules : `https://uexcorp.space/vehicles`
- Routes commerciales : `https://uexcorp.space/trade-routes`
- Factions : `https://uexcorp.space/factions`

**Pages de détail (pattern slug) :**
- Commodité : `https://uexcorp.space/commodities/copper`
- Terminal : `https://uexcorp.space/terminals/port-olisar`
- Véhicule : `https://uexcorp.space/vehicles/cutlass-black`

**⚠ URLs à vérifier/fournir par le user :**
- Pages missions : URL inconnue — le user doit fournir l'URL si elle existe
- Pages raffinerie : URL inconnue
- Pages événements : URL inconnue

### 8.5 Intégration dans le code existant

1. **Ajouter `uex_scraper.py`** dans `uexinfo/api/`
2. **Ajouter `UEXScraper` à `AppContext`** (lazy init, instancié au premier appel)
3. **Cache dédié** : stocker les résultats scrapés dans `~/.uexinfo/scraped/`
   avec un fichier par type (missions.json, distances.json, etc.)
4. **Fallback** : si le scraping échoue, utiliser les données API ou le cache disque
5. **Commande de refresh** : `/refresh web` ou `/refresh scrape` pour forcer

### 8.6 Dépendances

`beautifulsoup4` est **déjà dans `pyproject.toml`** — pas de nouvelle dépendance
pour le scraping basique. Playwright est déjà en dépendance optionnelle.

### 8.7 Plan d'implémentation

**Phase 1 — Reconnaissance (30min)**
- [ ] Ouvrir les pages UEX dans un navigateur, identifier la structure HTML
- [ ] Vérifier si les données sont dans le HTML statique ou chargées en XHR
- [ ] Si XHR : intercepter les appels réseau, possibilité d'appeler les endpoints
  internes directement (souvent plus stable que le scraping HTML)
- [ ] Documenter les sélecteurs CSS/XPath utilisés

**Phase 2 — Module scraper (1h)**
- [ ] Créer `uexinfo/api/uex_scraper.py`
- [ ] Implémenter les méthodes prioritaires : missions, distances
- [ ] Ajouter le cache disque dans `~/.uexinfo/scraped/`
- [ ] Tests manuels

**Phase 3 — Intégration (1h)**
- [ ] Brancher sur `AppContext` (lazy loading)
- [ ] Utiliser dans `/voyage tb` pour les données missions
- [ ] Utiliser dans `/nav` pour enrichir les distances
- [ ] Ajouter `/refresh web`

---

## 9. Récapitulatif des tâches par priorité

### Priorité 1 — Fondations
- [ ] Harmoniser l'aide de toutes les commandes (§2)
- [ ] Créer `cli/opts.py` pour le parsing unifié des options (§3)
- [ ] Ajouter `VoyageStep` au modèle + migration (§6 Phase A)
- [ ] Reconnaissance site web UEX : structure HTML, XHR, sélecteurs (§8 Phase 1)

### Priorité 2 — Tableau de bord + scraping
- [ ] Créer `uex_scraper.py` — missions et distances (§8 Phase 2)
- [ ] Implémenter `/voyage tb` affichage principal (§6 Phase B)
- [ ] Implémenter `list`, `compact`, `graph` (§6 Phase B)
- [ ] Intégration overlay (§6 Phase C)
- [ ] Complétion + aide (§6 Phase D)
- [ ] Brancher le scraper dans AppContext + `/refresh web` (§8 Phase 3)

### Priorité 3 — Qualité
- [ ] Découper `info.py` en 3 fichiers (§5.1)
- [ ] Extraire `voyage_calc.py` (§5.1)
- [ ] Optimiser le cache : LRU, lazy loading, `__slots__` (§4)
- [ ] Marquer TUI comme deprecated (§1.3)
- [ ] Écrire les tests minimaux (§7.4)

### Priorité 4 — Nettoyage
- [ ] Purger le code TUI si décision prise
- [ ] Nettoyer les stubs inutilisés
- [ ] Harmoniser les options entre commandes (§3)
