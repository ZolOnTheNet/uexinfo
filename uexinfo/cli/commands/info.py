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

# TTL géré par PriceCache (adaptatif selon fréquence d'usage)


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

# Index des codes commodité — initialisé lazily
_comm_codes: dict[str, str] = {}  # commodity_name.lower() → code
_comm_codes_by_id: dict[int, str] = {}  # commodity_id → code


def _ensure_comm_codes(ctx) -> None:
    """Construit les index de codes à partir du cache (une seule fois)."""
    if _comm_codes:
        return
    for c in (ctx.cache.commodities or []):
        if c.code:
            _comm_codes[c.name.lower()] = c.code
            _comm_codes_by_id[c.id] = c.code


def _comm_code(name: str = "", cid: int = 0) -> str:
    """Retourne le code abrégé d'une commodité (ex: 'AGRI')."""
    if cid and cid in _comm_codes_by_id:
        return _comm_codes_by_id[cid]
    return _comm_codes.get(name.lower(), "")


def _abbrev_name(name: str, maxlen: int = _NAME_MAX, code: str = "") -> str:
    """Raccourcit les noms longs. Ex: 'Construction Materials' → 'Constr. Materials'.

    Si *code* est fourni et que le nom est tronqué, le code est ajouté : 'Agricultural Su… [AGRI]'.
    """
    if len(name) <= maxlen:
        return name
    parts = name.split()
    if len(parts) >= 3:
        candidate = parts[0] + " " + parts[-1]
        if len(candidate) <= maxlen:
            return candidate
    short = name[:maxlen - 1] + "…"
    if code:
        # \[ = crochet ouvrant littéral en Rich markup (évite que [CM] soit interprété comme tag)
        short = f"{short} [{C.DIM}]\\[{code}][/{C.DIM}]"
    return short


def _abbrev_terminal(name: str, maxlen: int) -> str:
    """Raccourcit un nom de terminal pour tenir dans maxlen caractères.

    Stratégies par ordre :
      1. Nom complet
      2. Mots intermédiaires → initiale. (ex: 'Shubin Mining Facility SCD-1' → 'Shubin M. F. SCD-1')
      3. Tous les mots sauf le dernier → initiale.
      4. Troncature avec …
    """
    if len(name) <= maxlen:
        return name
    parts = name.split()
    n = len(parts)
    if n <= 1:
        return name[:maxlen - 1] + "…"
    # Essai 1 : abréger les mots intermédiaires (index 1 à n-2)
    if n >= 3:
        candidate = " ".join(
            [parts[0]] + [p[0] + "." for p in parts[1:-1]] + [parts[-1]]
        )
        if len(candidate) <= maxlen:
            return candidate
    # Essai 2 : abréger tout sauf le dernier mot
    candidate = " ".join([p[0] + "." for p in parts[:-1]] + [parts[-1]])
    if len(candidate) <= maxlen:
        return candidate
    # Essai 3 : troncature
    return name[:maxlen - 1] + "…"


