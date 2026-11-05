"""/mission offres lot s'affiche (journal du 05/11 : la commande plantait à chaque fois sur un
code de couleur mal écrit ; titres à crochets comme « Hunt Bounty: [TARGET] »)."""
from types import SimpleNamespace as NS

import uexinfo.cli.commands.mission as M
from uexinfo.cli.commands.mission import _cmd_offers_lot
from uexinfo.display.render_html import rich_renderables_to_html
from uexinfo.ocr.contract_watch import Offer, OffersBoard


def _ctx(*offers):
    b = OffersBoard()
    for o in offers:
        b.offers[o.key] = o
    ship = NS(name="Drake Ironclad Assault", scu=1440, cargo_config={})
    return NS(offers_board=b, player=NS(ships=[ship], active_ship=ship.name), cfg={"contracts": {}})


def _render(args, ctx) -> str:
    M.console.reset_capture()          # la console que la commande utilise vraiment
    _cmd_offers_lot(args, ctx)
    return rich_renderables_to_html(M.console.flush_renderables())


def test_lot_renders_with_bracketed_titles():
    ctx = _ctx(Offer(title="Hunt Bounty: [TARGET]", reward=None, recognized=True),
               Offer(title="Junior Hauler Needed for Small Shipment [BP]", reward=215250, scu=8,
                     pickups=["Orbituary [A]"], drops=["Ruin Station"]),
               Offer(title="Member Hauler Needed for Small Shipment", reward=258250, scu=None, scu_max=24))
    for args in ([], ["dest", "2"], ["32"]):
        html = _render(args, ctx)
        assert "Meilleur lot" in html and "215" in html
        assert "[TARGET]" in html                     # titre gardé tel quel, pas pris pour un style
