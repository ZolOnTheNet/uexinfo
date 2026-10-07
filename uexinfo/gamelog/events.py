"""Reconnaissance des événements de Game.log — pur, sans I/O.

Chaque reconnaisseur a un pré-filtre par sous-chaîne (rapide) puis une regex.
Formats et niveau de confiance : docs/ai/GAMELOG_SPEC.md (V = vérifié, S = à confirmer).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable

from uexinfo.gamelog import parser as _verified   # regex vérifiées sur un vrai log
from uexinfo.gamelog.lines import LogLine, is_spam, parse_line


@dataclass
class GameEvent:
    kind: str
    ts: datetime | None
    summary: str                     # phrase lisible (fr)
    data: dict = field(default_factory=dict)
    verified: bool = False           # format confirmé sur un vrai Game.log de l'utilisateur
    raw: str = ""


@dataclass(frozen=True)
class Recognizer:
    kind: str
    marker: str | tuple[str, ...]    # pré-filtre : une sous-chaîne ou plusieurs variantes
    regex: re.Pattern
    build: Callable[[re.Match], tuple[str, dict]]
    verified: bool = False
    strict: bool = True              # marqueur présent ⇒ la regex doit réussir (sinon : format changé ?)

    def seen(self, raw: str) -> bool:
        markers = (self.marker,) if isinstance(self.marker, str) else self.marker
        return any(m in raw for m in markers)


def _vehicle_model(code: str) -> str:
    """'DRAK_Cutlass_Black_200000002998' → 'DRAK Cutlass Black' (id numérique retiré)."""
    parts = code.split("_")
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return " ".join(parts)


# Segment « | MODELE_id[id] | » des lignes de navigation (vérifié 4.10) — cherché à part,
# pour que l'absence ou le déplacement du segment ne fasse pas échouer l'événement.
_RE_VEH_SEGMENT = re.compile(r"\|\s*(?P<veh>[A-Za-z][A-Za-z0-9_]*?)\[\d+\]\s*\|")


def _vehicle_in(raw: str) -> dict:
    m = _RE_VEH_SEGMENT.search(raw)
    return {"vehicle": _vehicle_model(m["veh"])} if m else {}


def _num(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return 0.0


def _qty(text: str) -> dict:
    """'100 cSCU' → {qty: 100, unit: 'cSCU', scu: 1.0} ; '100' → unité inconnue."""
    m = re.match(r"\s*([\d.]+)\s*(\S*)", text or "")
    if not m:
        return {"qty_raw": text}
    q, unit = _num(m.group(1)), m.group(2)
    out = {"qty": q, "unit": unit or "?"}
    if unit.lower() == "cscu":
        out["scu"] = q / 100
    elif unit.lower() == "scu":
        out["scu"] = q
    return out


def _fields(msg: str) -> dict:
    """Champs `cle[valeur]` d'une ligne → dict."""
    return {k: v for k, v in re.findall(r"(\w+)\[([^\]]*)\]", msg)}


def _trade(kind_fr: str):
    def build(m: re.Match) -> tuple[str, dict]:
        f = _fields(m.string)
        d = {"shop": f.get("shopName", ""), "price": _num(f.get("price", "0")),
             "resource_guid": f.get("resourceGUID", ""), **_qty(f.get("quantity", ""))}
        q = f"{d['scu']:g} SCU" if "scu" in d else f.get("quantity", "?")
        return f"{kind_fr} {q} au shop {d['shop']} pour {d['price']:,.0f} aUEC".replace(",", " "), d
    return build


