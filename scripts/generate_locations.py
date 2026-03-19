"""Génère transport_network.json enrichi depuis l'API UEX Corp 2.0.

Type codes :
  0 = system   1 = planet   2 = moon
  3 = station  4 = outpost  5 = city

Clé de nœud : name (chaîne complète UEX) — compatible avec les edges existantes.
Champ id    : "type_code.uex_id" — lien base de données.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

BASE = "https://uexcorp.space/api/2.0"
OUT  = Path(__file__).parent.parent / "uexinfo" / "data" / "transport_network.json"

# ── Type codes ────────────────────────────────────────────────────────────────
T_SYS  = 0
T_PLT  = 1
T_MON  = 2
T_STA  = 3
T_OUT  = 4
T_CTY  = 5

TYPE_NAMES = {T_SYS: "system", T_PLT: "planet", T_MON: "moon",
              T_STA: "station", T_OUT: "outpost", T_CTY: "city"}


def fetch(endpoint: str) -> list[dict]:
    url = f"{BASE}/{endpoint}"
    print(f"  GET {url} ...", end=" ", flush=True)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or []
    print(f"{len(data)} entrées")
    return data


def node_id(type_code: int, uex_id: int) -> str:
    return f"{type_code}.{uex_id}"


def auto_short(name: str) -> str | None:
    """'ArcCorp Mining Area 045' → 'ArcCorp 045' (1er mot + dernier mot)."""
    words = name.split()
    if len(words) > 2:
        return f"{words[0]} {words[-1]}"
    return None


def build_aliases(name: str, nickname: str | None) -> list[str]:
    aliases = []
    if nickname and nickname != name:
        aliases.append(nickname)
    short = auto_short(name)
    if short and short not in aliases and short != name:
        aliases.append(short)
    return aliases


def make_node(
    type_code: int,
    uex_id: int,
    name: str,
    nickname: str | None,
    aliases: list[str],
    system: str,
    system_id: str,
    parent_id: str | None,
    is_dest: bool,
    is_available: bool,
    terminal_ids: list[int],
    metadata: dict,
) -> dict:
    return {
        "id":          node_id(type_code, uex_id),
        "name":        name,
        "nickname":    nickname or name,
        "aliases":     aliases,
        "type":        TYPE_NAMES[type_code],
        "type_code":   type_code,
        "uex_id":      uex_id,
        "system":      system,
        "system_id":   system_id,
        "parent_id":   parent_id,
        "is_dest":     is_dest,
        "is_available": is_available,
        "terminal_ids": terminal_ids,
        "coordinates": None,
        "metadata":    metadata,
    }


# ── Fetch ─────────────────────────────────────────────────────────────────────
print("Téléchargement des données UEX...")
systems   = fetch("star_systems")
planets   = fetch("planets")
moons     = fetch("moons")
stations  = fetch("space_stations")
outposts  = fetch("outposts")
cities    = fetch("cities")
terminals = fetch("terminals")

# ── Index terminal_ids et is_nqa par (type, uex_id) ─────────────────────────
term_by:  dict[tuple, list[int]] = defaultdict(list)
nqa_locs: set[tuple] = set()   # lieux ayant au moins un terminal is_nqa=1

for t in terminals:
    if t["id_space_station"]:
        key = (T_STA, t["id_space_station"])
    elif t["id_outpost"]:
        key = (T_OUT, t["id_outpost"])
    elif t["id_city"]:
        key = (T_CTY, t["id_city"])
    else:
        continue
    term_by[key].append(t["id"])
    if t.get("is_nqa"):
        nqa_locs.add(key)

# ── Systèmes disponibles ─────────────────────────────────────────────────────
avail_sys = {s["id"] for s in systems if s.get("is_available")}

# ── Construction des nœuds ───────────────────────────────────────────────────
nodes: list[dict] = []

# 1. Systèmes
for s in systems:
    if s["id"] not in avail_sys:
        continue
    nid = node_id(T_SYS, s["id"])
    nodes.append(make_node(
        type_code    = T_SYS,
        uex_id       = s["id"],
        name         = s["name"],
        nickname     = s.get("nickname") or s["name"],
        aliases      = [],
        system       = s["name"],
        system_id    = nid,
        parent_id    = None,
        is_dest      = False,
        is_available = bool(s.get("is_available")),
        terminal_ids = [],
        metadata     = {},
    ))

# 2. Planètes (seulement dans les systèmes disponibles)
for p in planets:
    if p["id_star_system"] not in avail_sys:
        continue
    if not p.get("is_available"):
        continue
    sys_id = node_id(T_SYS, p["id_star_system"])
    nodes.append(make_node(
        type_code    = T_PLT,
        uex_id       = p["id"],
        name         = p["name"],
        nickname     = p.get("code") or p["name"],
        aliases      = build_aliases(p["name"], p.get("code")),
        system       = p["star_system_name"],
        system_id    = sys_id,
        parent_id    = sys_id,
        is_dest      = False,   # planète = waypoint, pas destination directe QT
        is_available = True,
        terminal_ids = [],
        metadata     = {},
    ))

# 3. Lunes (seulement dans les systèmes disponibles)
for m in moons:
    if m["id_star_system"] not in avail_sys:
        continue
    if not m.get("is_available"):
        continue
    sys_id    = node_id(T_SYS, m["id_star_system"])
    parent_id = node_id(T_PLT, m["id_planet"]) if m.get("id_planet") else sys_id
    nodes.append(make_node(
        type_code    = T_MON,
        uex_id       = m["id"],
        name         = m["name"],
        nickname     = m.get("code") or m["name"],
        aliases      = build_aliases(m["name"], m.get("code")),
        system       = m["star_system_name"],
        system_id    = sys_id,
        parent_id    = parent_id,
        is_dest      = False,   # lune = waypoint
        is_available = True,
        terminal_ids = [],
        metadata     = {"planet_name": m.get("planet_name")},
    ))

# 4. Stations spatiales
for s in stations:
    if s["id_star_system"] not in avail_sys:
        continue
    sys_id = node_id(T_SYS, s["id_star_system"])
    if s.get("id_moon"):
        parent_id = node_id(T_MON, s["id_moon"])
    elif s.get("id_planet"):
        parent_id = node_id(T_PLT, s["id_planet"])
    else:
        parent_id = sys_id
    nodes.append(make_node(
        type_code    = T_STA,
        uex_id       = s["id"],
        name         = s["name"],       # nom complet : "Baijini Point", "ARC-L1 Wide Forest Station"
        nickname     = s["nickname"],   # court : "Baijini", "ARC-L1"
        aliases      = build_aliases(s["name"], s["nickname"]),
        system       = s["star_system_name"],
        system_id    = sys_id,
        parent_id    = parent_id,
        is_dest      = bool(s.get("has_quantum_marker")),
        is_available = bool(s.get("is_available")),
        terminal_ids = term_by.get((T_STA, s["id"]), []),
        metadata     = {
            "is_monitored":        bool(s.get("is_monitored")),
            "is_armistice":        bool(s.get("is_armistice")),
            "is_landable":         bool(s.get("is_landable")),
            "is_decommissioned":   bool(s.get("is_decommissioned")),
            "is_nqa":              (T_STA, s["id"]) in nqa_locs,
            "is_lagrange":         bool(s.get("is_lagrange")),
            "is_jump_point":       bool(s.get("is_jump_point")),
            "orbit_name":          s.get("orbit_name"),
            "has_refinery":        bool(s.get("has_refinery")),
            "has_cargo_center":    bool(s.get("has_cargo_center")),
            "has_refuel":          bool(s.get("has_refuel")),
            "has_repair":          bool(s.get("has_repair")),
            "has_docking_port":    bool(s.get("has_docking_port")),
            "has_freight_elevator": bool(s.get("has_freight_elevator")),
        },
    ))

# Index des noms pour détecter les doublons (outposts + stations + villes)
_seen_names: dict[str, int] = {}   # name -> count
for _o in outposts:
    _seen_names[_o["name"]] = _seen_names.get(_o["name"], 0) + 1

# Index lune id → nom
moon_names: dict[int, str] = {m["id"]: m["name"] for m in moons}

# 5. Avant-postes
for o in outposts:
    if o["id_star_system"] not in avail_sys:
        continue
    sys_id = node_id(T_SYS, o["id_star_system"])
    if o.get("id_moon"):
        parent_id = node_id(T_MON, o["id_moon"])
    elif o.get("id_planet"):
        parent_id = node_id(T_PLT, o["id_planet"])
    else:
        parent_id = sys_id

    # Correction bug UEX : Shady Glen (id=59) a nickname="Samson" par erreur
    nick = o["nickname"]
    if o["id"] == 59 and nick == "Samson":
        nick = "Shady Glen"

    # Désambiguïsation : si le nom est partagé, ajouter la lune parentale
    canonical = o["name"]
    if _seen_names.get(canonical, 1) > 1 and o.get("id_moon"):
        moon_n = moon_names.get(o["id_moon"], "")
        if moon_n:
            canonical = f"{canonical} ({moon_n})"

    nodes.append(make_node(
        type_code    = T_OUT,
        uex_id       = o["id"],
        name         = canonical,
        nickname     = nick,
        aliases      = build_aliases(o["name"], nick),
        system       = o["star_system_name"],
        system_id    = sys_id,
        parent_id    = parent_id,
        is_dest      = bool(o.get("has_quantum_marker")),
        is_available = bool(o.get("is_available")),
        terminal_ids = term_by.get((T_OUT, o["id"]), []),
        metadata     = {
            "is_monitored":      bool(o.get("is_monitored")),
            "is_armistice":      bool(o.get("is_armistice")),
            "is_landable":       bool(o.get("is_landable")),
            "is_decommissioned": bool(o.get("is_decommissioned")),
            "is_nqa":            (T_OUT, o["id"]) in nqa_locs,
            "has_trade_terminal": bool(o.get("has_trade_terminal")),
            "has_refinery":      bool(o.get("has_refinery")),
        },
    ))

# 6. Villes
for c in cities:
    if c["id_star_system"] not in avail_sys:
        continue
    sys_id    = node_id(T_SYS, c["id_star_system"])
    parent_id = node_id(T_PLT, c["id_planet"]) if c.get("id_planet") else sys_id
    nodes.append(make_node(
        type_code    = T_CTY,
        uex_id       = c["id"],
        name         = c["name"],
        nickname     = c.get("code") or c["name"],
        aliases      = build_aliases(c["name"], c.get("code")),
        system       = c["star_system_name"],
        system_id    = sys_id,
        parent_id    = parent_id,
        is_dest      = bool(c.get("has_quantum_marker")),
        is_available = bool(c.get("is_available")),
        terminal_ids = term_by.get((T_CTY, c["id"]), []),
        metadata     = {
            "is_monitored":      bool(c.get("is_monitored")),
            "is_armistice":      bool(c.get("is_armistice")),
            "is_landable":       bool(c.get("is_landable")),
            "is_decommissioned": bool(c.get("is_decommissioned")),
            "is_nqa":            (T_CTY, c["id"]) in nqa_locs,
            "has_refinery":      bool(c.get("has_refinery")),
            "has_cargo_center":  bool(c.get("has_cargo_center")),
        },
    ))

# ── Charger edges + jump_points existants ────────────────────────────────────
print(f"\nChargement des edges existantes depuis {OUT} ...")
with open(OUT, encoding="utf-8") as f:
    current = json.load(f)

edges       = current.get("edges", [])
jump_points = current.get("jump_points", [])
print(f"  {len(edges)} edges, {len(jump_points)} jump_points conservés")

# ── Statistiques ─────────────────────────────────────────────────────────────
by_type: dict[str, int] = defaultdict(int)
for n in nodes:
    by_type[n["type"]] += 1
dest_count = sum(1 for n in nodes if n["is_dest"])

print(f"\nNœuds générés : {len(nodes)} total")
for t, cnt in sorted(by_type.items()):
    print(f"  {t:10s} : {cnt}")
print(f"  is_dest=True : {dest_count}")

# ── Écriture ─────────────────────────────────────────────────────────────────
output = {
    "version": 3,
    "generated_at": int(time.time()),
    "type_codes": {
        "0": "system",
        "1": "planet",
        "2": "moon",
        "3": "station",
        "4": "outpost",
        "5": "city",
    },
    "nodes":       nodes,
    "edges":       edges,
    "jump_points": jump_points,
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nFichier écrit : {OUT}")
print(f"Taille : {OUT.stat().st_size / 1024:.0f} Ko")
