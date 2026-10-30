"""Choisir un objet à partir d'une saisie du joueur (décision D11, règle 3).

- un seul candidat sûr (référence `#type:id`, nom exact, code, début ou partie d'un
  seul nom) : accepté ;
- plusieurs candidats aussi proches : liste au joueur ;
- seulement des noms approchants (faute de frappe) : proposition « Vouliez-vous
  dire… ? », jamais appliquée sans son choix.

La position et la destination du joueur se retrouvent par leur identifiant
(`position_terminal`, `destination_terminal`), jamais en relisant leur nom (règle 1).
"""
from __future__ import annotations

from typing import Any

from uexinfo.names import FUZZY, Entity, Resolution, get_index, link, resolve

KIND_LABELS = {
    "system": "système", "planet": "planète", "moon": "lune", "station": "station",
    "city": "ville", "outpost": "avant-poste", "terminal": "terminal",
    "commodity": "commodité", "vehicle": "vaisseau", "node": "lieu",
    "ship": "vaisseau de la flotte",
}


def describe(e: Entity) -> tuple[str, str]:
    """Libellé et précision affichés pour un candidat dans une liste de choix."""
    o = e.obj
    g = lambda a: getattr(o, a, "") or ""  # noqa: E731
    if e.kind == "terminal":
        return e.name, g("star_system_name")
    if e.kind == "commodity":
        return e.name, g("code")
    if e.kind == "vehicle":
        return e.name, g("manufacturer")
    if e.kind == "ship":
        return e.name, f"{o.scu} SCU" if getattr(o, "scu", 0) else ""
    if e.kind == "node":
        return e.name, g("system")
    where = " · ".join(x for x in (g("planet_name"), g("star_system_name")) if x and x != e.name)
    return e.name, f"{KIND_LABELS.get(e.kind, e.kind)}{' · ' + where if where else ''}"


def decide(ctx, r: Resolution, query: str, *, title: str = "", ask: bool = True) -> Any:
    """Objet retenu parmi les correspondances `r` (non vides), selon la règle 3.

    Renvoie None si le joueur annule, ou s'il faudrait lui demander et que `ask`
    est faux (traitement en tâche de fond, où personne ne peut répondre).
    """
    top = r.top
    if len(top) == 1 and top[0].level > FUZZY:
        return top[0].entity.obj
    if not ask:
        return None
    fuzzy = top[0].level == FUZZY
    options = r.matches[:12] if fuzzy else top[:20]
    head = f"Vouliez-vous dire… « {query} » ?" if fuzzy else f"Plusieurs choix pour « {query} »"
    full_title = f"{title} — {head}" if title else head

    from uexinfo.cli.selector import SelectItem, pick
    if callable(getattr(ctx, "select_fn", None)):
        items = [SelectItem(label=lbl, value=m.entity.obj, meta=meta)
                 for m in options for lbl, meta in [describe(m.entity)]]
        chosen = pick(ctx, items, title=full_title, mode="single")
        if chosen:
            return chosen[0].value
        from uexinfo.display.formatter import print_warn
        print_warn("Choix annulé.")
        return None

    # Pas de sélecteur (hors overlay) : liste de liens, un clic désigne l'objet exact
    from uexinfo.display import colors as C
    from uexinfo.display.formatter import console
    console.print(f"[{C.WARNING}]{full_title} :[/{C.WARNING}]")
    for m in options:
        lbl, meta = describe(m.entity)
        extra = f"  [{C.DIM}]{meta}[/{C.DIM}]" if meta else ""
        console.print(f"  [{C.UEX}]{link(m.entity.kind, m.entity.id, lbl)}[/{C.UEX}]{extra}")
    return None


def choose(ctx, query: str, kinds: set[str] | None = None, *, what: str = "",
           title: str = "", min_level: int = FUZZY, prefer_system: str = "",
           ask: bool = True, quiet: bool = False) -> Any:
    """Objet désigné par `query` parmi `kinds`, ou None (introuvable, annulé).

    `what` nomme ce qu'on cherche dans les messages (« Terminal », « Lieu »…) ;
    `quiet` tait le message « introuvable » quand l'appelant essaie autre chose ensuite.
    """
    r = resolve(ctx, query, kinds=kinds, min_level=min_level, prefer_system=prefer_system)
    if not r.matches:
        if not quiet:
            from uexinfo.display.formatter import print_warn
            print_warn(f"{what} introuvable : « {query} »" if what
                       else f"Rien trouvé pour « {query} »")
        return None
    return decide(ctx, r, query, title=title or what, ask=ask)


def display_line(line: str, ctx) -> str:
    """Ligne de commande telle qu'on l'affiche : chaque référence `#type:id` (envoyée par
    un clic) remplacée par le nom de l'objet. La commande, elle, s'exécute sur la référence."""
    import re
    from uexinfo.names.refs import KINDS

    def _name(m) -> str:
        """Nom de l'objet désigné par la référence, ou la référence telle quelle s'il est inconnu."""
        e = get_index(ctx).by_ref(m.group(1), m.group(2))
        return e.name if e is not None else m.group(0)

    return re.sub(rf"#({'|'.join(KINDS)}):(\S+)", _name, line)


# ── Position et destination du joueur : par identifiant ──────────────────────

def terminal_by_id(ctx, tid: int) -> Any:
    """Terminal UEX d'identifiant `tid`, ou None."""
    if not tid:
        return None
    e = get_index(ctx).by_ref("terminal", tid)
    return e.obj if e is not None else None


def _player_terminal(ctx, name_attr: str, id_attr: str) -> Any:
    """Terminal enregistré dans `ctx.player` (position ou destination).

    Un ancien enregistrement sans identifiant est relu une seule fois, et seulement
    si son nom désigne exactement un terminal ; l'identifiant est alors mémorisé.
    """
    player = getattr(ctx, "player", None)
    if player is None:
        return None
    t = terminal_by_id(ctx, getattr(player, id_attr, 0))
    if t is not None:
        return t
    name = (getattr(player, name_attr, "") or "").strip()
    if not name or getattr(player, id_attr, 0):
        return None
    found = get_index(ctx).exact(name, {"terminal"})
    if len(found) != 1:
        return None
    setattr(player, id_attr, found[0].id)
    return found[0].obj


def position_terminal(ctx) -> Any:
    """Terminal de la position du joueur, ou None (position vide, planète, système)."""
    return _player_terminal(ctx, "location", "location_id")


def destination_terminal(ctx) -> Any:
    """Terminal de la destination du joueur, ou None."""
    return _player_terminal(ctx, "destination", "destination_id")
