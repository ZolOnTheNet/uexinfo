"""Commande /trade — recherche de prix d'achat et de vente."""
from __future__ import annotations

import re

from uexinfo.cli.commands import register
from uexinfo.cli.commands.info import (
    _BUY_STATUS_COLOR,
    _SELL_STATUS_COLOR,
    _abbrev_name,
    _comm_code,
    _commodity_prices,
    _ensure_comm_codes,
    _dist_label,
    _fetch_container_sizes,
    _fetch_route_distances,
    _find_commodity,
    _find_terminal,
    _find_terminal_candidates,
    _fmt_date,
    _loc,
    _multi_col_table,
    _notable_scu,
    _player_cargo,
    _player_system,
    _price_short,
    _scu,
    _stock_bar,
    _terminal_prices,
)
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_warn, section

_SUBS  = {"buy", "sell", "best", "compare"}
_FROMS = {"from", "de"}
_TOS   = {"to", "à"}

_TERM_MAX     = 14  # largeur max du nom seul (même système)
_TERM_MAX_SYS = 20  # largeur max avec préfixe système


@register("trade", "t")
def cmd_trade(args: list[str], ctx) -> None:
    if not args:
        _trade_bilan(ctx)
        return
    sub = args[0].lower()
    if sub in _FROMS or sub in _TOS:
        _trade_bilan_override(args, ctx)
        return
    if sub == "sctrade":
        _trade_sctrade(args[1:], ctx)
        return
    if sub not in _SUBS:
        _trade_buy(args, ctx)
        console.print()
        _trade_sell(args, ctx)
        return
    rest = args[1:]
    if sub == "buy":
        _trade_buy(rest, ctx)
    elif sub == "sell":
        _trade_sell(rest, ctx)
    elif sub in ("best", "compare"):
        print_warn(f"/trade {sub} — disponible en Phase 3 (routes optimales).")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_active_buy(r: dict) -> bool:
    return bool(r.get("price_buy")) or int(r.get("status_buy") or 0) >= 1


def _is_active_sell(r: dict) -> bool:
    return bool(r.get("price_sell")) or int(r.get("status_sell") or 0) >= 1


def _sort_key_sys(r: dict, player_sys: str, price_field: str, reverse: bool) -> tuple:
    own = 0 if (r.get("star_system_name") or "").lower() == player_sys else 1
    price = r.get(price_field) or 0
    return (own, -price if reverse else price)


def _term_entry(terminal_name: str, star_system: str, player_sys: str,
                scu_lo, scu_hi, status, buy: bool) -> str:
    """Nom de terminal coloré selon le statut de stock.
    Préfixe 'Sys.' si hors du système du joueur.
    Plage SCU ajoutée entre parenthèses seulement si non-standard.
    """
    loc = _loc(terminal_name)
    sys_other = bool(star_system and star_system.lower() != player_sys)
    display = f"{star_system}.{loc}" if sys_other else loc
    short = _abbrev_name(display, maxlen=_TERM_MAX_SYS if sys_other else _TERM_MAX)

    s = int(status or 0)
    color = (_BUY_STATUS_COLOR if buy else _SELL_STATUS_COLOR).get(s, C.DIM)

    notable = _notable_scu(_scu(scu_lo, scu_hi))
    suffix = f" ({notable})" if notable else ""
    return f"[{color}]{short}[/{color}]{suffix}"


# ── /trade buy ────────────────────────────────────────────────────────────────