RECOGNIZERS: tuple[Recognizer, ...] = (
    # ── Vérifiés (regex de uexinfo.gamelog.parser) ───────────────────────────
    Recognizer("login", "AccountLoginCharacterStatus_Character", _verified.RE_LOGIN,
               lambda m: (f"Connexion de {m['name']}", {"name": m["name"]}), True),
    Recognizer("spawn", "OnClientSpawned", _verified.RE_SPAWN,
               lambda m: ("Apparition en jeu", {}), True),
    Recognizer("shard", "<Join PU>", _verified.RE_JOIN_PU,
               lambda m: (f"Shard {m['shard']}", {"shard": m["shard"]}), True),
    Recognizer("location", "Projected Start Location", _verified.RE_ROUTE_START,
               lambda m: (f"Position (départ de route QT) : {m['loc'].strip()}", {"loc": m["loc"].strip()}), True),
    Recognizer("routing_names", "routing from", _verified.RE_ROUTING_NAMES,
               lambda m: (f"Route QT {m['origin'].strip()} → {m['dest'].strip()}",
                          {"origin": m["origin"].strip(), "dest": m["dest"].strip()}), True),
    Recognizer("docking", "CDockingAnimatorComponent", _verified.RE_DOCKING,
               lambda m: ("Docking", {}), True),
    Recognizer("handle", "Legacy login response", re.compile(r"Handle\[(?P<name>[^\]]+)\]"),
               lambda m: (f"Pseudo : {m['name']}", {"name": m["name"]}), True),
    # En-tête du fichier (vérifié 4.10) : version de l'exécutable et environnement.
    Recognizer("game_version", "FileVersion:", re.compile(r"FileVersion:\s*(?P<v>\d+(?:\.\d+)+)"),
               lambda m: (f"Version du jeu : {m['v']}", {"version": m["v"]}), True),
    Recognizer("build", "BackupNameAttachment", re.compile(r"Build\((?P<b>\d+)\)"),
               lambda m: (f"Build {m['b']}", {"build": m["b"]}), True),
    Recognizer("environment", "Environment:", re.compile(r"\]\s*Environment:\s*(?P<env>\w+)"),
               lambda m: (f"Environnement : {m['env']}", {"env": m["env"]}), True),
    Recognizer("ship_leave", "ClearDriver",
               re.compile(r"releasing control token for '(?P<veh>[^']+)'"),
               lambda m: (f"Quitte les commandes de {_vehicle_model(m['veh'])}", {"vehicle": _vehicle_model(m["veh"])}), True),
    Recognizer("near_location", "RequestLocationInventory",
               re.compile(r"Location\[(?P<loc>[^\]]+)\]"),
               lambda m: (f"Lieu proche (inventaire) : {m['loc']}", {"loc_code": m["loc"]}), True),
    Recognizer("session_end", "<SystemQuit>", re.compile(r"<SystemQuit>"),
               lambda m: ("Fin de session", {}), True),
    Recognizer("qt_target", "as their destination",
               re.compile(r"selected point (?P<loc_id>\S+) as their destination"),
               lambda m: (lambda v: (f"Cible QT : {m['loc_id']}"
                                     + (f" (vaisseau {v['vehicle']})" if v else ""),
                                     {"loc_id": m["loc_id"], **v}))(_vehicle_in(m.string)), True),
    Recognizer("qt_arrived", ("Quantum Drive Arrived", "OnQuantumDriveArrived"),
               re.compile(r"arrived at final destination", re.I),
               lambda m: (lambda v: ("Arrivée du saut quantique"
                                     + (f" ({v['vehicle']})" if v else ""), v))(_vehicle_in(m.string)), True),
    # ── À confirmer (formats relevés, voir GAMELOG_SPEC.md) ──────────────────
    Recognizer("system_change", "Changing Solar System",
               re.compile(r"changing system from (?P<a>\S+) to (?P<b>\S+)"),
               lambda m: (f"Changement de système : {m['a']} → {m['b']}", {"from": m["a"], "to": m["b"]})),
    Recognizer("ship_enter", "SetDriver",
               re.compile(r"requesting control token for '(?P<veh>[^']+)'"),
               lambda m: (f"Aux commandes de {_vehicle_model(m['veh'])}", {"vehicle": _vehicle_model(m["veh"]), "code": m["veh"]})),
    Recognizer("ship_spawn", "OnVehicleSpawned",
               re.compile(r"OnVehicleSpawned \d+ \((?P<veh>[^)]+)\) by player (?P<geid>\d+)"),
               lambda m: (f"Vaisseau sorti : {_vehicle_model(m['veh'])}", {"vehicle": _vehicle_model(m["veh"]), "geid": m["geid"]})),
    Recognizer("commodity_buy", "SendCommodityBuyRequest", re.compile(r"SendCommodityBuyRequest"),
               _trade("Achat de")),
    Recognizer("commodity_sell", "SendCommoditySellRequest", re.compile(r"SendCommoditySellRequest"),
               _trade("Vente de")),
    Recognizer("item_buy", "SendStandardItemBuyRequest", re.compile(r"SendStandardItemBuyRequest"),
               lambda m: (lambda f: (f"Achat d'objet {f.get('itemName', '?')} au shop {f.get('shopName', '?')}"
                                     f" pour {_num(f.get('client_price', '0')):,.0f} aUEC".replace(",", " "),
                                     {"item": f.get("itemName", ""), "shop": f.get("shopName", ""),
                                      "price": _num(f.get("client_price", "0"))}))(_fields(m.string))),
    Recognizer("mission_end", "<EndMission>",
               re.compile(r"MissionId\[(?P<id>[^\]]*)\].*?CompletionType\[(?P<type>[^\]]*)\]"),
               lambda m: (f"Fin de mission ({m['type']})", {"mission_id": m["id"], "completion": m["type"]})),
    Recognizer("notification", "Added notification",
               re.compile(r'Added notification "(?P<text>(?:Contract Accepted|New Objective|Nouvelle mission|Nouvel objectif|Contract Complete|Contrat)[^"]*)"', re.I),
               lambda m: (f"Mission : {m['text'].strip()}", {"text": m["text"].strip()}), strict=False),
    Recognizer("death", "<Actor Death>",
               re.compile(r"CActor::Kill: '(?P<victim>[^']+)'.*?killed by '(?P<killer>[^']+)'.*?damage type '(?P<dmg>[^']+)'"),
               lambda m: (f"Mort : {m['victim']} tué par {m['killer']} ({m['dmg']})",
                          {"victim": m["victim"], "killer": m["killer"], "damage": m["dmg"]})),
    Recognizer("vehicle_destroyed", "<Vehicle Destruction>",
               re.compile(r"Vehicle '(?P<veh>[^']+)'.*?destroy level (?P<a>\d+) to (?P<b>\d+)"),
               lambda m: (f"Vaisseau endommagé : {_vehicle_model(m['veh'])} niveau {m['a']} → {m['b']}",
                          {"vehicle": _vehicle_model(m["veh"]), "level": int(m["b"])})),
)


