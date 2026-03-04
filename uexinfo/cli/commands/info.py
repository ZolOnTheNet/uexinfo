"""Commande /info — terminal (marché), commodité (prix), vaisseau."""
from __future__ import annotations

import re
import time
from datetime import datetime

from rich.table import Table

from uexinfo.api.uex_client import UEXClient, UEXError
from uexinfo.cache.models import Commodity, Terminal, Vehicle
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_warn, section
from uexinfo.models.scan_result import ScanResult
from uexinfo.models.transport_network import EdgeType

_PRICE_TTL = 300  # 5 minutes


# ── Helpers ────────────────────────────────────────────────────────────────────

def _scu(lo, hi=None) -> str:
    """Formate une plage SCU : '8-32', '32', ou '—'."""
    lo = int(lo or 0)
    hi = int(hi or lo)
    if not lo and not hi:
        return "—"
    if hi != lo and lo > 0:
        return f"{lo}-{hi}"
    return str(hi or lo)


def _price_fmt(value) -> str:
    """Formate un prix en aUEC avec séparateurs d'espaces."""
    if not value:
        return "—"
    return f"{int(value):,}".replace(",", " ")


def _price_short(val) -> str:
    """Format compact : '1 473', '5 M.', '—'."""
    if not val:
        return "—"
    v = int(val)
    if v >= 1_000_000:
        m = v / 1_000_000
        m_str = str(int(m)) if m == int(m) else f"{m:.1f}"
        return f"{m_str} M."
    return f"{v:,}".replace(",", " ")


_STANDARD_SCU_RANGES = {"", "—", "1-32", "1-4", "8-32"}

def _notable_scu(scu_str: str) -> str:
    """Retourne scu_str seulement si non-standard (1-32 / 1-4 / 8-32 = omis)."""
    return "" if scu_str in _STANDARD_SCU_RANGES else scu_str


_NAME_MAX = 17  # largeur max du nom seul (sans la partie SCU)


def _abbrev_name(name: str, maxlen: int = _NAME_MAX) -> str:
    """Raccourcit les noms longs. Ex: 'Construction Materials' → 'Constr. Materials'."""
    if len(name) <= maxlen:
        return name
    parts = name.split()
    if len(parts) >= 3:
        candidate = parts[0] + " " + parts[-1]
        if len(candidate) <= maxlen:
            return candidate
    return name[:maxlen - 1] + "…"


_STATUS_LABEL = {1: "Out", 2: "T.Bas", 3: "Bas", 4: "Moy", 5: "Haut", 7: "Max"}

# Achat : Max = blanc (abondant) → Out = rouge (épuisé)
_BUY_STATUS_COLOR  = {7: "bright_white", 5: "white", 4: "yellow", 3: "orange1", 2: "red1", 1: "red"}
# Vente : Out = blanc (terminal demandeur) → Max = rouge (terminal plein = bloquant)
_SELL_STATUS_COLOR = {1: "bright_white", 2: "white", 3: "yellow", 4: "orange1", 5: "red1", 7: "red"}


def _entry_ns(name: str, scu_str: str, status: int | None, buy: bool) -> str:
    """Formate 'NomCourt (SCU)' avec le SCU coloré selon le statut de stock."""
    short = _abbrev_name(name)
    s = int(status or 0)
    color_map = _BUY_STATUS_COLOR if buy else _SELL_STATUS_COLOR
    color = color_map.get(s, C.DIM)
    return f"{short} ([{color}]{scu_str}[/{color}])"


def _multi_col_table(
    entries: list[tuple[str, str]],
    headers: tuple[str, str],
    n_cols: int,
    name_style: str,
    price_style: str,
) -> Table:
    """Table multi-colonnes : (nom+scu, prix) × n_cols par ligne."""
    h_name, h_price = headers
    tbl = Table(show_header=True, box=None, padding=(0, 1), show_edge=False)
    for _ in range(n_cols):
        tbl.add_column(h_name,  style=name_style,  no_wrap=True, max_width=26)
        tbl.add_column(h_price, style=price_style, justify="right", no_wrap=True, min_width=5)
    for i in range(0, len(entries), n_cols):
        chunk = entries[i:i + n_cols]
        row: list[str] = []
        for ns, ps in chunk:
            row.extend([ns, ps])
        row.extend(["", ""] * (n_cols - len(chunk)))
        tbl.add_row(*row)
    return tbl


def _loc(full_name: str) -> str:
    """Retire le préfixe service ('Admin - ', 'Shop - ', …)."""
    return full_name.rsplit(" - ", 1)[-1].strip()


def _player_system(ctx) -> str:
    """Retourne le système du joueur en minuscules, ou ''."""
    loc = ctx.player.location or ""
    if not loc:
        return ""
    entries = ctx.location_index.search(loc, limit=1) if ctx.location_index else []
    if entries:
        return entries[0].full_path.split(".")[0].lower()
    for t in ctx.cache.terminals:
        if _loc(t.name).lower() == loc.lower():
            return t.star_system_name.lower()
    return ""


# ── Cache prix ─────────────────────────────────────────────────────────────────

def _fetch_prices(key: str, api_kwargs: dict, ctx) -> list[dict]:
    cached = ctx._price_cache.get(key)
    if cached:
        ts, data = cached
        if time.monotonic() - ts < _PRICE_TTL:
            return data
    client = UEXClient()
    try:
        data = client.get_prices(**api_kwargs)
    except UEXError as e:
        console.print(f"[{C.WARNING}]⚠  API : {e}[/{C.WARNING}]")
        return []
    ctx._price_cache[key] = (time.monotonic(), data)
    return data


