# Schéma CommandResult — IR entre commandes et renderers

**Date :** 2026-04-29  
**Objectif :** Remplacer le pipeline ANSI → StringIO → JS ANSI.toHtml() par un IR
structuré que chaque renderer (HTML overlay, Rich debug) consomme directement.

---

## Principe

```
Commande           IR                    Renderer
──────────         ──────────────────    ────────────────────
cmd_info()   →     CommandResult    →    RichRenderer  (debug)
cmd_trade()         blocs typés          HtmlRenderer  (overlay)
cmd_route()         styles sémantiques   → HTML natif, annotation
                    termes annotés         vocab intégrée
```

Les commandes **retournent** un `CommandResult` au lieu de `console.print()`.  
Le server.py appelle le renderer HTML et envoie `{"type": "result", "blocks": [...]}`.  
Plus de StringIO, plus de ANSI, plus de `ANSI.toHtml()` côté JS.

---

## Styles sémantiques

| Nom         | Signification            | Rich          | CSS / HTML          |
|-------------|--------------------------|---------------|---------------------|
| `""`        | texte normal             | —             | —                   |
| `dim`       | secondaire               | dim           | .dim                |
| `bold`      | important                | bold          | font-weight:bold    |
| `uex`       | donnée UEX Corp          | cyan          | .uex (cyan)         |
| `sctrade`   | donnée sc-trade.tools    | orange1       | .sctrade (orange)   |
| `profit`    | bénéfice positif         | bold green    | .profit             |
| `loss`      | perte / négatif          | bold red      | .loss               |
| `warn`      | avertissement            | yellow        | .warn               |
| `error`     | erreur                   | bold red      | .error              |
| `ok`        | succès                   | green         | .ok                 |
| `label`     | étiquette / titre col.   | bold          | .label              |
| `age-ok`    | donnée fraîche (≤1j)     | green         | .age-ok             |
| `age-mid`   | donnée correcte (2-3j)   | yellow        | .age-mid            |
| `age-old`   | donnée ancienne (≥4j)    | orange1       | .age-old            |

---

## Éléments inline

```python
Str      = str                        # texte brut, pas de style

Span(
    text:  str,
    style: str = "",                  # style sémantique
)

Term(
    text:  str,
    type:  str,                       # "location"|"commodity"|"ship"|"voyage"
    cmd:   str = "",                  # ex: "/info Area 18" — vide = juste tooltip
    style: str = "",
)

Cmd(
    text:  str,
    cmd:   str,                       # commande exécutée au clic
    style: str = "",
)

Inline = str | Span | Term | Cmd
```

---

## Blocs

```python
Text(
    content: list[Inline],            # paragraphe avec éléments inline mixés
)

Section(
    title:   str | list[Inline],      # titre de section / header
)

Rule()                                # séparateur horizontal ───────

Blank()                               # ligne vide

Column(
    header: str,
    style:  str  = "",                # style de toutes les cellules de cette colonne
    width:  int  = 0,                 # 0 = auto
    align:  str  = "left",            # "left" | "right" | "center"
    no_wrap: bool = False,
)

Row(
    cells: list[list[Inline] | str],  # une cellule = liste d'Inline ou str simple
    style: str = "",                  # style de la ligne entière (ex: "dim")
    is_header: bool = False,
)

Table(
    columns:  list[Column],
    rows:     list[Row],
    title:    str  = "",
    caption:  str  = "",
    box:      str  = "simple",        # "simple"|"rounded"|"heavy"|"none"
)

Action(
    label: str,
    cmd:   str,
    style: str = "",                  # "primary"|"secondary"|"danger"
)

Actions(
    items: list[Action],              # groupe de boutons inline
)

Block = Text | Section | Rule | Blank | Table | Actions
```

---

## CommandResult

```python
@dataclass
class CommandResult:
    blocks:         list[Block] = field(default_factory=list)

    # Flags post-rendu
    status_update:  bool = False      # refresh barre de statut après rendu
    vocab_update:   bool = False      # re-envoyer le vocab (après refresh cache)
    overlay_msgs:   list[dict] = field(default_factory=list)  # messages WS additionnels
```

