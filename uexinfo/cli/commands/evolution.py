"""Commande /evolution (alias /scevolution) — changement de version / d'univers SC (D3).

  /evolution          État (versions, surveillance, derniers lieux ajoutés/retirés)
  /evolution oui      L'univers a changé (« je ne sais pas » = oui)
  /evolution non      Rien n'a changé : on garde distances et graphe, fin de surveillance
  /evolution check    Comparer tout de suite les lieux UEX à la référence
"""
from __future__ import annotations

from datetime import datetime

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, section

_YES = {"oui", "yes", "o", "y", "jsp", "nsp"}
_NO = {"non", "no", "n"}
_CHECK = {"check", "verif", "vérif", "compare"}

_CAT_LABEL = {
    "terminals": "terminaux", "space_stations": "stations", "outposts": "avant-postes",
    "cities": "villes", "planets": "planètes", "moons": "lunes", "orbits": "orbites",
    "star_systems": "systèmes",
}


def _store(ctx):
    store = getattr(ctx, "evolution", None)
    if store is None:
        from uexinfo.cache.evolution import EvolutionStore
        store = ctx.evolution = EvolutionStore()
    return store


def run_check(ctx) -> dict | None:
    """Compare les ID UEX du cache statique à la référence ; None si cache vide."""
    from uexinfo.cache.evolution import collect_ids
    ids = collect_ids(ctx.cache)
    if not ids:
        return None
    store = _store(ctx)
    diff = store.check(ids)
    sync_price_cache(ctx)
    return diff


def sync_price_cache(ctx) -> None:
    """Propage version courante / version d'univers au cache des prix."""
    store = getattr(ctx, "evolution", None)
    if store is None:
        return
    ctx._price_cache.current_version = store.current_version
    ctx._price_cache.universe_version = store.universe_version


def _print_diff(diff: dict) -> None:
    for kind, label, color in (("added", "ajoutés", C.SUCCESS), ("removed", "retirés", C.WARNING)):
        for cat, ids in diff.get(kind, {}).items():
            console.print(f"  [{color}]{len(ids)} {_CAT_LABEL.get(cat, cat)} {label}[/{color}]"
                          f"  [{C.DIM}]id {', '.join(map(str, ids[:10]))}"
                          f"{'…' if len(ids) > 10 else ''}[/{C.DIM}]")
    if diff.get("added", {}).get("terminals"):
        console.print(f"  [{C.DIM}]→ /nav populate  pour ajouter les nouveaux terminaux au graphe[/{C.DIM}]")


def _show(ctx) -> None:
    store = _store(ctx)
    st = store.state
    section("Évolution de l'univers")
    console.print(f"  Version détectée     : [{C.LABEL}]{store.current_version or '—'}[/{C.LABEL}]")
    console.print(f"  Univers changé depuis : [{C.LABEL}]{store.universe_version or 'jamais déclaré'}[/{C.LABEL}]")
    if store.pending:
        console.print(f"  [{C.WARNING}]Question en attente pour {store.pending} :"
                      f" /evolution oui | non[/{C.WARNING}]")
    if store.watching():
        console.print(f"  Surveillance         : [{C.SUCCESS}]active[/{C.SUCCESS}]"
                      f" ({store.watch_days_left():.1f} j restants)")
    else:
        console.print(f"  Surveillance         : [{C.DIM}]inactive[/{C.DIM}]")
    if st["last_check_at"]:
        when = datetime.fromtimestamp(st["last_check_at"]).strftime("%d/%m/%Y %H:%M")
        console.print(f"  Dernière comparaison : {when}")
        diff = st["last_diff"]
        if diff["added"] or diff["removed"]:
            _print_diff(diff)
        else:
            console.print(f"  [{C.DIM}]aucun lieu ajouté ou retiré[/{C.DIM}]")


@register("evolution", "scevolution")
def cmd_evolution(args: list[str], ctx) -> None:
    sub = args[0].lower() if args else ""
    store = _store(ctx)
    if not sub:
        _show(ctx)
    elif sub in _YES:
        store.answer(changed=True)
        sync_price_cache(ctx)
        print_ok(f"Univers marqué comme changé (v{store.current_version or '?'}) — "
                 "surveillance 7 jours, distances et conteneurs re-téléchargés à la demande.")
        diff = run_check(ctx)
        if diff:
            _print_diff(diff)
    elif sub in _NO:
        store.answer(changed=False)
        sync_price_cache(ctx)
        print_ok("Univers inchangé — distances et graphe conservés, surveillance arrêtée.")
    elif sub in _CHECK:
        diff = run_check(ctx)
        if diff is None:
            print_error("Cache statique UEX vide — /refresh d'abord.")
        elif diff["added"] or diff["removed"]:
            _print_diff(diff)
        else:
            print_ok("Aucun lieu ajouté ou retiré.")
    else:
        print_error(f"Sous-commande inconnue : {sub}  —  /evolution [oui|non|check]")
