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
- **départ** : `Landing [b] -> [0]` ;
- **mort** : `[ActorState] Dead` au nom du joueur (vaisseau détruit), ou une réapparition sans écran
  de chargement (mort à pied, sans cause écrite) : à la connexion, l'écran de chargement précède
  toujours l'apparition, jamais après une mort (9 morts vérifiées, 15-28/10/2026). Le **réveil**
  qui suit est une apparition comme les autres : zone du lieu, puis ligne d'inventaire. En Arena
  Commander (pas de `<Join PU>` depuis le menu), les morts sont ignorées.

Les amarrages (`CDockingAnimatorComponent`) et les messages d'armistice ne servent pas : ils
apparaissent aussi quand la station se charge autour du joueur à pied.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from uexinfo.gamelog.events import GameEvent
from uexinfo.gamelog.places import outpost_label, place_label, system_of

_CODE_WAIT_S = 20         # délai entre l'entrée de zone et la ligne d'inventaire qui nomme le lieu
_SPAWN_CODE_WAIT_S = 90   # le même à l'apparition, pendant le chargement (11 s et 55 s observées)
_ELEVATOR_WAIT_S = 10     # délai entre le chargement de l'ascenseur et « Hangar Request Completed »
_RESPAWN_WAIT_S = 120     # une entrée de zone peu avant ou après une apparition est une apparition
_REQUEST_WAIT_S = 180     # au-delà, « Hangar Request Completed » est une demande de départ
_KNOWN_CODE_WAIT_S = 3    # zone déjà connue : attente de « Spawned! » (quelques ms) ou de l'inventaire
_DEATH_WAIT_S = 300       # une mort annoncée moins longtemps avant une apparition explique celle-ci
_RETURN_WAIT_S = 120      # retour dans la zone quittée moins longtemps après : on n'était pas parti
_CRASH_WAIT_S = 2         # « ClearDriver » juste après un crash : éjection, pas un atterrissage

# Erreurs de déconnexion relevées dans les Game.log de l'utilisateur (raison lue juste avant).
_ERRORS_FR = {
    30000: "le serveur ne répond plus depuis 30 s (serveur ou réseau)",
    30013: "le serveur du shard a planté",
    30028: "inactivité du joueur",
    70003: "authentification expirée pendant le chargement",
    19000: "connexion au compte impossible (services du jeu)",
    19005: "connexion au compte impossible (délai dépassé)",
}
_DISCONNECT_WAIT_S = 60   # raison de déconnexion lue au plus ce délai avant la fenêtre d'erreur

_SIZES_FR = {"Small": "petit", "Medium": "moyen", "Large": "grand", "XL": "très grand"}


