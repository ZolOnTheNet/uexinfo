"""Point d'entrée — boucle REPL interactive."""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

import appdirs
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console

import uexinfo.config.settings as settings
from uexinfo import __version__
from uexinfo.cache.manager import CacheManager
from uexinfo.cli.completer import UEXCompleter
from uexinfo.cli.parser import parse_line
from uexinfo.data.cargo_grids import CargoGridManager
from uexinfo.display import colors as C
from uexinfo.location.index import LocationIndex
from uexinfo.models.player import Player
from uexinfo.models.scan_result import ScanResult

# Imports des modules de commandes pour déclencher leur enregistrement
import uexinfo.cli.commands.help     # noqa: F401
import uexinfo.cli.commands.config   # noqa: F401
import uexinfo.cli.commands.refresh  # noqa: F401
import uexinfo.cli.commands.go       # noqa: F401
import uexinfo.cli.commands.select   # noqa: F401
import uexinfo.cli.commands.player   # noqa: F401
import uexinfo.cli.commands.scan     # noqa: F401
import uexinfo.cli.commands.info     # noqa: F401
import uexinfo.cli.commands.explore  # noqa: F401
import uexinfo.cli.commands.trade    # noqa: F401
import uexinfo.cli.commands.nav      # noqa: F401

from uexinfo.cli.commands import dispatch, get_names

console = Console()

HISTORY_FILE = Path(appdirs.user_data_dir("uexinfo")) / "history.txt"

PROMPT_STYLE = Style.from_dict({
    "prompt": "bold cyan",
})


@dataclass
class AppContext:
    cfg: dict = field(default_factory=dict)
    cache: CacheManager = field(default_factory=CacheManager)
    cargo_grid_manager: CargoGridManager = field(default_factory=CargoGridManager)
    location_index: LocationIndex | None = None
    player: Player = field(default_factory=Player)
    last_scan: ScanResult | None = None
    scan_history: list[ScanResult] = field(default_factory=list)
    _price_cache: dict = field(default_factory=dict)  # {"t27": (ts, data)}


def _banner() -> None:
    console.print(
        f"[bold cyan]UEXInfo[/bold cyan] [dim]v{__version__}[/dim]"
        "  —  Star Citizen Trade CLI\n"
        f"[{C.DIM}]Tapez [bold]help[/bold] pour l'aide  │  [bold]exit[/bold] pour quitter  │  Tab / Ctrl-Espace = complétion  │  Saisie libre = recherche  │  [bold]@lieu[/bold] = se positionner + info[/{C.DIM}]\n"
        f"[{C.DIM}]Le [bold]/[/bold] est optionnel : [bold]ship add Cutlass[/bold] = [bold]/ship add Cutlass[/bold][/{C.DIM}]"
    )
    console.print()


def _cleanup(ctx: AppContext) -> None:
    """Nettoyage avant fermeture : sauvegarde du graphe de transport si modifié."""
    if ctx.cache.transport_graph.has_unsaved_changes:
        count = ctx.cache.transport_graph._unsaved_changes
        console.print(
            f"[{C.WARNING}]⊕  {count} route(s) enrichie(s) — sauvegarde automatique...[/{C.WARNING}]"
        )
        try:
            ctx.cache.save_transport_graph()
            console.print(f"[{C.SUCCESS}]✓  Graphe sauvegardé dans uexinfo/data/transport_network.json[/{C.SUCCESS}]")
            console.print(f"[{C.DIM}]   Pensez à commiter ce fichier avec git[/{C.DIM}]")
        except Exception as e:
            console.print(f"[{C.WARNING}]⚠  Erreur lors de la sauvegarde : {e}[/{C.WARNING}]")


