"""Arrivée, atterrissage et départ d'un lieu, déduits des événements Game.log — pur, sans I/O.

Signaux vérifiés le 2026-10-31 (Baijini Point → Terra Gateway, voir docs/ai/GAMELOG_SPEC.md) :
- **arrivée** : `Landing [a] -> [b]` avec b ≠ 0 (zone de la station ou de la ville), suivi dans la
  même seconde de `RequestLocationInventory Location[<code>]` qui donne le lieu. Approcher suffit :
  pas besoin d'atterrir ;
- **apparition** (connexion, réapparition) : même entrée de zone, mais le lieu n'est nommé que
  ~11 s plus tard, et la ligne `Spawned!` peut suivre l'entrée de zone de quelques millisecondes ;
- **hangar attribué** : « Hangar Request Completed » dans les 3 minutes qui suivent l'arrivée (27 s
  et 56 s observées) ; la taille est celle de l'ascenseur à vaisseau chargé juste avant. La même
  notification plus tard (Area18 : 14 min après) est l'ouverture du hangar pour décoller ;
- **posé** : le joueur quitte les commandes (`ClearDriver`) dans la zone du lieu ;
- **départ** : `Landing [b] -> [0]`.

Les amarrages (`CDockingAnimatorComponent`) et les messages d'armistice ne servent pas : ils
apparaissent aussi quand la station se charge autour du joueur à pied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from uexinfo.gamelog.events import GameEvent
from uexinfo.gamelog.places import place_label, system_of

_CODE_WAIT_S = 20         # délai entre l'entrée de zone et la ligne d'inventaire qui nomme le lieu
_SPAWN_CODE_WAIT_S = 90   # le même à l'apparition, pendant le chargement (11 s et 55 s observées)
_ELEVATOR_WAIT_S = 10     # délai entre le chargement de l'ascenseur et « Hangar Request Completed »
_RESPAWN_WAIT_S = 120     # une entrée de zone peu avant ou après une apparition est une apparition
_REQUEST_WAIT_S = 180     # au-delà, « Hangar Request Completed » est une demande de départ

_SIZES_FR = {"Small": "petit", "Medium": "moyen", "Large": "grand", "XL": "très grand"}


@dataclass
class PresenceNotice:
    """Fait à annoncer au joueur.

    `kind` : arrival, respawn, hangar, pad, landed, departure. `place` : nom affiché en jeu
    (« » si inconnu), `system` : son système, `code` : code interne du lieu.
    """
    kind: str
    ts: datetime | None
    place: str = ""
    system: str = ""
    code: str = ""
    detail: str = ""

    @property
    def text(self) -> str:
        """Phrase à afficher."""
        where = self.place or "un lieu inconnu"
        return {
            "arrival":   f"📍 Arrivée à {where}",
            "respawn":   f"📍 Apparition à {where}",
            "hangar":    f"🅷 Hangar attribué à {where}" + (f" ({self.detail})" if self.detail else ""),
            "pad":       f"🅿 Pad attribué à {where}",
            "landed":    f"⬇ Posé à {where}",
            "departure": f"🛫 Départ de {where}",
        }.get(self.kind, self.kind)


@dataclass
class PresenceTracker:
    """État « où est le joueur » ; `feed()` renvoie les faits nouveaux à annoncer.

    `known_codes` (identifiant de zone → code de lieu) est appris au fil des arrivées ; l'appelant
    peut le conserver entre deux sessions pour nommer une arrivée sans ligne d'inventaire.
    """
    known_codes: dict[int, str] = field(default_factory=dict)
    phase: str = "away"            # away (en vol, hors zone) | arrived (dans la zone) | landed (posé, à pied)
    zone_id: int = 0
    code: str = ""
    place: str = ""
    system: str = ""
    _pending: list | None = None                                # [zone, heure, apparition] pas encore nommée
    _arrived_at: datetime | None = None
    _last_spawn: datetime | None = None
    _elevator: tuple[str, datetime | None] | None = None        # dernier ascenseur de hangar chargé

    def feed(self, events) -> list[PresenceNotice]:
        """Applique les événements dans l'ordre ; faits à annoncer, dans l'ordre."""
        out: list[PresenceNotice] = []
        for ev in events:
            out += self._apply(ev)
        return out

    def flush(self, now: datetime | None = None) -> list[PresenceNotice]:
        """Annonce une arrivée restée sans nom (pas de ligne d'inventaire), une fois le délai passé."""
        if self._pending and (now is None or _elapsed(self._pending[1], now) > self._code_wait()):
            return self._arrive("", now)
        return []

    # ── Interne ───────────────────────────────────────────────────────────────

    def _apply(self, ev: GameEvent) -> list[PresenceNotice]:
        """Faits produits par un événement."""
        out = self.flush(ev.ts) if self._pending and ev.kind != "near_location" else []
        k, d = ev.kind, ev.data
        if k == "spawn":
            self._last_spawn = ev.ts
            if self._pending:
                self._pending[2] = True
        elif k == "place_zone":
            if d["to"]:
                if d["to"] != self.zone_id or self.phase == "away":
                    respawn = bool(self._last_spawn and _elapsed(self._last_spawn, ev.ts) < _RESPAWN_WAIT_S)
                    self._pending = [d["to"], ev.ts, respawn]
                    self.zone_id = d["to"]
                    if d["to"] in self.known_codes:
                        out += self._arrive(self.known_codes[d["to"]], ev.ts)
            elif self.phase != "away" and d["from"] == self.zone_id:
                out.append(PresenceNotice("departure", ev.ts, self.place, self.system, self.code))
                self.phase, self.zone_id = "away", 0
        elif k == "near_location" and self._pending and _elapsed(self._pending[1], ev.ts) <= self._code_wait():
            self.known_codes[self._pending[0]] = d["loc_code"]
            out += self._arrive(d["loc_code"], ev.ts)
        elif k == "ship_elevator":
            self._elevator = (d["size"], ev.ts)
        elif (k == "landing_request" and self.phase == "arrived"
              and _elapsed(self._arrived_at, ev.ts) <= _REQUEST_WAIT_S):
            if d.get("hangar"):
                size = ""
                if self._elevator and _elapsed(self._elevator[1], ev.ts) <= _ELEVATOR_WAIT_S:
                    size = f"hangar {_SIZES_FR.get(self._elevator[0], self._elevator[0])}"
                out.append(PresenceNotice("hangar", ev.ts, self.place, self.system, self.code, size))
            else:
                out.append(PresenceNotice("pad", ev.ts, self.place, self.system, self.code))
        elif k == "ship_leave" and self.phase == "arrived":
            self.phase = "landed"
            out.append(PresenceNotice("landed", ev.ts, self.place, self.system, self.code))
        return out

    def _code_wait(self) -> float:
        """Attente maximale du nom du lieu pour l'entrée de zone en cours."""
        return _SPAWN_CODE_WAIT_S if self._pending and self._pending[2] else _CODE_WAIT_S

    def _arrive(self, code: str, ts: datetime | None) -> list[PresenceNotice]:
        """Termine une entrée de zone : lieu nommé (ou inconnu), fait « arrivée » ou « apparition »."""
        _, _, respawn = self._pending or (0, None, False)
        self._pending = None
        self._arrived_at = ts
        self.code = code
        self.place = place_label(code) if code else ""
        self.system = system_of(code) if code else ""
        self.phase = "landed" if respawn else "arrived"      # on réapparaît à pied
        return [PresenceNotice("respawn" if respawn else "arrival", ts, self.place, self.system, code)]


def _elapsed(a: datetime | None, b: datetime | None) -> float:
    """Secondes de `a` à `b` ; 0 si l'une manque."""
    return (b - a).total_seconds() if a and b else 0.0