def _to_slug(name: str) -> str:
    """'Admin - Orbituary' → 'admin-orbituary' (slug UEX Corp)."""
    s = name.lower().replace(" - ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    return s.strip("-")


def _terminal_prices(t: Terminal, ctx) -> list[dict]:
    """Récupère les prix d'un terminal avec chaîne de fallback : id → code → loc → slug."""
    rows = _fetch_prices(f"t{t.id}", {"id_terminal": t.id}, ctx)
    if rows:
        return rows
    if t.code:
        rows = _fetch_prices(f"tc_{t.code}", {"terminal_code": t.code}, ctx)
        if rows:
            return rows
    # Nom court (dernière partie après " - ") : "Admin - Orbituary" → "orbituary"
    loc_q = _loc(t.name).lower()
    if loc_q:
        rows = _fetch_prices(f"tl_{loc_q}", {"terminal_name": loc_q}, ctx)
        if rows:
            return rows
    # Dernier recours : slug complet
    slug = _to_slug(t.name)
    if slug and slug != loc_q:
        rows = _fetch_prices(f"ts_{slug}", {"terminal_name": slug}, ctx)
    return rows


def _commodity_prices(c_id: int, ctx) -> list[dict]:
    return _fetch_prices(f"c{c_id}", {"id_commodity": c_id}, ctx)


_ROUTES_TTL = 300  # 5 minutes


def _fetch_route_distances(terminal_id: int, ctx) -> dict[str, float]:
    """Retourne {terminal_name_lower: distance_gm} depuis terminal_id (routes UEX).

    Enrichit automatiquement le graphe de transport avec les distances découvertes.
    """
    key = f"rd_{terminal_id}"
    cached = ctx._price_cache.get(key)
    if cached:
        ts, data = cached
        if time.monotonic() - ts < _ROUTES_TTL:
            return data
    client = UEXClient()
    try:
        routes = client.get_routes(id_terminal_origin=terminal_id)
    except UEXError:
        return {}

    # Récupérer le nom du terminal d'origine
    origin_terminal = None
    for t in ctx.cache.terminals:
        if t.id == terminal_id:
            origin_terminal = t.name
            break

    dist_map: dict[str, float] = {}
    enriched_count = 0

    for route in routes:
        dest = route.get("terminal_name_destination") or ""
        dist = route.get("distance")
        if dest and dist is not None:
            dist_map[dest.lower()] = float(dist)

            # Enrichir le graphe de transport (opportuniste)
            if origin_terminal:
                # Convertir distance en Gm (API UEX retourne en Mkm = mégamètres)
                distance_gm = float(dist) / 1000.0

                # Ajouter/mettre à jour la route dans le graphe
                modified = ctx.cache.transport_graph.add_or_update_route(
                    from_node=origin_terminal,
                    to_node=dest,
                    distance_gm=distance_gm,
                    edge_type=EdgeType.QUANTUM,
                    duration_sec=0,  # Pas de durée fournie par l'API
                    source="uex",
                    notes="Auto-enrichi via API /routes",
                    timestamp=time.time(),
                )
                if modified:
                    enriched_count += 1

    # Afficher un feedback discret si enrichissement
    if enriched_count > 0:
        console.print(
            f"[{C.DIM}]⊕ Graphe enrichi : {enriched_count} nouvelle(s) route(s)[/{C.DIM}]"
        )

    ctx._price_cache[key] = (time.monotonic(), dist_map)
    return dist_map


# ── Données scan ───────────────────────────────────────────────────────────────

_STOCK_LABELS = {1: "Out", 2: "Très bas", 3: "Bas", 4: "Moyen", 5: "Haut", 7: "Max"}
_STOCK_COLORS = {1: C.DIM, 2: "red", 3: "yellow", 4: C.UEX, 5: C.PROFIT, 7: C.PROFIT}


def _find_scan(loc_name: str, ctx) -> ScanResult | None:
    """Trouve le scan le plus récent dont le nom correspond à ce terminal."""
    if not ctx.scan_history:
        return None
    q = loc_name.lower()
    for result in reversed(ctx.scan_history):
        t = result.terminal.lower()
        if q in t or t in q:
            return result
    return None


def _show_scan_section(result: ScanResult, ctx) -> None:
    """Affiche les données d'un ScanResult dans le contexte d'un terminal."""
    ago_s = int((datetime.now() - result.timestamp).total_seconds())
    ago_str = f"{ago_s // 60} min" if ago_s < 3600 else f"{ago_s // 3600} h"
    console.print(f"[italic {C.DIM}]Scan ({result.source}) · il y a {ago_str}[/italic {C.DIM}]")
    if not result.commodities:
        console.print(f"[{C.DIM}]Aucune commodité scannée.[/{C.DIM}]")
        return
    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Commodité", style=C.NEUTRAL, no_wrap=True, min_width=20)
    tbl.add_column("Prix/SCU",  style=C.UEX,     justify="right", no_wrap=True)
    tbl.add_column("SCU",       style=C.DIM,     justify="right", no_wrap=True)
    tbl.add_column("Stock",     no_wrap=True)
    for sc in sorted(result.commodities, key=lambda s: s.name):
        price = _price_fmt(sc.price) if sc.price else "—"
        qty   = str(sc.quantity) if sc.quantity is not None else "—"
        color = _STOCK_COLORS.get(sc.stock_status, C.DIM)
        label = _STOCK_LABELS.get(sc.stock_status, sc.stock or "?")
        tbl.add_row(sc.name, price, qty, f"[{color}]{label}[/{color}]")
    console.print(tbl)


# ── Helpers pour affichage ligne par ligne ────────────────────────────────────

def _stock_bar(status: int, sell: bool) -> str:
    """Génère une barre de stock visuelle ●●●○ (4 symboles)."""
    if not status:
        return f"[{C.DIM}]○○○○[/{C.DIM}]"

    # Mapping du status (1-7) vers le nb de symboles pleins (0-4)
    levels = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 7: 4}
    filled = levels.get(status, 0)

    # Pour la vente : Out=vert (forte demande), Max=rouge (terminal plein)
    # Pour l'achat : Max=vert (abondant), Out=rouge (rupture)
    if sell:
        colors_map = {0: "green", 1: "green", 2: "yellow", 3: "orange1", 4: "red"}
    else:
        colors_map = {0: "red", 1: "orange1", 2: "yellow", 3: "green", 4: "green"}

    color = colors_map.get(filled, C.DIM)
    bar = "●" * filled + "○" * (4 - filled)
    return f"[{color}]{bar}[/{color}]"


