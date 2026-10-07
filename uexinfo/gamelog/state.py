"""État courant du joueur déduit des événements Game.log — pur, sans I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from uexinfo.gamelog.events import GameEvent


@dataclass
class GameState:
    player: str = ""
    game_version: str = ""        # FileVersion de l'en-tête (ex. 4.10.193.11644)
    build: str = ""
    environment: str = ""         # valeur brute de l'en-tête (ex. PUB)
    shard: str = ""
    session_start: datetime | None = None
    system: str = ""
    location: str = ""            # dernier lieu en clair (départ de route QT)
    near_location: str = ""       # dernier code de lieu (inventaire)
    qt_target: str = ""
    qt_route: tuple[str, str] | None = None
    ship: str = ""                # vaisseau piloté
    zone: str = ""
    last_event: datetime | None = None
    trades: list[GameEvent] = field(default_factory=list)
    missions: list[GameEvent] = field(default_factory=list)
    deaths: int = 0
    counts: dict[str, int] = field(default_factory=dict)

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
        elif k == "spawn":
            self.session_start = ev.ts
        elif k == "shard":
            self.shard = d["shard"]
        elif k == "location":
            self.location = d["loc"]
        elif k == "near_location":
            self.near_location = d["loc_code"]
        elif k == "qt_target":
            self.qt_target = d["loc_id"]
            self.ship = d.get("vehicle") or self.ship
        elif k == "routing_names":
            self.qt_route = (d["origin"], d["dest"])
        elif k == "qt_arrived":
            self.ship = d.get("vehicle") or self.ship
        elif k == "system_change":
            self.system = d["to"]
        elif k in ("ship_enter", "ship_spawn"):
            self.ship = d["vehicle"]
        elif k == "zone":
            self.zone = d["zone"]
        elif k in ("commodity_buy", "commodity_sell", "item_buy"):
            self.trades.append(ev)
        elif k in ("notification", "mission_end"):
            self.missions.append(ev)
        elif k == "death" and self.player and d.get("victim") == self.player:
            self.deaths += 1


def build_state(events) -> GameState:
    st = GameState()
    for ev in events:
        st.apply(ev)
    return st
