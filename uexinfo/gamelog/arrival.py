"""Corrélation d'événements Game.log pour une proposition d'arrivée fiable.

Principe (vérifié sur un vrai log, voir gamelog/parser.py) :
- "Player has selected point LOC_xxx as their destination" donne l'identifiant
  interne de la cible QT choisie.
- "...routing from Seraphim Station to Pyro Gateway..." (quand elle apparaît,
  pas systématique) donne le nom en clair de cette même destination — apprise
  une fois, réutilisable pour les recalculs ultérieurs vers le même LOC_xxx.
- Un docking (peu importe le nom de code interne du tube — vérifié non fiable
  pour identifier la station) qui survient après une cible connue est un signal
  raisonnable d'arrivée à cette destination.

Ce n'est qu'une PROPOSITION (comme l'auto-position existante) : jamais appliquée
directement, toujours via confirmation utilisateur (bandeau [MàJ]/[Ign]).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import appdirs

from uexinfo.gamelog.parser import GameLogEvent

# Fenêtre au-delà de laquelle deux lignes de docking sont deux arrivées
# distinctes plutôt qu'un seul burst — vérifié sur un vrai log qu'un burst peut
# s'étaler jusqu'à ~40s (plusieurs tubes/composants s'initialisant en séquence).
_DOCKING_BURST_GAP_S = 45.0

# Table de correspondance loc_id -> nom en clair, persistée sur disque (pas
# seulement en mémoire de session) : une fois qu'un identifiant a été vu avec
# son nom une fois (via une ligne "routing from X to Y"), il reste résolvable
# indéfiniment, même lors d'une session future qui ne recroise jamais la ligne
# d'origine — par sécurité/robustesse plutôt que de tout réapprendre à chaque
# fois.
_KNOWN_NAMES_FILE = Path(appdirs.user_data_dir("uexinfo")) / "game_log_known_locations.json"


class ArrivalTracker:
    """État cumulatif sur une session : à nourrir en continu via `feed()`."""

    def __init__(self) -> None:
        self.known_names: dict[str, str] = self._load_known_names()   # loc_id -> nom en clair
        self.pending_target: str | None = None    # loc_id de la dernière cible QT sélectionnée
        self._last_docking_ts: datetime | None = None

    @staticmethod
    def _load_known_names() -> dict[str, str]:
        if _KNOWN_NAMES_FILE.exists():
            try:
                with open(_KNOWN_NAMES_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_known_names(self) -> None:
        try:
            _KNOWN_NAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_KNOWN_NAMES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.known_names, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def feed(self, events: list[GameLogEvent]) -> list[GameLogEvent]:
        """Traite des événements chronologiques, retourne les propositions d'arrivée
        (kind="arrival_candidate", text=nom en clair de la destination probable)."""
        arrivals: list[GameLogEvent] = []
        for e in events:
            if e.kind == "qt_target":
                self.pending_target = e.data.get("loc_id") or self.pending_target

            elif e.kind == "routing_names":
                dest = e.data.get("dest")
                if self.pending_target and dest and self.known_names.get(self.pending_target) != dest:
                    self.known_names[self.pending_target] = dest
                    self._save_known_names()

            elif e.kind == "docking":
                is_new_burst = (
                    self._last_docking_ts is None
                    or (e.timestamp - self._last_docking_ts).total_seconds() > _DOCKING_BURST_GAP_S
                )
                self._last_docking_ts = e.timestamp
                if not is_new_burst:
                    continue
                if self.pending_target and self.pending_target in self.known_names:
                    arrivals.append(GameLogEvent(
                        kind="arrival_candidate",
                        text=self.known_names[self.pending_target],
                        timestamp=e.timestamp,
                    ))
                    # Évite de reproposer la même arrivée pour un docking ultérieur
                    # (ex: undocking puis redocking au même endroit) tant qu'aucune
                    # nouvelle cible n'a été sélectionnée.
                    self.pending_target = None

        return arrivals
