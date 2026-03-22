# Étude : Système missions & voyages

> **Projet** : uexinfo — CLI Star Citizen
> **Date** : 2026-03-22
> **Statut** : Phase 2 en cours — scan batch screenshots implémenté

---

## 1. Concepts

### Mission (ligne de facture)
Une mission est un trajet élémentaire : aller d'un point A à un point B, éventuellement avec du fret.
Elle appartient au **catalogue** et peut être réutilisée dans plusieurs voyages.

### Voyage (facture)
Un voyage est un ensemble de missions planifiées formant un itinéraire global A → M (via B, C, D…).
C'est la solution en construction du trajet que le joueur souhaite faire.
Un voyage peut devenir une **route régulière** s'il est répété.

```
Voyage "trajet-1"  :  HUR-L2 → GrimHEX → Baijini → HUR-L2
  Mission 1  :  HUR-L2 → GrimHEX  (Quantainium 12 SCU, 50 000 aUEC)
  Mission 2  :  GrimHEX → Baijini  (Laranite     8 SCU, 35 000 aUEC)
  Mission 3  :  Baijini → HUR-L2   (Agricium     6 SCU, 28 000 aUEC)
```

---

## 2. Catégories de missions SC (détectées automatiquement)

Catégories visibles dans le panneau gauche de l'onglet Contrats :

| Catégorie interne       | Libellé affiché              | Détection                                      |
|-------------------------|------------------------------|------------------------------------------------|
| `hauling_stellar`       | Hauling · Stellaire          | "haul/cargo" dans titre + même système         |
| `hauling_interstellar`  | Hauling · Interstellaire     | "haul/cargo" + systèmes différents             |
| `salvage`               | Récupération                 | "salvage" dans titre                           |
| `bounty_hunter`         | Chasseur de primes           | "bounty/fugitive/wanted" dans titre            |
| `mercenary`             | Mercenaire                   | "elimination/neutralize/destroy" dans titre    |
| `collection`            | Collecte                     | "collection" dans titre                        |
| `investigation`         | Enquête                      | "investigation/locate/find" dans titre         |
| `delivery`              | Livraison                    | "delivery/courier" dans titre                  |
| `hand_mining`           | Minage                       | "mining" dans titre                            |
| `pvp`                   | PvP                          | "pvp/arena/combat" dans titre                  |
| `unknown`               | Inconnu                      | Fallback                                       |

**STELLAR vs INTERSTELLAR** : vérifié via le graphe de transport (`transport_network.json`).
Si source et destination appartiennent à des systèmes différents → interstellaire.
Fallback : mots-clés des corps célestes connus (Stanton, Pyro).

