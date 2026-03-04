"""Commande /trade — recherche de prix d'achat et de vente."""
from __future__ import annotations

from uexinfo.cli.commands import register
from uexinfo.cli.commands.info import (
    _BUY_STATUS_COLOR,
    _SELL_STATUS_COLOR,
    _abbrev_name,
    _commodity_prices,
    _find_commodity,
    _loc,
    _multi_col_table,
    _notable_scu,
    _player_system,
    _price_short,
    _scu,
)
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_warn, section

_SUBS = {"buy", "sell", "best", "compare"}

_TERM_MAX     = 14  # largeur max du nom seul (même système)
_TERM_MAX_SYS = 20  # largeur max avec préfixe système


@register("trade", "t")
def cmd_trade(args: list[str], ctx) -> None:
    if not args:
        print_warn("Usage : /trade <commodité>  |  /trade buy|sell <commodité>")
        return
    sub = args[0].lower()
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
