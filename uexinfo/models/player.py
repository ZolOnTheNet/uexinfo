"""Modèles joueur — Player et Ship."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Ship:
    name: str
    scu: int = 0


@dataclass
class Player:
    username: str = ""
    ships: list[Ship] = field(default_factory=list)
    active_ship: str = ""
    location: str = ""
    destination: str = ""

    @classmethod
    def from_config(cls, cfg_player: dict) -> "Player":
        ships = [Ship(**s) for s in cfg_player.get("ships", [])]
        return cls(
            username=cfg_player.get("username", ""),
            ships=ships,
            active_ship=cfg_player.get("active_ship", ""),
            location=cfg_player.get("location", ""),
            destination=cfg_player.get("destination", ""),
        )

    def to_config(self) -> dict:
        return {
            "username": self.username,
            "ships": [{"name": s.name, "scu": s.scu} for s in self.ships],
            "active_ship": self.active_ship,
            "location": self.location,
            "destination": self.destination,
        }