def _find_best_buyers(commodity_name: str, ctx, player_dest: str = "") -> list[dict]:
    """Trouve les terminaux achetant cette commodité, triés par :
    1. Destination du joueur (si définie)
    2. Prix (décroissant)
    Retourne les 3 meilleurs acheteurs.
    """
    client = UEXClient()
    try:
        rows = client.get_prices(commodity_name=commodity_name)
    except Exception:
        return []

    # Filtrer uniquement les terminaux qui achètent (price_sell > 0)
    buyers = [r for r in rows if r.get("price_sell")]

    if not buyers:
        return []

    # Trier : destination joueur en premier, puis par prix décroissant
    def sort_key(row):
        terminal = (row.get("terminal_name") or "").lower()
        is_player_dest = 1 if player_dest and terminal == player_dest else 0
        price = float(row.get("price_sell") or 0)
        return (-is_player_dest, -price)

    return sorted(buyers, key=sort_key)[:3]  # Top 3 acheteurs


def _show_buy_detailed(buy_rows: list[dict], origin_terminal: Terminal, ctx) -> None:
    """Affiche la section Acheter avec calculs détaillés de cargo, prix, profit."""
    console.print(f"\n[bold {C.UEX}]▼ Acheter ici[/bold {C.UEX}]")

    # Récupérer le cargo du vaisseau actif
    ship_cargo = 0
    if ctx.player.active_ship:
        for ship in ctx.player.ships:
            if ship.name == ctx.player.active_ship:
                ship_cargo = ship.scu
                break

    if ship_cargo == 0:
        console.print(f"[{C.WARNING}]⚠  Vaisseau actif non défini ou cargo = 0 SCU[/{C.WARNING}]")
        console.print(f"[{C.DIM}]   Utilisez /ship set <nom> pour définir votre vaisseau[/{C.DIM}]")
        return

    player_dest = (ctx.player.destination or "").lower().strip()

    for r in buy_rows:
        name = r.get("commodity_name", "?")
        scu_min = int(r.get("scu_buy") or 0)
        scu_max = int(r.get("scu_buy_max") or scu_min)
        price_buy = float(r.get("price_buy") or 0)
        status_buy = int(r.get("status_buy") or 0)

        # Quantité disponible à l'achat (estimation basée sur le status)
        # Status: 1=Out, 2=TrèsBas, 3=Bas, 4=Moyen, 5=Haut, 7=Max
        stock_multiplier = {1: 0, 2: 0.2, 3: 0.4, 4: 0.6, 5: 0.8, 7: 1.0}
        stock_percent = stock_multiplier.get(status_buy, 0.5)
        stock_available = int(ship_cargo * stock_percent) if status_buy != 1 else 0

        # Quantité achetable = min(cargo vaisseau, stock disponible)
        qty_buy = min(ship_cargo, stock_available) if stock_available > 0 else ship_cargo

        # Total achat
        total_buy = qty_buy * price_buy

        # Trouver le meilleur acheteur
        best_buyers = _find_best_buyers(name, ctx, player_dest)

        if not best_buyers:
            # Pas de destination connue — affichage simple
            console.print(
                f"  [{C.NEUTRAL}]{_abbrev_name(name)}[/{C.NEUTRAL}] "
                f"[{C.DIM}]({scu_min}-{scu_max})[/{C.DIM}]  "
                f"[italic {C.UEX}]{price_buy:.2f}[/italic {C.UEX}]  "
                f"[{C.DIM}]→  ?  (aucune destination connue)[/{C.DIM}]"
            )
            continue

        buyer = best_buyers[0]
        dest_name = buyer.get("terminal_name", "?")
        dest_system = buyer.get("star_system_name", "")
        price_sell = float(buyer.get("price_sell") or 0)
        status_sell = int(buyer.get("status_sell") or 0)

        # Inventory du terminal vendeur (capacité restante)
        # Status sell: 1=Out (forte demande), 7=Max (plein)
        inv_multiplier = {1: 1.0, 2: 0.8, 3: 0.6, 4: 0.4, 5: 0.2, 7: 0}
        inv_percent = inv_multiplier.get(status_sell, 0.5)
        inv_remaining = int(qty_buy * inv_percent)

        # Total vente (si tout vendu)
        total_sell_full = qty_buy * price_sell

        # Total vente limité par inventaire
        qty_sell_limited = inv_remaining
        total_sell_limited = qty_sell_limited * price_sell
        qty_unsold = qty_buy - qty_sell_limited

        # Profit
        profit_full = total_sell_full - total_buy
        profit_limited = total_sell_limited - total_buy

        # Notation système (ajouter "." si différent)
        origin_system = origin_terminal.star_system_name
        dest_display = dest_name
        if dest_system and dest_system != origin_system:
            dest_display = f"{dest_system}.{dest_name}"

        # Souligner si destination = celle du joueur
        dest_style = "underline" if dest_name.lower() == player_dest else ""

        # Distance depuis le graphe
        distance_str = ""
        graph = ctx.cache.transport_graph
        if origin_terminal.name in graph.nodes and dest_name in graph.nodes:
            # Chercher dans les arêtes
            for edge in graph._adjacency.get(origin_terminal.name, []):
                if edge.to_node == dest_name:
                    distance_str = f"  [{C.DIM}]{edge.distance_gm:.1f} Gm[/{C.DIM}]"
                    break

        # Affichage ligne 1 : Nom, conditionnement, destination, distance
        console.print(
            f"  [{C.NEUTRAL}]{_abbrev_name(name, 18)}[/{C.NEUTRAL}] "
            f"[{C.DIM}]({scu_min}-{scu_max})[/{C.DIM}]  "
            f"[{C.DIM}]→[/{C.DIM}]  "
            f"[{dest_style} {C.LABEL}]{_abbrev_name(dest_display, 22)}[/{dest_style} {C.LABEL}]"
            f"{distance_str}"
        )

        # Affichage ligne 2 : Calculs détaillés
        profit_color = C.PROFIT if profit_full > 0 else C.LOSS
        profit_sign = "+" if profit_full >= 0 else ""

        vente_detail = f"{int(total_sell_full)}"
        if qty_unsold > 0:
            vente_detail += f" [{C.DIM}]({int(total_sell_limited)} - {qty_unsold} invendus)[/{C.DIM}]"

        console.print(
            f"    [{C.DIM}]{qty_buy} SCU[/{C.DIM}]  "
            f"[italic {C.UEX}]Achat: {int(total_buy)}[/italic {C.UEX}]  "
            f"[{C.DIM}]→[/{C.DIM}]  "
            f"[italic {C.PROFIT}]Vente: {vente_detail}[/italic {C.PROFIT}]  "
            f"[{profit_color}]{profit_sign}{int(profit_full)}[/{profit_color}]"
        )