---

## Sérialisation JSON (transport WebSocket)

Message envoyé par le server :

```json
{
  "type": "result",
  "blocks": [
    { "kind": "section", "title": "Marché — Area 18.tdd" },
    {
      "kind": "table",
      "columns": [
        { "header": "Commodité", "align": "left"  },
        { "header": "Achat",     "align": "right" },
        { "header": "Vente",     "align": "right" }
      ],
      "rows": [
        {
          "cells": [
            [{ "kind": "term", "text": "Waste", "type": "commodity", "cmd": "/info Waste" }],
            [{ "kind": "span", "text": "229 α", "style": "uex" }],
            [{ "kind": "span", "text": "—",     "style": "dim" }]
          ]
        }
      ]
    },
    { "kind": "text", "content": [
        { "kind": "span", "text": "Données UEX Corp · non confirmées", "style": "dim" }
    ]}
  ]
}
```

Règle de sérialisation : chaque objet Python → dict avec `"kind"` = nom de classe en minuscule.
Les `str` inline deviennent `{ "kind": "span", "text": "...", "style": "" }`.

---

## Renderers

### `HtmlRenderer` (`uexinfo/display/render_html.py`)

- `Section` → `<div class="section-title">...</div>`
- `Table` → `<table class="rt">` avec `<thead>` / `<tbody>`
  - chaque `Term` → `<span class="cw cw-{type}" data-cmd="...">text</span>`
  - chaque `Span` → `<span class="s-{style}">text</span>` (ou inline style)
- `Text` → `<div class="line">...</div>`
- `Rule` → `<hr class="rule">`
- `Actions` → `<div class="inline-actions">` + `<button>`
- **L'annotation vocab est intégrée** : les `Term` sont déjà balisés, pas besoin de post-traitement `annotateElement`

### `RichRenderer` (`uexinfo/display/render_rich.py`)

- Utilise les objets Rich (`rich.table.Table`, `rich.text.Text`) directement
- Mappe les styles sémantiques → styles Rich (via `colors.py`)
- Pour les tests et debug uniquement — ne passe plus par StringIO

---

## Migration

### Stratégie : Progressive, commande par commande

1. Créer `uexinfo/display/result.py` (dataclasses + sérialisation)
2. Créer `uexinfo/display/render_html.py` et `render_rich.py`
3. Modifier `server.py` : accepter les deux modes pendant la transition
   - Si commande retourne `CommandResult` → rendu HTML
   - Si commande retourne `None` (ancienne) → fallback StringIO ANSI (deprecated)
4. Migrer les commandes une par une, en commençant par les plus simples (`/go`, `/help`)
5. Quand toutes les commandes sont migrées : supprimer le fallback ANSI

### Ordre de migration suggéré

| Priorité | Commandes | Raison |
|---|---|---|
| 1 | `/go`, `/dest`, `/help` | Simples, pas de tables |
| 2 | `/player`, `/config` | Tables simples |
| 3 | `/trade buy/sell/best` | Tables avec termes vocab |
| 4 | `/info terminal/commodity` | Tables complexes, termes annotés |
| 5 | `/scan`, `/mission`, `/voyage` | Plus complexes, formulaires |
| 6 | `/route` (nouveau) | Natif dès le départ |

### Règle pendant la transition

`/route` est écrit **natif** `CommandResult` dès le départ — c'est la première
commande sans dette ANSI.

---

## Ce qui disparaît

- `_buf = io.StringIO()` dans server.py
- `Console(file=_buf, force_terminal=True)`
- `{"type": "output", "ansi": "..."}` WebSocket message
- `ANSI.toHtml()` dans index.html
- `annotateElement()` comme post-traitement (remplacé par annotation intégrée au renderer)
- `ansi_html.py` (convertisseur Python ANSI→HTML pour l'historique)

---

*Document de référence — à conserver pendant toute la durée de la migration.*
