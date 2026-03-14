# OCR & Scan de Screenshots — Décisions architecturales

## Contexte

Le Mode B (scan par screenshot) repose sur **Tesseract OCR** via `pytesseract`.
Pour être précis sur les polices de Star Citizen, il faut un modèle entraîné
spécifiquement (`eng_sc.traineddata`), fourni par le projet SC-Datarunner-UEX.

Ce modèle **n'est pas sous licence libre** — il ne peut pas être redistribué
dans uexinfo sans accord de l'équipe SC-Datarunner.

---

## Stratégie retenue

### Scénario principal : SC-Datarunner installé par le joueur

Le joueur installe SC-Datarunner-UEX (gratuit, Windows).
uexinfo lit les fichiers depuis le chemin configuré :

```toml
[scan]
sc_datarunner_path = "C:/Users/toto/AppData/Local/SC-Datarunner-UEX"
```

**SC-Datarunner n'a pas besoin de tourner.** uexinfo utilise seulement :
- `dep/Tesseract-OCR/tesseract.exe`
- `data/eng_sc.traineddata`
- `data/commodities.user-words`
- `data/terminals.user-words`
- `data/sc.patterns`

### Fallback : Tesseract système + modèle `eng` standard

Si SC-Datarunner n'est pas configuré, uexinfo tente :
1. `tesseract` dans le PATH système (installation standard, Apache 2.0)
2. Modèle `eng` (anglais généraliste)

Précision réduite (notamment sur le symbole ø, les prix K/M, les noms de commodités).
Un avertissement est affiché, et l'édition manuelle post-scan est recommandée.

**Ce fallback est particulièrement utile pour :**
- L'écran Missions (texte standard, peu de polices exotiques)
- Les zones de texte courant (objectifs de contrats, descriptions)

Ordre de priorité dans `engine.py` :

```
1. [scan] sc_datarunner_path configuré  → tesseract.exe + eng_sc
2. [scan] tesseract_exe configuré       → exe custom + eng_sc ou eng
3. tesseract dans le PATH               → modèle eng (fallback)
```

---

## Option future : modèle maison `eng_sc2.traineddata`

### Charge de travail estimée

Entraîner un modèle Tesseract custom par fine-tuning depuis `eng` :

| Phase | Tâches | Durée estimée |
|-------|--------|---------------|
| Collecte de données | 500–1000 screenshots annotés (terminal, commodités, prix) | 2–4 semaines |
| Annotation | Bounding boxes + texte ground truth (jTessBoxEditor ou tesstrain) | 2–4 semaines |
| Entraînement | `tesstrain` fine-tuning depuis `eng` base | 1–3 jours (GPU recommandé) |
| Évaluation / itérations | Tests sur screenshots hors-dataset, ajustements | 1–2 semaines |
| **Total anglais seul** | | **~2 mois** |

### Ajout du français

Star Citizen peut être joué en français. Les éléments qui changent de langue :
- Niveaux de stock : "High Inventory" → "Stock élevé" (à confirmer)
- Certains textes d'interface (boutons, onglets)
- Textes de missions (descriptions, objectifs)

Les éléments qui restent en **anglais quelle que soit la langue** :
- Noms de commodités (GOLD, STIMS, SLAM…)
- Prix (format numérique + ø)
- Noms de terminaux (noms propres du jeu)

**Charge additionnelle pour le français :**
- ~300–500 screenshots en client français annotés
- Nouveau fichier `fra_sc.user-words` pour les libellés de stock FR
- ~3–4 semaines supplémentaires

**Total modèle bilingue eng+fra :** ~3–4 mois de travail

### Réalisme

Ce travail est réalisable mais nécessite :
- Un accès régulier au jeu pour les screenshots
- De la rigueur sur l'annotation (c'est le goulot d'étranglement)
- Un outil d'annotation (recommandé : `tesstrain` + `ground_truth/`)

À envisager si SC-Datarunner cesse d'être maintenu ou change de licence.
Pour l'instant, la dépendance SC-Datarunner reste la voie pragmatique.

---

## À implémenter (ticket futur)

- [ ] Lire `[scan] sc_datarunner_path` dans `settings.py` DEFAULT
- [ ] `engine.py` : `_find_exe()` et `_find_data()` lisent la config
- [ ] `engine.py` : `_find_model()` → `eng_sc` si dispo, sinon `eng` + warning
- [ ] `/config scan` : afficher/modifier `sc_datarunner_path`
- [ ] `/scan status` : afficher quel modèle est actif et son chemin
