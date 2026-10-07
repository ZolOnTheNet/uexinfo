"""Rejouer un Game.log sans lancer le jeu ni l'overlay.

    python -m uexinfo.gamelog chemin/Game.log [--debug] [--all]

--debug : chaque ligne reconnue et l'événement produit ; --all : aussi les lignes non reconnues.
"""
from __future__ import annotations

import argparse

from uexinfo.gamelog.events import recognize
from uexinfo.gamelog.follow import read_lines
from uexinfo.gamelog.state import GameState


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m uexinfo.gamelog", description="Rejoue un Game.log")
    ap.add_argument("log")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    st = GameState()
    dbg = (lambda m: print("  DBG", m)) if a.debug else None
    for raw in read_lines(a.log):
        ev = recognize(raw, dbg)
        if ev:
            st.apply(ev)
            mark = "" if ev.verified else " (?)"
            ts = ev.ts.strftime("%H:%M:%S") if ev.ts else "--:--:--"
            print(f"{ts}  {ev.kind:<16} {ev.summary}{mark}")
        elif a.all and raw.strip():
            print(f"          ·              {raw[:150]}")
    print("\n── État final ──")
    for k in ("player", "shard", "system", "location", "near_location", "qt_target", "ship", "zone"):
        print(f"  {k:<14} {getattr(st, k) or '—'}")
    print(f"  événements     {st.counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
