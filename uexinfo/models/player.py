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
    location_id: int = 0
    destination_id: int = 0
    # Lieu déduit en direct de Game.log ("Projected Start Location is X", écrit par le
    # jeu à chaque calcul de route QT — nom d'affichage exact, pas un identifiant à
    # mapper). Source qui fait autorité pour le nom de lieu affiché hors trading, mais
    # PAS un terminal UEX résolvable (à quai précis vs. corps céleste parent selon
    # l'éloignement) — donc jamais utilisé pour écraser location/location_id.
    # Ne se met à jour qu'à chaque calcul de route ; conserve la dernière valeur connue
    # entre deux calculs (pas de flux continu).
    zone: str = ""
    zone_ts: float = 0.0
    # Juridiction/statut courant (SHUDEvent_OnNotification — "Crusader Industries
    # Jurisdiction", "Armistice Zone"...). Contexte complémentaire UNIQUEMENT : "Crusader
    # Industries" y désigne la compagnie/juridiction légale, pas la planète Crusader —
    # ne jamais l'utiliser ni l'afficher comme nom de lieu principal (cf. zone ci-dessus).
    zone_status: str = ""
    zone_status_ts: float = 0.0
    # Shard PU réel (ex: "pub_euw1b_12269732_050", Game.log "<Join PU> ... shard[...]")
    # — écrit une fois par connexion/reconnexion à l'univers persistant. Change au
    # relance du jeu, mais aussi en cours de session si reconnexion après crash/
    # instabilité serveur — signal important pour repérer un shard HS.
    shard: str = ""
    shard_ts: float = 0.0

    def set_location(self, name: str, terminal_id: int = 0) -> None:
        """Position courante — nom et id terminal toujours écrits ensemble.

        `location_id` (0 si non résolu contre un terminal UEX) fait autorité
        pour tout calcul (/trade, distances) ; `location` reste nécessaire
        pour les lieux hors cache UEX (Pyro, lieu perso) où aucun id n'existe.
        Ne jamais assigner ces deux champs séparément (source historique d'un
        bug : /player @lieu mettait à jour location sans toucher location_id,
        qui restait bloqué sur un ancien terminal).
        """
        self.location = name
        self.location_id = terminal_id

    def clear_location(self) -> None:
        self.location = ""
        self.location_id = 0

    def set_destination(self, name: str, terminal_id: int = 0) -> None:
        self.destination = name
        self.destination_id = terminal_id

    def clear_destination(self) -> None:
        self.destination = ""
        self.destination_id = 0

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
            location_id=int(cfg_player.get("location_id", 0) or 0),
            destination_id=int(cfg_player.get("destination_id", 0) or 0),
            zone=cfg_player.get("zone", ""),
            zone_ts=float(cfg_player.get("zone_ts", 0) or 0),
            zone_status=cfg_player.get("zone_status", ""),
            zone_status_ts=float(cfg_player.get("zone_status_ts", 0) or 0),
            shard=cfg_player.get("shard", ""),
            shard_ts=float(cfg_player.get("shard_ts", 0) or 0),
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
            "location_id": self.location_id,
            "destination_id": self.destination_id,
            "zone": self.zone,
            "zone_ts": self.zone_ts,
            "zone_status": self.zone_status,
            "zone_status_ts": self.zone_status_ts,
            "shard": self.shard,
            "shard_ts": self.shard_ts,
        }
