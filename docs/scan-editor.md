# Éditeur de scan — spec & guide utilisateur

## Vue d'ensemble

Après un `/scan`, le résultat OCR peut contenir des erreurs (nom mal reconnu,
prix illisible, stock incorrect). L'éditeur permet de corriger le tableau avant
de valider les données en base.

## Lancement

| Action | Effet |
|--------|-------|
| `Ctrl+↑` dans le REPL | Ouvre l'éditeur sur le dernier scan |

Si aucun scan n'a été effectué dans la session, un message d'avertissement
s'affiche.

## Mise en page

```
  Éditeur de scan  ·  Orbituary  ·  18:01:35
  ──────────────────────────────────────────────────────────────────
  Terminal : [ Orbituary                    ]   Mode : [ VENTE ]
  ──────────────────────────────────────────────────────────────────
       Commodité                  Stock          Qté    Prix/SCU
  ──────────────────────────────────────────────────────────────────
  [X]  Medical Supplies           Out              0           ?
  [X]  Agricultural Supplies      Out              0        1325
  [X]  Altruciatoxin              Out              0        6438
  [X]  Revenant Tree Pollen       Out              0        1249
  ──────────────────────────────────────────────────────────────────
  Tab/→/Entrée: suiv  ←/Shift+Tab: préc  Espace: basculer  Suppr: effacer
  ──────────────────────────────────────────────────────────────────
    [ Annuler ]                                  [ MAJ DB ]
```

La cellule active est mise en surbrillance (fond grisé). Un curseur `▌`
apparaît en fin des champs texte.

## Champs

### En-tête

| Champ | Type | Interaction |
|-------|------|-------------|
| Terminal | texte libre | frappe directe + Suppr |
| Mode | ACHAT / VENTE | Espace pour basculer |

### Par commodité

| Col | Type | Interaction |
|-----|------|-------------|
| `[X]` / `[ ]` | case à cocher | Espace pour activer/désactiver |
| Commodité | texte libre | frappe directe + Suppr *(complétion : future)* |
| Stock | cycle de 8 niveaux | Espace pour passer au suivant |
| Qté SCU | entier | chiffres + Suppr |
| Prix/SCU | entier aUEC | chiffres + Suppr |

Les commodités décochées `[ ]` sont **exclues** de l'envoi en base (MAJ DB).

### Niveaux de stock (cycle Espace)

`?` → `Out` → `Very Low` → `Low` → `Medium` → `High` → `Very High` → `Max` → `?` …

## Navigation clavier

| Touche | Action |
|--------|--------|
| `Tab` / `→` / `Entrée` | Champ suivant |
| `Shift+Tab` / `←` | Champ précédent |
| `Espace` | Basculer checkbox / cycler stock ou mode |
| `Retour arrière` | Supprimer le dernier caractère (champs texte) |
| `Ctrl+D` | Effacer le contenu de la cellule courante |
| `Échap` / `Ctrl+C` | Annuler sans sauvegarder |
| `Entrée` sur `[ Annuler ]` | Annuler |
| `Entrée` sur `[ MAJ DB ]` | Valider et enregistrer |

## Boutons

- **Annuler** : ferme l'éditeur, le scan en mémoire reste inchangé.
- **MAJ DB** : construit un `ScanResult` corrigé, le sauvegarde comme
  `ctx.last_scan` et le pousse dans `ctx.scan_history`.
  *(Soumission à l'API UEX Corp : future — nécessite clé API contributeur.)*

## Indication dans le REPL

Après chaque affichage de scan, la ligne suivante rappelle le raccourci :

```
  Ctrl+↑ pour éditer
```

## Limitations actuelles / futures

| Sujet | État |
|-------|------|
| Complétion des noms de commodités dans l'éditeur | À faire |
| Soumission à l'API UEX Corp (endpoint prices_submit) | À faire |
| Sauvegarde locale JSON dans `~/.uexinfo/scans/` | À faire |
| Historique des éditions | À faire |
| Ajout / suppression de lignes | À faire |
