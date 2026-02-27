# UEXInfo — Manuel des commandes CLI

> Toutes les commandes commencent par `/` (espaces/tabulations tolérés en préfixe)
> Autocomplétion disponible via `Tab`
> Aide contextuelle : `/help <commande>`

---

## Syntaxe générale

```
/commande [sous-commande] [argument] [--option valeur]
```

---

## /help — Aide

```
/help                    Aide générale
/help <commande>         Aide sur une commande spécifique
/help trade              Aide sur /trade
```

---

## /config — Configuration

Gère le profil utilisateur, les vaisseaux et les préférences.

```
/config                        Afficher la configuration actuelle
/config ship add <nom>         Ajouter un vaisseau disponible
/config ship remove <nom>      Retirer un vaisseau
/config ship set <nom>         Définir le vaisseau actif
/config ship cargo <nom> <scu> Définir le cargo SCU d'un vaisseau

/config trade profit <aUEC>    Profit minimum par SCU
/config trade margin <pct>     Marge minimale en %
/config trade illegal on|off   Autoriser les commodités illégales

/config cache ttl <secondes>   TTL du cache prix
/config cache clear            Vider tout le cache
```

**Exemple :**
```
/config ship add "Cutlass Black"
/config ship cargo "Cutlass Black" 46
/config trade profit 500
```

---

## /go — Position courante et destination

Alias : `/lieu`

```
/go                          Afficher position courante et destination
/go <lieu>                   Définir la position courante
/go from <lieu>              Définir le point de départ
/go to <lieu>                Définir la destination
/go clear                    Réinitialiser position et destination
```

`<lieu>` accepte (autocomplétion disponible) :
- Nom de terminal : `"Tram & Myers Mining"`, `TCC` (code)
- Station : `"Port Olisar"`, `"CRU-L1"`
- Ville : `"Area 18"`, `"Lorville"`
- Planète : `Crusader`, `Hurston`, `ArcCorp`, `MicroTech`
- Système : `Stanton`, `Pyro`

**Exemple :**
```
/go from "Port Tressler"
/go to "Lorville"
/lieu Area 18
```

---

## /select — Filtres actifs

Définit les filtres qui s'appliquent aux commandes `/trade` et `/route`.

```
/select                          Afficher les filtres actifs
/select system <nom>             Filtrer sur un système
/select planet <nom>             Filtrer sur une planète
/select station <nom>            Filtrer sur une station
/select terminal <nom>           Filtrer sur un terminal
/select add <type> <nom>         Ajouter un filtre
/select remove <type> <nom>      Retirer un filtre
/select clear                    Supprimer tous les filtres
/select clear <type>             Supprimer filtres d'un type

Types : system | planet | station | terminal | city | outpost
```

**Exemple :**
```
/select planet Hurston
/select add station "Port Tressler"
/select clear planet
```

---

## /trade — Recherche commerciale

Interroge l'API UEX pour les prix et opportunités de trading.

```
/trade                           Meilleures opportunités (position courante)
/trade buy <commodité>           Où acheter une commodité
/trade sell <commodité>          Où vendre une commodité
/trade <commodité>               Résumé buy+sell pour une commodité
/trade best                      Meilleures routes depuis la position courante
/trade best --profit             Trier par profit total
/trade best --roi                Trier par ROI
/trade best --margin             Trier par marge %
/trade best --scu <n>            Limiter au cargo de n SCU
/trade compare <commodité>       Comparer UEX et sc-trade.tools (données oranges)
```

**Exemple :**
```
/trade sell Copper
/trade best --scu 46 --profit
/trade compare Gold
```

