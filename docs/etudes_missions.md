# Étude : Système missions & voyages

> **Projet** : uexinfo — CLI Star Citizen
> **Date** : 2026-03-20
> **Statut** : Phase 1 en cours

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

## 2. Modèles de données

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
  source_raw: str | None       # Origine ("manual", "scan:fichier.png", "clipboard")
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

### Rétention des voyages (config)

```toml
[voyages]
retention = 24        # heures — supprimer les voyages > 24h
# ou
retention = "ps"      # prochaine session — supprimer après 1 session
# ou
retention = "ps:3"    # garder les 3 dernières sessions
```

Une **session** commence au démarrage et se termine au `/quit` (ou équivalent).
`/quit -tbc` (to be continued) ne ferme pas la session — le compteur n'est pas incrémenté.

---

## 3. Commandes `/mission` (catalogue)

```
/mission list                    Liste toutes les missions du catalogue
/mission add <nom> reward:<n>
         [obj:<c> from:<s> to:<d> scu:<n> [tdd|shop|delay:<r>]]+
                                 Ajoute une mission manuellement
/mission edit <id|nom> ...       Modifie une mission (mêmes options)
/mission remove <id|nom>         Supprime du catalogue
/mission scan [<fichier>]        Scanne screenshot → extrait mission(s) — Phase 2
```

**Alias** : `/m` = `/mission`

### Synergies entre missions

| Symbole | Signification |
|---------|---------------|
| `⊙` | Même lieu de départ qu'une autre mission sélectionnée |
| `⊕` | Même lieu d'arrivée qu'une autre mission sélectionnée |
| `⇄` | Mission relais (destination d'une autre = ce départ) |

---

## 4. Commandes `/voyage` (planification)

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

### Affichage `/voyage list` (missions d'un voyage actif)

Même format que `/mission list` mais limité aux missions du voyage, avec en-tête :
```
─── Voyage : trajet-1 ● ──────────────────────────────────────────────────
  Départ : HUR-L2  →  Arrivée : HUR-L2 (boucle)
  3 missions · 26 SCU · 113 000 aUEC
```

---

## 5. Barre d'état overlay

Indicateur `🗺` dans la status bar :
- **Pas de voyage actif** : `🗺` grisé
- **Voyage actif** : `🗺 trajet-1 · 3m` en orange, clic → `/voyage list`

---

## 6. Noms de voyage cliquables (overlay)

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

## 7. Indicateurs temps (Phase 3)

Chaque lieu aura des méta-données de timing (à affiner par l'expérience de jeu) :
- `access_time` : temps de vol depuis l'orbite (minutes)
- `landing_time` : temps d'atterrissage/amarrage
- `takeoff_time` : temps de décollage
- `tdd_time` : temps estimé pour passer au TDD (si applicable)

Le voyage affichera la durée estimée totale, affinée au fil du temps.

---

## 8. Résumé d'un voyage (Phase 3)

```
Voyage "trajet-1"  ·  3 missions  ·  26 SCU max  ·  113 000 aUEC
Durée estimée  : ~45 min    Distance : 38.2 Gm    Risque : ⚔ (GrimHEX)
Charge utile   : [38 Gm, 68%]   ← Gm avec fret / total Gm
Vaisseau suggéré : Cutlass Black (46 SCU)
```

`[38 Gm, 68%]` = Gm parcourus avec du fret / Gm totaux du voyage.

---

## 9. Scan lot de screenshots (Phase 2 — overlay)

Interface overlay en deux étapes :

### Étape 1 : Sélection des fichiers
- Liste des screenshots détectés avec case à cocher `[✓]` pré-cochée
- Boutons "Tout sélectionner" / "Tout désélectionner"
- Bouton "Scanner"

### Étape 2 : Validation par lot
Après reconnaissance OCR, deux panneaux selon le type d'écran détecté :

**Écrans de mission** → prévisualisation : nom, récompense, objectifs extraits
→ Validation ajoute au catalogue `/mission`

**Écrans achat/vente** → tableau de commodités avec `[✓]` par ligne
→ Boutons "Tout sélectionner" / "Tout désélectionner"
→ Validation crée un scan terminal normal

Boutons finaux : **Valider** · **Annuler**

---

## 10. Phases d'implémentation

### Phase 1 (en cours) ✓

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

### Phase 2

- [ ] Scan lot screenshots → overlay (sélection fichiers + validation par type)
- [ ] `/mission scan` → formulaire overlay
- [ ] Résolution robuste des lieux OCR (Levenshtein + confirmation)

### Phase 3

- [ ] Algorithme TSP route optimale
- [ ] Timing par lieu (accès, atterrissage, décollage)
- [ ] Durée estimée voyage
- [ ] `[Gm, %]` charge utile
- [ ] Suggestion vaisseau automatique
- [ ] Complément de soute (intégration `/trade`)
