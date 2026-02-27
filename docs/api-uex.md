# UEX Corp 2.0 — Référence API REST

> Base URL : `https://uexcorp.space/api/2.0/`
> Authentification : Aucune pour les GET publics
> Format : JSON `{ "status": "ok", "http_code": 200, "data": [...] }`

---

## Endpoints disponibles

### Géographie / Lieux

| Endpoint           | Params       | Description                            |
|--------------------|--------------|----------------------------------------|
| `/star_systems`    | —            | Systèmes stellaires (Stanton, Pyro…)   |
| `/planets`         | —            | Planètes avec lien système             |
| `/moons`           | —            | Lunes                                  |
| `/orbits`          | —            | Corps orbitaux, Lagrange, jump points  |
| `/space_stations`  | —            | Stations spatiales + flags équipements |
| `/outposts`        | —            | Avant-postes au sol (119 enregistrements) |
| `/cities`          | —            | Villes (Area 18, Lorville, New Babbage, Orison, Levski) |

### Terminaux

| Endpoint      | Params | Description                                    |
|---------------|--------|------------------------------------------------|
| `/terminals`  | —      | Tous les terminaux avec métadonnées complètes  |

Champs clés d'un terminal :
```
id, name, fullname, code, type
id_star_system, id_planet, id_orbit, id_moon, id_space_station
id_outpost, id_city, id_faction
max_container_size
is_available, is_player_owned
is_refinery, is_cargo_center, is_medical, is_food
is_shop_vehicle, is_refuel, is_repair
has_loading_dock, has_docking_port, has_freight_elevator
star_system_name, planet_name, orbit_name, terminal_name
```

### Commodités

| Endpoint              | Params requis                         | Description                       |
|-----------------------|---------------------------------------|-----------------------------------|
| `/commodities`        | `name=`, `id=` (optionnels)           | Liste des commodités              |
| `/categories`         | —                                     | 107 catégories d'items/services   |
| `/commodities_prices` | `id_terminal=` **OU** `id_commodity=` | Prix live par terminal            |
| `/commodities_routes` | `id_terminal_origin=`                 | Routes rentables depuis un terminal |

#### Champs d'une commodité (`/commodities`)
```
id, id_parent, name, code, kind (Metal/Mineral/Drug/Food…)
weight_scu
price_buy, price_sell
is_available, is_available_live, is_visible
is_extractable, is_refinable, is_harvestable
is_mineral, is_raw, is_refined, is_pure
is_buyable, is_sellable
is_illegal, is_volatile_qt, is_volatile_time
is_inert, is_explosive, is_fuel
wiki
```

**Exemple — Copper (id=20) :**
```json
{
  "id": 20, "name": "Copper", "code": "COPP",
  "kind": "Metal", "weight_scu": 1.2,
  "price_buy": 1427, "price_sell": 1700,
  "is_refined": 1, "is_buyable": 1, "is_sellable": 1
}
```

#### Champs d'un prix (`/commodities_prices`)
```
id_commodity, id_terminal
price_buy, price_buy_min, price_buy_max, price_buy_avg
price_buy_min_week, price_buy_max_week, price_buy_avg_week
price_buy_min_month, price_buy_max_month, price_buy_avg_month
price_sell, price_sell_min, price_sell_max, price_sell_avg
(mêmes variantes semaine/mois pour sell)
scu_buy, scu_buy_min, scu_buy_max, scu_buy_avg
scu_sell, scu_sell_min, scu_sell_max, scu_sell_avg, scu_sell_stock
status_buy, status_sell
volatility_buy, volatility_sell
commodity_name, commodity_code
star_system_name, planet_name, orbit_name, terminal_name, terminal_code
game_version, date_modified
```

#### Champs d'une route (`/commodities_routes`)
```
id_commodity, code
id_terminal_origin, id_terminal_destination
price_origin, price_destination
price_margin, price_roi
scu_origin, scu_destination, scu_margin, scu_reachable
investment, profit, distance, score
has_docking_port, has_freight_elevator, has_loading_dock (origin + dest)
has_refuel, has_cargo_center, has_quantum_marker (origin + dest)
is_monitored, is_space_station, is_on_ground (origin + dest)
container_sizes_origin, container_sizes_destination
commodity_name, commodity_slug
[noms/codes des systèmes, planètes, terminaux origin/dest]
faction_name_origin, faction_name_destination
is_player_owned_origin, is_player_owned_destination
```

### Véhicules / Vaisseaux

| Endpoint                    | Params | Description                         |
|-----------------------------|--------|-------------------------------------|
| `/vehicles_purchases_prices`| —      | Prix d'achat vaisseaux par terminal |
| `/vehicles_rentals_prices`  | —      | Prix de location vaisseaux          |

### Factions

| Endpoint    | Params | Description                             |
|-------------|--------|-----------------------------------------|
| `/factions` | —      | 47 factions avec relations alliés/hostiles |

---

## Exemples de requêtes

```python
import requests

BASE = "https://uexcorp.space/api/2.0"

# Toutes les commodités
r = requests.get(f"{BASE}/commodities")
commodities = r.json()["data"]

# Prix du Copper (id=20) sur tous les terminaux
r = requests.get(f"{BASE}/commodities_prices", params={"id_commodity": 20})
prices = r.json()["data"]

# Routes depuis un terminal (id=1)
r = requests.get(f"{BASE}/commodities_routes", params={"id_terminal_origin": 1})
routes = r.json()["data"]

# Terminaux disponibles
r = requests.get(f"{BASE}/terminals")
terminals = r.json()["data"]
```

---

## Notes

- Toutes les requêtes sont des GET HTTP
- Le champ `game_version` indique la version SC des données
- `date_modified` permet de détecter les mises à jour
- `is_available_live` = données soumises par les joueurs récemment
- Les prix en **aUEC** (alpha UEC)
- `weight_scu` = masse en SCU (Standard Cargo Unit)

---

*Référence API UEX 2.0 — uexinfo v0.1*