# ── Affichage terminal ─────────────────────────────────────────────────────────

def _show_terminal(t: Terminal, ctx) -> None:
    loc_name = _loc(t.name)
    station = t.space_station_name or t.city_name or t.orbit_name or t.planet_name
    loc_label = t.star_system_name
    if station and station.lower() != loc_name.lower():
        loc_label += f" › {station}"
    loc_label += f" › {loc_name}"
    section(f"Marché — {loc_name}  [{loc_label}]")

    rows = _terminal_prices(t, ctx)
    scan  = _find_scan(loc_name, ctx)

    if not rows and not scan:
        console.print(f"[{C.DIM}]Aucune donnée pour ce terminal.[/{C.DIM}]")
        console.print(f"[{C.DIM}]Utilisez /scan pour capturer les prix directement en jeu.[/{C.DIM}]")
        return

    # ── Scan personnel : données confirmées (priorité) ────────────────────
    if scan:
        _show_scan_section(scan, ctx)
        if rows:
            console.print()

    # ── Données UEX Corp communauté : affichées en italique (non confirmées) ─
    if rows:
        if scan:
            console.print(f"[italic {C.DIM}]Référence UEX Corp · données communauté[/italic {C.DIM}]")
        else:
            console.print(f"[italic {C.DIM}]UEX Corp · données communauté · non confirmées[/italic {C.DIM}]")

        buy_rows  = sorted([r for r in rows if r.get("price_buy")],
                           key=lambda r: r.get("commodity_name") or "")
        sell_rows = sorted([r for r in rows if r.get("price_sell")],
                           key=lambda r: r.get("commodity_name") or "")

        if not buy_rows and not sell_rows:
            console.print(f"[italic {C.DIM}]Terminal sans transaction active.[/italic {C.DIM}]")
        else:
            term_w = getattr(console, "width", None) or 100
            n_cols = max(1, min(4, term_w // 32))

            if buy_rows:
                _show_buy_detailed(buy_rows, t, ctx)

            if sell_rows:
                console.print(f"\n[bold {C.PROFIT}]▼ Vendre ici[/bold {C.PROFIT}]")
                entries = [
                    (_entry_ns(
                        r.get("commodity_name") or "?",
                        _scu(r.get("scu_sell"), r.get("scu_sell_max"))
                        or _scu(r.get("scu_sell_stock")),
                        r.get("status_sell"), buy=False,
                    ), _price_short(r.get("price_sell")))
                    for r in sell_rows
                ]
                console.print(_multi_col_table(
                    entries, ("Commodité (SCU)", "Vente"), n_cols,
                    f"italic {C.NEUTRAL}", f"italic {C.PROFIT}",
                ))

            total = len({r.get("commodity_name") for r in rows})
            dates = [r.get("date_modified") for r in rows if r.get("date_modified")]
            date_str = ""
            if dates:
                try:
                    dt = datetime.fromtimestamp(max(float(d) for d in dates))
                    date_str = f"  ·  màj {dt.strftime('%d %b %Y %H:%M')}"
                except Exception:
                    pass
            console.print(f"\n[italic {C.DIM}]{total} commodités{date_str}[/italic {C.DIM}]")


# ── Affichage commodité ────────────────────────────────────────────────────────

_BUY_STATUS_BAR: dict[int, str] = {
    1: f"[{C.DIM}]░░░░[/{C.DIM}]",
    2: "[red]▓░░░[/red]",
    3: "[yellow]▓▓░░[/yellow]",
    4: "[cyan]▓▓▓░[/cyan]",
    5: "[green]▓▓▓▓[/green]",
    7: "[bold green]████[/bold green]",
}

_SELL_STATUS_BAR: dict[int, str] = {
    1: "[bold green]░░░░[/bold green]",
    2: "[green]▓░░░[/green]",
    3: "[yellow]▓▓░░[/yellow]",
    4: "[orange1]▓▓▓░[/orange1]",
    5: "[red]▓▓▓▓[/red]",
    7: "[bold red]████[/bold red]",
}


def _bar_buy(status: int, qty) -> str:
    """Barre de stock achat + quantité (plus = mieux)."""
    bar = _BUY_STATUS_BAR.get(int(status or 0), "????")
    q = int(qty or 0)
    return f"{bar} {q:,}".replace(",", "\u202f") if q else bar


def _bar_sell(status: int, qty) -> str:
    """Barre de saturation vente + stock (moins = mieux pour vendre)."""
    bar = _SELL_STATUS_BAR.get(int(status or 0), "????")
    q = int(qty or 0)
    return f"{bar} {q:,}".replace(",", "\u202f") if q else bar


def _player_cargo(ctx) -> int:
    """SCU du vaisseau actif du joueur (config joueur > cache UEX), 0 si inconnu."""
    ship_name = (ctx.player.active_ship or "").strip()
    if not ship_name:
        return 0
    for s in ctx.player.ships:
        if s.name.lower() == ship_name.lower() and s.scu:
            return s.scu
    for v in (ctx.cache.vehicles or []):
        if v.name_full.lower() == ship_name.lower() or v.name.lower() == ship_name.lower():
            return v.scu
    return 0


def _player_terminal(ctx):
    """Retourne le Terminal correspondant à la position du joueur, ou None."""
    loc = (ctx.player.location or "").strip()
    if not loc:
        return None
    return _find_terminal(loc, ctx)


def _dist_label(term_name: str, terminal_sys: str, player_sys: str,
                dist_map: dict | None = None) -> str:
    """Distance : Gm si routes dispo, sinon 'local' / nom système."""
    if dist_map and term_name:
        name_lo  = term_name.lower()
        short_lo = _loc(term_name).lower()
        d = dist_map.get(name_lo) if name_lo in dist_map else dist_map.get(short_lo)
        if d is not None:
            if d < 5:
                return f"[{C.PROFIT}]{d:.1f} Gm[/{C.PROFIT}]"
            elif d < 100:
                return f"[{C.UEX}]{d:.0f} Gm[/{C.UEX}]"
            else:
                return f"[{C.DIM}]{d:.0f} Gm[/{C.DIM}]"
    if not player_sys:
        return f"[{C.DIM}]—[/{C.DIM}]"
    if (terminal_sys or "").lower() == player_sys.lower():
        return f"[{C.PROFIT}]local[/{C.PROFIT}]"
    return terminal_sys or f"[{C.DIM}]—[/{C.DIM}]"


def _term_sys_cell(r: dict, maxlen: int = 22) -> str:
    """'TermCourt  (Sys)' — nom court + système en dim."""
    term = _loc(r.get("terminal_name") or "?")
    sys  = r.get("star_system_name") or ""
    if len(term) > maxlen:
        term = term[:maxlen - 1] + "…"
    sys_part = f"  [{C.DIM}]({sys})[/{C.DIM}]" if sys else ""
    return f"{term}{sys_part}"


def _scu_cell(qty) -> str:
    q = int(qty or 0)
    return f"{q:,} SCU".replace(",", "\u202f") if q else f"[{C.DIM}]—[/{C.DIM}]"


def _scu_range(lo, hi) -> str:
    """Plage de tailles de conteneurs : '1-8', '8-32', 'tous', '1', '—'."""
    lo = int(lo or 0)
    hi = int(hi or lo)
    if not lo and not hi:
        return f"[{C.DIM}]—[/{C.DIM}]"
    if lo <= 1 and hi >= 32:
        return "tous"
    if hi > lo:
        return f"{lo}-{hi}"
    return str(hi or lo)


def _parse_sys_filter(
    args: list[str], player_sys: str
) -> tuple[list[str] | None, list[str]]:
    """Parse les flags --all, --Sys1,Sys2, --Cur depuis args.

    Retourne (sys_filter, remaining_args).
      sys_filter=None → filtre par player_sys (comportement par défaut)
      sys_filter=[]   → --all, aucun filtre
      sys_filter=[…]  → liste de systèmes en minuscules
    """
    remaining: list[str] = []
    sys_filter: list[str] | None = None
    for arg in args:
        if arg.startswith("--"):
            val = arg[2:].lower()
            if val == "all":
                sys_filter = []
            else:
                parts = [s.strip() for s in val.split(",") if s.strip()]
                resolved = []
                for s in parts:
                    if s == "cur":
                        if player_sys:
                            resolved.append(player_sys.lower())
                    else:
                        resolved.append(s.lower())
                if resolved:
                    sys_filter = resolved
        else:
            remaining.append(arg)
    return sys_filter, remaining


def _show_commodity(c: Commodity, ctx, sys_filter=None) -> None:
    flags = []
    if c.is_illegal:     flags.append("[red]illégal[/red]")
    if c.is_refinable:   flags.append("raffinable")
    if c.is_extractable: flags.append("extractable")
    flag_str = "  " + " · ".join(flags) if flags else ""

    player_sys = _player_system(ctx)
    player_scu = _player_cargo(ctx)

    # Résoudre le filtre effectif
    if sys_filter is None:
        effective_filter = [player_sys] if player_sys else None
    elif sys_filter == []:          # --all
        effective_filter = None
    else:
        effective_filter = sys_filter

    if effective_filter:
        sys_label = f"  [{C.DIM}]filtre : {', '.join(effective_filter)}[/{C.DIM}]"
    elif sys_filter == []:
        sys_label = f"  [{C.DIM}]tous systèmes[/{C.DIM}]"
    else:
        sys_label = ""

    cargo_hint = (f"  [{C.DIM}]cargo : {player_scu} SCU[/{C.DIM}]" if player_scu
                  else f"  [{C.DIM}](cargo non configuré)[/{C.DIM}]" if ctx.player.active_ship
                  else "")
    section(f"Commodité — {c.name}  [{c.code}]{flag_str}{sys_label}{cargo_hint}")

    rows = _commodity_prices(c.id, ctx)
    if not rows:
        console.print(f"[{C.DIM}]Aucune donnée de prix disponible.[/{C.DIM}]")
        return

    if effective_filter:
        rows_filtered = [
            r for r in rows
            if (r.get("star_system_name") or "").lower() in effective_filter
        ]
        if rows_filtered:
            rows = rows_filtered

    active    = [r for r in rows if r.get("price_buy") or r.get("price_sell")]
    buy_rows  = sorted([r for r in active if r.get("price_buy")],
                       key=lambda r: r["price_buy"])
    sell_rows = sorted([r for r in active if r.get("price_sell")],
                       key=lambda r: -(r["price_sell"]))

    if not active:
        filter_note = f" dans {', '.join(effective_filter)}" if effective_filter else ""
        console.print(f"[{C.DIM}]Aucun terminal actif{filter_note}.[/{C.DIM}]")
        return

    # Prix de référence pour ROI
    ref_buy = (buy_rows[0]["price_buy"] if buy_rows else float(c.price_buy or 0))

    # ── Distances via routes API ────────────────────────────────────────────
    dist_map: dict[str, float] = {}
    player_term = _player_terminal(ctx)
    if player_term and player_term.id:
        dist_map = _fetch_route_distances(player_term.id, ctx)

    # ── Résumé ─────────────────────────────────────────────────────────────
    parts = []
    if buy_rows:
        parts.append(f"Achat min : [{C.UEX}]{_price_fmt(buy_rows[0]['price_buy'])}[/{C.UEX}]")
    if sell_rows:
        parts.append(f"Vente max : [{C.PROFIT}]{_price_fmt(sell_rows[0]['price_sell'])}[/{C.PROFIT}]")
    if ref_buy and sell_rows:
        spread = sell_rows[0]["price_sell"] - ref_buy
        roi    = spread / ref_buy * 100
        color  = C.PROFIT if spread > 0 else C.LOSS
        parts.append(
            f"Meilleur écart : [{color}]{_price_fmt(spread)}[/{color}]"
            f"  [{C.DIM}]ROI {roi:+.0f}%[/{C.DIM}]"
        )
    if parts:
        console.print("  ".join(parts))
        console.print()

    # ── Table ACHAT ────────────────────────────────────────────────────────
    if buy_rows:
        console.print(f"[bold {C.UEX}]▼ Acheter ici[/bold {C.UEX}]")
        tbl = Table(show_header=True, box=None, padding=(0, 1), show_edge=False)
        tbl.add_column("Terminal (Sys)", no_wrap=True, min_width=24)
        tbl.add_column("Achat/SCU",      style=C.UEX,  justify="right", no_wrap=True)
        tbl.add_column("T.Cargo",        style=C.DIM,  justify="right", no_wrap=True)
        tbl.add_column("Dispo",          no_wrap=True)
        tbl.add_column("Dist",           no_wrap=True)
        tbl.add_column("Total achat",    style=C.UEX,  justify="right", no_wrap=True)

        for r in buy_rows[:30]:
            price     = r.get("price_buy") or 0
            scu_min   = int(r.get("scu_buy") or 0)
            scu_max   = int(r.get("scu_buy_max") or scu_min)
            status    = int(r.get("status_buy") or 0)
            sys       = r.get("star_system_name") or ""
            term_name = r.get("terminal_name") or ""
            if player_scu and scu_max:
                qty_buy = min(player_scu, scu_max)
            elif player_scu:
                qty_buy = player_scu
            else:
                qty_buy = scu_max
            total = price * qty_buy if price and qty_buy else None
            total_cell = (
                f"{_price_fmt(total)} [{C.DIM}](×{qty_buy})[/{C.DIM}]"
                if total else f"[{C.DIM}]—[/{C.DIM}]"
            )
            tbl.add_row(
                _term_sys_cell(r),
                _price_fmt(price),
                _scu_range(scu_min, scu_max),
                _bar_buy(status, scu_max),
                _dist_label(term_name, sys, player_sys, dist_map),
                total_cell,
            )
        console.print(tbl)

    # ── Séparateur — "Vente" positionné au tiers gauche ────────────────────
    w     = max(40, (getattr(console, "width", None) or 80) - 10)
    mid   = " Vente "
    left  = w // 3
    right = w - left - len(mid)
    console.print(f"[{C.DIM}]{'─' * left}{mid}{'─' * right}[/{C.DIM}]")

    # ── Table VENTE ────────────────────────────────────────────────────────
    if sell_rows:
        console.print(f"[bold {C.PROFIT}]▼ Vendre ici[/bold {C.PROFIT}]")
        tbl = Table(show_header=True, box=None, padding=(0, 1), show_edge=False)
        tbl.add_column("Terminal (Sys)",  no_wrap=True, min_width=24)
        tbl.add_column("Vente/SCU",       style=C.PROFIT, justify="right", no_wrap=True)
        tbl.add_column("Saturation",      no_wrap=True)
        tbl.add_column("T.Cargo",         style=C.DIM,    justify="right", no_wrap=True)
        tbl.add_column("Dist",            no_wrap=True)
        tbl.add_column("ROI",             justify="right", no_wrap=True)
        tbl.add_column("Revenu cargo",    style=C.PROFIT, justify="right", no_wrap=True)

        for r in sell_rows[:30]:
            price        = r.get("price_sell") or 0
            scu_sell_min = int(r.get("scu_sell") or 0)
            scu_sell_max = int(r.get("scu_sell_max") or scu_sell_min)
            scu_stock    = int(r.get("scu_sell_stock") or 0)
            status       = int(r.get("status_sell") or 0)
            sys          = r.get("star_system_name") or ""
            term_name    = r.get("terminal_name") or ""
            if player_scu and scu_sell_max:
                qty_sell = min(player_scu, scu_sell_max)
            elif player_scu:
                qty_sell = player_scu
            else:
                qty_sell = scu_sell_max
            revenue = price * qty_sell if price and qty_sell else None

            if ref_buy and price:
                roi_val   = (price - ref_buy) / ref_buy * 100
                roi_color = C.PROFIT if roi_val > 0 else C.LOSS
                roi_str   = f"[{roi_color}]{roi_val:+.0f}%[/{roi_color}]"
            else:
                roi_str = f"[{C.DIM}]—[/{C.DIM}]"

            revenue_cell = (
                f"{_price_fmt(revenue)} [{C.DIM}](×{qty_sell})[/{C.DIM}]"
                if revenue else f"[{C.DIM}]—[/{C.DIM}]"
            )
            tbl.add_row(
                _term_sys_cell(r),
                _price_fmt(price),
                _bar_sell(status, scu_stock),
                _scu_range(scu_sell_min, scu_sell_max),
                _dist_label(term_name, sys, player_sys, dist_map),
                roi_str,
                revenue_cell,
            )
        console.print(tbl)

    # ── Footer ─────────────────────────────────────────────────────────────
    n_t    = len({r.get("terminal_name") for r in active})
    dates  = [r.get("date_modified") for r in active if r.get("date_modified")]
    date_str = ""
    if dates:
        try:
            dt = datetime.fromtimestamp(max(float(d) for d in dates))
            date_str = f"  ·  màj {dt.strftime('%d %b %Y %H:%M')}"
        except Exception:
            pass
    ship_note = ""
    if player_scu:
        ship_note = f"  ·  {ctx.player.active_ship} ({player_scu} SCU)"
    elif ctx.player.active_ship:
        ship_note = f"  ·  {ctx.player.active_ship} — /ship cargo <nom> <n> pour le SCU"
    console.print(f"\n[{C.DIM}]{n_t} terminaux{date_str}{ship_note}[/{C.DIM}]")
    console.print(
        f"[{C.DIM}]  Prix en aUEC  ·  T.Cargo : taille conteneurs (ex. 1-8, 8-32, tous)"
        f"  ·  Dispo ░=vide ████=plein  ·  ROI vs meilleur achat local[/{C.DIM}]"
    )


# ── Cache prix véhicules ────────────────────────────────────────────────────────

_VEHICLE_PRICE_TTL = 3600  # 1 h (prix d'achat vaisseaux varient peu)


def _fetch_vehicle_purchases(id_vehicle: int, ctx) -> list[dict]:
    key = f"vp_{id_vehicle}"
    cached = ctx._price_cache.get(key)
    if cached:
        ts, data = cached
        if time.monotonic() - ts < _VEHICLE_PRICE_TTL:
            return data
    client = UEXClient()
    try:
        data = client.get_vehicles_purchases_prices(id_vehicle=id_vehicle)
    except UEXError as e:
        console.print(f"[{C.WARNING}]⚠  API : {e}[/{C.WARNING}]")
        return []
    ctx._price_cache[key] = (time.monotonic(), data)
    return data


def _fetch_vehicle_rentals(id_vehicle: int, ctx) -> list[dict]:
    key = f"vr_{id_vehicle}"
    cached = ctx._price_cache.get(key)
    if cached:
        ts, data = cached
        if time.monotonic() - ts < _VEHICLE_PRICE_TTL:
            return data
    client = UEXClient()
    try:
        data = client.get_vehicles_rentals_prices(id_vehicle=id_vehicle)
    except UEXError as e:
        console.print(f"[{C.WARNING}]⚠  API : {e}[/{C.WARNING}]")
        return []
    ctx._price_cache[key] = (time.monotonic(), data)
    return data


# ── Affichage vaisseau ──────────────────────────────────────────────────────────

def _show_vehicle(v: Vehicle, ctx) -> None:
    section(f"Vaisseau — {v.name_full}")

    # ── Fiche technique ────────────────────────────────────────────────────
    roles = []
    if v.is_cargo:          roles.append("cargo")
    if v.is_mining:         roles.append("mining")
    if v.is_salvage:        roles.append("salvage")
    if v.is_military:       roles.append("militaire")

    crew_str = str(v.crew) if v.crew and v.crew != "0" else "—"
    pad_str  = v.pad_type or "—"
    scu_str  = str(v.scu) if v.scu else "—"

    console.print(
        f"[{C.LABEL}]Fabricant[/{C.LABEL}]  {v.manufacturer or '—'}"
        f"    [{C.LABEL}]Cargo[/{C.LABEL}]  [{C.UEX}]{scu_str} SCU[/{C.UEX}]"
        f"    [{C.LABEL}]Équipage[/{C.LABEL}]  {crew_str}"
        f"    [{C.LABEL}]Pad[/{C.LABEL}]  {pad_str}"
    )
    if roles:
        console.print(f"[{C.LABEL}]Rôles[/{C.LABEL}]  " + " · ".join(roles))
    console.print()

    player_sys = _player_system(ctx)

    # ── Prix d'achat ───────────────────────────────────────────────────────
    buy_rows = _fetch_vehicle_purchases(v.id, ctx)
    if buy_rows:
        prices = [int(r.get("price") or r.get("price_buy") or 0) for r in buy_rows]
        prices = [p for p in prices if p > 0]
        avg_buy = sum(prices) // len(prices) if prices else 0

        console.print(
            f"[bold {C.UEX}]▼ Achat[/bold {C.UEX}]"
            + (f"  [{C.DIM}]moy {_price_fmt(avg_buy)} aUEC[/{C.DIM}]" if avg_buy else "")
        )

        def _buy_sort(r):
            sys = (r.get("star_system_name") or "").lower()
            same = (sys == player_sys) if player_sys else False
            return (0 if same else 1, int(r.get("price") or r.get("price_buy") or 0))

        tbl = Table(show_header=True, box=None, padding=(0, 1))
        tbl.add_column("Terminal",  style=C.NEUTRAL, no_wrap=True, min_width=20)
        tbl.add_column("Système",   style=C.DIM,     no_wrap=True)
        tbl.add_column("Prix",      style=C.UEX,     justify="right", no_wrap=True)
        for r in sorted(buy_rows, key=_buy_sort)[:20]:
            price = int(r.get("price") or r.get("price_buy") or 0)
            if not price:
                continue
            term = r.get("terminal_name") or "?"
            sys  = r.get("star_system_name") or "?"
            tbl.add_row(term, sys, f"{_price_fmt(price)} aUEC")
        console.print(tbl)
        console.print()
    else:
        console.print(f"[{C.DIM}]Prix d'achat non disponibles.[/{C.DIM}]\n")

    # ── Prix de location ───────────────────────────────────────────────────
    rent_rows = _fetch_vehicle_rentals(v.id, ctx)
    if rent_rows:
        prices = [int(r.get("price_rent") or r.get("price") or 0) for r in rent_rows]
        prices = [p for p in prices if p > 0]
        avg_rent = sum(prices) // len(prices) if prices else 0

        console.print(
            f"[bold {C.PROFIT}]▼ Location[/bold {C.PROFIT}]"
            + (f"  [{C.DIM}]moy {_price_fmt(avg_rent)} aUEC/jour[/{C.DIM}]" if avg_rent else "")
        )

        def _rent_sort(r):
            sys = (r.get("star_system_name") or "").lower()
            same = (sys == player_sys) if player_sys else False
            return (0 if same else 1, int(r.get("price_rent") or r.get("price") or 0))

        tbl = Table(show_header=True, box=None, padding=(0, 1))
        tbl.add_column("Terminal",  style=C.NEUTRAL, no_wrap=True, min_width=20)
        tbl.add_column("Système",   style=C.DIM,     no_wrap=True)
        tbl.add_column("Prix/jour", style=C.PROFIT,  justify="right", no_wrap=True)
        for r in sorted(rent_rows, key=_rent_sort)[:20]:
            price = int(r.get("price_rent") or r.get("price") or 0)
            if not price:
                continue
            term = r.get("terminal_name") or "?"
            sys  = r.get("star_system_name") or "?"
            tbl.add_row(term, sys, f"{_price_fmt(price)} aUEC")
        console.print(tbl)
    else:
        console.print(f"[{C.DIM}]Prix de location non disponibles.[/{C.DIM}]")


# ── Recherche ──────────────────────────────────────────────────────────────────

def _find_terminal(query: str, ctx) -> Terminal | None:
    q = query.replace("_", " ").lower().strip()
    for t in ctx.cache.terminals:
        if t.name.lower() == q or t.code.lower() == q:
            return t
    for t in ctx.cache.terminals:
        loc = _loc(t.name).lower()
        if loc == q or loc.startswith(q):
            return t
    for t in ctx.cache.terminals:
        if q in t.name.lower():
            return t
    return None


def _find_commodity(query: str, ctx) -> Commodity | None:
    q = query.replace("_", " ").lower().strip()
    for c in ctx.cache.commodities:
        if c.name.lower() == q or c.code.lower() == q:
            return c
    for c in ctx.cache.commodities:
        if c.name.lower().startswith(q):
            return c
    for c in ctx.cache.commodities:
        if q in c.name.lower():
            return c
    return None


def _find_vehicle(query: str, ctx) -> Vehicle | None:
    q = query.replace("_", " ").lower().strip()
    vehicles = ctx.cache.vehicles or []
    for v in vehicles:
        if v.name_full.lower() == q or v.name.lower() == q:
            return v
    for v in vehicles:
        if v.name_full.lower().startswith(q):
            return v
    for v in vehicles:
        if q in v.name_full.lower():
            return v
    try:
        from rapidfuzz import process, fuzz
        names_lower = [v.name_full.lower() for v in vehicles]
        r = process.extractOne(q, names_lower, scorer=fuzz.WRatio, score_cutoff=65)
        if r:
            return vehicles[names_lower.index(r[0])]
    except ImportError:
        import difflib
        names_lower = [v.name_full.lower() for v in vehicles]
        m = difflib.get_close_matches(q, names_lower, n=1, cutoff=0.6)
        if m:
            return vehicles[names_lower.index(m[0])]
    return None


def _show_terminal_by_name(query: str, ctx) -> bool:
    """Requête directe pour les terminaux absents du cache (ex: système Pyro).
    Construit un Terminal virtuel depuis les données de prix et l'affiche.
    """
    q = query.replace("_", " ").lower().strip()
    cache_key = f"tn_{q}"
    rows = _fetch_prices(cache_key, {"terminal_name": q}, ctx)
    if not rows:
        return False

    r0 = rows[0]
    t = Terminal(
        id=int(r0.get("id_terminal") or 0),
        name=r0.get("terminal_name") or query,
        code=r0.get("terminal_code") or "",
        star_system_name=r0.get("star_system_name") or "",
        planet_name=r0.get("planet_name") or "",
        orbit_name=r0.get("orbit_name") or "",
        space_station_name=(
            r0.get("space_station_name") or
            r0.get("outpost_name") or
            r0.get("poi_name") or ""
        ),
        city_name=r0.get("city_name") or "",
    )
    # Pré-remplir le cache id pour éviter un double appel dans _show_terminal
    tid_key = f"t{t.id}"
    if tid_key not in ctx._price_cache:
        ctx._price_cache[tid_key] = ctx._price_cache[cache_key]
    _show_terminal(t, ctx)
    return True


# ── Commande principale ────────────────────────────────────────────────────────

@register("info", "i")
def cmd_info(args: list[str], ctx) -> None:
    # Extraire les flags système (--all, --Sys,Sys) avant de router
    player_sys = _player_system(ctx)
    sys_filter, args = _parse_sys_filter(args, player_sys)

    if not args:
        loc = (ctx.player.location or "").strip()
        if not loc:
            print_warn("Usage : /info <nom>   ou   /info terminal|commodity <nom>")
            return
        t = _find_terminal(loc, ctx)
        if t:
            _show_terminal(t, ctx)
        elif not _show_terminal_by_name(loc, ctx):
            print_warn(f"Position actuelle introuvable comme terminal : {loc}")
        return

    _SUBS = {"terminal", "commodity", "ship"}
    first = args[0].lower()

    if first in _SUBS:
        query = " ".join(args[1:])
        if not query:
            print_warn(f"Usage : /info {first} <nom>")
            return
        if first == "terminal":
            t = _find_terminal(query, ctx)
            if t is None:
                print_warn(f"Terminal introuvable : {query}")
            else:
                _show_terminal(t, ctx)
        elif first == "commodity":
            c = _find_commodity(query, ctx)
            if c is None:
                print_warn(f"Commodité introuvable : {query}")
            else:
                _show_commodity(c, ctx, sys_filter=sys_filter)
        else:
            v = _find_vehicle(query, ctx)
            if v is None:
                print_warn(f"Vaisseau introuvable : {query}")
            else:
                _show_vehicle(v, ctx)
        return

    # Recherche libre
    query = " ".join(args).replace("_", " ")
    # Gérer les tokens @Sys.Planet.Loc issus de la complétion de lieu
    if query.startswith("@"):
        query = query[1:].rsplit(".", 1)[-1]
    t = _find_terminal(query, ctx)
    if t:
        _show_terminal(t, ctx)
        return
    c = _find_commodity(query, ctx)
    if c:
        _show_commodity(c, ctx, sys_filter=sys_filter)
        return
    # Fallback : terminal hors cache (Pyro, etc.) → requête directe par nom
    if _show_terminal_by_name(query, ctx):
        return
    # Fallback : vaisseau
    v = _find_vehicle(query, ctx)
    if v:
        _show_vehicle(v, ctx)
        return

    console.print(
        f"[{C.DIM}]Rien trouvé pour « {query} »"
        f"  —  les commandes commencent par /  (ex: /help)[/{C.DIM}]"
    )