**Affichage type `/trade sell Copper` :**
```
COPPER — Meilleurs prix de vente
┌─ Système ──┬─ Terminal ──────────────────┬── Sell ──┬── Stock ─┬─ Dist. ─┐
│ Stanton    │ Tram & Myers Mining (TCC)   │ 1700 aUEC│  250 SCU │  12 QT  │
│ Stanton    │ Shubin Mining (SAL-2)       │ 1680 aUEC│  100 SCU │  25 QT  │
└────────────┴─────────────────────────────┴──────────┴──────────┴─────────┘
  [SC-Trade] Tram & Myers: 1695 aUEC  |  SAL-2: 1682 aUEC
```

---

## /route — Routes commerciales

Calcule les meilleures routes de trade.

```
/route                           Routes depuis la position courante
/route from <terminal>           Routes depuis un terminal spécifique
/route to <terminal>             Routes vers une destination spécifique
/route <terminal_a> <terminal_b> Route spécifique aller-retour
/route --commodity <nom>         Filtrer sur une commodité
/route --min-profit <aUEC>       Profit minimum total
/route --min-roi <pct>           ROI minimum
/route --scu <n>                 Taille cargo du vaisseau
```

**Exemple :**
```
/route from "Port Tressler"
/route --scu 46 --min-profit 50000
/route "Area 18 TDD" "Levski"
```

---

## /plan — Plan de vol multi-étapes

```
/plan                            Afficher le plan de vol actuel
/plan new                        Démarrer un nouveau plan
/plan add <terminal>             Ajouter une étape
/plan remove <étape>             Supprimer une étape
/plan optimize                   Optimiser l'ordre des étapes (profit max)
/plan clear                      Effacer le plan
/plan show                       Résumé détaillé du plan (distances, profits)
```

---

## /info — Informations détaillées

```
/info <lieu>                     Infos sur un lieu (terminal/station/ville)
/info <commodité>                Infos sur une commodité
/info terminal <nom>             Détail d'un terminal
/info commodity <nom>            Détail d'une commodité
/info ship <nom>                 Infos sur un vaisseau (prix d'achat/location)
```

**Exemple :**
```
/info "Port Tressler"
/info commodity Laranite
/info ship "Cutlass Black"
```

---

## /refresh — Mise à jour du cache

```
/refresh                         Rafraîchir le cache prix (TTL expiré)
/refresh all                     Forcer le refresh complet (statique + prix)
/refresh static                  Rafraîchir données statiques (terminaux, commodités…)
/refresh prices                  Rafraîchir les prix uniquement
/refresh sctrade                 Rafraîchir données sc-trade.tools
/refresh status                  Afficher l'état du cache (âge des données)
```

---

## /exit — Quitter

```
/exit
/quit
Ctrl+D
```

---

## Autocomplétion

La touche `Tab` complète automatiquement :
- Les noms de commandes (`/tr` → `/trade`, `/ro` → `/route`)
- Les sous-commandes
- Les noms de commodités (`Cop` → `Copper`, `Lara` → `Laranite`)
- Les noms de terminaux, stations, planètes
- Les noms de vaisseaux configurés
- Les valeurs d'options (`--scu`, `--profit`…)

La complétion est **contextuelle** : après `/trade sell`, seules les
commodités vendables sont proposées. Après `/go from`, les terminaux
connus sont listés.

---

## Codes couleur

| Couleur       | Signification                             |
|---------------|-------------------------------------------|
| Blanc / Cyan  | Données UEX Corp (primaires)              |
| **Orange**    | Données sc-trade.tools (croisées)         |
| Vert          | Bon deal, profit positif                  |
| Jaune         | Avertissement, stock faible, données old  |
| Rouge         | Erreur, marge négative, indisponible      |
| Gris          | Métadonnées, informations secondaires     |

---

## Variables de session

Des raccourcis sont disponibles une fois définis via `/go` ou `/select` :
- `@here` — position courante
- `@dest` — destination
- `@ship` — vaisseau actif
- `@cargo` — SCU du vaisseau actif

```
/trade best --scu @cargo
/route from @here to @dest
```

---

*Manuel des commandes — uexinfo v0.1*
