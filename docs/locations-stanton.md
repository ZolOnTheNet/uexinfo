# Stanton — Catalogue des lieux

Système stellaire de Stanton (United Empire of Earth). 4 planètes industrielles,
chacune avec des stations orbitales, des points de Lagrange et des lunes.

## Convention de nommage UEX

| Préfixe | Planète   | Type     |
|---------|-----------|----------|
| `HUR`   | Hurston   | Planète  |
| `MIC`   | microTech | Planète  |
| `ARC`   | ArcCorp   | Planète  |
| `CRU`   | Crusader  | Géante gazeuse |

Les points de Lagrange **L1 à L5** sont les 5 points d'équilibre gravitationnel
autour de chaque planète. Chacun accueille une station spatiale permanente.

---

## Hurston (HUR)

**Type** : Planète industrielle (minière/manufacture)
**Ville principale** : Lorville
**Station orbitale** : Everus Harbor

### Stations de Lagrange

| Code       | Nom complet                     |
|------------|---------------------------------|
| HUR-L1     | HUR-L1 Green Glade Station      |
| HUR-L2     | HUR-L2 Faithful Dream Station   |
| HUR-L3     | HUR-L3 Thundering Express Station |
| HUR-L4     | HUR-L4 Melodic Fields Station   |
| HUR-L5     | HUR-L5 High Course Station      |

### Lunes de Hurston

| Lune    | Notes                          |
|---------|--------------------------------|
| Arial   | Lune aride                     |
| Aberdeen| Lune rocheuse, avant-postes    |
| Magda   | Lune de glace                  |
| Ita     | Petite lune désertique         |

### Avant-postes HDMS (Hurston Dynamics Military Spec)
Posés en surface : Anderson, Bezdek, Edmond, Hadley, Hahn, Lathan,
Norgaard, Oparei, Perlman, Pinewood, Ryder, Stanhope, Thedus, Woodruff.

---

## microTech (MIC)

**Type** : Planète technologique (haute technologie)
**Ville principale** : New Babbage
**Station orbitale** : Port Tressler

### Stations de Lagrange

| Code       | Nom complet                        |
|------------|------------------------------------|
| MIC-L1     | MIC-L1 Shallow Frontier Station    |
| MIC-L2     | MIC-L2 Long Forest Station         |
| MIC-L3     | MIC-L3 Endless Odyssey Station     |
| MIC-L4     | MIC-L4 Red Crossroads Station      |
| MIC-L5     | MIC-L5 Modern Icarus Station       |

### Lunes de microTech

| Lune     | Notes                             |
|----------|-----------------------------------|
| Calliope | Lune enneigée, avant-postes Rayari|
| Clio     | Lune rocheuse                     |
| Euterpe  | Lune glaciale                     |

---

## ArcCorp (ARC)

**Type** : Planète entièrement urbanisée
**Ville principale** : Area 18
**Station orbitale** : Baijini Point

### Stations de Lagrange

| Code       | Nom complet                        |
|------------|------------------------------------|
| ARC-L1     | ARC-L1 Wide Forest Station         |
| ARC-L2     | ARC-L2 Lively Pathway Station      |
| ARC-L3     | ARC-L3 Modern Express Station      |
| ARC-L4     | ARC-L4 Faint Glen Station          |
| ARC-L5     | ARC-L5 Yellow Core Station         |

### Lunes d'ArcCorp

| Lune  | Notes                                |
|-------|--------------------------------------|
| Lyria | Lune rocheuse, zones minières        |
| Wala  | Petite lune, avant-postes Shubin     |

---

## Crusader (CRU)

**Type** : Géante gazeuse (extraction de gaz)
**Ville principale** : Orison (plateformes flottantes dans l'atmosphère)
**Station orbitale** : Seraphim Station
**Ancienne station** : Port Olisar (désaffectée, encore présente en jeu)

### Stations de Lagrange

| Code       | Nom complet                           |
|------------|---------------------------------------|
| CRU-L1     | CRU-L1 Ambitious Dream Station        |
| CRU-L2     | CRU-L2 — non nommée (pas de terminal) |
| CRU-L3     | CRU-L3 — non nommée                   |
| CRU-L4     | CRU-L4 Shallow Fields Station         |
| CRU-L5     | CRU-L5 Beautiful Glen Station         |

### Lunes de Crusader

| Lune   | Notes                                      |
|--------|--------------------------------------------|
| Cellin | Lune volcanique, avant-postes              |
| Daymar | Lune désertique, Jumptown, raffineries     |
| Yela   | Lune glaciale, ceinture d'astéroïdes       |

---

## Autres lieux dans Stanton

### Portes de saut (Jump Gates)
Connectent Stanton aux autres systèmes :

| Lieu (côté Stanton)       | Destination     |
|---------------------------|-----------------|
| Pyro Gateway (Stanton)    | Pyro            |
| Nyx Gateway (Stanton)     | Nyx (Levski)    |
| Terra Gateway (Stanton)   | Terra           |

### GrimHEX
Station pirate dissimulée dans la ceinture d'astéroïdes de Yela (lune de Crusader).
Accès possible en QT depuis la plupart des stations.

---

## Correspondance préfixes → nœuds de graphe

Dans `transport_network.json`, les nœuds utilisent les noms complets.
Les codes courts (ex. `HUR-L4`) sont des **alias** du nom long
(`HUR-L4 Melodic Fields Station`) et ne doivent pas exister comme nœuds séparés.

La commande `/nav dedup` fusionne automatiquement les codes courts
avec leurs nœuds longs correspondants.

---

## Distances QT typiques depuis Lorville (Hurston)

Ces valeurs sont indicatives et varient selon la position orbitale des planètes.

| Destination               | Distance approx. |
|---------------------------|-----------------|
| Everus Harbor             | ~1–5 Gm         |
| HUR-L1 à HUR-L5          | ~3–20 Gm        |
| MIC-L1 à MIC-L5          | ~50–200 Gm      |
| ARC-L1 à ARC-L5          | ~30–150 Gm      |
| CRU-L1 à CRU-L5          | ~50–250 Gm      |
| New Babbage               | ~80–300 Gm (surface)|
| Area 18                   | ~40–200 Gm (surface)|
| Orison                    | ~60–280 Gm (surface)|

*Les distances varient car les planètes sont en orbite continue.*
NB : actuellement, elle n'orbite pas.