def main() -> None:
    cfg = settings.load()
    ttl = cfg.get("cache", {}).get("ttl_static", 86400)
    cache = CacheManager(ttl_static=ttl)

    try:
        cache.load()
    except Exception as e:
        console.print(f"[{C.WARNING}]⚠  Cache indisponible : {e}[/{C.WARNING}]")
        console.print(f"[{C.DIM}]Utilisez /refresh pour réessayer.[/{C.DIM}]\n")

    ctx = AppContext(cfg=cfg, cache=cache)
    ctx.location_index = LocationIndex(cache)
    ctx.player = Player.from_config(cfg.get("player", {}))

    # ── Migration : cfg["ships"]/cfg["cargo"] → ctx.player (une seule fois) ─
    if not ctx.player.ships:
        _old_avail = cfg.get("ships", {}).get("available", [])
        if _old_avail:
            from uexinfo.models.player import Ship as _Ship
            _old_cargo = cfg.get("cargo", {})
            _old_cur   = cfg.get("ships", {}).get("current", "")
            ctx.player.ships = [
                _Ship(name=n, scu=_old_cargo.get(n, 0) or 0)
                for n in _old_avail
            ]
            if _old_cur and not ctx.player.active_ship:
                ctx.player.active_ship = _old_cur
            cfg["player"] = ctx.player.to_config()
            settings.save(cfg)
    # ─────────────────────────────────────────────────────────────────────────

    completer = UEXCompleter(ctx=ctx)

    # ── Ctrl+↑ : ouvrir l'éditeur de scan ────────────────────────────────────
    _edit_pending = [False]

    repl_kb = KeyBindings()

    @repl_kb.add("c-up")
    def _request_edit(event):
        _edit_pending[0] = True
        event.current_buffer.text = ""
        event.current_buffer.validate_and_handle()

    # ── Ctrl+Espace : forcer l'affichage de la complétion ─────────────────────
    @repl_kb.add("c-space")
    def _force_completion(event):
        """Force l'affichage du menu de complétion."""
        buff = event.current_buffer
        if buff.complete_state:
            # Si déjà ouvert, passer au suivant
            buff.complete_next()
        else:
            # Sinon, démarrer la complétion (select_first=True pour forcer l'affichage)
            buff.start_completion(select_first=True)

    # ─────────────────────────────────────────────────────────────────────────

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    session: PromptSession = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
        style=PROMPT_STYLE,
        key_bindings=repl_kb,
        complete_while_typing=True,
        complete_in_thread=True,
    )

    _banner()

    while True:
        try:
            line = session.prompt([("class:prompt", "> ")])
        except KeyboardInterrupt:
            continue
        except EOFError:
            _cleanup(ctx)
            console.print(f"\n[{C.DIM}]Au revoir, fly safe o7[/{C.DIM}]")
            break

        # ── Traitement Ctrl+↑ ─────────────────────────────────────────────
        if _edit_pending[0]:
            _edit_pending[0] = False
            if ctx.last_scan is None:
                console.print(f"[{C.WARNING}]⚠  Aucun scan disponible — faites d'abord /scan[/{C.WARNING}]")
            else:
                from uexinfo.cli.commands.scan_editor import ScanEditor
                from uexinfo.cli.commands.scan import _display_scan
                editor = ScanEditor(
                    ctx.last_scan,
                    commodities    = ctx.cache.commodities,
                    location_index = ctx.location_index,
                )
                result = editor.run()
                if result is not None:
                    ctx.last_scan = result
                    ctx.scan_history.append(result)
                    console.print(f"[bold green]✓  Scan mis à jour[/bold green]")
                    _display_scan(result, ctx)
            continue
        # ─────────────────────────────────────────────────────────────────

        line = line.strip()
        if not line:
            continue

        # Traitement spécial pour @lieu
        if line.startswith("@"):
            try:
                words = shlex.split(line)
            except ValueError:
                words = line.split()

            full_loc = " ".join(words)  # "@Port Tressler"
            dispatch("player", [full_loc], ctx)
            loc_name = full_loc[1:]     # "Port Tressler"
            if "." in loc_name:
                loc_name = loc_name.rsplit(".", 1)[-1]
            dispatch("info", [loc_name], ctx)
            continue

        # Parser la ligne (avec ou sans /)
        known_cmds = set(get_names())
        cmd, args = parse_line(line, known_commands=known_cmds)

        # Si pas de commande reconnue → recherche libre via /info
        if not cmd:
            try:
                words = shlex.split(line)
            except ValueError:
                words = line.split()
            dispatch("info", words, ctx)
            continue

        if cmd in ("exit", "quit", "bye"):
            _cleanup(ctx)
            console.print(f"[{C.DIM}]Au revoir, fly safe o7[/{C.DIM}]")
            break

        dispatch(cmd, args, ctx)
