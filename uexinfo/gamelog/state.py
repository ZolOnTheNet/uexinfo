"""État courant du joueur déduit des événements Game.log — pur, sans I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from uexinfo.gamelog.events import GameEvent
from uexinfo.gamelog.places import place_label, system_of

# Une mort enregistrée « absorbe » les marqueurs de mort suivants pendant ce délai
# (mort dans un vaisseau détruit puis réapparition : une seule mort).
_DEATH_DEDUP_S = 180


@dataclass
class GameState:
    player: str = ""
    game_version: str = ""        # FileVersion de l'en-tête (ex. 4.10.193.11644)
    build: str = ""
    environment: str = ""         # valeur brute de l'en-tête (ex. PUB)
    shard: str = ""
    session_start: datetime | None = None
    system: str = ""
    location: str = ""            # dernier lieu connu en clair (départ QT, arrivée QT, inventaire)
    near_location: str = ""       # dernier code de lieu (inventaire)
    qt_target: str = ""           # cible QT en cours ; vidée à l'arrivée
    qt_route: tuple[str, str] | None = None
    ship: str = ""                # vaisseau piloté ; vidé s'il est détruit ou à la réapparition
    zone: str = ""
    # Menu principal (lancement, déconnexion) jusqu'au <Join PU>. Faux par défaut : une lecture
    # de la fin du fichier peut commencer après le <Join PU>.
    in_menu: bool = False
    last_event: datetime | None = None
    trades: list[GameEvent] = field(default_factory=list)
    missions: list[GameEvent] = field(default_factory=list)
    deaths: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    _down_pending: bool = False               # mis en récupération, mort non encore confirmée
    _last_death: datetime | None = None

    def _place(self, code: str) -> None:
        """Lieu et système déduits d'un code (inventaire, cible QT atteinte)."""
        self.location = place_label(code) or self.location
        self.system = system_of(code) or self.system

    def _count_death(self, ts: datetime | None) -> None:
        if ts and self._last_death and (ts - self._last_death).total_seconds() < _DEATH_DEDUP_S:
            return
        self.deaths += 1
        self._last_death = ts

    def apply(self, ev: GameEvent) -> None:
        self.counts[ev.kind] = self.counts.get(ev.kind, 0) + 1
        self.last_event = ev.ts or self.last_event
        d = ev.data
        k = ev.kind
        if k == "login":
            self.player = d["name"]
        elif k == "handle":
            self.player = self.player or d["name"]
        elif k == "game_version":
            self.game_version = d["version"]
        elif k == "build":
            self.build = d["build"]
        elif k == "environment":
            self.environment = d["env"]
        elif k == "menu":
            self.in_menu = True
        elif k == "spawn":
            if self.in_menu:              # apparition dans le menu principal, pas dans l'univers
                return
            self.session_start = self.session_start or ev.ts
            if self._down_pending:        # réapparition après mise à terre : c'était une mort
                self._count_death(ev.ts)
            self._down_pending = False
            self.ship = ""
            self.location = ""            # lieu de réapparition : connu au prochain inventaire
            self.qt_target = ""
        elif k == "shard":
            self.shard = d["shard"]
            self.in_menu = False
            self.session_start = None     # nouvelle connexion : la session part de la 1re apparition
        elif k == "location":
            self.location = d["loc"]
        elif k == "near_location":
            self.near_location = d["loc_code"]
            self._place(d["loc_code"])
        elif k == "qt_target":
            self.qt_target = d["loc_id"]
            self.ship = d.get("vehicle") or self.ship
        elif k == "routing_names":
            self.qt_route = (d["origin"], d["dest"])
        elif k == "qt_arrived":
            self.ship = d.get("vehicle") or self.ship
            if self.qt_target:
                self.location = ""        # plus au point de départ ; destination si code connu
                self._place(self.qt_target)
            self.qt_target = ""
        elif k == "system_change":
            self.system = d["to"]
        elif k in ("ship_enter", "ship_spawn"):
            self.ship = d["vehicle"]
        elif k == "crash":
            if d.get("player_pilot") or d.get("vehicle") == self.ship:
                self.ship = ""
        elif k == "player_dead":
            if not self.player or d.get("name") == self.player:
                self._count_death(ev.ts)
                self._down_pending = False
                self.ship = ""
        elif k == "down":
            recent = ev.ts and self._last_death and (ev.ts - self._last_death).total_seconds() < _DEATH_DEDUP_S
            self._down_pending = not recent
        elif k == "zone":
            self.zone = d["zone"]
        elif k in ("commodity_buy", "commodity_sell", "item_buy"):
            self.trades.append(ev)
        elif k in ("notification", "mission_end"):
            self.missions.append(ev)
        elif k == "death" and self.player and d.get("victim") == self.player:
            self._count_death(ev.ts)


def build_state(events) -> GameState:
    st = GameState()
    for ev in events:
        st.apply(ev)
    return st
