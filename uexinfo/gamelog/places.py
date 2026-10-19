"""Codes de lieu internes du Game.log → nom affiché en jeu et système — pur, sans I/O.

Les noms viennent de 317 Game.log réels de l'utilisateur (relevé du 2026-10-19) : un code
d'inventaire (`requested inventory for Location[RR_CRU_LEO]`) ou une cible QT atteinte, suivi
d'un calcul de route depuis le même endroit (`Projected Start Location is Seraphim Station`).
Seules les correspondances majoritaires et cohérentes sont gardées. Un code inconnu donne « ».
"""
from __future__ import annotations

import re

# Corps célestes : <Système><index>, ex. Stanton1c = Magda (vérifié via OOC_Stanton_1c_Magda).
_BODIES = {
    "stanton1": "Hurston", "stanton1a": "Arial", "stanton1c": "Magda", "stanton1d": "Ita",
    "stanton2": "Crusader", "stanton2a": "Cellin", "stanton2b": "Daymar", "stanton2c": "Yela",
    "stanton3": "ArcCorp", "stanton3a": "Lyria", "stanton3b": "Wala",
    "stanton4": "microTech", "stanton4a": "Calliope", "stanton4b": "Clio",
    "pyro2": "Monox", "pyro3": "Bloom", "pyro4": "Pyro IV",
}

# Préfixe des aires de repos de Stanton : RR_<CORPS>_… et LOC_RR_S<n>_… (S1 = Hurston…).
_RR_STANTON = {"HUR": "1", "CRU": "2", "ARC": "3", "MIC": "4"}

_NAMES = {
    "RR_HUR_LEO": "Everus Harbor", "RR_CRU_LEO": "Seraphim Station",
    "RR_ARC_LEO": "Baijini Point", "RR_MIC_LEO": "Port Tressler",
    "RR_HUR_L1": "HUR-L1 Green Glade Station", "RR_HUR_L2": "HUR-L2 Faithful Dream Station",
    "RR_HUR_L3": "HUR-L3 Thundering Express Station", "RR_HUR_L4": "HUR-L4 Melodic Fields Station",
    "RR_HUR_L5": "HUR-L5 High Course Station",
    "RR_CRU_L1": "CRU-L1 Ambitious Dream Station", "RR_CRU_L4": "CRU-L4 Shallow Fields Station",
    "RR_CRU_L5": "CRU-L5 Beautiful Glen Station",
    "RR_ARC_L1": "ARC-L1 Wide Forest Station", "RR_ARC_L2": "ARC-L2 Lively Pathway Station",
    "RR_ARC_L3": "ARC-L3 Modern Express Station", "RR_ARC_L4": "ARC-L4 Faint Glen Station",
    "RR_ARC_L5": "ARC-L5 Yellow Core Station",
    "RR_MIC_L1": "MIC-L1 Shallow Frontier Station", "RR_MIC_L2": "MIC-L2 Long Forest Station",
    "RR_MIC_L3": "MIC-L3 Endless Odyssey Station", "RR_MIC_L4": "MIC-L4 Red Crossroads Station",
    "RR_MIC_L5": "MIC-L5 Modern Icarus Station",
    "RR_P3_L1": "Starlight Service Station", "RR_P3_L3": "Patch City", "RR_P3_LEO": "Orbituary",
    "RR_P5_L2": "Gaslight", "RR_P5_L4": "Rod's Fuel 'N Supplies", "RR_P5_L5": "Rat's Nest",
    "RR_P6_L3": "Endgame", "RR_P6_LEO": "Ruin Station",
    # Points de saut : le 1er système du code est celui où l'on se trouve
    # (RR_JP_PyroStanton = la « Stanton Gateway » située dans Pyro).
    "RR_JP_StantonPyro": "Pyro Gateway", "RR_JP_StantonMagnus": "Nyx Gateway",
    "RR_JP_StantonTerra": "Terra Gateway", "RR_JP_PyroStanton": "Stanton Gateway",
    "RR_JP_PyroNyx": "Nyx Gateway", "RR_JP_NyxPyro": "Pyro Gateway", "RR_JP_NyxCastra": "Stanton Gateway",
    "LOC_rs_ext_stan-pyro_jp1": "Pyro Gateway", "LOC_rs_ext_stan-magnus_jp1": "Nyx Gateway",
    "LOC_rs_ext_stan-terra_jp1": "Terra Gateway",
    # Villes et stations hors aires de repos
    "Stanton1_Lorville": "Lorville", "ObjectContainer_Lorville_City": "Lorville",
    "Stanton2_Orison": "Orison", "Orison_LOC": "Orison",
    "Stanton3_Area18": "Area18", "Area18_City_objectContainer": "Area18",
    "Stanton4_NewBabbage": "New Babbage", "NewBabbage_LOC": "New Babbage",
    "GrimHEX": "Grim HEX", "GrimHEX_OC": "Grim HEX",
    "Nyx_Levski": "Levski", "levski_all-001": "Levski",
}