def _term_name_maxlen() -> int:
    """Calcule la largeur max du nom de terminal selon la largeur de la console.

    Utilise ~1/3 de la largeur disponible (les colonnes fixes en occupent ~2/3).
    Minimum 16 pour rester lisible.
    """
    w = getattr(console, "width", None) or 80
    return max(16, w // 3)


_STATUS_LABEL = {1: "Out", 2: "T.Bas", 3: "Bas", 4: "Moy", 5: "Haut", 7: "Max"}

# Achat : Max = blanc (abondant) → Out = rouge (épuisé)
_BUY_STATUS_COLOR  = {7: "bright_white", 5: "white", 4: "yellow", 3: "orange1", 2: "red1", 1: "red"}
# Vente : Out = blanc (terminal demandeur) → Max = rouge (terminal plein = bloquant)
_SELL_STATUS_COLOR = {1: "bright_white", 2: "white", 3: "yellow", 4: "orange1", 5: "red1", 7: "red"}


def _fmt_date(date_modified) -> str:
    """Format relatif compact depuis un timestamp Unix.
    1h 4h 8h 12h 16h 20h · 1j-9j · 1sem 2sem 3sem · 1M-8M · 9M+
    """
    if not date_modified:
        return ""
    try:
        diff = time.time() - float(date_modified)
        if diff < 0:
            return ""
        h = int(diff / 3600)
        d = int(diff / 86400)
        if h < 4:
            return "1h"
        elif h < 8:
            return "4h"
        elif h < 12:
            return "8h"
        elif h < 16:
            return "12h"
        elif h < 20:
            return "16h"
        elif h < 24:
            return "20h"
        elif d < 10:
            return f"{d}j"
        elif d < 14:
            return "1sem"
        elif d < 21:
            return "2sem"
        elif d < 28:
            return "3sem"
        else:
            m = max(1, int(d / 30))
            return f"{m}M" if m < 9 else "9M+"
    except Exception:
        return ""


def _entry_ns(name: str, scu_str: str, status: int | None, buy: bool, code: str = "") -> str:
    """Formate 'NomCourt (SCU)' avec le SCU coloré selon le statut de stock."""
    short = _abbrev_name(name, code=code)
    s = int(status or 0)
    color_map = _BUY_STATUS_COLOR if buy else _SELL_STATUS_COLOR
    color = color_map.get(s, C.DIM)
    return f"{short} ([{color}]{scu_str}[/{color}])"


def _n_cols(term_w: int) -> int:
    """Calcule le nombre de colonnes selon la largeur du terminal.

    Chaque paire (nom 26 car + prix 12 car + paddings) ≈ 42 chars.
    On cible 3 colonnes pour un terminal standard (≥ 125) et 4 pour les larges (≥ 170).
    """
    if term_w >= 170:
        return 4
    if term_w >= 125:
        return 3
    if term_w >= 80:
        return 2
    return 1


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
    """Retire le préfixe service ('Admin - ', 'Shop - ', …).
    Exception TDD : retourne 'TDD - <lieu>' pour garder le contexte.
    """
    from uexinfo.display.formatter import shorten_terminal_name
    short = shorten_terminal_name(full_name)
    if short != full_name:
        return short  # ex. "TDD - Area 18"
    return full_name.rsplit(" - ", 1)[-1].strip()


def _dot_name(
    terminal_name: str,
    star_system: str = "",
    player_system: str = "",
    space_station: str = "",
    planet: str = "",
    orbit: str = "",
) -> str:
    """Notation pointée : [Système.]Station.service

    Règles :
    - service  = partie avant ' - ' (minuscule), ex. 'admin', 'shop'
    - station  = partie après ' - ' ; sinon space_station / orbit / planet
    - système  = affiché seulement si différent du système courant du joueur
    """
    from uexinfo.display.formatter import shorten_terminal_name
    name = shorten_terminal_name(terminal_name.strip())
    if " - " in name:
        service_raw = name.split(" - ", 1)[0].strip()
        service = service_raw.lower()
        # Pour les noms multi-segments ("TDD - Trade and Dev Division - Area 18"),
        # on veut le dernier segment (le lieu réel), pas le second.
        station = _loc(name)
    else:
        # Pas de séparateur : le nom entier est le lieu, pas de type de service
        service = ""
        station = (
            space_station or name
        )

    # Fallback station depuis les champs de localisation
    if not station:
        station = space_station or orbit or planet or name

    parts: list[str] = []
    if star_system and star_system.lower() != player_system.lower():
        parts.append(star_system)
    parts.append(station)
    if service:
        parts.append(service)

    return ".".join(parts)


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


# ── Cache prix — délégué au DataManager ────────────────────────────────────────

from uexinfo.cache.data_manager import DataManager as _DM, Source as _Source


def _fetch_prices(key: str, api_kwargs: dict, ctx) -> list[dict]:
    """Compatibilité — délègue à DataManager.fetch_prices, retourne seulement les données."""
    data, _src = _DM.fetch_prices(key, api_kwargs, ctx)
    return data


def _to_slug(name: str) -> str:
    s = name.lower().replace(" - ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    return s.strip("-")


def _terminal_prices(t: Terminal, ctx) -> list[dict]:
    rows, _src = _DM.terminal_prices(t, ctx)
    return rows


def _commodity_prices(c_id: int, ctx) -> list[dict]:
    data, _src = _DM.commodity_prices(c_id, ctx)
    return data




def _add_graph_distances(dist_map: dict[str, float], origin_t_obj, ctx) -> None:
    """Complète dist_map avec les distances Dijkstra du graphe de transport local.

    Ne remplace pas les entrées déjà présentes (priorité UEX API).
    Utilise le dictionnaire d'alias pour résoudre les noms de nœuds.
    """
    if not origin_t_obj:
        return
    alias_map = _get_site_alias_map(ctx)
    origin_node_name = alias_map.get(_site_key(origin_t_obj).lower())
    if not origin_node_name:
        return
    graph = ctx.cache.transport_graph
    graph_dists = graph.find_all_distances(origin_node_name)
    if not graph_dists:
        return
    for t in ctx.cache.terminals:
        t_lo   = t.name.lower()
        loc_lo = _loc(t.name).lower()
        if t_lo in dist_map or loc_lo in dist_map:
            continue
        # Résoudre le terminal destination vers son nœud graphe via l'alias
        dest_node = alias_map.get(_site_key(t).lower())
        d = graph_dists.get(dest_node) if dest_node else None
        if d is not None and d > 0:
            dist_map[t_lo] = d
            if loc_lo != t_lo:
                dist_map[loc_lo] = d


def _fetch_route_distances(terminal_id: int, ctx) -> dict[str, float]:
    """Retourne {terminal_name_lower: distance_gm} depuis terminal_id.

    Sources (par ordre de priorité) :
    1. API UEX routes (si disponible)
    2. Graphe de transport local (fallback)

    Enrichit automatiquement le graphe de transport avec les distances UEX découvertes.
    """
    key = f"rd_{terminal_id}"

    # Récupérer le terminal d'origine (nécessaire pour le graphe local)
    origin_t_obj = None
    origin_terminal = None
    for t in ctx.cache.terminals:
        if t.id == terminal_id:
            origin_t_obj = t
            origin_terminal = t.name
            break

    # Cache valide ET non-vide → retour direct
    cached = ctx._price_cache.get(key)
    if cached:
        _ts, data = cached
        if data:
            return data
        # Données vides en cache → complète depuis le graphe local sans re-fetch
        dist_map = {}
        _add_graph_distances(dist_map, origin_t_obj, ctx)
        return dist_map

    client = UEXClient()
    try:
        routes = client.get_routes(id_terminal_origin=terminal_id)
    except UEXError:
        routes = []

    # Index terminal → système depuis le cache statique (pour éviter les "Unknown")
    _term_sys: dict[str, str] = {
        t.name: (t.star_system_name or "Unknown")
        for t in ctx.cache.terminals
    }

    dist_map: dict[str, float] = {}
    enriched_count = 0

    for route in routes:
        dest = route.get("terminal_name_destination") or ""
        dist = route.get("distance")
        if dest and dist is not None:
            dist_gm = float(dist)          # l'API retourne déjà en Gm
            dist_map[dest.lower()] = dist_gm

            # Enrichir le graphe de transport (opportuniste)
            if origin_terminal:
                n = ctx.cache.transport_graph.propagate_distances(
                    from_node=origin_terminal,
                    to_node=dest,
                    distance_gm=dist_gm,
                    edge_type=EdgeType.QUANTUM,
                    source="uex",
                    timestamp=time.time(),
                )
                if n:
                    enriched_count += 1

                # Corriger le système des nœuds auto-créés ("Unknown")
                graph = ctx.cache.transport_graph
                for node_name in (origin_terminal, dest):
                    node = graph.nodes.get(node_name)
                    if node and node.system == "Unknown":
                        sys_fixed = _term_sys.get(node_name)
                        if sys_fixed and sys_fixed != "Unknown":
                            node.system = sys_fixed

    # Afficher un feedback discret si enrichissement
    if enriched_count > 0:
        console.print(
            f"[{C.DIM}]⊕ Graphe enrichi : {enriched_count} nouvelle(s) route(s)[/{C.DIM}]"
        )

    # ── Fallback : graphe de transport local ─────────────────────────────────
    _add_graph_distances(dist_map, origin_t_obj, ctx)

    ctx._price_cache[key] = (time.time(), dist_map)
    return dist_map




def _fetch_container_sizes(commodity_id: int, ctx) -> dict[str, str]:
    """Retourne {terminal_name_lower: 'tailles'} pour une commodité.

    Utilise /commodities_routes?id_commodity=X — champ container_sizes_origin.
    Ex: {'terra gateway': '1·2·4', 'grimhex': '1·2'}
    """
    key = f"cs_{commodity_id}"
    cached = ctx._price_cache.get(key)
    if cached:
        _ts, data = cached
        return data

    client = UEXClient()
    try:
        routes = client.get_routes(id_commodity=commodity_id)
    except UEXError:
        return {}

    sizes: dict[str, str] = {}
    for route in routes:
        # origin
        t_orig = (route.get("origin_terminal_name") or "").strip()
        cs_orig = route.get("container_sizes_origin")
        if t_orig and cs_orig:
            sizes[t_orig.lower()] = _fmt_container_sizes(cs_orig)
        # destination
        t_dest = (route.get("destination_terminal_name") or "").strip()
        cs_dest = route.get("container_sizes_destination")
        if t_dest and cs_dest:
            sizes[t_dest.lower()] = _fmt_container_sizes(cs_dest)

    ctx._price_cache[key] = (time.time(), sizes)
    return sizes


def _fmt_container_sizes(raw, short: bool = False) -> str:
    """Formate container_sizes en '1/2/4' ou '1-4' (short).

    raw peut être une liste [1,2,4], une chaîne '1,2,4', ou un int.
    short=True → format compact min-max (ex: '8-32').
    """
    if not raw:
        return "—"
    if isinstance(raw, (int, float)):
        return str(int(raw))
    if isinstance(raw, list):
        vals = sorted({int(v) for v in raw if str(v).isdigit()})
    else:
        vals = sorted({int(v.strip()) for v in str(raw).split(",") if v.strip().isdigit()})
    if not vals:
        return "—"
    if short:
        return str(vals[0]) if len(vals) == 1 else f"{vals[0]}-{vals[-1]}"
    return "/".join(str(v) for v in vals)


def _short_sizes(s: str) -> str:
    """Convertit '8/16/24/32' ou '1·2·4' → '8-32' ou '1-4'. Passe-plat si déjà court ou vide."""
    if not s or s == "—":
        return ""
    # Déjà au format court (ex: "8-32")
    if "-" in s and "/" not in s and "·" not in s:
        return s
    # Extraire les nombres
    import re
    vals = sorted({int(v) for v in re.findall(r'\d+', s)})
    if not vals:
        return ""
    return str(vals[0]) if len(vals) == 1 else f"{vals[0]}-{vals[-1]}"


def _fetch_terminal_container_sizes(terminal_id: int, ctx) -> dict:
    """Retourne les données de routes depuis un terminal (un seul appel API).

    Clé = commodity_name_lower → {
        "origin_sizes": "8-32",
        "dest_sizes":   {"dest_name_lower": "8-32"},
        "best_route":   {   # meilleur trade UEX pour cette commodité
            "dest_name": str, "dest_system": str,
            "dest_planet": str, "dest_orbit": str, "dest_station": str,
            "price_sell": float, "profit": float, "distance": float, "score": float,
        } | None
    }
    """
    import time as _time
    cache_key = f"tcs_{terminal_id}"
    cached = ctx._price_cache.get(cache_key)
    if cached and _time.time() - cached[0] < 300:
        return cached[1]

    try:
        routes = UEXClient().get_routes(id_terminal_origin=terminal_id)
    except UEXError:
        return {}

    # Grouper par commodité — garder toutes les routes + meilleure non filtrée
    result: dict = {}
    for route in routes:
        cname = (route.get("commodity_name") or "").lower()
        if not cname:
            continue
        if cname not in result:
            result[cname] = {
                "origin_sizes": _fmt_container_sizes(route.get("container_sizes_origin"), short=True),
                "dest_sizes": {},
                "best_route": None,
                "routes": [],   # toutes les routes (pour filtrage à l'affichage)
            }
        dest = (route.get("destination_terminal_name") or "").lower()
        if dest:
            result[cname]["dest_sizes"][dest] = _fmt_container_sizes(route.get("container_sizes_destination"), short=True)
        score = float(route.get("score") or 0)
        rdict = {
            "_score":      score,
            "dest_name":   route.get("destination_terminal_name") or "",
            "dest_system": route.get("destination_star_system_name") or "",
            "dest_planet": route.get("destination_planet_name") or "",
            "dest_orbit":  route.get("destination_orbit_name") or "",
            "dest_station":route.get("destination_space_station_name") or "",
            "price_sell":  float(route.get("price_destination") or 0),
            "profit":      float(route.get("profit") or 0),
            "distance":    float(route.get("distance") or 0),
        }
        result[cname]["routes"].append(rdict)
        prev = result[cname]["best_route"]
        if prev is None or score > prev.get("_score", 0):
            result[cname]["best_route"] = rdict

    ctx._price_cache[cache_key] = (_time.time(), result)
    return result


# ── Données scan ───────────────────────────────────────────────────────────────

_STOCK_LABELS = {1: "Out", 2: "Très bas", 3: "Bas", 4: "Moyen", 5: "Haut", 7: "Max"}
_STOCK_COLORS = {1: C.DIM, 2: "red", 3: "yellow", 4: C.UEX, 5: C.PROFIT, 7: C.PROFIT}


def _find_scan(loc_name: str, ctx) -> ScanResult | None:
    """Trouve le scan le plus récent dont le nom correspond à ce terminal."""
    if not ctx.scan_history:
        return None
    q = loc_name.lower()
    for result in reversed(ctx.scan_history):
        if not isinstance(result, ScanResult):
            continue
        t = result.terminal.lower()
        if q in t or t in q:
            return result
    return None


def _show_scan_section(result: ScanResult, ctx) -> None:
    """Affiche les données d'un ScanResult dans le contexte d'un terminal."""
    ago_s = int((datetime.now() - result.timestamp).total_seconds())
    ago_str = f"{ago_s // 60} min" if ago_s < 3600 else f"{ago_s // 3600} h"

    if result.source == "log":
        if result.validated:
            badge = f"  [bold green]✓ validé UEX[/bold green]"
        else:
            badge = f"  [{C.DIM}]en attente[/{C.DIM}]"
    else:
        badge = ""

    console.print(
        f"[bold]Scan joueur[/bold]"
        f"  [{C.DIM}]{result.source} · il y a {ago_str} · données confirmées[/{C.DIM}]"
        + badge
    )
    if not result.commodities:
        console.print(f"[{C.DIM}]Aucune commodité scannée.[/{C.DIM}]")
        return

    # Récupérer les prix UEX du terminal pour comparaison / fallback prix=0
    uex_prices: dict[int, int] = {}      # commodity_id → prix UEX
    uex_prices_by_name: dict[str, int] = {}  # commodity_name.lower() → prix UEX
    terminal_name_q = result.terminal.replace("_", " ").lower().strip()
    all_terminals = ctx.cache.terminals if hasattr(ctx.cache, "terminals") else []
    matched_terminal = next(
        (t for t in all_terminals if t.name.lower() == terminal_name_q
         or t.name.lower().endswith(f"- {terminal_name_q}")
         or terminal_name_q in t.name.lower()),
        None,
    )
    if matched_terminal:
        t_rows = _fetch_prices(f"t{matched_terminal.id}", {"id_terminal": matched_terminal.id}, ctx)
        is_sell = result.mode == "sell"
        price_field = "price_sell" if is_sell else "price_buy"
        for r in t_rows:
            cid = int(r.get("id_commodity") or 0)
            p = int(r.get(price_field) or 0)
            if p:
                if cid:
                    uex_prices[cid] = p
                cname = (r.get("commodity_name") or "").lower()
                if cname:
                    uex_prices_by_name[cname] = p

    # Charger les prix persistants (édités via /scan edit) pour overlay
    from uexinfo.cache.scan_prices import ScanPriceStore
    _store_key_q = str(matched_terminal.id) if matched_terminal and matched_terminal.id else f"name:{terminal_name_q}"
    store_rows = ScanPriceStore().get_rows(_store_key_q)
    store_prices: dict[int, int] = {}       # commodity_id → prix store
    store_prices_by_name: dict[str, int] = {}  # name.lower() → prix store
    is_sell = result.mode == "sell"
    store_price_field = "price_sell" if is_sell else "price_buy"
    for sr in store_rows:
        sp = sr.get(store_price_field) or 0
        if sp:
            scid = sr.get("commodity_id") or 0
            if scid:
                store_prices[scid] = sp
            sname = (sr.get("commodity_name") or "").lower()
            if sname:
                store_prices_by_name[sname] = sp

    tbl = Table(show_header=True, box=None, padding=(0, 1))
    tbl.add_column("Commodité", style=C.NEUTRAL, no_wrap=True, min_width=20)
    tbl.add_column(f"Prix/{C.SCU}", justify="right", no_wrap=True)
    tbl.add_column(f"UEX/{C.SCU}", style=f"italic {C.DIM}", justify="right", no_wrap=True)
    tbl.add_column(C.SCU,          style=C.DIM,              justify="right", no_wrap=True)
    tbl.add_column("Stock",        no_wrap=True)

    for sc in sorted(result.commodities, key=lambda s: s.name):
        uex_p = uex_prices.get(sc.commodity_id) or uex_prices_by_name.get(sc.name.lower(), 0)
        # Prix persistant (édité) prioritaire sur la valeur OCR en mémoire
        stored_p = store_prices.get(sc.commodity_id) or store_prices_by_name.get(sc.name.lower(), 0)
        price_corrected = False
        if stored_p:
            price_val = stored_p
        elif sc.price:
            price_val = sc.price
        elif result.validated and uex_p:
            price_val = uex_p
            price_corrected = True
        else:
            price_val = 0

        if price_corrected:
            price_str = f"[{C.DIM}]~{_price_fmt(price_val)}[/{C.DIM}]"
        elif price_val:
            price_str = _price_fmt(price_val)
        else:
            price_str = "—"

        uex_str = _price_fmt(uex_p) if uex_p else "—"
        qty   = str(sc.quantity) if sc.quantity is not None else "—"
        color = _STOCK_COLORS.get(sc.stock_status, C.DIM)
        label = _STOCK_LABELS.get(sc.stock_status, sc.stock or "?")
        tbl.add_row(sc.name, price_str, uex_str, qty, f"[{color}]{label}[/{color}]")
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


def _find_best_buyers(id_commodity: int, origin_terminal_id: int, ctx,
                      player_dest: str = "", sys_filter=None) -> list[dict]:
    """Trouve les terminaux achetant cette commodité (price_sell > 0), triés par :
    1. Destination du joueur (si définie)
    2. Prix de vente (décroissant)
    Exclut le terminal d'origine. Retourne les 3 meilleurs acheteurs.
    sys_filter : None=système joueur, []=tous, [str,…]=liste explicite.
    """
    if not id_commodity:
        return []

    rows = _commodity_prices(id_commodity, ctx)

    # Calcul du filtre effectif (même logique que _show_commodity)
    player_sys = _player_system(ctx)
    if sys_filter is None:
        effective_filter: list[str] | None = [player_sys] if player_sys else None
    elif sys_filter == []:          # --all
        effective_filter = None
    else:
        effective_filter = sys_filter

    # Terminaux acheteurs (price_sell > 0), hors terminal d'origine, filtrés par système
    buyers = [
        r for r in rows
        if r.get("price_sell")
        and int(r.get("id_terminal") or 0) != origin_terminal_id
        and (not effective_filter
             or (r.get("star_system_name") or "").lower() in effective_filter)
    ]

    if not buyers:
        return []

    def sort_key(row):
        terminal = (row.get("terminal_name") or "").lower()
        is_player_dest = 1 if player_dest and terminal == player_dest else 0
        price = float(row.get("price_sell") or 0)
        return (-is_player_dest, -price)

    return sorted(buyers, key=sort_key)[:3]


def _pick_best_allowed_route(routes: list, filters: dict, ctx) -> dict | None:
    """Retourne la meilleure route filtrée selon les filtres /select."""
    from uexinfo.cli.commands.select import is_destination_allowed
    term_by_name = {t.name.lower(): t for t in (ctx.cache.terminals or [])}
    allowed = []
    for r in routes:
        dn = (r.get("dest_name") or "").lower()
        t_obj = term_by_name.get(dn)
        if t_obj is None:
            # Terminal Pyro absent du cache → laisser passer
            allowed.append(r)
        elif is_destination_allowed(t_obj, filters):
            allowed.append(r)
    if not allowed:
        return None
    best = max(allowed, key=lambda r: r.get("_score", 0))
    return {k: v for k, v in best.items() if k != "_score"}


def _find_best_allowed_from_prices(id_commodity: int, buy_price: float,
                                    filters: dict, ctx) -> dict | None:
    """Fallback : trouve la meilleure destination autorisée via commodities_prices.

    Utilisé quand les routes pré-calculées UEX sont toutes filtrées (ex. Pyro exclu).
    """
    import time as _time
    from uexinfo.cli.commands.select import is_destination_allowed

    cache_key = f"cprices_{id_commodity}"
    cached = ctx._price_cache.get(cache_key)
    if cached and _time.time() - cached[0] < 300:
        all_prices = cached[1]
    else:
        try:
            all_prices = UEXClient().get_prices(id_commodity=id_commodity)
            ctx._price_cache[cache_key] = (_time.time(), all_prices)
        except UEXError:
            return None

    term_by_name = {t.name.lower(): t for t in (ctx.cache.terminals or [])}
    best: dict | None = None
    best_roi = -1.0

    for p in all_prices:
        sell = float(p.get("price_sell") or 0)
        if sell <= 0 or buy_price <= 0 or sell <= buy_price:
            continue
        dn = (p.get("terminal_name") or "").lower()
        t_obj = term_by_name.get(dn)
        if t_obj is None:
            continue  # Terminal inconnu (Pyro hors cache) → skip en fallback
        if not is_destination_allowed(t_obj, filters):
            continue
        roi = (sell - buy_price) / buy_price
        if roi > best_roi:
            best_roi = roi
            best = {
                "dest_name":    p.get("terminal_name") or "",
                "dest_system":  t_obj.star_system_name or "",
                "dest_planet":  t_obj.planet_name or "",
                "dest_orbit":   t_obj.orbit_name or "",
                "dest_station": t_obj.space_station_name or "",
                "price_sell":   sell,
                "profit":       sell - buy_price,
                "distance":     0.0,
            }

    return best


def _show_buy_detailed(buy_rows: list[dict], origin_terminal: Terminal, ctx, sys_filter=None) -> None:
    """Affiche la section Acheter avec table alignée, triée par profit décroissant."""
    # Récupérer le cargo du vaisseau actif
    ship_cargo = 0
    if ctx.player.active_ship:
        for ship in ctx.player.ships:
            if ship.name == ctx.player.active_ship:
                ship_cargo = ship.scu
                break

    if ship_cargo == 0:
        console.print(f"[{C.WARNING}]⚠  Vaisseau actif non défini ou cargo = 0 {C.SCU}[/{C.WARNING}]")
        console.print(f"[{C.DIM}]   Utilisez /ship set <nom> pour définir votre vaisseau[/{C.DIM}]")
        return

    player_dest = (ctx.player.destination or "").lower().strip()
    hint = f"  [{C.DIM}](⭐ = vendable à destination)[/{C.DIM}]" if player_dest else ""
    pc = C.SCTRADE if getattr(ctx, "_api_offline", False) else C.UEX
    console.print(f"\n[bold {pc}]▼ Acheter sur place[/bold {pc}]{hint}")
    origin_system = origin_terminal.star_system_name

    # ── Distances via API UEX (même logique que _show_commodity) ─────────
    dist_map: dict[str, float] = {}
    player_sys = _player_system(ctx)

    # ── Routes UEX : tailles cargo + destinations (UN seul appel API) ─────
    cargo_sizes: dict = {}
    if origin_terminal.id:
        cargo_sizes = _fetch_terminal_container_sizes(origin_terminal.id, ctx)

    # Filtres /select
    _sel = ctx.cfg.get("filters", {})

    # Meilleure route filtrée par commodité — itère sur buy_rows (source de vérité)
    _best_filtered: dict[str, dict | None] = {}
    _has_filters = any(
        (isinstance(v, dict) and (v.get("include") or v.get("exclude")))
        for v in _sel.values()
    )
    for _r in buy_rows:
        _ckey = (_r.get("commodity_name") or "").lower()
        if not _ckey:
            continue
        cs_v = cargo_sizes.get(_ckey, {})
        if _has_filters:
            best = _pick_best_allowed_route(cs_v.get("routes", []), _sel, ctx)
            if best is None:
                # Fallback : UEX ne propose que des routes vers des systèmes filtrés
                _cid  = int(_r.get("id_commodity") or 0)
                _pbuy = float(_r.get("price_buy") or 0)
                if _cid and _pbuy > 0:
                    best = _find_best_allowed_from_prices(_cid, _pbuy, _sel, ctx)
            _best_filtered[_ckey] = best
        else:
            _best_filtered[_ckey] = cs_v.get("best_route")

    # dist_map construit depuis les meilleures routes filtrées (pas d'appel séparé)
    dist_map: dict[str, float] = {
        br["dest_name"].lower(): br["distance"]
        for br in _best_filtered.values()
        if br and br.get("dest_name") and br.get("distance")
    }

    # ── Construire toutes les lignes avec calculs ──────────────────────────
    entries: list[tuple[float, dict]] = []   # (profit_full, data)

    _ensure_comm_codes(ctx)
    # Table nom→id pour résoudre les scans joueur sans id
    _comm_name_to_id: dict[str, int] = {
        c.name.lower(): c.id
        for c in (getattr(ctx.cache, "commodities", None) or [])
        if c.id
    }

    for r in buy_rows:
        name       = r.get("commodity_name", "?")
        id_comm    = int(r.get("id_commodity") or 0)
        if not id_comm:
            id_comm = _comm_name_to_id.get(name.lower(), 0)
        scu_min    = int(r.get("scu_buy") or 0)
        scu_max    = int(r.get("scu_buy_max") or scu_min)
        price_buy  = float(r.get("price_buy") or 0)
        status_buy = int(r.get("status_buy") or 0)
        _ts_buy    = r.get("_scan_ts") if r.get("_player_buy") else r.get("date_modified")
        date_buy   = _fmt_date(_ts_buy)

        stock_multiplier = {1: 0, 2: 0.2, 3: 0.4, 4: 0.6, 5: 0.8, 7: 1.0}
        stock_percent    = stock_multiplier.get(status_buy, 0.5)
        stock_available  = int(ship_cargo * stock_percent) if status_buy != 1 else 0
        qty_buy          = min(ship_cargo, stock_available) if stock_available > 0 else ship_cargo
        total_buy        = qty_buy * price_buy

        # ── Destination : meilleure route filtrée par les filtres /select catégorie
        cs_entry   = cargo_sizes.get(name.lower(), {})
        best_route = _best_filtered.get(name.lower())

        if best_route and best_route.get("dest_name"):
            dest_name      = best_route["dest_name"]
            dest_system    = best_route["dest_system"]
            price_sell     = best_route["price_sell"]
            total_sell_opt = qty_buy * price_sell
            profit_opt     = total_sell_opt - total_buy
            qty_sell_lim   = qty_buy
            qty_unsold     = 0
            risk_pct       = 20
            dest_display   = _dot_name(
                dest_name, dest_system, origin_system,
                space_station=best_route.get("dest_station") or "",
                planet=best_route.get("dest_planet") or "",
                orbit=best_route.get("dest_orbit") or "",
            )
            dest_style   = "underline" if dest_name.lower() == player_dest else ""
            dest_tag     = f"{dest_style} {C.LABEL}".strip()
            distance_str = _dist_label(dest_name, dest_system, player_sys, dist_map)
        else:
            # Pas de route connue → afficher sans destination, zéro appel API
            dest_name      = ""
            dest_display   = f"[{C.DIM}]—[/{C.DIM}]"
            dest_tag       = C.DIM
            price_sell     = 0.0
            qty_sell_lim   = qty_buy
            qty_unsold     = 0
            total_sell_opt = 0.0
            profit_opt     = -total_buy
            risk_pct       = 100
            distance_str   = ""

        comm_code = _comm_code(name, id_comm)
        # Tailles conteneurs (cs_entry déjà calculé plus haut)
        orig_sz = cs_entry.get("origin_sizes", "")
        dest_sz = cs_entry.get("dest_sizes", {}).get(dest_name.lower(), "") if dest_name else ""

        entries.append((profit_opt, {
            "name": name, "code": comm_code,
            "scu_range": _notable_scu(_scu(scu_min, scu_max)),
            "price_buy": price_buy, "date": date_buy,
            "dest": dest_display, "dest_tag": dest_tag,
            "price_sell": price_sell,
            "qty": qty_buy, "qty_sell": qty_sell_lim,
            "total_buy": total_buy,
            "total_sell": total_sell_opt, "profit": profit_opt,
            "risk": risk_pct, "unsold": qty_unsold,
            "distance": distance_str,
            "dest_name_raw": dest_name,
            "_player": r.get("_player_buy", False),
            "orig_sizes": orig_sz, "dest_sizes": dest_sz,
        }))

    # ── Trier : destination prioritaire, puis ROI décroissant ───────────
    def _roi_key(e):
        d = e[1]
        pb = d.get("price_buy") or 0
        ps = d.get("price_sell") or 0
        roi = (ps - pb) / pb if pb else -1e9
        prio = 0 if (player_dest and d.get("dest_name_raw", "").lower() == player_dest) else 1
        return (prio, -roi)

    entries.sort(key=_roi_key)

    # ── Afficher en table alignée ─────────────────────────────────────────
    has_player = any(d.get("_player") for _, d in entries)

    tbl = Table(show_header=True, box=None, padding=(0, 1), show_edge=False)
    tbl.add_column("Commodité",      no_wrap=True, min_width=14)
    tbl.add_column(f"Prix/{C.SCU}",  justify="right", no_wrap=True)
    tbl.add_column("Âge",            style=C.DIM,    justify="right", no_wrap=True)
    tbl.add_column("→ Dest",         no_wrap=True,   min_width=20, max_width=32)
    tbl.add_column(f"→Prix/{C.SCU}", justify="right", no_wrap=True)
    tbl.add_column("ROI",            justify="right", no_wrap=True)
    tbl.add_column("Dist",           style=C.DIM,    justify="right", no_wrap=True)
    tbl.add_column(C.SCU,            style=C.DIM,    justify="right", no_wrap=True)
    tbl.add_column("T.Cargo",        style=C.DIM,    no_wrap=True)
    tbl.add_column("Coût",           style=C.DIM,    justify="right", no_wrap=True)
    tbl.add_column("Vente",          justify="right", no_wrap=True)
    tbl.add_column("Profit",         justify="right", no_wrap=True)
    tbl.add_column("Risque",         justify="right", no_wrap=True)

    for _, d in entries:
        profit  = d["profit"]
        p_color = C.PROFIT if profit > 0 else (C.LOSS if profit < 0 else C.DIM)
        p_sign  = "+" if profit > 0 else ""
        player  = d.get("_player", False)

        pb = d.get("price_buy") or 0
        ps = d.get("price_sell") or 0
        if pb and ps:
            roi_val = (ps - pb) / pb * 100
            r_color = C.PROFIT if roi_val > 5 else (C.LOSS if roi_val < 0 else C.NEUTRAL)
            r_sign  = "+" if roi_val >= 0 else ""
            roi_cell = f"[{r_color}]{r_sign}{roi_val:.0f}%[/{r_color}]"
        else:
            roi_cell = f"[{C.DIM}]—[/{C.DIM}]"

        # Risque : vert <20%, orange 20-50%, rouge >50%
        risk = d.get("risk", 0)
        if risk <= 15:
            risk_cell = f"[{C.PROFIT}]{risk}%[/{C.PROFIT}]"
        elif risk <= 45:
            risk_cell = f"[{C.WARNING}]{risk}%[/{C.WARNING}]"
        else:
            risk_cell = f"[{C.LOSS}]{risk}%[/{C.LOSS}]"

        name_raw = _abbrev_name(d["name"], 16, code=d.get("code", ""))
        if d["scu_range"]:
            name_raw = f"{name_raw} [dim]({d['scu_range']})[/dim]"
        if player:
            name_cell  = f"[bold {C.NEUTRAL}]★ {name_raw}[/bold {C.NEUTRAL}]"
            price_cell = f"[bold {C.UEX}]{_price_short(d['price_buy'])}[/bold {C.UEX}]"
            sell_cell  = f"[bold {C.PROFIT}]{_price_short(d.get('price_sell'))}[/bold {C.PROFIT}]"
        else:
            name_cell  = f"[italic {C.NEUTRAL}]{name_raw}[/italic {C.NEUTRAL}]"
            price_cell = f"[italic {C.UEX}]{_price_short(d['price_buy'])}[/italic {C.UEX}]"
            sell_cell  = f"[italic {C.PROFIT}]{_price_short(d.get('price_sell'))}[/italic {C.PROFIT}]"

        dest_str = f"[{d['dest_tag']}]{d['dest']}[/{d['dest_tag']}]"
        if player_dest and d.get("dest_name_raw", "").lower() == player_dest:
            dest_str = f"⭐ {dest_str}"

        scu_cell = str(d["qty"])
        if d["unsold"]:
            scu_cell = f"[{C.WARNING}]{d['qty_sell']}/{d['qty']}[/{C.WARNING}]"

        # T.Cargo : tailles origine → destination (format compact min-max)
        o_sz = _short_sizes(d.get("orig_sizes", ""))
        d_sz = _short_sizes(d.get("dest_sizes", ""))
        if o_sz and d_sz and o_sz != d_sz:
            cargo_cell = f"{o_sz}→{d_sz}"
        elif o_sz:
            cargo_cell = o_sz
        elif d_sz:
            cargo_cell = d_sz
        else:
            cargo_cell = f"[{C.DIM}]—[/{C.DIM}]"

        tbl.add_row(
            name_cell,
            price_cell,
            d["date"],
            dest_str,
            sell_cell,
            roi_cell,
            d["distance"],
            scu_cell,
            cargo_cell,
            _price_short(d["total_buy"]),
            _price_short(d["total_sell"]),
            f"[{p_color}]{p_sign}{_price_short(profit)}[/{p_color}]",
            risk_cell,
        )
    if has_player:
        console.print(f"[{C.DIM}]★ = données joueur (confirmées)[/{C.DIM}]")
    console.print(tbl)

    # Stocker les entrées pour l'overlay (boutons → Voyage + input SCU)
    # Uniquement les entrées avec une destination connue (sinon bouton inutile)
    ctx.last_terminal_buy_entries = {
        "origin": _loc(origin_terminal.name),
        "origin_id": origin_terminal.id,
        "entries": [
            {
                "idx":        i,
                "name":       d["name"],
                "code":       d.get("code", ""),
                "price_buy":  int(d["price_buy"]),
                "price_sell": int(d["price_sell"]),
                "dest":       d["dest_name_raw"],
                "dest_display": d["dest"],
                "qty":        d["qty"],
                "profit":     int(d["profit"]),
                "risk":       d.get("risk", 0),
                "distance":   d.get("distance", ""),
            }
            for i, (_, d) in enumerate(entries)
            if d.get("dest_name_raw")   # seulement si destination connue
        ],
    }


# ── Affichage site ─────────────────────────────────────────────────────────────

_NON_SHOP_TYPES = frozenset({"commodity", "commodity_raw", "refinery", "fuel"})


def _site_key(t: Terminal) -> str:
    """Clé de site : space_station > city > orbit > name."""
    return (t.space_station_name or t.city_name or t.orbit_name or t.name).strip()


def _site_terminals(t: Terminal, ctx) -> list[Terminal]:
    """Tous les terminaux appartenant au même site."""
    key = _site_key(t).lower()
    return [
        x for x in ctx.cache.terminals
        if (x.space_station_name or x.city_name or x.orbit_name or x.name).strip().lower() == key
    ]


def _svc_name(t: Terminal) -> str:
    """Nom court du service : partie avant ' - ', sinon displayname/nickname/nom."""
    if " - " in t.name:
        return t.name.split(" - ", 1)[0].strip()
    return (t.displayname or t.nickname or _loc(t.name)).strip()


def _get_site_alias_map(ctx) -> dict[str, str]:
    """Dictionnaire d'alias : site_key_lower → nom du nœud dans le graphe.

    Construit une seule fois et mis en cache sur ctx.
    Stratégie : pour chaque site unique, essaye les noms candidats
    (exact, premier mot, deux premiers mots) contre les nœuds du graphe.
    """
    if hasattr(ctx, "_site_alias_map"):
        return ctx._site_alias_map

    graph = ctx.cache.transport_graph
    alias_map: dict[str, str] = {}
    seen: set[str] = set()

    for t in ctx.cache.terminals:
        site = _site_key(t).lower()
        if site in seen:
            continue
        seen.add(site)

        # Candidats ordonnés par priorité
        candidates: list[str] = []
        for field in (_site_key(t), t.city_name, _loc(t.name), t.space_station_name, t.orbit_name, t.name):
            if field:
                candidates.append(field)
                # Premier mot (ex: "ARC-L3" de "ARC-L3 Modern Express Station")
                first = field.split()[0]
                if first != field and len(first) >= 3:
                    candidates.append(first)
                # Deux premiers mots (ex: "Everus Harbor")
                words = field.split()
                if len(words) >= 2:
                    candidates.append(" ".join(words[:2]))

        for c in candidates:
            node = graph.find_node_by_alias(c)
            if node:
                alias_map[site] = node.name
                break

    ctx._site_alias_map = alias_map
    return alias_map


def _site_graph_node(t: Terminal, ctx):
    """Retourne le LocationNode correspondant au site du terminal, ou None.

    Utilise le dictionnaire d'alias (construit une fois) pour résoudre
    le nom court du nœud dans le graphe de transport.
    """
    alias_map = _get_site_alias_map(ctx)
    node_name = alias_map.get(_site_key(t).lower())
    if node_name:
        return ctx.cache.transport_graph.nodes.get(node_name)
    return None


def _show_site_header(t: Terminal, ctx) -> None:
    """Affiche services et groupes de terminaux du site (juste après le titre de section)."""
    all_t = _site_terminals(t, ctx) or [t]

    # ── Agrégats services ─────────────────────────────────────────────────
    has_fret        = any(x.has_freight_elevator for x in all_t)
    has_auto_load   = any(x.is_auto_load for x in all_t)
    has_refuel      = any(x.is_refuel or x.type == "fuel" for x in all_t)
    has_repair      = any(x.is_repair for x in all_t)
    has_docking     = any(x.has_docking_port for x in all_t)
    has_habitation  = any(x.is_habitation for x in all_t)
    has_medical     = any(x.is_medical for x in all_t)
    is_player_owned = any(x.is_player_owned for x in all_t)
    faction         = next((x.faction_name for x in all_t if x.faction_name), "")

    # ── Statuts sécurité depuis le graphe de lieux ─────────────────────────
    node = _site_graph_node(t, ctx)
    meta = node.metadata if node else {}

    # ── Ligne icônes services ──────────────────────────────────────────────
    icons: list[str] = []
    if has_fret:       icons.append(f"[{C.UEX}]↑ fret[/{C.UEX}]")
    if has_auto_load:  icons.append(f"[{C.UEX}]⟳ auto-load[/{C.UEX}]")
    if has_refuel:     icons.append(f"[{C.UEX}]⛽ carburant[/{C.UEX}]")
    if has_repair:     icons.append(f"[{C.UEX}]⚙ réparation[/{C.UEX}]")
    if has_docking:    icons.append(f"[{C.UEX}]⚓ amarrage[/{C.UEX}]")
    if has_habitation: icons.append(f"[{C.UEX}]⌂ habitation[/{C.UEX}]")
    if has_medical:    icons.append(f"[{C.UEX}]✚ médical[/{C.UEX}]")

    extra: list[str] = []
    if faction:
        extra.append(f"[{C.DIM}]{faction}[/{C.DIM}]")
    if is_player_owned:
        extra.append(f"[bold {C.LABEL}]⚑ joueur[/bold {C.LABEL}]")

    line_parts = icons + extra
    if line_parts:
        console.print("  " + "  ·  ".join(line_parts))

    # ── Ligne statuts sécurité (si données disponibles dans le graphe) ─────
    if meta:
        sec: list[str] = []
        # Surveillance (👁 = oeil)
        if meta.get("is_monitored"):
            sec.append(f"[{C.DIM}]👁 surveillé[/{C.DIM}]")
        else:
            sec.append(f"[yellow]👁 hors radar[/yellow]")
        # Armistice (⚔ = arme)
        if meta.get("is_armistice"):
            sec.append(f"[{C.DIM}]🛡 armistice[/{C.DIM}]")
        else:
            sec.append(f"[red]⚔ zone combat[/red]")
        # NQA (🎭 = masque)
        if meta.get("is_nqa"):
            sec.append(f"[orange1]🎭 NQA[/orange1]")
        console.print("  " + "  ·  ".join(sec))

    # ── Groupes de terminaux ───────────────────────────────────────────────
    magasins = sorted(
        [x for x in all_t
         if x.has_freight_elevator and not x.is_medical
         and x.type not in _NON_SHOP_TYPES],
        key=lambda x: x.name,
    )
    restaurants = sorted(
        [x for x in all_t
         if x.type == "item" and not x.has_freight_elevator and not x.is_medical],
        key=lambda x: x.name,
    )
    services = sorted(
        [x for x in all_t
         if x.is_medical
         or x.type in ("commodity", "commodity_raw")
         or x.type == "refinery"
         or x.is_refinery],
        key=lambda x: x.name,
    )

    def _fmt_names(terminals: list[Terminal]) -> str:
        names: list[str] = []
        refinery_done = False
        for x in terminals:
            n = _svc_name(x)
            if n.lower().startswith("refinery") or x.is_refinery or x.type == "refinery":
                if not refinery_done:
                    names.append("Raffinerie")
                    refinery_done = True
            else:
                names.append(n)
        return "  ·  ".join(names)

    disp = ctx.cfg.get("display", {})
    show_mag  = disp.get("magasins",    True)
    show_rest = disp.get("restaurants", True)
    show_svc  = disp.get("services",    True)

    if magasins and show_mag:
        console.print(
            f"  [{C.DIM}]Magasins[/{C.DIM}]     [{C.NEUTRAL}]{_fmt_names(magasins)}[/{C.NEUTRAL}]"
        )
    if restaurants and show_rest:
        console.print(
            f"  [{C.DIM}]Restaurants[/{C.DIM}]  [{C.NEUTRAL}]{_fmt_names(restaurants)}[/{C.NEUTRAL}]"
        )
    if services and show_svc:
        console.print(
            f"  [{C.DIM}]Services[/{C.DIM}]     [{C.DIM}]{_fmt_names(services)}[/{C.DIM}]"
        )
    if line_parts or (magasins and show_mag) or (restaurants and show_rest) or (services and show_svc):
        console.print()


# ── Affichage terminal ─────────────────────────────────────────────────────────

def _show_terminal(t: Terminal, ctx, sys_filter=None) -> None:
    player_sys = _player_system(ctx)
    dot = _dot_name(
        t.name, t.star_system_name, player_sys,
        space_station=t.space_station_name,
        planet=t.planet_name,
        orbit=t.orbit_name,
    )
    section(f"Marché — {dot}")
    _show_site_header(t, ctx)

    rows = _terminal_prices(t, ctx)

    if not rows:
        console.print(f"[{C.DIM}]Aucune donnée pour ce terminal.[/{C.DIM}]")
        console.print(f"[{C.DIM}]Utilisez /scan pour capturer les prix directement en jeu.[/{C.DIM}]")
        return

    _ensure_comm_codes(ctx)

    # ── Données fusionnées : scan joueur (★ bold) + UEX communauté (italic) ─
    has_player_data = any(
        r.get("_player_buy") or r.get("_player_sell") for r in rows
    )
    offline = getattr(ctx, "_api_offline", False)
    if offline:
        console.print(f"[{C.SCTRADE}]cache local · UEX Corp hors-ligne · données plus ou moins récentes[/{C.SCTRADE}]")
    elif has_player_data:
        console.print(f"[italic {C.DIM}]UEX Corp · données communauté · non confirmées  ·  ★ données joueur[/italic {C.DIM}]")
    else:
        console.print(f"[italic {C.DIM}]UEX Corp · données communauté · non confirmées[/italic {C.DIM}]")

    if rows:
        # Filtrer les commodités avec price_buy à 0 ou price_sell à 0
        buy_rows  = sorted([r for r in rows if r.get("price_buy") and r.get("price_buy") > 0],
                           key=lambda r: r.get("commodity_name") or "")
        sell_rows = sorted([r for r in rows if r.get("price_sell") and r.get("price_sell") > 0],
                           key=lambda r: r.get("commodity_name") or "")

        if not buy_rows and not sell_rows:
            console.print(f"[italic {C.DIM}]Terminal sans transaction active.[/italic {C.DIM}]")
        else:
            term_w = getattr(console, "width", None) or 100
            n_cols = _n_cols(term_w)

            pc = C.SCTRADE if offline else C.UEX   # couleur prix : orange si cache local

            if buy_rows:
                _show_buy_detailed(buy_rows, t, ctx, sys_filter=sys_filter)
            else:
                console.print(f"\n[bold {pc}]▼ Acheter sur place[/bold {pc}]")
                console.print(f"  [bold red]✗[/bold red] [italic {C.DIM}]Rien à acheter ici[/italic {C.DIM}]")

            console.print(f"\n[bold {C.PROFIT}]▼ Vendre ici[/bold {C.PROFIT}]")
            if sell_rows:
                sell_has_player = any(r.get("_player_sell") for r in sell_rows)
                if sell_has_player:
                    console.print(f"[{C.DIM}]★ = données joueur (confirmées)[/{C.DIM}]")
                entries = []
                for r in sell_rows:
                    ts = r.get("_scan_ts") if r.get("_player_sell") else r.get("date_modified")
                    d = _fmt_date(ts)
                    price_val = _price_short(r.get("price_sell"))
                    player_sell = r.get("_player_sell", False)
                    if player_sell:
                        price_str = f"[bold {C.PROFIT}]★ {price_val}[/bold {C.PROFIT}]"
                    elif offline:
                        price_str = f"[{C.SCTRADE}]{price_val}[/{C.SCTRADE}]"
                    else:
                        price_str = price_val
                    if d:
                        price_str = f"{price_str}  [{C.DIM}]{d}[/{C.DIM}]"
                    cname = r.get("commodity_name") or "?"
                    name_raw = _entry_ns(
                        cname,
                        _scu(r.get("scu_sell"), r.get("scu_sell_max"))
                        or _scu(r.get("scu_sell_stock")),
                        r.get("status_sell"), buy=False,
                        code=_comm_code(cname, int(r.get("id_commodity") or 0)),
                    )
                    if player_sell:
                        name_raw = f"[bold {C.NEUTRAL}]{name_raw}[/bold {C.NEUTRAL}]"
                    entries.append((name_raw, price_str))
                sell_col = f"{C.SCTRADE}" if offline else f"italic {C.PROFIT}"
                console.print(_multi_col_table(
                    entries, ("Marchandise (SCU)", "Vente"), n_cols,
                    f"italic {C.NEUTRAL}", sell_col,
                ))
            else:
                console.print(f"  [bold red]✗[/bold red] [italic {C.DIM}]Rien à vendre ici[/italic {C.DIM}]")

            total = len({r.get("commodity_name") for r in rows})
            dates = [r.get("date_modified") for r in rows if r.get("date_modified")]
            date_str = ""
            if dates:
                try:
                    dt = datetime.fromtimestamp(max(float(d) for d in dates))
                    date_str = f"  ·  màj {dt.strftime('%d %b %Y %H:%M')}"
                except Exception:
                    pass
            footer_col = C.SCTRADE if offline else C.DIM
            console.print(f"\n[italic {footer_col}]{total} marchandises{date_str}[/italic {footer_col}]")


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
        d = dist_map.get(term_name.lower()) or dist_map.get(_loc(term_name).lower())
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


def _term_sys_cell(r: dict, maxlen: int | None = None,
                   player_loc: str = "", player_dest: str = "") -> str:
    """'TermCourt  (Sys)' — nom court + système en dim.
    Souligne le nom si le joueur est sur ce terminal.
    Ajoute ⭐ si c'est la destination définie.
    maxlen=None → calculé depuis la largeur de la console.
    """
    if maxlen is None:
        maxlen = _term_name_maxlen()

    term    = _loc(r.get("terminal_name") or "?")
    sys     = r.get("star_system_name") or ""
    term_lo = term.lower()

    is_here = bool(player_loc and (term_lo in player_loc or player_loc in term_lo))
    is_dest = bool(player_dest and (term_lo in player_dest or player_dest in term_lo))

    term = _abbrev_terminal(term, maxlen)

    term_part = f"[bold underline]{term}[/bold underline]" if is_here else term
    suffix    = f" [{C.PROFIT}]⭐[/{C.PROFIT}]" if is_dest else ""
    sys_part  = f"  [{C.DIM}]({sys})[/{C.DIM}]" if sys else ""
    return f"{term_part}{suffix}{sys_part}"


def _scu_cell(qty) -> str:
    q = int(qty or 0)
    return f"{q:,} {C.SCU}".replace(",", "\u202f") if q else f"[{C.DIM}]—[/{C.DIM}]"


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
    _RESERVED = {"edit", "e"}  # flags non-système à ne pas consommer
    for arg in args:
        if arg.startswith("--"):
            val = arg[2:].lower()
            if val in _RESERVED:
                remaining.append(arg)
                continue
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

    cargo_hint = (f"  [{C.DIM}]cargo : {player_scu} {C.SCU}[/{C.DIM}]" if player_scu
                  else f"  [{C.DIM}](cargo non configuré)[/{C.DIM}]" if ctx.player.active_ship
                  else "")
    section(f"Commodité — {c.name}  [{c.code}]{flag_str}{sys_label}{cargo_hint}")

    rows = _commodity_prices(c.id, ctx)
    if not rows:
        console.print(f"[{C.DIM}]Aucune donnée de prix disponible.[/{C.DIM}]")
        return

    offline = getattr(ctx, "_api_offline", False)
    pc = C.SCTRADE if offline else C.UEX
    if offline:
        console.print(f"[{C.SCTRADE}]cache local · UEX Corp hors-ligne · données plus ou moins récentes[/{C.SCTRADE}]")

    all_rows = rows  # sauvegardé avant le filtre système pour le résumé "existe aussi"

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

    # ── Distances via routes API + graphe de transport ─────────────────────
    dist_map: dict[str, float] = {}
    player_term = _player_terminal(ctx)
    if player_term and player_term.id:
        dist_map = _fetch_route_distances(player_term.id, ctx)
    # Fallback : graphe de transport local (même si l'API a retourné des données)
    if player_term:
        _add_graph_distances(dist_map, player_term, ctx)

    # Clés de comparaison pour le soulignement et l'étoile destination
    player_loc_key  = _loc(player_term.name).lower() if player_term else ""
    player_dest_key = _loc(ctx.player.destination or "").lower()

    # Tailles de conteneurs par terminal (via /commodities_routes)
    container_map = _fetch_container_sizes(c.id, ctx)

    # ── Résumé ─────────────────────────────────────────────────────────────
    parts = []
    if buy_rows:
        parts.append(f"Achat min : [{pc}]{_price_fmt(buy_rows[0]['price_buy'])}[/{pc}]")
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
        console.print(f"[bold {pc}]▼ Acheter là-bas[/bold {pc}]")
        tbl = Table(show_header=True, box=None, padding=(0, 1), show_edge=False)
        tbl.add_column("Terminal (Sys)", no_wrap=True, min_width=24)
        tbl.add_column(f"Achat/{C.SCU}",  style=pc,    justify="right", no_wrap=True)
        tbl.add_column("T.Cargo",        style=C.DIM,  justify="right", no_wrap=True)
        tbl.add_column("Dispo",          no_wrap=True)
        tbl.add_column("Dist",           no_wrap=True)
        tbl.add_column("Total achat",    style=pc,     justify="right", no_wrap=True)

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
                _term_sys_cell(r, player_loc=player_loc_key, player_dest=player_dest_key),
                _price_fmt(price),
                container_map.get(term_name.lower(), f"[{C.DIM}]—[/{C.DIM}]"),
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
    console.print(f"[bold {C.PROFIT}]▼ Vendre là-bas[/bold {C.PROFIT}]")
    if sell_rows:
        tbl = Table(show_header=True, box=None, padding=(0, 1), show_edge=False)
        tbl.add_column("Terminal (Sys)",  no_wrap=True, min_width=24)
        tbl.add_column(f"Vente/{C.SCU}",   style=C.PROFIT, justify="right", no_wrap=True)
        tbl.add_column("Niveau/Max",      no_wrap=True)
        tbl.add_column("T.Cargo",         style=C.DIM,    justify="right", no_wrap=True)
        tbl.add_column("Dist",            no_wrap=True)
        tbl.add_column("ROI",             justify="right", no_wrap=True)
        tbl.add_column("Revenu cargo",    style=C.PROFIT, justify="right", no_wrap=True)

        for r in sell_rows[:30]:
            price        = r.get("price_sell") or 0
            scu_sell_min = int(r.get("scu_sell") or 0)
            scu_sell_max = int(r.get("scu_sell_max") or scu_sell_min)
            scu_stock    = int(r.get("scu_sell_stock") or 0)
            player_sell_max = r.get("scu_sell_max") if r.get("_player_sell") else None
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
                _term_sys_cell(r, player_loc=player_loc_key, player_dest=player_dest_key),
                _price_fmt(price),
                _bar_sell(status, scu_sell_max),
                (f"{_price_short(player_sell_max)} {C.SCU}"
                 if player_sell_max
                 else container_map.get(term_name.lower(), f"[{C.DIM}]—[/{C.DIM}]")),
                _dist_label(term_name, sys, player_sys, dist_map),
                roi_str,
                revenue_cell,
            )
        console.print(tbl)
    else:
        console.print(f"  [bold red]✗[/bold red] [italic {C.DIM}]Rien à acheter ici[/italic {C.DIM}]")

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
        ship_note = f"  ·  {ctx.player.active_ship} ({player_scu} {C.SCU})"
    elif ctx.player.active_ship:
        ship_note = f"  ·  {ctx.player.active_ship} — /ship cargo <nom> <n> pour le {C.SCU}"
    footer_col = C.SCTRADE if offline else C.DIM
    console.print(f"\n[{footer_col}]{n_t} terminaux{date_str}{ship_note}[/{footer_col}]")

    # ── Résumé autres systèmes (si filtre actif) ────────────────────────────
    if effective_filter and all_rows is not rows:
        shown_sys = set(effective_filter)
        other: dict[str, set] = {}
        for r in all_rows:
            if not (r.get("price_buy") or r.get("price_sell")):
                continue
            sys_name = (r.get("star_system_name") or "").strip()
            term     = (r.get("terminal_name") or "").strip()
            if sys_name and sys_name.lower() not in shown_sys and term:
                other.setdefault(sys_name, set()).add(term)
        if other:
            parts = [f"[bold]{sys}[/bold] : {len(terms)}"
                     for sys, terms in sorted(other.items())]
            console.print(
                f"[{C.DIM}]  Existe aussi : {' · '.join(parts)}"
                f"  ([italic]--all pour tout voir[/italic])[/{C.DIM}]"
            )

    console.print(
        f"[{C.DIM}]  Prix en {C.AUEC}  ·  T.Cargo : tailles des conteneurs en {C.SCU} (ex. 1/2/4)"
        f"  ·  Dispo ░=vide ████=plein  ·  ROI vs meilleur achat local[/{C.DIM}]"
    )

    # ── sc-trade.tools (public — aucun token requis) ──────────────────────────
    sct_cfg = ctx.cfg.get("sctrade", {})
    if sct_cfg.get("enabled", True):
        try:
            from uexinfo.api.sctrade_client import SCTradeClient
            token = sct_cfg.get("token", "")
            client = SCTradeClient(token=token)
            if token:
                # Endpoint token : données structurées par terminal
                txs = client.commodity_transactions(c.name)
            else:
                # Endpoint public : listings communauté
                txs = client.crowdsource_for_commodity(c.name)
            if txs:
                _show_sctrade_transactions(txs, ctx, crowdsource=not token)
        except Exception:
            pass


def _show_sctrade_transactions(txs: list[dict], ctx, crowdsource: bool = False) -> None:
    """Affiche les prix sc-trade.tools pour une commodité."""
    from rich.table import Table
    src = "données communauté · crowdsource" if crowdsource else "données communauté"
    console.print(f"\n[bold {C.SCTRADE}]sc-trade.tools[/bold {C.SCTRADE}]  [{C.DIM}]{src}[/{C.DIM}]")
    t = Table(show_header=True, header_style=f"bold {C.SCTRADE}", box=None, pad_edge=False)
    t.add_column("Terminal",   style=C.SCTRADE, min_width=28)
    t.add_column("Action",     style="white",   width=7)
    t.add_column("Prix/□",     justify="right", min_width=9)
    t.add_column("Stock SCU",  justify="right", min_width=9)

    if crowdsource:
        # Format crowdsource : transaction="BUYS"|"SELLS", location, price, quantity, saturation
        def _action(r):
            t = r.get("transaction", "")
            return "SELL" if t == "BUYS" else "BUY"   # BUYS = terminal achète = joueur vend
        rows_norm = [
            {"location": r.get("location", "?"), "action": _action(r),
             "price": r.get("price", 0), "stock": r.get("quantity", 0),
             "ts": r.get("timestamp", "")}
            for r in txs if r.get("price", 0) > 0
        ]
    else:
        # Format token : action="BUY"|"SELL", location, price, quantityInScu
        rows_norm = [
            {"location": r.get("location", "?"), "action": r.get("action", "?"),
             "price": r.get("price", 0),
             "stock": r.get("quantityInScu") or r.get("itemQuantityInScu") or 0,
             "ts": ""}
            for r in txs if r.get("price", 0) > 0
        ]

    buys  = sorted([r for r in rows_norm if r["action"] == "BUY"],  key=lambda r: r["price"])
    sells = sorted([r for r in rows_norm if r["action"] == "SELL"], key=lambda r: r["price"], reverse=True)

    for r in (buys + sells)[:20]:
        color = C.PROFIT if r["action"] == "SELL" else C.LOSS
        t.add_row(
            r["location"],
            f"[{color}]{r['action']}[/{color}]",
            f"{int(r['price']):,}".replace(",", " "),
            f"{int(r['stock']):,}".replace(",", " ") if r["stock"] else "—",
        )
    console.print(t)


# ── Cache prix véhicules ────────────────────────────────────────────────────────



def _fetch_vehicle_purchases(id_vehicle: int, ctx) -> list[dict]:
    key = f"vp_{id_vehicle}"
    cached = ctx._price_cache.get(key)
    if cached:
        _ts, data = cached
        return data
    client = UEXClient()
    try:
        data = client.get_vehicles_purchases_prices(id_vehicle=id_vehicle)
    except UEXError as e:
        console.print(f"[{C.WARNING}]⚠  API : {e}[/{C.WARNING}]")
        return []
    ctx._price_cache[key] = (time.time(), data)
    return data


def _fetch_vehicle_rentals(id_vehicle: int, ctx) -> list[dict]:
    key = f"vr_{id_vehicle}"
    cached = ctx._price_cache.get(key)
    if cached:
        _ts, data = cached
        return data
    client = UEXClient()
    try:
        data = client.get_vehicles_rentals_prices(id_vehicle=id_vehicle)
    except UEXError as e:
        console.print(f"[{C.WARNING}]⚠  API : {e}[/{C.WARNING}]")
        return []
    ctx._price_cache[key] = (time.time(), data)
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

    from uexinfo.data.cargo_grids import format_cargo_config
    grid      = ctx.cargo_grid_manager.get_grid(v.name_full)
    grid_str  = format_cargo_config(grid) if grid else ""

    console.print(
        f"[{C.LABEL}]Fabricant[/{C.LABEL}]  {v.manufacturer or '—'}"
        f"    [{C.LABEL}]Cargo[/{C.LABEL}]  [{C.UEX}]{scu_str} {C.SCU}[/{C.UEX}]"
        f"    [{C.LABEL}]Équipage[/{C.LABEL}]  {crew_str}"
        f"    [{C.LABEL}]Pad[/{C.LABEL}]  {pad_str}"
        + (f"    [{C.LABEL}]Grilles[/{C.LABEL}]  [{C.DIM}]{grid_str}[/{C.DIM}]" if grid_str else "")
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
            + (f"  [{C.DIM}]moy {_price_fmt(avg_buy)} {C.AUEC}[/{C.DIM}]" if avg_buy else "")
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
            tbl.add_row(term, sys, f"{_price_fmt(price)} {C.AUEC}")
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
            + (f"  [{C.DIM}]moy {_price_fmt(avg_rent)} {C.AUEC}/jour[/{C.DIM}]" if avg_rent else "")
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
            tbl.add_row(term, sys, f"{_price_fmt(price)} {C.AUEC}")
        console.print(tbl)
    else:
        console.print(f"[{C.DIM}]Prix de location non disponibles.[/{C.DIM}]")


# ── Recherche ──────────────────────────────────────────────────────────────────

_TRADING_SERVICES = {"admin", "tdd", "trade"}   # priorité commerce


def _trading_priority(t: Terminal) -> int:
    """0 = terminal de commerce (Admin/TDD), 1 = autre."""
    if " - " not in t.name:
        return 1
    svc = t.name.split(" - ")[0].strip().lower()
    return 0 if svc in _TRADING_SERVICES else 1


def _find_terminal(query: str, ctx, strong: bool = False) -> Terminal | None:
    """Recherche un terminal avec priorités :
    1. Notation pointée  station.service  ou  système.station.service
    2. Nom/code exact
    3. Nom court exact   → préfère Admin/TDD
    4. Préfixe           → préfère Admin/TDD
    5. Contient          → préfère Admin/TDD  (ignoré si strong=True)

    strong=True : seulement les étapes 1-4 (pas de match "contient").
    Utilisé en recherche libre pour ne pas écraser une commodité homonyme.
    """
    q = query.replace("_", " ").lower().strip()

    # ── 1. Notation pointée ──────────────────────────────────────────────
    if "." in q:
        parts = q.rsplit(".", 1)          # ["system.station", "service"]  ou  ["station", "service"]
        service_q = parts[1].strip()
        station_q = parts[0].rsplit(".", 1)[-1].strip()  # dernier segment avant le service
        # Correspondance exacte service + station
        for t in ctx.cache.terminals:
            if " - " not in t.name:
                continue
            svc, loc = t.name.lower().split(" - ", 1)
            if svc.strip() == service_q and loc.strip() == station_q:
                return t
        # Correspondance partielle
        for t in ctx.cache.terminals:
            if " - " not in t.name:
                continue
            svc, loc = t.name.lower().split(" - ", 1)
            if service_q in svc and station_q in loc:
                return t
        # Fallback : chercher sans le service (juste la station)
        q = station_q

    # ── 2. Nom ou code exact ─────────────────────────────────────────────
    for t in ctx.cache.terminals:
        if t.name.lower() == q or t.code.lower() == q:
            return t

    # ── 3. Nom court ou espace-station exact → préfère Admin/TDD ─────────
    matches = [t for t in ctx.cache.terminals
               if _loc(t.name).lower() == q or t.space_station_name.lower() == q]
    if matches:
        return min(matches, key=_trading_priority)

    # ── 4. Préfixe du nom court / espace-station → préfère Admin/TDD ─────
    matches = [t for t in ctx.cache.terminals
               if _loc(t.name).lower().startswith(q)
               or t.space_station_name.lower().startswith(q)]
    if matches:
        return min(matches, key=_trading_priority)

    if strong:
        return None

    # ── 5. Contient (nom ou espace-station) → préfère Admin/TDD ──────────
    matches = [t for t in ctx.cache.terminals
               if q in t.name.lower() or q in t.space_station_name.lower()]
    if matches:
        return min(matches, key=_trading_priority)

    return None


def _find_terminal_candidates(query: str, ctx) -> list[Terminal]:
    """Retourne tous les terminaux correspondant à query (préfixe du nom court).

    Utile pour désambigüer quand la query est trop courte.
    Déduplique par station (garde le meilleur service Admin/TDD par station).
    """
    q = query.replace("_", " ").lower().strip()
    if not q:
        return []

    # Préfixe exact
    matches = [t for t in ctx.cache.terminals if _loc(t.name).lower().startswith(q)]
    if not matches:
        matches = [t for t in ctx.cache.terminals if q in t.name.lower()]

    # Dédupliquer par station : garder le terminal de commerce (Admin/TDD)
    seen: dict[str, Terminal] = {}
    for t in matches:
        station = _loc(t.name).lower()
        if station not in seen or _trading_priority(t) < _trading_priority(seen[station]):
            seen[station] = t
    return sorted(seen.values(), key=lambda t: _loc(t.name).lower())


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
    from uexinfo.cli.completer_data import MFR_ABBREV
    q = query.replace("_", " ").lower().strip()
    vehicles = ctx.cache.vehicles or []

    # ── Notation pointée : <mfr_abbrev>.<nom>  ou  ship.<nom> ────────────
    mfr_prefix: str | None = None
    name_q = q
    if "." in q:
        pfx, rest = q.split(".", 1)
        pfx  = pfx.strip()
        rest = rest.strip()
        mfr_full = MFR_ABBREV.get(pfx)
        if mfr_full is not None or pfx == "ship":
            mfr_prefix = mfr_full   # None pour "ship" = pas de filtre fabricant
            name_q = rest
        # Si préfixe non reconnu, on laisse q inchangé (ex: "port.tressler")

    # ── Recherche avec filtre fabricant éventuel ──────────────────────────
    def _mfr_ok(v) -> bool:
        return not mfr_prefix or (v.manufacturer or "").lower().startswith(mfr_prefix)

    for v in vehicles:
        if _mfr_ok(v) and (v.name_full.lower() == name_q or v.name.lower() == name_q):
            return v
    for v in vehicles:
        if _mfr_ok(v) and v.name_full.lower().startswith(name_q):
            return v
    for v in vehicles:
        if _mfr_ok(v) and name_q in v.name_full.lower():
            return v

    # Si la notation pointée n'a rien donné, ne pas tomber sur la recherche floue
    # pour éviter les faux positifs avec le point dans q.
    if name_q != q:
        return None

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


def _show_commodity_list(args: list[str], ctx) -> None:
    """Liste les commodités du jeu, triées alpha ou par prix.

    /info list [-p] [filtre]
    """
    # Flags de tri : -b gagne sur -p si les deux sont présents
    sort_mode = "alpha"  # alpha | price_asc | price_desc | benef_asc | benef_desc
    filter_parts: list[str] = []
    for a in args:
        al = a.lower()
        if al in ("-b", "-b-"):
            sort_mode = "benef_desc"
        elif al == "-b+":
            sort_mode = "benef_asc"
        elif al in ("-p", "-p-", "--price"):
            if not sort_mode.startswith("benef"):
                sort_mode = "price_desc"
        elif al == "-p+":
            if not sort_mode.startswith("benef"):
                sort_mode = "price_asc"
        else:
            filter_parts.append(a)
    q = " ".join(filter_parts).replace("_", " ").lower().strip()

    items = [c for c in ctx.cache.commodities if c.is_available]
    if q:
        items = [c for c in items if q in c.name.lower()]

    if not items:
        print_warn(f"Aucune commodité trouvée pour « {q} »" if q else "Aucune commodité en base")
        return

    def _benef(c):
        return (c.price_sell or 0) - (c.price_buy or 0)

    if sort_mode == "price_desc":
        items.sort(key=lambda c: -(c.price_buy or c.price_sell or 0))
    elif sort_mode == "price_asc":
        items.sort(key=lambda c: (c.price_buy or c.price_sell or 0))
    elif sort_mode == "benef_desc":
        items.sort(key=lambda c: -_benef(c))
    elif sort_mode == "benef_asc":
        items.sort(key=lambda c: _benef(c))
    else:
        items.sort(key=lambda c: c.name.lower())

    tbl = Table(box=None, pad_edge=False, show_header=True, padding=(0, 1))
    tbl.add_column("Commodité", style=C.LABEL)
    tbl.add_column("Code", style=C.DIM)
    tbl.add_column("Type", style=C.DIM)
    tbl.add_column("Achat", justify="right")
    tbl.add_column("Vente", justify="right")
    tbl.add_column("Bénéf.", justify="right")
    tbl.add_column("Flags", style=C.DIM)

    for c in items:
        benef = _benef(c)
        if benef > 0:
            benef_str = f"[{C.PROFIT}]+{_price_fmt(benef)}[/{C.PROFIT}]"
        elif benef < 0:
            benef_str = f"[{C.LOSS}]{_price_fmt(benef)}[/{C.LOSS}]"
        else:
            benef_str = f"[{C.DIM}]—[/{C.DIM}]"

        flags: list[str] = []
        if c.is_illegal:
            flags.append(f"[{C.LOSS}]illégal[/{C.LOSS}]")
        if c.is_extractable:
            flags.append("minable")
        if c.is_refinable:
            flags.append("raffinable")
        tbl.add_row(
            c.name,
            c.code or "—",
            c.kind or "—",
            _price_fmt(c.price_buy),
            _price_fmt(c.price_sell),
            benef_str,
            " ".join(flags) if flags else "—",
        )

    section(f"Commodités ({len(items)})" + (f" · filtre « {q} »" if q else ""))
    console.print(tbl)


def _show_terminal_by_name(query: str, ctx, sys_filter=None) -> bool:
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
        ctx._price_cache.copy_entry(cache_key, tid_key)
    _show_terminal(t, ctx, sys_filter=sys_filter)
    return True


# ── Commande principale ────────────────────────────────────────────────────────

@register("info", "i", "?")
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
            _show_terminal(t, ctx, sys_filter=sys_filter)
        elif not _show_terminal_by_name(loc, ctx, sys_filter=sys_filter):
            print_warn(f"Position actuelle introuvable comme terminal : {loc}")
        return

    _SUBS = {"terminal", "commodity", "ship"}
    first = args[0].lower()

    if first == "list":
        _show_commodity_list(args[1:], ctx)
        return

    # /info --edit <terminal> → formulaire overlay d'édition des scans
    if first in ("--edit", "-edit", "-e"):
        from uexinfo.cli.commands.scan import _scan_edit
        terminal_args = args[1:]
        if not terminal_args:
            loc = (ctx.player.location or "").strip()
            if loc:
                terminal_args = [loc]
            else:
                print_warn("Usage : /info --edit <terminal>")
                return
        _scan_edit(terminal_args, ctx)
        return

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
                _show_terminal(t, ctx, sys_filter=sys_filter)
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

    # Priorité : terminal exact/préfixe > commodité > terminal "contient" > API > vaisseau
    # On ne fait pas le match "contient" des terminaux en premier pour éviter
    # qu'un nom de terminal comme "Devlin Scrap and Salvage" écrase la commodité "Scrap".
    t = _find_terminal(query, ctx, strong=True)
    if t:
        _show_terminal(t, ctx, sys_filter=sys_filter)
        return
    c = _find_commodity(query, ctx)
    if c:
        _show_commodity(c, ctx, sys_filter=sys_filter)
        return
    # Fallback : terminal hors cache (Pyro, etc.) → requête directe par nom
    if _show_terminal_by_name(query, ctx, sys_filter=sys_filter):
        return
    # Fallback : terminal match "contient" (ex: "devlin scrap" → Devlin Scrap and Salvage)
    t = _find_terminal(query, ctx)
    if t:
        _show_terminal(t, ctx, sys_filter=sys_filter)
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