@dataclass
class PresenceNotice:
    """Fait à annoncer au joueur.

    `kind` : arrival, respawn, regen (réveil après une mort), hangar, pad, landed, departure,
    death, disconnect. `place` : nom affiché en jeu
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
            "departure": f"🛫 Départ de {self.place}" if self.place else "🛫 Départ d'un lieu inconnu",
            "death":     "💀 Mort" + (f" à {self.place}" if self.place else "")
                         + (f" ({self.detail})" if self.detail else ""),
            "regen":     f"🏥 Réveil à {where}",
            "disconnect": "⚠ Déconnexion du serveur" + (f" ({self.detail})" if self.detail else ""),
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
    player: str = ""               # pseudo du joueur (ligne « Handle[…] ») ; vide = inconnu
    _pending: list | None = None                                # [zone, heure, sorte de fait] pas encore nommée
    _arrived_at: datetime | None = None
    _last_spawn: datetime | None = None
    _elevator: tuple[str, datetime | None] | None = None        # dernier ascenseur de hangar chargé
    _spawn_kind: str = "respawn"   # sorte de la dernière apparition : respawn | regen
    _loading: bool = True          # écran de chargement depuis la dernière apparition (inconnu au début : oui)
    _in_pu: bool | None = None     # dans l'univers persistant ; None = inconnu (lecture commencée en cours)
    _dead_at: datetime | None = None
    _crash_at: datetime | None = None
    _disconnect: tuple[str, datetime | None] | None = None   # dernière raison de déconnexion lue
    _left: tuple[int, datetime | None] | None = None   # dernière zone quittée, et quand
    _quiet: bool = False           # revenu aussitôt dans la zone quittée : sa sortie n'est pas annoncée

    def feed(self, events) -> list[PresenceNotice]:
        """Applique les événements dans l'ordre ; faits à annoncer, dans l'ordre."""
        out: list[PresenceNotice] = []
        for ev in events:
            out += self._apply(ev)
        return out

    def flush(self, now: datetime | None = None) -> list[PresenceNotice]:
        """Annonce une arrivée restée sans nom (pas de ligne d'inventaire), une fois le délai passé."""
        if self._pending and (now is None or _elapsed(self._pending[1], now) > self._code_wait()):
            code = self.known_codes.get(self._pending[0], "")
            return self._arrive(code, self._pending[1] if code else now)
        return []

    # ── Interne ───────────────────────────────────────────────────────────────

    def _apply(self, ev: GameEvent) -> list[PresenceNotice]:
        """Faits produits par un événement."""
        out = self.flush(ev.ts) if self._pending and ev.kind != "near_location" else []
        k, d = ev.kind, ev.data
        if k == "handle":
            self.player = d["name"]
        elif k == "shard":
            self._in_pu = True
        elif k == "menu":                                      # déconnexion : plus nulle part
            self._in_pu, self._loading = False, True
            self.phase, self.zone_id, self._pending = "away", 0, None
        elif k == "disconnect":
            self._disconnect = (d["reason"], ev.ts)
        elif k == "error_popup":
            code = d["code"]
            reason = ""
            if self._disconnect and 0 <= _elapsed(self._disconnect[1], ev.ts) <= _DISCONNECT_WAIT_S:
                reason = re.sub(r"^Remote Disconnect - ", "", self._disconnect[0]).split(" (", 1)[0]
            why = _ERRORS_FR.get(code) or reason
            out.append(PresenceNotice("disconnect", ev.ts, self.place if self.phase != "away" else "",
                                      detail=f"erreur {code}" + (f" : {why}" if why else "")))
            self._disconnect = None
            self.phase, self.zone_id, self._pending = "away", 0, None
        elif k == "loading_screen":
            self._loading = True
        elif k == "crash":
            self._crash_at = ev.ts
        elif k == "player_dead" and self._is_player(d["name"]) and self._in_pu is not False:
            if not self._recent_death(ev.ts):
                out += self._die(ev.ts, "vaisseau détruit" if d.get("ship_destroyed") else "")
        elif k == "spawn":
            # Sans écran de chargement depuis l'apparition précédente : réveil après une mort.
            regen = self._in_pu is not False and (not self._loading or self._recent_death(ev.ts))
            if regen and not self._recent_death(ev.ts):
                out += self._die(ev.ts, "")                     # mort à pied : aucune cause écrite
            self._last_spawn, self._loading = ev.ts, False
            self._spawn_kind = "regen" if regen else "respawn"
            if self._pending:
                self._pending[2] = self._spawn_kind
        elif k == "place_zone":
            if d["to"]:
                spawned = bool(self._last_spawn and _elapsed(self._last_spawn, ev.ts) < _RESPAWN_WAIT_S)
                if (not spawned and self.phase == "away" and self._left and self._left[0] == d["to"]
                        and _elapsed(self._left[1], ev.ts) <= _RETURN_WAIT_S):
                    # Retour aussitôt dans la zone quittée (bordure d'un avant-poste) : rien à annoncer,
                    # et la sortie suivante non plus.
                    self.phase, self.zone_id, self._quiet = "arrived", d["to"], True
                elif d["to"] != self.zone_id or self.phase == "away":
                    self._pending = [d["to"], ev.ts, self._spawn_kind if spawned else "arrival"]
                    self.zone_id, self._quiet = d["to"], False
            elif self.phase != "away" and d["from"] == self.zone_id:
                if not self._quiet:
                    out.append(PresenceNotice("departure", ev.ts, self.place, self.system, self.code))
                self._left = (self.zone_id, ev.ts)
                self.phase, self.zone_id = "away", 0
        elif (k == "near_location" and self._pending
              and _elapsed(self._pending[1], ev.ts) <= self._code_wait(known=False)):
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
        elif (k == "ship_leave" and self.phase == "arrived"
              and not (self._crash_at and 0 <= _elapsed(self._crash_at, ev.ts) <= _CRASH_WAIT_S)):
            self.phase = "landed"
            out.append(PresenceNotice("landed", ev.ts, self.place, self.system, self.code))
        return out

    def _code_wait(self, known: bool = True) -> float:
        """Attente maximale du nom du lieu pour l'entrée de zone en cours.

        Zone déjà connue (`known`) : quelques secondes suffisent, le nom est déjà su ; la ligne
        d'inventaire reste acceptée jusqu'au délai normal tant que rien d'autre ne l'a close.
        """
        if known and self._pending and self._pending[0] in self.known_codes:
            return _KNOWN_CODE_WAIT_S
        return _SPAWN_CODE_WAIT_S if self._pending and self._pending[2] != "arrival" else _CODE_WAIT_S

    def _is_player(self, name: str) -> bool:
        """Le nom est celui du joueur ; pseudo inconnu : tout sauf un PNJ (« PU_… », suffixe numérique)."""
        if self.player:
            return name == self.player
        return not (name.startswith("PU_") or re.search(r"_\d{6,}$", name))

    def _recent_death(self, ts: datetime | None) -> bool:
        """Une mort a été annoncée peu avant `ts`."""
        return bool(self._dead_at and 0 <= _elapsed(self._dead_at, ts) <= _DEATH_WAIT_S)

    def _die(self, ts: datetime | None, cause: str) -> list[PresenceNotice]:
        """Mort du joueur : annoncée, il n'est plus nulle part (sans fait « départ »)."""
        self._dead_at = ts
        where = self.place if self.phase != "away" else ""
        self.phase = "away"
        if not self._pending:
            self.zone_id = 0
        return [PresenceNotice("death", ts, where, self.system if where else "", self.code if where else "", cause)]

    def _arrive(self, code: str, ts: datetime | None) -> list[PresenceNotice]:
        """Termine une entrée de zone : lieu nommé (ou inconnu), fait « arrivée » ou « apparition »."""
        _, _, kind = self._pending or (0, None, "arrival")
        self._pending = None
        self._arrived_at = ts
        self.code = code
        self.place = (outpost_label(code) or place_label(code)) if code else ""
        self.system = system_of(code) if code else ""
        self.phase = "arrived" if kind == "arrival" else "landed"      # on réapparaît à pied
        return [PresenceNotice(kind, ts, self.place, self.system, code)]


def _elapsed(a: datetime | None, b: datetime | None) -> float:
    """Secondes de `a` à `b` ; 0 si l'une manque."""
    return (b - a).total_seconds() if a and b else 0.0
