"""Commande /route — itinéraire de navigation entre deux lieux."""
from __future__ import annotations

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error


def _resolve_at(token: str, ctx) -> str:
    """Résout @local → position courante, @dest → destination, sinon renvoie tel quel."""
    t = token.strip()
    if t.startswith("@"):
        key = t[1:].lower()
        if key in ("local", "loc", "ici", "here", "position", "pos"):
            loc = (ctx.player.location or "").strip()
            if not loc:
                return ""   # signale l'absence
            return loc
        if key in ("dest", "destination"):
            dest = (ctx.player.destination or "").strip()
            if not dest:
                return ""
            return dest
        # @NomTerminal classique
        return t[1:]
    return t


@register("route", "itineraire", "itinéraire", "chemin")
def cmd_route(args: list[str], ctx) -> None:
    """Calcule un itinéraire QT entre deux lieux (délègue à /nav route)."""
    if not args:
        _usage(ctx)
        return

    # Résoudre les tokens @local / @dest dans les arguments
    resolved = []
    for a in args:
        r = _resolve_at(a, ctx)
        if a.startswith("@") and r == "":
            # @local ou @dest non défini
            key = a[1:].lower()
            if key in ("local", "loc", "ici", "here", "position", "pos"):
                print_error("Position courante non définie — utilisez /go <lieu> ou @<terminal>")
            else:
                print_error(f"Destination non définie — utilisez /go to <lieu>")
            return
        resolved.append(r)

    # Déléguer à la logique de /nav route
    from uexinfo.cli.commands.nav import _find_route
    _find_route(resolved, ctx)


def _usage(ctx) -> None:
    loc  = ctx.player.location    or "(non définie)"
    dest = ctx.player.destination or "(non définie)"
    console.print(
        f"[{C.LABEL}]/route[/{C.LABEL}]  [{C.DIM}]Itinéraire QT entre deux lieux[/{C.DIM}]\n"
        f"\n"
        f"  [bold]Exemples :[/bold]\n"
        f"  /route @local @dest          Depuis ta position vers ta destination\n"
        f"  /route GrimHEX Port_Tressler Calcule le chemin entre deux terminaux\n"
        f"  /route @local to Area_18     Depuis ta position vers Area 18\n"
        f"\n"
        f"  [bold]Raccourcis :[/bold]\n"
        f"  @local  →  position courante : [{C.UEX}]{loc}[/{C.UEX}]\n"
        f"  @dest   →  destination :       [{C.UEX}]{dest}[/{C.UEX}]\n"
        f"\n"
        f"  [{C.DIM}]Alias : /itineraire  /chemin[/{C.DIM}]"
    )
