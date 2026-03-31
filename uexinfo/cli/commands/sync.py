"""Commande /sync — resynchronisation forcée des prix d'un terminal.

Invalide le cache local et refetch depuis l'API UEX, puis affiche
ce qui a changé (commodités ajoutées / disparues).

Usage :
  /sync                   Resync le terminal à la position actuelle du joueur
  /sync <lieu>            Resync un terminal par nom ou fuzzy
  /sync <lieu> --quiet    Sans affichage du diff
"""
from __future__ import annotations

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section


def _find_terminal(q: str, ctx):
    """Recherche floue d'un terminal par nom."""
    q_lo = q.lower().replace("_", " ")
    # Exact d'abord
    for t in ctx.cache.terminals:
        if t.name.lower() == q_lo:
            return t
    # Fuzzy via LocationIndex
    if ctx.location_index:
        entries = ctx.location_index.search(q, limit=1, types={"terminal"})
        if entries:
            name = entries[0].name
            for t in ctx.cache.terminals:
                if t.name.lower() == name.lower():
                    return t
    # Sous-chaîne
    for t in ctx.cache.terminals:
        if q_lo in t.name.lower():
            return t
    return None


def _invalidate_terminal(t, ctx) -> None:
    """Supprime toutes les entrées de prix liées à ce terminal dans le cache."""
    keys_to_del = []
    for key in list(ctx._price_cache._mem.keys()):
        if (key == f"t{t.id}"
                or (t.code and key == f"tc_{t.code}")
                or key == f"tl_{t.name.lower()}"
                or key == f"tn_{t.name.lower()}"):
            keys_to_del.append(key)
    for k in keys_to_del:
        del ctx._price_cache._mem[k]
    if keys_to_del:
        ctx._price_cache._dirty = True
        ctx._price_cache.flush()


def _fetch_fresh(t, ctx) -> list[dict]:
    """Force le fetch depuis l'API (cache vidé avant)."""
    from uexinfo.api.uex_client import UEXClient, UEXError
    client = UEXClient()
    try:
        import time
        data = client.get_prices(id_terminal=t.id)
        if not data and t.code:
            data = client.get_prices(terminal_code=t.code)
        if not data:
            loc_q = t.name.lower().split(" - ")[-1].strip()
            data = client.get_prices(terminal_name=loc_q)
        key = f"t{t.id}"
        ctx._price_cache[key] = (time.time(), data)
        return data
    except UEXError as e:
        print_error(f"API : {e}")
        return []


@register("sync", "resync")
def cmd_sync(args: list[str], ctx) -> None:
    """Resynchronise les prix d'un terminal (supprime le cache local et refetch)."""
    quiet = "--quiet" in args
    args = [a for a in args if a != "--quiet"]

    # Déterminer le terminal cible
    if args:
        q = " ".join(args).replace("_", " ")
        t = _find_terminal(q, ctx)
        if t is None:
            print_error(f"Terminal introuvable : {q!r}")
            return
    else:
        # Utiliser la position du joueur
        pos = getattr(ctx.player, "location", None) if ctx.player else None
        if not pos:
            print_error("Position inconnue — précisez un terminal : /sync <lieu>")
            return
        t = _find_terminal(pos, ctx)
        if t is None:
            print_error(f"Terminal introuvable pour la position : {pos!r}")
            return

    # Récupérer l'ancien état (avant invalidation)
    import time as _time
    cached_before = ctx._price_cache.get(f"t{t.id}")
    old_commodities: set[str] = set()
    if cached_before:
        _ts, old_data = cached_before
        old_commodities = {r.get("commodity_name", "") for r in old_data if r.get("commodity_name")}

    section(f"Sync — {t.name}")
    console.print(f"  [{C.DIM}]Invalidation du cache local…[/{C.DIM}]")
    _invalidate_terminal(t, ctx)

    console.print(f"  [{C.DIM}]Fetch API UEX…[/{C.DIM}]")
    new_data = _fetch_fresh(t, ctx)

    if not new_data:
        print_warn("Aucune donnée reçue depuis l'API.")
        return

    new_commodities = {r.get("commodity_name", "") for r in new_data if r.get("commodity_name")}

    print_ok(f"{len(new_commodities)} commodité(s) récupérée(s) pour {t.name}")

    if not quiet and old_commodities:
        added   = new_commodities - old_commodities
        removed = old_commodities - new_commodities
        if added:
            console.print(f"  [{C.PROFIT}]+ Nouvelles :[/{C.PROFIT}] " +
                          ", ".join(sorted(added)))
        if removed:
            console.print(f"  [{C.LOSS}]- Disparues :[/{C.LOSS}]  " +
                          ", ".join(sorted(removed)))
        if not added and not removed:
            console.print(f"  [{C.DIM}]Aucun changement de commodités.[/{C.DIM}]")
    elif not quiet and not old_commodities:
        console.print(f"  [{C.DIM}](Pas de données précédentes pour comparaison)[/{C.DIM}]")