def recognize(line: str | LogLine, debug: Callable[[str], None] | None = None) -> GameEvent | None:
    """Premier événement reconnu dans la ligne, ou None. `debug(msg)` trace chaque correspondance."""
    ll = line if isinstance(line, LogLine) else parse_line(line)
    raw = ll.raw
    if not raw or is_spam(raw):
        return None
    for r in RECOGNIZERS:
        if not r.seen(raw):
            continue
        m = r.regex.search(raw)
        if not m:
            continue
        summary, data = r.build(m)
        ev = GameEvent(r.kind, ll.ts, summary, data, r.verified, raw)
        if debug:
            debug(f"[{r.kind}] {raw[:160]}  →  {summary}")
        return ev
    # Zone/juridiction (vérifié) : seulement « Entered … »
    if "SHUDEvent_OnNotification" in raw:
        m = _verified.RE_ZONE.search(raw)
        if m and m["zone"].strip().startswith(_verified._ZONE_PREFIXES):
            ev = GameEvent("zone", ll.ts, f"Zone : {m['zone'].strip()}", {"zone": m["zone"].strip()}, True, raw)
            if debug:
                debug(f"[zone] {raw[:160]}  →  {ev.summary}")
            return ev
    return None


def recognize_all(lines: Iterable[str], debug=None) -> list[GameEvent]:
    return [ev for ev in (recognize(l, debug) for l in lines) if ev]


@dataclass
class AuditRow:
    kind: str
    verified: bool
    marker_lines: int = 0            # lignes contenant le marqueur
    recognized: int = 0              # lignes dont la regex a réussi
    samples: list[str] = field(default_factory=list)   # lignes marquées mais non reconnues

    @property
    def suspect(self) -> bool:
        """Marqueur vu mais jamais reconnu : le format a probablement changé."""
        return self.marker_lines > 0 and self.recognized == 0


def audit(lines: Iterable[str], max_samples: int = 2) -> list[AuditRow]:
    """Pour chaque reconnaisseur : combien de lignes portent son marqueur, combien sont reconnues.

    Sert à détecter qu'une mise à jour du jeu a changé un format (marqueur présent,
    regex en échec), au lieu de perdre l'information en silence.
    """
    rows = {r.kind: AuditRow(r.kind, r.verified) for r in RECOGNIZERS}
    for raw in lines:
        if not raw or is_spam(raw):
            continue
        for r in RECOGNIZERS:
            if not r.seen(raw):
                continue
            row = rows[r.kind]
            row.marker_lines += 1
            if r.regex.search(raw):
                row.recognized += 1
            elif r.strict and len(row.samples) < max_samples:
                row.samples.append(raw)
    for r in RECOGNIZERS:
        if not r.strict:
            rows[r.kind].samples.clear()
            if rows[r.kind].recognized == 0:
                rows[r.kind].marker_lines = 0
    return list(rows.values())
