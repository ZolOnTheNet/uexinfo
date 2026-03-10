"""Modèles joueur — Player et Ship."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Ship:
    name: str
    scu: int = 0
    cargo_config: dict[int, int] = field(default_factory=dict)  # {taille_scu: quantité}


@dataclass
class Player:
    username: str = ""
    ships: list[Ship] = field(default_factory=list)
    active_ship: str = ""
    location: str = ""
    destination: str = ""

    @classmethod
    def from_config(cls, cfg_player: dict) -> "Player":
        ships = []
        for s in cfg_player.get("ships", []):
            # Convertir cargo_config de dict[str, int] → dict[int, int]
            raw_cargo = s.get("cargo_config", {})
            cargo_config = {int(k): v for k, v in raw_cargo.items()} if raw_cargo else {}
            ships.append(Ship(
                name=s.get("name", ""),
                scu=s.get("scu", 0),
                cargo_config=cargo_config,
            ))
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
            "ships": [
                {
                    "name": s.name,
                    "scu": s.scu,
                    "cargo_config": {str(k): v for k, v in s.cargo_config.items()},
                }
                for s in self.ships
            ],
            "active_ship": self.active_ship,
            "location": self.location,
            "destination": self.destination,
        }