### Rangs de confiance par entreprise
Les titres de missions intègrent un rang de confiance (variable selon l'entreprise/alliance) :
`Not Eligible` → `Trainee` → `Rookie` → `Junior` → `Member` → `Experienced` → `Senior` → `Master`

Le rang fait partie du titre affiché mais n'est **pas** une clé de déduplication.
La **clé unique** d'une mission dans la base est son **fichier source** (nom du screenshot).

---

## 3. Modèles de données

### `uexinfo/models/mission.py`

```python
MissionObjective
  commodity: str | None       # Commodité à transporter
  source: str | None           # Lieu de départ
  destination: str | None      # Lieu d'arrivée
  quantity_scu: float | None   # Volume SCU
  time_cost: str | None        # "tdd", "shop", raison libre → pénalité de temps
  notes: str | None

Mission
  id: int                      # Auto-incrémenté dans le catalogue
  name: str
  reward_uec: int
  objectives: list[MissionObjective]
  source_raw: str | None       # Origine ("manual", "ocr", "scan:fichier.png")
  notes: str | None
```

**Stockage catalogue** : `~/.uexinfo/missions.json`

### `uexinfo/models/voyage.py`

```python
Voyage
  id: int                      # Auto-incrémenté
  name: str                    # Défaut : "trajet-{id}"
  mission_ids: list[int]       # IDs ordonnés des missions du catalogue
  departure: str | None        # Point de départ (défaut : position joueur)
  arrival: str | None          # Point d'arrivée désiré (peut différer des missions)
  created_at: float            # Timestamp Unix de création
  session_id: int              # Numéro de session lors de la création
  notes: str | None
```

**Stockage** : `~/.uexinfo/voyages.json`

### `uexinfo/cache/screenshot_db.py` ← **Nouveau (Phase 2)**

Base de données des screenshots pré-traités. Évite de relancer l'OCR à chaque demande.

```python
ScreenshotEntry
  file: str            # Nom du fichier (clé unique, basename)
  path: str            # Chemin absolu
  file_mtime: float    # mtime du fichier (stat)
  processed_at: float  # Timestamp traitement OCR
  type: str            # "mission" | "terminal_buy" | "terminal_sell" | "unknown" | "pending"
  engine: str          # "tesseract" | "sc-datarunner" | "none"
  session_id: str      # "2026-03-21_session1"
  category: str        # Catégorie détectée (voir tableau ci-dessus)
  data: dict           # Données extraites (MissionResult ou ScanResult sérialisé)
  raw: dict            # OCR brut (réservé debug / re-processing)
  errors: list[str]    # Erreurs OCR éventuelles
```

`data` pour une mission contient :
```json
{
  "title":          "Rookie Rank - Small Cargo Haul",
  "tab":            "OFFERS",
  "reward":         42000,
  "availability":   "2h 33m",
  "contracted_by":  "Covalex Independent Contractors",
  "sources":        ["CRU-L4 Shallow Fields Station", "CRU-L5 Beautiful Glen Station"],
  "destinations":   ["Seraphim Station above Crusader"],
  "total_scu":      12.0,
  "objectives":     [ { "kind": "collect|deliver", "commodity": "...", ... } ],
  "blue_text":      [ "..." ],
  "timestamp":      "2026-03-21T11:25:35"
}
```

**Stockage** : `~/.uexinfo/screenshot_db.json` (JSON atomique — write tmp → rename)

### Rétention des voyages (config)

```toml
[voyages]
retention = 24        # heures — supprimer les voyages > 24h
# ou
retention = "ps"      # prochaine session — supprimer après 1 session
# ou
retention = "ps:3"    # garder les 3 dernières sessions
```

---

## 4. Système de sessions

### Définition
Une **session de jeu** correspond à une fenêtre temporelle où les mêmes missions sont
disponibles dans SC. Les missions sont oubliées à chaque changement de serveur.

**Détection automatique** : gap > `scan.session_gap` minutes entre deux screenshots consécutifs
= nouvelle session.

```
ScreenShot-2026-03-21_11-25-35 ┐
ScreenShot-2026-03-21_11-25-47 │ session1 (gap < 60 min)
ScreenShot-2026-03-21_11-27-37 ┘
   [gap > 60 min]
ScreenShot-2026-03-21_14-10-22 ┐
ScreenShot-2026-03-21_14-12-05 ┘ session2
```

`session_id` = `"YYYY-MM-DD_session1"` calculé depuis les gaps existants en DB.

### Config session
```toml
[scan]
session_gap = 60    # minutes — gap = nouvelle session (défaut)
hour        = 2     # heures en arrière pour /mission scan (défaut)
auto_ocr    = true  # lancer OCR dès détection screenshot (défaut)
```

---

## 5. OCR Worker en arrière-plan

### `uexinfo/ocr/ocr_worker.py` ← **Nouveau (Phase 2)**

Thread daemon qui traite les screenshots à mesure qu'ils arrivent.

```
Overlay détecte nouveau screenshot (toutes les 10s)
    ↓
OcrWorker.submit(path)  [si pas déjà en DB]
    ↓  (thread de fond, priorité basse)
TesseractEngine.detect_screen_type(path) → "mission" | "terminal" | "unknown"
    ↓
Si mission  : extract_mission() → MissionResult → _mission_result_to_dict()
Si terminal : extract_from_image() → ScanResult → _scan_result_to_dict()
    ↓
Calcul session_id (gaps mtime)
Détection catégorie (_detect_category)
    ↓
ScreenshotDB.upsert(entry) → save() atomique
    ↓
Callback → broadcast WebSocket {type: "screenshot_processed", n_missions, n_terminals}
    ↓
Badge 📷 N missions dans la barre de statut overlay
```

**Moteur OCR par type** :
- `mission` → Tesseract (seul capable des panneaux Contrats)
- `terminal_buy` / `terminal_sell` → SC-Datarunner log en priorité, Tesseract sinon

---

## 6. Commandes `/mission` (catalogue)

```
/mission list                    Liste toutes les missions du catalogue
/mission scan                    Missions dans la fenêtre scan.hour (défaut 2h)
/mission scan all                Toute la base de screenshots
/mission scan today              Captures d'aujourd'hui
/mission scan terminal           Terminaux scannés dans la base

/mission add <nom> reward:<n>
         [obj:<c> from:<s> to:<d> scu:<n> [tdd|shop|delay:<r>]]+
                                 Ajoute une mission manuellement
/mission add                     Depuis le dernier /scan
/mission add <fichier.jpg>       Scanne screenshot → extrait mission (OCR unitaire)

/mission edit <id|nom> ...       Modifie une mission (mêmes options)
/mission remove <id|nom>         Supprime du catalogue
```

**Alias** : `/m` = `/mission`

### Workflow scan batch (overlay — implémenté)

1. Ouvrir le menu **Contrats** dans Star Citizen
2. Prendre des screenshots (F12) de chaque mission disponible
   - L'animation de défilement peut générer plusieurs captures de la même mission
   - Ce n'est pas un problème : chaque fichier = entrée unique
3. Le badge **📷 N missions** s'allume dans la barre de statut (OCR en fond)
4. Cliquer → panneau `/mission scan` avec :
   - Missions groupées par session
   - Colonnes : ✓ · Heure · Catégorie · Titre · SCU · Récompense · Départ → Arrivée
   - Cases à cocher individuelles + maître par session
   - "Tout sélectionner / Tout désélectionner"
5. Boutons :
   - **Ajouter au catalogue** → crée les missions dans `/mission list`
   - **+ Voyage actif** → crée + ajoute immédiatement au voyage courant
   - **Annuler**

### Synergies entre missions

| Symbole | Signification |
|---------|---------------|
| `⊙` | Même lieu de départ qu'une autre mission sélectionnée |
| `⊕` | Même lieu d'arrivée qu'une autre mission sélectionnée |
| `⇄` | Mission relais (destination d'une autre = ce départ) |

---

## 7. Commandes `/voyage` (planification)

```
/voyage on                       Active le dernier voyage ou crée un nouveau
/voyage off                      Désactive le voyage courant (conservé)
/voyage new [<nom>]              Crée un nouveau voyage + l'active
/voyage <n|nom>                  Active le voyage (quand nom seul)
/voyage <n|nom> <sous-cmd>       Applique sous-commande à ce voyage sans changer l'actif
-n <n|nom>                       Flag pour cibler un voyage précis dans une sous-cmd

/voyage name <nom>               Renomme le voyage actif
/voyage list [--trajets]         Missions du voyage actif, ou tous les voyages
/voyage clear                    Vide les missions du voyage actif
/voyage add [m1 m2 ...]          Ajoute des missions par ID/nom
/voyage remove <id|nom>          Retire une mission du voyage
/voyage copy [<n|nom>]           Copie le voyage actif vers n (fusion) ou nouveau
/voyage accept                   Valide + analyse
/voyage later                    Sauvegarde sans analyse, désactive
/voyage cancel                   Annule les modifications depuis la dernière sauvegarde
```

**Alias** : `/v` = `/voyage`

### Affichage `/voyage list` (liste des voyages)

```
─── Voyages ────────────────────────────────────────────────────────────────
 #  * Nom              Missions  SCU    Récompense   Départ → Arrivée
── ── ──────────────── ──────── ──────  ──────────── ──────────────────────
 1  ● trajet-1          3 miss.   26□    113 000 aUEC  HUR-L2 → HUR-L2
 2    Route-Quant        2 miss.   16□     64 000 aUEC  ArcCorp → Baijini

● = voyage actif
```

---

## 8. Barre d'état overlay

| Indicateur | Signification | Clic |
|---|---|---|
| `ScanSC` | Nouveau screenshot SC détecté | Lance `/scan` |
| `ScanLog` | Log SC-Datarunner modifié | Lance `/scan log` |
| `📷 N missions` | N missions prêtes dans la DB OCR | Lance `/mission scan` |
| `🗺 nom · Nm` | Voyage actif | Lance `/voyage list` |

**Priorité** : ScanLog prend le dessus sur ScanSC (ils ne clignotent pas simultanément).
ScanSC et `📷` sont indépendants.

---

## 9. Config `/config scan`

```
/config scan auto_ocr on|off          OCR auto dès détection (défaut : on)
/config scan hour <n>                 Fenêtre /mission scan en heures (défaut : 2)
/config scan session_gap <minutes>    Gap entre sessions en minutes (défaut : 60)
/config scan mode ocr|log|confirm     Mode de scan terminal
/config scan tesseract <path>         Chemin tesseract.exe (auto-détecté sinon)
/config scan logpath <path>           Chemin app.log SC-Datarunner
/config scan screenshots <path>       Dossier screenshots SC
```

---

## 10. Noms de voyage cliquables (overlay)

Les noms de voyage sont ajoutés au vocabulaire reconnu (`vocab.voyages`).
JS les détecte dans tout le texte de sortie → `<span class="cw cw-voyage" data-type="voyage">`.

- **Double-clic** → `/voyage <nom> list` (affiche les missions du voyage)
- **Clic droit** → menu contextuel :
  - Afficher (`/voyage <nom> list`)
  - **Activer** (`/voyage <nom>`)
  - Analyser (`/voyage <nom> accept`)
  - Copier (`/voyage <nom> copy`)
  - Supprimer (`/voyage <nom> clear`)

---

## 11. Indicateurs temps (Phase 3)

Chaque lieu aura des méta-données de timing (à affiner par l'expérience de jeu) :
- `access_time` : temps de vol depuis l'orbite (minutes)
- `landing_time` : temps d'atterrissage/amarrage
- `takeoff_time` : temps de décollage
- `tdd_time` : temps estimé pour passer au TDD (si applicable)

Le voyage affichera la durée estimée totale, affinée au fil du temps.

---

## 12. Résumé d'un voyage (Phase 3)

```
Voyage "trajet-1"  ·  3 missions  ·  26 SCU max  ·  113 000 aUEC
Durée estimée  : ~45 min    Distance : 38.2 Gm    Risque : ⚔ (GrimHEX)
Charge utile   : [38 Gm, 68%]   ← Gm avec fret / total Gm
Vaisseau suggéré : Cutlass Black (46 SCU)
```

`[38 Gm, 68%]` = Gm parcourus avec du fret / Gm totaux du voyage.

---

## 13. Scan lot de screenshots (Phase 2 — implémenté)

### Architecture

```
uexinfo/cache/screenshot_db.py   ScreenshotDB + ScreenshotEntry
uexinfo/ocr/ocr_worker.py        OcrWorker (thread daemon) + détection catégorie
uexinfo/overlay/server.py        Intégration : check toutes 10s, broadcast WS
uexinfo/cli/commands/mission.py  /mission scan — lit DB, affiche, sélection
uexinfo/overlay/static/index.html  Panneau mission_scan_list + checkboxes
```

### Décisions d'architecture

**Clé de déduplication** : le nom de fichier (basename du screenshot).
- Chaque screenshot = une entrée unique, indépendamment du contenu OCR
- Justification : le titre SC n'est pas suffisamment discriminant (même rang/taille
  pour plusieurs missions différentes) ; le prix ne distingue pas non plus

**Plusieurs captures de la même mission** : elles apparaissent comme entrées séparées.
L'utilisateur choisit celles qu'il veut (typiquement la dernière si animation incomplete).
Phase future : détecter les doublons probables (titre + récompense identiques) et les
regrouper visuellement.

**Moteur OCR** : Tesseract uniquement pour les missions (SC-Datarunner ne couvre pas
l'écran Contrats). SC-Datarunner reste prioritaire pour les terminaux.

**Sessions** : gap temporel configurable (`scan.session_gap`, défaut 60 min).
Les missions expirent entre sessions de serveur → la fenêtre `scan.hour` (défaut 2h)
couvre généralement une session complète.

**Base évolutive** : `screenshot_db.json` est versionné (`"version": "1.0"`).
Champs `raw` réservé pour données OCR brutes (re-processing futur).
Champ `errors` pour traçabilité des échecs.

---

## 14. Phases d'implémentation

### Phase 1 ✓ (complet)

- [x] Modèle `Mission` + `MissionObjective` (catalogue)
- [x] `MissionManager` : CRUD + persistance JSON
- [x] Commandes `/mission` : list/add/edit/remove
- [x] Synergies : `⊙ ⊕ ⇄`
- [x] Modèle `Voyage`
- [x] `VoyageManager` : CRUD + persistance + rétention + session
- [x] Commandes `/voyage` : on/off/new/list/add/remove/name/clear/copy/accept/later/cancel
- [x] Noms de voyage cliquables dans l'overlay (vocab `cw-voyage`)
- [x] Indicateur barre d'état `🗺`
- [x] `/quit -tbc` (to be continued)

### Phase 2 (en cours)

- [x] `ScreenshotDB` — base screenshots persistante (`cache/screenshot_db.py`)
- [x] `OcrWorker` — thread OCR background + détection catégorie (`ocr/ocr_worker.py`)
- [x] Intégration overlay — détection auto + broadcast `screenshot_processed`
- [x] Badge `📷 N missions` dans la barre de statut
- [x] `/mission scan` — lecture DB + tableau sélection (CLI + overlay)
- [x] Panneau overlay `mission_scan_list` — checkboxes par session + boutons
- [x] Config `scan.auto_ocr`, `scan.hour`, `scan.session_gap`
- [ ] Résolution robuste des lieux OCR (Levenshtein + confirmation joueur)
- [ ] Déduplication visuelle des captures probablement identiques
- [ ] `/mission scan` — re-OCR d'une entrée existante (`/mission scan reocr <fichier>`)

### Phase 3

- [ ] Algorithme TSP route optimale
- [ ] Timing par lieu (accès, atterrissage, décollage)
- [ ] Durée estimée voyage
- [ ] `[Gm, %]` charge utile
- [ ] Suggestion vaisseau automatique
- [ ] Complément de soute (intégration `/trade`)