_SYSTEM_OF_NAME = {
    "Lorville": "Stanton", "Orison": "Stanton", "Area18": "Stanton", "New Babbage": "Stanton",
    "Grim HEX": "Stanton", "Levski": "Nyx",
}

_RE_RS_EXT = re.compile(r"^rs_ext_(?:(?P<body>hur|cru|arc|mic)-(?P<pt>leo|l\d)\d*|pyro(?P<p>\d)_(?P<ppt>leo|l\d))$", re.I)
_RE_LOC_RR = re.compile(r"^LOC_RR_S(?P<n>\d)_(?P<pt>L\d|LEO)$", re.I)
_RE_OOC = re.compile(r"^OOC_(?P<sys>[A-Za-z]+)_(?P<idx>\d+[a-z]?)_(?P<name>[A-Za-z]+)$")
_RE_BODY_PREFIX = re.compile(r"^(?P<body>(?:Stanton|Pyro)\d[a-z]?)_", re.I)
_RE_HDMS = re.compile(r"HurdynMining_HDMS(?P<name>[A-Za-z]+)$")


def _normalize(code: str) -> str:
    """Formes équivalentes ramenées au code d'aire de repos (`rs_ext_cru-leo1` → `RR_CRU_LEO`)."""
    m = _RE_RS_EXT.match(code)
    if m:
        if m["body"]:
            return f"RR_{m['body'].upper()}_{m['pt'].upper()}"
        return f"RR_P{m['p']}_{m['ppt'].upper()}"
    m = _RE_LOC_RR.match(code)
    if m:
        body = next((b for b, n in _RR_STANTON.items() if n == m["n"]), "")
        if body:
            return f"RR_{body}_{m['pt'].upper()}"
    return code


def place_label(code: str) -> str:
    """Nom affiché en jeu pour un code de lieu ou de cible QT ; « » si inconnu."""
    if not code:
        return ""
    code = _normalize(code.strip())
    if code in _NAMES:
        return _NAMES[code]
    m = re.match(r"^RR_(HUR|CRU|ARC|MIC)_(L\d)$", code)
    if m:                                   # Lagrange non relevé : nom court du jeu
        return f"{m[1]}-{m[2]}"
    m = _RE_OOC.match(code)
    if m:
        return _BODIES.get(f"{m['sys']}{m['idx']}".lower(), "")
    m = _RE_HDMS.search(code)
    if m:
        return f"HDMS-{m['name']}"
    m = _RE_BODY_PREFIX.match(code)
    if m:                                   # avant-poste : le jeu n'affiche que le corps céleste
        return _BODIES.get(m["body"].lower(), "")
    return ""


def system_of(code: str) -> str:
    """Système d'un code de lieu ou de cible QT (`Stanton`, `Pyro`, `Nyx`) ; « » si inconnu."""
    if not code:
        return ""
    code = _normalize(code.strip())
    if re.match(r"^RR_(HUR|CRU|ARC|MIC)_", code):
        return "Stanton"
    if re.match(r"^RR_P\d_", code):
        return "Pyro"
    m = re.match(r"^RR_JP_(Stanton|Pyro|Nyx)", code)
    if m:
        return m[1]
    if code.startswith("LOC_rs_ext_stan-"):
        return "Stanton"
    m = re.match(r"^(?:OOC_)?(Stanton|Pyro|Nyx)", code, re.I)
    if m:
        return m[1].capitalize()
    return _SYSTEM_OF_NAME.get(_NAMES.get(code, ""), "")
