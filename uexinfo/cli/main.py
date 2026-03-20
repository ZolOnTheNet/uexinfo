"""Point d'entrée — boucle REPL interactive."""
from __future__ import annotations

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
from uexinfo.cache.price_cache import PriceCache
from uexinfo.cli.completer import UEXCompleter
from uexinfo.cli.runner import normalize_command, run_command
from uexinfo.data.cargo_grids import CargoGridManager
from uexinfo.display import colors as C
from uexinfo.location.index import LocationIndex
from uexinfo.cache.mission_manager import MissionManager
from uexinfo.cache.voyage_manager import VoyageManager
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
import uexinfo.cli.commands.debug    # noqa: F401
import uexinfo.cli.commands.auto     # noqa: F401
import uexinfo.cli.commands.undo     # noqa: F401
import uexinfo.cli.commands.calc     # noqa: F401
import uexinfo.cli.commands.route    # noqa: F401
import uexinfo.cli.commands.mission  # noqa: F401
import uexinfo.cli.commands.voyage   # noqa: F401

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
    _price_cache: PriceCache = field(default_factory=PriceCache)
    mission_manager: MissionManager = field(default_factory=MissionManager)
    voyage_manager: VoyageManager = field(default_factory=VoyageManager)
    debug_level: int = 0
    log_last_mtime: float = 0.0          # mtime du log lors du dernier check auto
    screenshots_last_seen_ts: float = 0.0  # wall-clock du dernier check screenshots
    select_fn: object = None             # callable | None — injecté par overlay server


def _banner() -> None:
    console.print(
        f"[bold cyan]UEXInfo[/bold cyan] [dim]v{__version__}[/dim]"
        "  —  Star Citizen Trade CLI\n"
        f"[{C.DIM}]Tapez [bold]help[/bold] pour l'aide  │  [bold]exit[/bold] pour quitter  │  Tab / F2 = complétion  │  Saisie libre = recherche  │  [bold]@lieu[/bold] = se positionner + info[/{C.DIM}]\n"
        f"[{C.DIM}]Le [bold]/[/bold] est optionnel : [bold]ship add Cutlass[/bold] = [bold]/ship add Cutlass[/bold][/{C.DIM}]\n"
        f"[{C.DIM}]Symboles : [bold]{C.SCU}[/bold] = SCU (cargo)  │  [bold]{C.AUEC}[/bold] = aUEC (monnaie)[/{C.DIM}]"
    )
    console.print()


def _cleanup(ctx: AppContext, tbc: bool = False) -> None:
    """Nettoyage avant fermeture : sauvegarde du graphe de transport et du cache prix."""
    ctx._price_cache.flush()   # écrit price_cache.json si modifié
    ctx.voyage_manager.on_session_end(tbc=tbc)
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

    # ── Ctrl+Espace / F2 : forcer l'affichage de la complétion ───────────────
    # Note : avec complete_while_typing=True, complete_state est souvent déjà
    # actif → start_completion() est un no-op. Il faut cancel_completion()
    # d'abord. Windows Terminal intercepte souvent Ctrl+Espace → F2 en repli.
    @repl_kb.add("c-space", eager=True)
    @repl_kb.add("c-@",     eager=True)  # NUL : Ctrl+Espace sur certains terminaux Windows
    @repl_kb.add("f2",      eager=True)  # alternative sûre (jamais interceptée)
    def _force_completion(event):
        """Annule l'état en cours puis rouvre le menu de complétion."""
        b = event.current_buffer
        try:
            b.cancel_completion()
        except Exception:
            pass
        b.start_completion(select_first=False)

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

    # Hint /nav populate si le graphe est peu peuplé
    if len(ctx.cache.transport_graph.nodes) < 100:
        console.print(
            f"[{C.DIM}]ℹ  Réseau de navigation vide ou partiel "
            f"({len(ctx.cache.transport_graph.nodes)} nœuds) — "
            f"lancez [{C.LABEL}]/nav populate[/{C.LABEL}] pour importer les distances depuis UEX Corp.[/{C.DIM}]\n"
        )

    from uexinfo.cli.commands.scan import check_log_auto, check_screenshots_auto, _display_scan as _ds

    def normalized_first_word(line: str) -> str:
        return line.strip().lstrip("/").split()[0].lower() if line.strip() else ""

    def _is_info_cmd(line: str) -> bool:
        """Vrai si la ligne sera traitée comme /info (recherche libre ou /info explicite)."""
        s = line.strip()
        if not s or s.startswith("@"):
            return False
        first = normalized_first_word(s)
        return first == "info" or (not s.startswith("/") and first not in ("scan", "s"))

    while True:
        try:
            line = session.prompt([("class:prompt", "> ")])
        except KeyboardInterrupt:
            continue
        except EOFError:
            _cleanup(ctx)
            console.print(f"\n[{C.DIM}]Au revoir, fly safe o7[/{C.DIM}]")
            break

        # ── Trace top-level (avant tout traitement) ───────────────────────
        if ctx.debug_level >= 1:
            console.print(f"[bold yellow]DBG0 >>> input brut = {line!r}  (debug_level={ctx.debug_level})[/bold yellow]")

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

        _quit_parts = line.lower().lstrip("/").split()
        if _quit_parts and _quit_parts[0] in ("exit", "quit", "bye"):
            _tbc = "-tbc" in _quit_parts
            _cleanup(ctx, tbc=_tbc)
            if _tbc:
                console.print(f"[{C.DIM}]Session suspendue (to be continued) o7[/{C.DIM}]")
            else:
                console.print(f"[{C.DIM}]Au revoir, fly safe o7[/{C.DIM}]")
            break

        # Pre-hook : avant /info, mettre à jour ctx.last_scan sans afficher
        _info = _is_info_cmd(line)
        if _info:
            check_log_auto(ctx)

        run_command(line, ctx)

        # Post-hook : après les autres commandes, afficher les nouveaux scans log + screenshots
        if not _info and normalized_first_word(line) not in ("scan", "s"):
            _new = check_log_auto(ctx)
            if _new:
                console.print(f"\n[{C.DIM}]── Auto-scan log : {len(_new)} nouveau(x) scan(s) ──[/{C.DIM}]")
                for _r in _new:
                    _ds(_r, ctx)

            _new_shots = check_screenshots_auto(ctx)
            if _new_shots:
                console.print(
                    f"\n[{C.DIM}]── {len(_new_shots)} nouveau(x) screenshot(s) SC détecté(s) ──[/{C.DIM}]"
                )
                for _p in _new_shots:
                    console.print(
                        f"  [{C.LABEL}]{_p.name}[/{C.LABEL}]"
                        f"  [{C.DIM}]→ scan screenshot {_p.name}[/{C.DIM}]"
                    )
