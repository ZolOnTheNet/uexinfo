"""Commande /game — lecteur du Game.log de Star Citizen.

  /game                    État déduit du log (joueur, vaisseau, lieu, shard…)
  /game events [n]         Derniers événements reconnus   (-d : avec la ligne brute)
  /game tail [n] [texte]   Dernières lignes brutes (hors spam), interprétées si possible
  /game find <texte>       Lignes contenant <texte>
  /game stats              Reconnaisseurs (formats changés ?) + catégories <…> du log
  /game live [texte]       Suivi en direct (bouton ■ Arrêter ou Échap)
  /game stop               Arrêter le suivi en direct
  /game replay <fichier>   Rejouer un autre fichier (ex: logbackups\\…)
  /game extract            Extrait anonymisé (un exemple par catégorie) à me transmettre

Formats et confiance : docs/ai/GAMELOG_SPEC.md — « (?) » = format à confirmer.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from uexinfo.cli.commands import register
from uexinfo.display import colors as C
from uexinfo.display.formatter import console, print_error, print_ok, print_warn, section
from uexinfo.gamelog.events import audit, recognize
from uexinfo.gamelog.follow import game_log_path, read_lines, tail_lines
from uexinfo.gamelog.lines import is_spam, parse_line
from uexinfo.gamelog.state import GameState

_STATE_WINDOW = 50_000   # lignes relues pour reconstruire l'état (fin du fichier)


def _path(ctx, args: list[str] | None = None) -> Path | None:
    p = game_log_path(ctx.cfg)
    if p is None:
        print_error("Dossier du jeu non configuré — /config gamelog.install_path_live <dossier LIVE>")
        return None
    if not p.is_file():
        print_warn(f"Game.log introuvable : {p}  (Star Citizen pas encore lancé ?)")
        return None
    return p


def _ts(ev_ts) -> str:
    return ev_ts.strftime("%H:%M:%S") if ev_ts else "--:--:--"


def _event_line(ev, raw: bool = False) -> str:
    mark = "" if ev.verified else f" [{C.DIM}](?)[/{C.DIM}]"
    out = f"[{C.DIM}]{_ts(ev.ts)}[/{C.DIM}]  [{C.UEX}]{ev.kind:<16}[/{C.UEX}] {ev.summary}{mark}"
    if raw:
        out += f"\n           [{C.DIM}]{ev.raw[:220]}[/{C.DIM}]"
    return out


def _show_state(lines: list[str], source: str) -> None:
    st = GameState()
    for raw in lines:
        ev = recognize(raw)
        if ev:
            st.apply(ev)
    section(f"Game.log — {source}")
    rows = [
        ("Joueur", st.player), ("Shard", st.shard), ("Session depuis", _ts(st.session_start) if st.session_start else ""),
        ("Système", st.system), ("Position (route QT)", st.location), ("Lieu proche", st.near_location),
        ("Zone", st.zone), ("Cible QT", st.qt_target),
        ("Route QT", " → ".join(st.qt_route) if st.qt_route else ""), ("Vaisseau", st.ship),
    ]
    for label, val in rows:
        console.print(f"  {label:<20} {val or f'[{C.DIM}]—[/{C.DIM}]'}")
    if st.trades:
        console.print(f"\n  [{C.LABEL}]Commerce ({len(st.trades)})[/{C.LABEL}]")
        for ev in st.trades[-5:]:
            console.print("  " + _event_line(ev))
    if st.missions:
        console.print(f"\n  [{C.LABEL}]Missions ({len(st.missions)})[/{C.LABEL}]")
        for ev in st.missions[-5:]:
            console.print("  " + _event_line(ev))
    if st.counts:
        console.print(f"\n  [{C.DIM}]" + "  ".join(f"{k}:{v}" for k, v in sorted(st.counts.items())) + f"[/{C.DIM}]")
    console.print(f"  [{C.DIM}](?) = format à confirmer sur ton Game.log — /game extract pour me l'envoyer[/{C.DIM}]")


def _show_events(lines: list[str], n: int, raw: bool) -> None:
    evs = [ev for ev in (recognize(l) for l in lines) if ev]
    if not evs:
        print_warn("Aucun événement reconnu.")
        return
    for ev in evs[-n:]:
        console.print(_event_line(ev, raw))


def _show_lines(lines: list[str], n: int, needle: str = "") -> None:
    needle_l = needle.lower()
    picked = [l for l in lines if l.strip() and not is_spam(l) and (not needle_l or needle_l in l.lower())][-n:]
    if not picked:
        print_warn("Aucune ligne.")
        return
    for raw in picked:
        ev = recognize(raw)
        ll = parse_line(raw)
        head = f"[{C.DIM}]{_ts(ll.ts)}[/{C.DIM}] "
        body = raw[:200].replace("[", "\\[")
        console.print(head + (f"[{C.UEX}]{ev.summary}[/{C.UEX}]  " if ev else "") + f"[{C.DIM}]{body}[/{C.DIM}]")


def _show_stats(lines: list[str]) -> None:
    rows = audit(lines)
    section("Reconnaisseurs (marqueur vu / reconnu)")
    for r in rows:
        if not r.marker_lines:
            continue
        tag = "V" if r.verified else "?"
        color = C.LOSS if r.suspect else (C.DIM if r.recognized < r.marker_lines else C.PROFIT)
        console.print(f"  [{color}]{r.kind:<18} {r.marker_lines:>5} / {r.recognized:<5} ({tag})[/{color}]")
        for smp in r.samples:
            console.print(f"    [{C.DIM}]{smp[:200]}[/{C.DIM}]")
    if any(r.suspect for r in rows):
        print_warn("Marqueur présent mais jamais reconnu : le format a probablement changé (mise à jour du jeu).")
    cats = Counter(parse_line(l).category or "(sans catégorie)" for l in lines if l.strip())
    section(f"Catégories du log ({len(lines)} lignes)")
    for cat, n in cats.most_common(60):
        console.print(f"  {n:>7}  {cat}")


def _extract(lines: list[str], ctx) -> None:
    """Un ou deux exemples par catégorie, pseudo remplacé — pour fabriquer de vrais tests."""
    st = GameState()
    for raw in lines:
        ev = recognize(raw)
        if ev and ev.kind == "login":
            st.apply(ev)
    names = {n for n in (st.player,) if n}
    for raw in lines:
        if "Handle[" in raw:
            names.add(raw.split("Handle[", 1)[1].split("]", 1)[0])
    seen: Counter = Counter()
    out: list[str] = []
    for raw in lines:
        if not raw.strip() or is_spam(raw):
            continue
        cat = parse_line(raw).category or raw[27:60]
        if seen[cat] >= 2:
            continue
        seen[cat] += 1
        for nm in names:
            raw = raw.replace(nm, "JOUEUR")
        out.append(raw)
    from uexinfo.cache.manager import DATA_DIR
    dest = DATA_DIR / f"gamelog_extract_{datetime.now():%Y%m%d_%H%M}.log"
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print_ok(f"{len(out)} lignes ({len(seen)} catégories) écrites dans : {dest}")
    console.print(f"  [{C.DIM}]Pseudo remplacé par JOUEUR. Relis le fichier avant de le partager.[/{C.DIM}]")


@register("game", "gamelog", "jeu")
def cmd_game(args: list[str], ctx) -> None:
    sub = args[0].lower() if args else ""
    rest = args[1:]

    if sub in ("stop", "arret", "arrêt"):
        ctx._game_live = {"stop": True}
        print_ok("Suivi en direct arrêté.")
        return

    if sub == "replay":
        if not rest:
            print_error("Usage : /game replay <fichier>")
            return
        p = Path(" ".join(rest).strip('"'))
        if not p.is_file():
            print_error(f"Fichier introuvable : {p}")
            return
        lines = read_lines(p)
        _show_events(lines, 200, raw="-d" in rest)
        _show_state(lines, p.name)
        return

    p = _path(ctx)
    if p is None:
        return

    if sub in ("live", "direct", "suivi"):
        ctx._game_live = {"path": str(p), "filter": " ".join(rest)}
        print_ok(f"Suivi en direct de {p.name}" + (f" (filtre « {' '.join(rest)} »)" if rest else "")
                 + " — bouton ■ Arrêter ou Échap pour sortir.")
        return

    if sub in ("", "etat", "état", "state"):
        console.print(f"[{C.DIM}]{p}  ·  {p.stat().st_size / 1e6:.1f} Mo  ·  "
                      f"modifié {datetime.fromtimestamp(p.stat().st_mtime):%d/%m %H:%M}[/{C.DIM}]")
        _show_state(tail_lines(p, _STATE_WINDOW), "état actuel")
    elif sub in ("events", "ev", "evenements", "événements"):
        n = next((int(a) for a in rest if a.isdigit()), 30)
        _show_events(tail_lines(p, _STATE_WINDOW), n, raw="-d" in rest)
    elif sub in ("tail", "fin"):
        n = next((int(a) for a in rest if a.isdigit()), 40)
        needle = " ".join(a for a in rest if not a.isdigit())
        _show_lines(tail_lines(p, _STATE_WINDOW), n, needle)
    elif sub in ("find", "cherche", "chercher"):
        if not rest:
            print_error("Usage : /game find <texte>")
            return
        _show_lines(read_lines(p), 60, " ".join(rest))
    elif sub == "stats":
        _show_stats(read_lines(p))
    elif sub == "extract":
        _extract(read_lines(p), ctx)
    else:
        print_error(f"Sous-commande inconnue : {sub}  —  /game help")
