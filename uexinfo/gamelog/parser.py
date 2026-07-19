"""Extraction d'événements depuis les lignes de Game.log.

Catégories vérifiées contre un vrai Game.log (build 4.9 LIVE, juillet 2026) :
connexion, spawn, zone/juridiction, lieu de départ de route QT, cible QT
sélectionnée, correspondance identifiant↔nom de lieu en clair, et docking
(déclencheur, sans dépendre des noms de code internes des tubes d'accostage —
vérifié non fiables : mêmes noms génériques "Reststop-arm"/"Secdock-arm"
réutilisés à plusieurs stations différentes). La confirmation d'arrivée
(uexinfo.gamelog.arrival.ArrivalTracker) corrèle cible QT + nom en clair +
docking pour proposer un lieu précis sans jamais décoder les codes internes.
Mort/destruction reste hors scope (regex non observée sur un vrai log).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

RE_TIMESTAMP = re.compile(r"^<(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)>")
RE_LOGIN = re.compile(r"AccountLoginCharacterStatus_Character.*?name (?P<name>\S+)")
RE_SPAWN = re.compile(r"\[CSessionManager::OnClientSpawned\] Spawned!")
RE_ZONE = re.compile(r'SHUDEvent_OnNotification.*?Added notification "(?P<zone>[^"]+)"')
# Source principale et faisant autorité pour le nom de lieu affiché : écrite par le jeu
# à chaque calcul de route QT (starmap, sélection de destination), avec le nom exact
# affiché en jeu — pas un identifiant interne à mapper. Ne se met à jour que lors d'un
# calcul de route (pas de flux continu) ; une fois éloigné d'une station, le champ
# redevient le nom du corps céleste parent — c'est la précision réelle du jeu, pas une
# erreur à corriger côté parsing.
RE_ROUTE_START = re.compile(r"Projected Start Location is (?P<loc>.+?) for route to destination")

# La notification SHUDEvent_OnNotification sert aussi à des textes hors-zone
# (conseils medbay, "Contract Accepted: ...") — vérifié sur un vrai log : seules
# les entrées commençant par "Entered "/"Entering " sont des franchissements de
# zone/juridiction exploitables pour la localisation.
_ZONE_PREFIXES = ("Entered ", "Entering ")

# Identifiant interne de la cible QT sélectionnée (ex: LOC_rs_ext_stan-pyro_jp1) —
# sert de clé pour associer plus tard un nom en clair (RE_ROUTING_NAMES) et pour
# savoir "vers où" un docking ultérieur correspond probablement (ArrivalTracker).
RE_QT_TARGET = re.compile(r"Player has selected point (?P<loc_id>\S+) as their destination")

# Seule ligne qui donne origine ET destination en clair dans la même phrase — sert à
# apprendre la correspondance identifiant→nom humain (le "Player has selected point"
# qui la précède immédiatement dans le même calcul de route donne l'identifiant).
RE_ROUTING_NAMES = re.compile(
    r"routing from (?P<origin>.+?) to (?P<dest>.+?) (?:Obstructing|Routing)\b"
)

# Déclencheur seul, jamais le nom capté : vérifié sur un vrai log que
# "Reststop-arm"/"Secdock-arm" sont des gabarits de tube d'accostage réutilisés à
# plusieurs stations différentes dans la même session — ne permettent pas d'identifier
# QUELLE station. Seul le fait "un docking a eu lieu" est exploité.
RE_DOCKING = re.compile(r"CDockingAnimatorComponent::OnSetCurrentState>")


@dataclass
class GameLogEvent:
    kind: str        # "login"|"spawn"|"zone"|"location"|"qt_target"|"routing_names"|"docking"
    text: str        # contenu principal (nom, texte de zone, lieu…) ; vide si non pertinent
    timestamp: datetime
    data: dict = field(default_factory=dict)   # champs auxiliaires (loc_id, origin, dest…)


def _parse_timestamp(line: str) -> datetime | None:
    m = RE_TIMESTAMP.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("ts"), "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return None


def parse_lines(lines: list[str]) -> list[GameLogEvent]:
    """Parse une liste de lignes brutes de Game.log en événements reconnus."""
    events: list[GameLogEvent] = []
    for line in lines:
        ts = _parse_timestamp(line) or datetime.now()

        m = RE_ROUTE_START.search(line)
        if m:
            events.append(GameLogEvent(kind="location", text=m.group("loc").strip(), timestamp=ts))
            continue

        m = RE_QT_TARGET.search(line)
        if m:
            events.append(GameLogEvent(kind="qt_target", text="", timestamp=ts,
                                        data={"loc_id": m.group("loc_id")}))
            continue

        m = RE_ROUTING_NAMES.search(line)
        if m:
            events.append(GameLogEvent(kind="routing_names", text="", timestamp=ts,
                                        data={"origin": m.group("origin").strip(),
                                              "dest": m.group("dest").strip()}))
            continue

        if RE_DOCKING.search(line):
            events.append(GameLogEvent(kind="docking", text="", timestamp=ts))
            continue

        m = RE_ZONE.search(line)
        if m:
            zone_text = m.group("zone").strip()
            if zone_text.startswith(_ZONE_PREFIXES):
                events.append(GameLogEvent(kind="zone", text=zone_text, timestamp=ts))
            continue

        m = RE_LOGIN.search(line)
        if m:
            events.append(GameLogEvent(kind="login", text=m.group("name"), timestamp=ts))
            continue

        if RE_SPAWN.search(line):
            events.append(GameLogEvent(kind="spawn", text="", timestamp=ts))
            continue

    return events
