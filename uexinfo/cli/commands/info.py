"""Commande /info — terminal (marché), commodité (prix), vaisseau."""
from __future__ import annotations

import re
import time
from datetime import datetime

from rich.table import Table

from uexinfo.api.uex_client import UEXClient, UEXError
from uexinfo.cache.models import Commodity, Terminal
from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_warn, section
from uexinfo.models.scan_result import ScanResult

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
                console.print(f"\n[bold {C.UEX}]▼ Acheter ici[/bold {C.UEX}]")
                entries = [
                    (_entry_ns(
                        r.get("commodity_name") or "?",
                        _scu(r.get("scu_buy"), r.get("scu_buy_max")),
                        r.get("status_buy"), buy=True,
                    ), _price_short(r.get("price_buy")))
                    for r in buy_rows
                ]
                console.print(_multi_col_table(
                    entries, ("Commodité (SCU)", "Achat"), n_cols,
                    f"italic {C.NEUTRAL}", f"italic {C.UEX}",
                ))

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

def _show_commodity(c: Commodity, ctx) -> None:
    flags = []
    if c.is_illegal:     flags.append("[red]illégal[/red]")
    if c.is_refinable:   flags.append("raffinable")
    if c.is_extractable: flags.append("extractable")
    flag_str = "  " + " · ".join(flags) if flags else ""

    player_sys = _player_system(ctx)
    sys_label = f"  [{C.DIM}]filtre : {player_sys}[/{C.DIM}]" if player_sys else ""
    section(f"Commodité — {c.name}  [{c.code}]{flag_str}{sys_label}")

    rows = _commodity_prices(c.id, ctx)
    if not rows:
        console.print(f"[{C.DIM}]Aucune donnée de prix disponible.[/{C.DIM}]")
        return

    if player_sys:
        rows = [r for r in rows if (r.get("star_system_name") or "").lower() == player_sys]

    active = [r for r in rows if r.get("price_buy") or r.get("price_sell")]
    if not active:
        console.print(
            f"[{C.DIM}]Aucun terminal actif"
            + (f" dans {player_sys}" if player_sys else "")
            + f".[/{C.DIM}]"
        )
        return

    # Résumé sur une ligne
    best_buy  = min((r["price_buy"]  for r in active if r.get("price_buy")),  default=0)
    best_sell = max((r["price_sell"] for r in active if r.get("price_sell")), default=0)
    parts = []
    if best_buy:  parts.append(f"Achat min : [{C.UEX}]{_price_fmt(best_buy)}[/{C.UEX}]")
    if best_sell: parts.append(f"Vente max : [{C.PROFIT}]{_price_fmt(best_sell)}[/{C.PROFIT}]")
    if best_buy and best_sell:
        spread = best_sell - best_buy
        color  = C.PROFIT if spread > 0 else C.LOSS
        parts.append(f"Écart : [{color}]{_price_fmt(spread)}[/{color}]")
    if parts:
        console.print("  ".join(parts))
        console.print()

    # Tri : both buy+sell → sell-only → buy-only
    def _sort_key(r):
        has_b = bool(r.get("price_buy"))
        has_s = bool(r.get("price_sell"))
        if has_b and has_s:
            return (0, -(r.get("price_sell") or 0))
        if has_s:
            return (1, -(r.get("price_sell") or 0))
        return (2, r.get("price_buy") or 0)

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Terminal",  style=C.NEUTRAL, no_wrap=True, min_width=18)
    tbl.add_column("Sys",       style=C.DIM,     no_wrap=True)
    tbl.add_column("Achat/SCU", style=C.UEX,     justify="right", no_wrap=True)
    tbl.add_column("Dispo",     style=C.DIM,     justify="right", no_wrap=True)
    tbl.add_column("Vente/SCU", style=C.PROFIT,  justify="right", no_wrap=True)
    tbl.add_column("Stock",     style=C.DIM,     justify="right", no_wrap=True)

    prev_group = None
    for r in sorted(active, key=_sort_key)[:30]:
        has_b = bool(r.get("price_buy"))
        has_s = bool(r.get("price_sell"))
        group = 0 if (has_b and has_s) else (1 if has_s else 2)
        if prev_group is not None and group != prev_group:
            tbl.add_section()  # séparateur horizontal entre groupes
        prev_group = group

        term  = _loc(r.get("terminal_name") or "?")
        sys   = r.get("star_system_name") or "?"
        buy   = _price_fmt(r.get("price_buy"))
        buy_s = _scu(r.get("scu_buy"), r.get("scu_buy_max"))
        sell  = _price_fmt(r.get("price_sell"))
        stock = _scu(r.get("scu_sell_stock"))
        tbl.add_row(term, sys, buy, buy_s, sell, stock)

    console.print(tbl)
    console.print(f"\n[{C.DIM}]{len(active)} terminaux  ·  Achat = où acheter  ·  Vente = où vendre[/{C.DIM}]")


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

@register("info")
def cmd_info(args: list[str], ctx) -> None:
    if not args:
        print_warn("Usage : /info <nom>   ou   /info terminal|commodity <nom>")
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
                _show_commodity(c, ctx)
        else:
            print_warn("/info ship — disponible en Phase 2.")
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
        _show_commodity(c, ctx)
        return
    # Fallback : terminal hors cache (Pyro, etc.) → requête directe par nom
    if _show_terminal_by_name(query, ctx):
        return

    console.print(
        f"[{C.DIM}]Rien trouvé pour « {query} »"
        f"  —  les commandes commencent par /  (ex: /help)[/{C.DIM}]"
    )