def _trade_buy(args: list[str], ctx) -> None:
    query = " ".join(args).replace("_", " ")
    if not query:
        print_warn("Usage : /trade buy <commodité>")
        return

    c = _find_commodity(query, ctx)
    if not c:
        print_error(f"Commodité introuvable : {query}")
        return

    rows = _commodity_prices(c.id, ctx)
    if not rows:
        print_warn("Aucune donnée de prix disponible.")
        return

    buy_rows = [r for r in rows if _is_active_buy(r)]
    if not buy_rows:
        console.print(f"[{C.DIM}]Aucun terminal ne vend {c.name}.[/{C.DIM}]")
        return

    player_sys = _player_system(ctx)
    buy_rows.sort(key=lambda r: _sort_key_sys(r, player_sys, "price_buy", reverse=False))

    flags = "[red]illégal[/red]  " if c.is_illegal else ""
    sys_note = f"  [{C.DIM}]· {player_sys} en tête[/{C.DIM}]" if player_sys else ""
    section(f"Acheter — {flags}{c.name}  [{c.code}]{sys_note}")
    console.print(f"[italic {C.DIM}]UEX Corp · données communauté · non confirmées[/italic {C.DIM}]")

    term_w = getattr(console, "width", None) or 100
    n_cols = max(1, min(4, term_w // 32))

    entries = [
        (_term_entry(r.get("terminal_name") or "?", r.get("star_system_name") or "",
                     player_sys, r.get("scu_buy"), r.get("scu_buy_max"),
                     r.get("status_buy"), buy=True),
         _price_short(r.get("price_buy")))
        for r in buy_rows[:40]
    ]
    console.print(_multi_col_table(
        entries, ("Terminal (stock)", "Achat"), n_cols,
        f"italic {C.NEUTRAL}", f"italic {C.UEX}",
    ))
    console.print(f"\n[{C.DIM}]{len(buy_rows)} terminaux · prix croissant[/{C.DIM}]")


# ── /trade sell ───────────────────────────────────────────────────────────────

def _trade_sell(args: list[str], ctx) -> None:
    query = " ".join(args).replace("_", " ")
    if not query:
        print_warn("Usage : /trade sell <commodité>")
        return

    c = _find_commodity(query, ctx)
    if not c:
        print_error(f"Commodité introuvable : {query}")
        return

    rows = _commodity_prices(c.id, ctx)
    if not rows:
        print_warn("Aucune donnée de prix disponible.")
        return

    sell_rows = [r for r in rows if _is_active_sell(r)]
    if not sell_rows:
        console.print(f"[{C.DIM}]Aucun terminal n'achète {c.name}.[/{C.DIM}]")
        return

    player_sys = _player_system(ctx)
    sell_rows.sort(key=lambda r: _sort_key_sys(r, player_sys, "price_sell", reverse=True))

    flags = "[red]illégal[/red]  " if c.is_illegal else ""
    sys_note = f"  [{C.DIM}]· {player_sys} en tête[/{C.DIM}]" if player_sys else ""
    section(f"Vendre — {flags}{c.name}  [{c.code}]{sys_note}")
    console.print(f"[italic {C.DIM}]UEX Corp · données communauté · non confirmées[/italic {C.DIM}]")

    term_w = getattr(console, "width", None) or 100
    n_cols = max(1, min(4, term_w // 32))

    entries = [
        (_term_entry(r.get("terminal_name") or "?", r.get("star_system_name") or "",
                     player_sys, r.get("scu_sell"), r.get("scu_sell_max"),
                     r.get("status_sell"), buy=False),
         _price_short(r.get("price_sell")))
        for r in sell_rows[:40]
    ]
    console.print(_multi_col_table(
        entries, ("Terminal (stock)", "Vente"), n_cols,
        f"italic {C.NEUTRAL}", f"italic {C.PROFIT}",
    ))
    console.print(f"\n[{C.DIM}]{len(sell_rows)} terminaux · prix décroissant[/{C.DIM}]")


# ── /trade from X to Y ────────────────────────────────────────────────────────

def _parse_from_to(args: list[str]) -> tuple[str, str]:
    """Extrait les parties 'from ...' et 'to ...' depuis une liste d'args."""
    from_parts: list[str] = []
    to_parts:   list[str] = []
    current = None
    for a in args:
        lo = a.lower()
        if lo in _FROMS:
            current = "from"
        elif lo in _TOS:
            current = "to"
        elif current == "from":
            from_parts.append(a)
        elif current == "to":
            to_parts.append(a)
    return " ".join(from_parts), " ".join(to_parts)


def _trade_bilan_override(args: list[str], ctx) -> None:
    from_str, to_str = _parse_from_to(args)
    _trade_bilan(ctx, origin_override=from_str, dest_override=to_str)


# ── /trade (bilan route) ───────────────────────────────────────────────────────

def _plain_len(s: str) -> int:
    """Longueur visible (balises Rich retirées)."""
    return len(re.sub(r'\[/?[^\]]*\]', '', s))


def _ship_container_sizes(ctx) -> list[int]:
    """Tailles de containers acceptées par le vaisseau actif."""
    ship_name = (ctx.player.active_ship or "").lower()
    if not ship_name:
        return []
    for v in (ctx.cache.vehicles or []):
        if v.name_full.lower() == ship_name or v.name.lower() == ship_name:
            if v.container_sizes:
                return sorted(
                    int(x.strip()) for x in v.container_sizes.split(",")
                    if x.strip().isdigit()
                )
    return []


def _intersect_sizes(sets: list[set[int]], ship_cargo: int) -> list[int]:
    """Intersecte les sets non-vides ; filtre par ship_cargo. Décroissant."""
    non_empty = [s for s in sets if s]
    if not non_empty:
        return []
    common = non_empty[0].copy()
    for s in non_empty[1:]:
        common &= s
    return sorted((x for x in common if 0 < x <= ship_cargo), reverse=True)


def _pack(qty: int, sizes: list[int]) -> str:
    """Calcule le packing optimal. Ex: 256 SCU avec [8,32] → '8×32'."""
    remaining = qty
    parts = []
    for size in sorted(sizes, reverse=True):
        if remaining <= 0:
            break
        n = remaining // size
        if n > 0:
            parts.append(f"{n}×{size}{C.SCU}")
            remaining -= n * size
    return f"[ {' '.join(parts)} ]" if parts else f"[ {qty}×1{C.SCU} ]"


def _pack_remainder(qty: int, sizes: list[int]) -> int:
    """SCU restants après packing (ne rentrent dans aucun container disponible)."""
    remaining = qty
    for size in sorted(sizes, reverse=True):
        remaining -= (remaining // size) * size
    return remaining


def _ship_slot_grid(ctx) -> dict[int, int]:
    """Grille cargo du vaisseau actif {taille_slot: nb_slots} via cargo_grid_manager."""
    ship_name = (ctx.player.active_ship or "").strip()
    if not ship_name:
        return {}
    grid = ctx.cargo_grid_manager.get_grid(ship_name)
    return dict(grid) if grid else {}


def _pack_grid(qty: int, slot_grid: dict[int, int], avail_sizes: set[int]) -> dict[int, int]:
    """
    Emballe qty SCU en respectant la grille cargo {taille_slot: nb_slots}.

    Règle : un slot de taille S peut contenir des containers de taille <= S.
    Remplit chaque slot greedy du plus grand au plus petit container.
    avail_sizes vide → toutes les tailles <= slot_size sont tentées.
    Retourne {container_size: count}.
    """
    result: dict[int, int] = {}
    remaining = qty

    for slot_size in sorted(slot_grid.keys(), reverse=True):
        n_slots = slot_grid[slot_size]
        if remaining <= 0:
            break

        # Tailles disponibles pour ce slot (acceptées aux terminaux ET ≤ slot_size)
        if avail_sizes:
            slot_avail = sorted([s for s in avail_sizes if s <= slot_size], reverse=True)
        else:
            # Aucune donnée terminaux → on essaie toutes les tailles standard ≤ slot
            _STD = [32, 24, 16, 8, 4, 2, 1]
            slot_avail = [s for s in _STD if s <= slot_size]

        if not slot_avail:
            continue

        for _ in range(n_slots):
            if remaining <= 0:
                break
            slot_remaining = slot_size
            for container_size in slot_avail:
                if remaining <= 0 or slot_remaining < container_size:
                    break
                n = min(slot_remaining // container_size, remaining // container_size)
                if n > 0:
                    result[container_size] = result.get(container_size, 0) + n
                    remaining -= n * container_size
                    slot_remaining -= n * container_size

    return result


def _fmt_pack(pack_map: dict[int, int]) -> str:
    """Formate {32: 8, 16: 2} → '[ 8×32□  2×16□ ]'."""
    inner = "  ".join(
        f"{count}×{size}{C.SCU}"
        for size, count in sorted(pack_map.items(), reverse=True)
        if count > 0
    )
    return f"[ {inner} ]" if inner else ""


def _print_trade_entry(d: dict) -> None:
    """Affichage freeform une ou deux lignes par commodité."""
    profit = d["profit"]
    p_color = C.PROFIT if profit > 0 else (C.LOSS if profit < 0 else C.DIM)
    p_sign = "+" if profit > 0 else ""

    buy_bar  = _stock_bar(d["status_buy"],  sell=False)
    sell_bar = _stock_bar(d["status_sell"], sell=True)
    stock_flow = f"{buy_bar} [dim]→[/dim] {sell_bar}"

    dist_gm = d.get("dest_dist")
    ppg = ""
    if dist_gm and dist_gm > 0:
        ppg = f"  [{p_color}]{p_sign}{_price_short(profit / dist_gm)}/Gm[/{p_color}]"

    qty_str = str(d["qty"])
    if d["qty_unsold"]:
        qty_str = f"{d['qty_sell']}/{d['qty']}"

    dest_sz = d.get("dest_sizes") or "—"
    orig_sz = d.get("orig_sizes") or "—"

    dist_part = f"  {d['dist_str']}" if d.get("dist_str") else ""

    player     = d.get("_player", False)
    cc = d.get("code", "")
    name_pfx   = f"★ {_abbrev_name(d['name'], 20, code=cc)}" if player else _abbrev_name(d['name'], 22, code=cc)
    buy_color  = f"bold {C.UEX}" if player else C.UEX
    sell_color = f"bold {C.PROFIT}" if player else C.PROFIT

    part1 = (
        f"[bold {C.NEUTRAL}]▶ {name_pfx}[/bold {C.NEUTRAL}]"
        f"  [{C.DIM}]A:[/{C.DIM}][{buy_color}]{_price_short(d['price_buy'])}[/{buy_color}] ->"
        f"  [{C.DIM}]V:[/{C.DIM}][{sell_color}]{_price_short(d['price_sell'])}[/{sell_color}]"
        f"  [{C.DIM}]{d['date']}[/{C.DIM}]"
        f"  {stock_flow}"
        f"  {qty_str} {C.SCU}"
        + (f"  [{C.DIM}]orig:[/{C.DIM}] {orig_sz}" if orig_sz not in ("—", "", None) else "")
        + dist_part
        + (f"  [{C.DIM}]dest:[/{C.DIM}] {dest_sz}" if dest_sz not in ("—", "", None) else "")
    )

    rest = f" [{C.DIM}]· {d['remainder']} restant[/{C.DIM}]" if d["remainder"] else ""
    roi_str = ""
    roi = d.get("roi")
    if roi is not None:
        r_sign = "+" if roi >= 0 else ""
        r_color = C.PROFIT if roi > 5 else (C.LOSS if roi < 0 else C.NEUTRAL)
        roi_str = f"  ROI:[{r_color}]{r_sign}{roi:.0f}%[/{r_color}]"
    risk = d.get("risk", 0)
    if risk <= 15:
        risk_str = f"  [{C.PROFIT}]⚠{risk}%[/{C.PROFIT}]"
    elif risk <= 45:
        risk_str = f"  [{C.WARNING}]⚠{risk}%[/{C.WARNING}]"
    else:
        risk_str = f"  [{C.LOSS}]⚠{risk}%[/{C.LOSS}]"
    part2 = (
        f"[{C.DIM}]{d['packing']}[/{C.DIM}]{rest}"
        f"  A_Tot: [{C.UEX}]{_price_short(d['total_buy'])}[/{C.UEX}]"
        f"  V_Tot:[{C.PROFIT}]{_price_short(d['total_sell'])}[/{C.PROFIT}]"
        f"  Gain:[{p_color}]{p_sign}{_price_short(profit)}[/{p_color}]"
        + roi_str + risk_str + ppg
    )

    w = getattr(console, "width", 120) or 120
    if _plain_len(part1) + _plain_len(part2) + 4 <= w:
        console.print(part1 + "  ·  " + part2)
    else:
        console.print(part1)
        console.print("  " + part2)


def _trade_bilan(ctx, origin_override: str = "", dest_override: str = "") -> None:
    """Bilan achat/vente entre position joueur et destination."""
    origin_loc = origin_override.strip() or (ctx.player.location or "").strip()
    dest_loc   = dest_override.strip()   or (ctx.player.destination or "").strip()

    if not origin_loc:
        print_warn("Position non définie — utilisez @lieu pour vous positionner.")
        return
    if not dest_loc:
        print_warn("Destination non définie — utilisez /go <terminal>.")
        return

    origin = _find_terminal(origin_loc, ctx)
    if not origin:
        print_error(f"Terminal d'origine introuvable : {origin_loc}")
        return

    # Désambigüation origine
    origin_candidates = _find_terminal_candidates(origin_loc, ctx)
    if len(origin_candidates) > 1 and _loc(origin.name).lower() != origin_loc.lower():
        console.print(
            f"[{C.WARNING}]Plusieurs terminaux correspondent à «{origin_loc}» — "
            f"précisez l'origine :[/{C.WARNING}]"
        )
        for t in origin_candidates[:20]:
            sys_tag = f"  [{C.DIM}]{t.star_system_name}[/{C.DIM}]" if t.star_system_name else ""
            console.print(f"  [cyan]{_loc(t.name)}[/cyan]{sys_tag}")
        return

    dest = _find_terminal(dest_loc, ctx)
    if not dest:
        print_error(f"Terminal de destination introuvable : {dest_loc}")
        return

    # Désambigüation : si la query correspond à plusieurs stations différentes, afficher la liste
    dest_candidates = _find_terminal_candidates(dest_loc, ctx)
    if len(dest_candidates) > 1 and _loc(dest.name).lower() != dest_loc.lower():
        console.print(
            f"[{C.WARNING}]Plusieurs terminaux correspondent à «{dest_loc}» — "
            f"précisez la destination :[/{C.WARNING}]"
        )
        for t in dest_candidates[:20]:
            sys_tag = f"  [{C.DIM}]{t.star_system_name}[/{C.DIM}]" if t.star_system_name else ""
            console.print(f"  [cyan]{_loc(t.name)}[/cyan]{sys_tag}")
        return

    ship_cargo = _player_cargo(ctx)
    if ship_cargo == 0:
        print_warn(f"Vaisseau actif non défini ou cargo = 0 {C.SCU}. Utilisez /ship set <nom>.")
        return

    origin_rows = _terminal_prices(origin, ctx)
    dest_rows   = _terminal_prices(dest, ctx)

    buy_rows = [r for r in origin_rows if r.get("price_buy")]
    dest_sell_map = {
        (r.get("commodity_name") or "").lower(): r
        for r in dest_rows if r.get("price_sell")
    }

    dist_map   = _fetch_route_distances(origin.id, ctx) if origin.id else {}
    player_sys = _player_system(ctx)
    dest_name_lo = _loc(dest.name).lower()
    dest_dist  = dist_map.get(dest.name.lower()) or dist_map.get(dest_name_lo)
    # Afficher la distance en Gm (même si "local") — utile pour planifier le trajet
    if dest_dist and dest_dist > 0:
        dist_str = f"{dest_dist:.1f}Gm" if dest_dist >= 1 else f"{dest_dist*1000:.0f}Mm"
    else:
        dist_str = _dist_label(dest.name, dest.star_system_name, player_sys, dist_map)
        if re.sub(r'\[/?[^\]]*\]', '', dist_str).strip() == "local":
            dist_str = ""

    stock_mult = {1: 0, 2: 0.2, 3: 0.4, 4: 0.6, 5: 0.8, 7: 1.0}
    inv_mult   = {1: 1.0, 2: 0.8, 3: 0.6, 4: 0.4, 5: 0.2, 7: 0}

    orig_lo      = origin.name.lower()
    orig_loc_lo  = _loc(origin.name).lower()
    ship_grid    = _ship_slot_grid(ctx)          # {slot_size: nb_slots} ou {}
    ship_szs     = set(_ship_container_sizes(ctx))  # fallback si pas de grille

    _STD_SIZES = [32, 24, 16, 8, 4, 2, 1]

    def _ps(raw: str) -> set[int]:
        return (
            {int(x) for x in raw.split("/") if x.strip().isdigit()}
            if raw and raw != "—" else set()
        )

    def _term_fallback(max_scu: int) -> set[int]:
        """Tailles inférées depuis max_container_size quand les routes API sont absentes.
        Convention SC : grand terminal (max>=8) → plage 8-max ; petit → 1-max.
        Ex: max=32 → {8,16,24,32}  |  max=4 → {1,2,4}  |  max=8 → {8}
        """
        if max_scu <= 0:
            return set()
        floor = 8 if max_scu >= 8 else 1
        return {s for s in _STD_SIZES if floor <= s <= max_scu}

    def _range(sizes: set[int], approx: bool = False) -> str:
        """Convertit un ensemble de tailles en notation range SC.
        {8,16,24,32} → '8-32'  |  {1,2,4} → '1-4'  |  {8} → '8'
        approx=True ajoute '□' pour indiquer une valeur inférée.
        """
        if not sizes:
            return "—"
        lo, hi = min(sizes), max(sizes)
        r = f"{lo}-{hi}" if lo != hi else str(lo)
        return r + C.SCU if approx else r

    def _fmt_szs(raw: str, fb: set[int]) -> str:
        if raw and raw != "—":
            # Convertir la liste slash de l'API en notation range
            parts = {int(x) for x in raw.split("/") if x.strip().isdigit()}
            return _range(parts)
        if fb:
            return _range(fb, approx=True)
        return "—"

    # Fallback terminal à partir du max_container_size (utilisé si routes API vide)
    orig_term_fb = _term_fallback(origin.max_container_size)
    dest_term_fb = _term_fallback(dest.max_container_size)

    _ensure_comm_codes(ctx)
    entries = []
    for r in buy_rows:
        name    = r.get("commodity_name", "?")
        name_lo = name.lower()
        if name_lo not in dest_sell_map:
            continue

        dest_row    = dest_sell_map[name_lo]
        id_comm     = int(r.get("id_commodity") or 0)
        scu_min     = int(r.get("scu_buy") or 0)
        scu_max     = int(r.get("scu_buy_max") or scu_min)
        price_buy   = float(r.get("price_buy") or 0)
        status_buy  = int(r.get("status_buy") or 0)
        date_buy    = _fmt_date(r.get("date_modified"))

        price_sell  = float(dest_row.get("price_sell") or 0)
        status_sell = int(dest_row.get("status_sell") or 0)

        qty = int(ship_cargo * stock_mult.get(status_buy, 0.5))
        if qty == 0:
            qty = ship_cargo

        qty_sell   = int(qty * inv_mult.get(status_sell, 0.5))
        qty_unsold = qty - qty_sell

        total_buy  = qty * price_buy
        total_sell = qty * price_sell      # optimiste (tout vendu)
        profit     = total_sell - total_buy

        # Risque = saturation destination (70%) + ancienneté données (30%)
        import time as _time
        sat_risk  = qty_unsold / qty if qty > 0 else 0
        dest_ts   = dest_row.get("date_modified") or 0
        age_hours = (_time.time() - dest_ts) / 3600 if dest_ts else 24
        age_risk  = min(1.0, age_hours / 12)
        risk_pct  = int((sat_risk * 0.7 + age_risk * 0.3) * 100)

        container_map = _fetch_container_sizes(id_comm, ctx)
        orig_raw  = container_map.get(orig_lo) or container_map.get(orig_loc_lo) or "—"
        dest_raw  = (container_map.get(dest.name.lower())
                     or container_map.get(dest_name_lo) or "—")

        orig_szs = _ps(orig_raw)
        dest_szs = _ps(dest_raw)
        # Intersection des tailles terminaux (sets non-vides seulement)
        term_sets = [s for s in [orig_szs, dest_szs] if s]
        if term_sets:
            term_szs: set[int] = term_sets[0].copy()
            for s in term_sets[1:]:
                term_szs &= s
        else:
            # Routes API vide → fallback max_container_size
            fb_sets = [s for s in [orig_term_fb, dest_term_fb] if s]
            if fb_sets:
                term_szs = fb_sets[0].copy()
                for s in fb_sets[1:]:
                    term_szs &= s
            else:
                term_szs = set()

        if ship_grid:
            pack_map  = _pack_grid(qty, ship_grid, term_szs)
            loaded    = sum(sz * cnt for sz, cnt in pack_map.items())
            packing   = _fmt_pack(pack_map) if pack_map else f"[ {qty}×1{C.SCU} ]"
            remainder = qty - loaded
        else:
            # Fallback : pas de grille connue → algo simple par liste de tailles
            sizes_list = _intersect_sizes([orig_szs, dest_szs, ship_szs], ship_cargo)
            packing    = _pack(qty, sizes_list) if sizes_list else f"[ {qty}×1{C.SCU} ]"
            remainder  = _pack_remainder(qty, sizes_list) if sizes_list else 0

        roi = (price_sell - price_buy) / price_buy * 100 if price_buy else None
        entries.append({
            "name": name, "code": _comm_code(name, id_comm),
            "price_buy": price_buy, "price_sell": price_sell,
            "date": date_buy,
            "status_buy": status_buy, "status_sell": status_sell,
            "qty": qty, "qty_sell": qty_sell, "qty_unsold": qty_unsold,
            "scu_origin": _scu(scu_min, scu_max),
            "dest_sizes": _fmt_szs(dest_raw, dest_term_fb),
            "orig_sizes": _fmt_szs(orig_raw, orig_term_fb),
            "packing": packing, "remainder": remainder,
            "total_buy": total_buy, "total_sell": total_sell,
            "profit": profit, "roi": roi, "risk": risk_pct,
            "dest_dist": dest_dist, "dist_str": dist_str,
        })

    if not entries:
        console.print(
            f"[{C.WARNING}]Aucune commodité commune entre "
            f"{_loc(origin.name)} et {_loc(dest.name)}.[/{C.WARNING}]"
        )
        return

    entries.sort(key=lambda d: -(d["roi"] if d["roi"] is not None else -1e9))

    section(f"Trade — {_loc(origin.name)} → {_loc(dest.name)}")
    dist_note = f"  ·  distance : {dist_str}" if dist_str else ""
    console.print(
        f"[{C.DIM}]Cargo : {ship_cargo} {C.SCU}  ·  {len(entries)} commodité(s){dist_note}[/{C.DIM}]"
    )
    console.print(
        f"[{C.DIM}]stock achat :[/{C.DIM}]"
        f"  [red]○○○○[/red][{C.DIM}] rupture[/{C.DIM}]"
        f"  [orange1]●○○○[/orange1][{C.DIM}] bas[/{C.DIM}]"
        f"  [yellow]●●○○[/yellow][{C.DIM}] moyen[/{C.DIM}]"
        f"  [green]●●●○[/green][{C.DIM}] haut[/{C.DIM}]"
        f"  [green]●●●●[/green][{C.DIM}] abondant[/{C.DIM}]"
    )
    console.print()

    for d in entries:
        _print_trade_entry(d)

    # Stocker les entrées pour le panneau "Choisir" de l'overlay
    ctx.last_trade_entries = {
        "origin":  _loc(origin.name),
        "dest":    _loc(dest.name),
        "entries": [
            {
                "idx":        i,
                "name":       d["name"],
                "profit":     int(d["profit"]),
                "qty":        d["qty"],
                "packing":    re.sub(r'\[/?[^\]]*\]', '', d["packing"]).strip(),
                "price_buy":  int(d["price_buy"]),
                "price_sell": int(d["price_sell"]),
            }
            for i, d in enumerate(entries)
        ],
    }


# ── /trade sctrade ─────────────────────────────────────────────────────────────

def _trade_sctrade(args: list[str], ctx) -> None:
    """/trade sctrade [--from <loc>] [--to <dest>] [--ship <ship>] [--budget <N>]
                      [--stops <N>] [--same-system|--ss]

    Utilise sc-trade.tools pour trouver les meilleures routes.
    Token requis pour le calcul de routes : /config sctrade token <token>
    Sans token : affiche les données communauté disponibles.

    Auto-remplissage : origin ← position joueur, dest ← destination joueur.
    Si origin == dest après auto-remplissage, dest est effacée (même lieu = inutile).
    --same-system / --ss : restreindre les routes au système du joueur.
    """
    from uexinfo.api.sctrade_client import SCTradeClient, SCTradeError, SCTradeAuthError
    from uexinfo.display.formatter import section

    sct_cfg = ctx.cfg.get("sctrade", {})
    if not sct_cfg.get("enabled", True):
        print_warn("sc-trade.tools désactivé — /config sctrade on")
        return

    token = sct_cfg.get("token", "")
    client = SCTradeClient(token=token)

    # ── Parsing des arguments ─────────────────────────────────────────────────
    origin      = ""
    ship_name   = ""
    budget      = 0
    max_stops   = 3
    dest        = ""
    same_system = False
    _dest_explicit = False   # --to passé explicitement → pas d'effacement auto

    i = 0
    while i < len(args):
        a = args[i].lower()
        if a in ("--from", "-f") and i + 1 < len(args):
            origin = args[i + 1].replace("_", " "); i += 2
        elif a in ("--ship", "-s") and i + 1 < len(args):
            ship_name = args[i + 1]; i += 2
        elif a in ("--budget", "-b") and i + 1 < len(args):
            budget = int(args[i + 1].replace(" ", "").replace("k", "000").replace("K", "000")); i += 2
        elif a in ("--stops", "-n") and i + 1 < len(args):
            max_stops = int(args[i + 1]); i += 2
        elif a in ("--to", "-t") and i + 1 < len(args):
            dest = args[i + 1].replace("_", " "); _dest_explicit = True; i += 2
        elif a in ("--same-system", "--ss", "--same", "-ss"):
            same_system = True; i += 1
        else:
            i += 1

    # ── Auto-remplissage depuis le joueur ─────────────────────────────────────
    if not origin:
        origin = (ctx.player.location or "").strip().replace("_", " ")

    if not _dest_explicit:
        _auto = (ctx.player.destination or "").strip().replace("_", " ")
        if _auto:
            # Destination auto : si elle est identique à l'origin, inutile de la garder
            if _auto.lower() != origin.lower():
                dest = _auto
            # sinon dest reste vide (pas de boucle sur soi-même)

    # Si --to passé manuellement et == origin → effacer dest (c'est dest qui "venait de" l'autre)
    if _dest_explicit and dest and dest.lower() == origin.lower():
        dest = ""

    if not ship_name:
        ship_name = getattr(ctx.player, "active_ship", "") or ctx.cfg.get("player", {}).get("active_ship", "")
    if not budget:
        cargo = _player_cargo(ctx)
        budget = max(10_000, cargo * 1_000)

    cargo_scu  = _player_cargo(ctx) or 32
    player_sys = _player_system(ctx) or ""

    dest_label = f"  →  [{C.UEX}]{dest}[/{C.UEX}]" if dest else ""
    ss_label   = f"  [{C.DIM}](système : {player_sys})[/{C.DIM}]" if same_system and player_sys else ""
    section(f"Routes sc-trade.tools{dest_label}{ss_label}  [{C.DIM}]{ship_name or '?'}  {budget:,} aUEC  {cargo_scu} SCU[/{C.DIM}]")

    if client.has_token:
        # Route via API serveur (token Patreon)
        try:
            kw: dict = dict(
                ship        = ship_name or "Freelancer",
                investment  = budget,
                max_cargo_scu = cargo_scu,
                max_stops   = max_stops,
                origin      = origin,
            )
            if same_system and player_sys:
                kw["star_system"] = player_sys
            if dest:
                routes = client.itinerary(destination=dest, **kw)
            else:
                routes = client.trades(**kw)
        except SCTradeAuthError as e:
            print_error(str(e))
            return
        except SCTradeError as e:
            print_error(str(e))
            return
        _display_sctrade_routes(routes)
    else:
        # Calcul local depuis les listings publics
        if dest:
            console.print(f"[{C.WARNING}]Itinéraire origin→dest nécessite un token Patreon sc-trade.tools.[/{C.WARNING}]")
            console.print(f"[{C.DIM}]/config sctrade token <token>[/{C.DIM}]")
            return
        console.print(f"[{C.DIM}]Chargement des données communauté sc-trade.tools…[/{C.DIM}]")
        import time
        CACHE_KEY = "sct_listings"
        TTL = 15 * 60  # 15 minutes

        cached = ctx._price_cache.get(CACHE_KEY)
        if cached and (time.time() - cached[0]) < TTL:
            listings = cached[1]
        else:
            try:
                listings = client.crowdsource_listings(max_pages=6)
            except SCTradeError as e:
                print_error(str(e))
                return
            ctx._price_cache[CACHE_KEY] = (time.time(), listings)

        # Filtrer par système si --same-system
        if same_system and player_sys:
            sys_lower = player_sys.lower()
            listings = [l for l in listings if sys_lower in l.get("location", "").lower()]

        routes = _compute_routes_from_listings(
            listings, budget=budget, cargo_scu=cargo_scu,
            origin=origin, same_system=same_system, player_sys=player_sys,
        )
        _display_sctrade_routes(routes)
        console.print(
            f"[{C.DIM}]Calcul local · {len(listings)} enregistrements · "
            f"Token Patreon = routes optimisées côté serveur[/{C.DIM}]"
        )


def _display_sctrade_routes(routes: list[dict]) -> None:
    """Affiche un tableau de routes sc-trade.tools (format token ou local)."""
    from rich.table import Table
    if not routes:
        console.print(f"[{C.DIM}]Aucune route trouvée.[/{C.DIM}]")
        return
    t = Table(show_header=True, header_style=f"bold {C.SCTRADE}", box=None, pad_edge=False)
    t.add_column("#",         style="dim",      width=3)
    t.add_column("Achat",     style=C.SCTRADE,  min_width=30)
    t.add_column("Commodité", style="white",     min_width=14)
    t.add_column("Prix/□",    justify="right",  min_width=7)
    t.add_column("→ Vente",   style=C.SCTRADE,  min_width=30)
    t.add_column("→Prix/□",   justify="right",  min_width=7)
    t.add_column("Profit",    justify="right",  style=C.PROFIT, min_width=9)
    t.add_column("ROI",       justify="right",  min_width=5)
    for n, r in enumerate(routes[:15], 1):
        p_buy  = float(r.get("price_buy")  or r.get("p_buy",  0))
        p_sell = float(r.get("price_sell") or r.get("p_sell", 0))
        profit = int(r.get("profit", (p_sell - p_buy) * r.get("qty", 1)))
        roi    = f"+{int((p_sell - p_buy) / p_buy * 100)}%" if p_buy else "—"
        ps     = f"+{profit:,}".replace(",", " ") if profit >= 0 else f"{profit:,}".replace(",", " ")
        t.add_row(
            str(n),
            r.get("origin_loc", r.get("origin", {}).get("location", "?")),
            r.get("commodity", r.get("origin", {}).get("itemName", "?")),
            f"{int(p_buy):,}".replace(",", " "),
            r.get("dest_loc",   r.get("destination", {}).get("location", "?")),
            f"{int(p_sell):,}".replace(",", " "),
            ps, roi,
        )
    console.print(t)
    console.print(f"[{C.DIM}]{len(routes)} route(s) · sc-trade.tools[/{C.DIM}]\n")


def _compute_routes_from_listings(
    listings: list[dict],
    *,
    budget: int,
    cargo_scu: int,
    origin: str = "",
    same_system: bool = False,
    player_sys: str = "",
) -> list[dict]:
    """Calcul local de routes depuis les listings crowdsource sc-trade.tools.

    Stratégie : pour chaque commodité, meilleur achat + meilleure vente.
    Si same_system=True, achat ET vente doivent être dans player_sys.
    Si origin est fourni, le lieu d'achat est scoré comme prioritaire si proche.
    """
    from collections import defaultdict

    sys_lower = player_sys.lower() if (same_system and player_sys) else ""

    # Index : commodity → {location → {buy/sell: price}}
    prices: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))
    for r in listings:
        comm = r.get("commodity", "").lower().strip()
        loc  = r.get("location", "").strip()
        p    = int(r.get("price") or 0)
        tx   = r.get("transaction", "")
        if not comm or not loc or p <= 0:
            continue
        # Filtre système (déjà appliqué sur listings avant appel, mais double-sécurité)
        if sys_lower and sys_lower not in loc.lower():
            continue
        if tx == "SELLS":   # terminal vend → joueur achète
            existing = prices[comm][loc].get("buy", 0)
            if p < existing or not existing:
                prices[comm][loc]["buy"] = p
        elif tx == "BUYS":  # terminal achète → joueur vend
            existing = prices[comm][loc].get("sell", 0)
            if p > existing:
                prices[comm][loc]["sell"] = p

    origin_lower = origin.lower()
    routes = []
    for comm, locs in prices.items():
        buy_opts  = [(loc, d["buy"])  for loc, d in locs.items() if "buy"  in d]
        sell_opts = [(loc, d["sell"]) for loc, d in locs.items() if "sell" in d]
        if not buy_opts or not sell_opts:
            continue
        buy_loc,  p_buy  = min(buy_opts,  key=lambda x: x[1])
        sell_loc, p_sell = max(sell_opts, key=lambda x: x[1])
        if sell_loc == buy_loc or p_sell <= p_buy:
            continue
        margin = (p_sell - p_buy) / p_buy
        if margin < 0.05:
            continue
        qty    = min(cargo_scu, budget // max(p_buy, 1))
        profit = int((p_sell - p_buy) * qty)
        # Bonus de tri si le lieu d'achat est proche de l'origin du joueur
        origin_bonus = 1 if (origin_lower and origin_lower in buy_loc.lower()) else 0
        routes.append({
            "commodity":    comm.title(),
            "origin_loc":   buy_loc,
            "dest_loc":     sell_loc,
            "p_buy":        p_buy,
            "p_sell":       p_sell,
            "profit":       profit,
            "qty":          qty,
            "_origin_bonus": origin_bonus,
        })

    # Tri : profit desc, avec légère préférence pour les achats proches de l'origin
    routes.sort(key=lambda r: (r["_origin_bonus"], r["profit"]), reverse=True)
    return routes
