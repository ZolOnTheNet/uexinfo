"""Point d'entrée — boucle REPL interactive."""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

import appdirs
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console

import uexinfo.config.settings as settings
from uexinfo import __version__
from uexinfo.cache.manager import CacheManager
from uexinfo.cli.completer import UEXCompleter
from uexinfo.cli.parser import parse_line
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

from uexinfo.cli.commands import dispatch

console = Console()

HISTORY_FILE = Path(appdirs.user_data_dir("uexinfo")) / "history.txt"

PROMPT_STYLE = Style.from_dict({
    "prompt": "bold cyan",
})


@dataclass
class AppContext:
    cfg: dict = field(default_factory=dict)
    cache: CacheManager = field(default_factory=CacheManager)
    location_index: LocationIndex | None = None
    player: Player = field(default_factory=Player)
    last_scan: ScanResult | None = None
    scan_history: list[ScanResult] = field(default_factory=list)
    _price_cache: dict = field(default_factory=dict)  # {"t27": (ts, data)}


def _banner() -> None:
    console.print(
        f"[bold cyan]UEXInfo[/bold cyan] [dim]v{__version__}[/dim]"
        "  —  Star Citizen Trade CLI\n"
        f"[{C.DIM}]Tapez [bold]/help[/bold] pour l'aide  │  [bold]/exit[/bold] pour quitter  │  ↓/Tab = parcourir  │  Entrée = valider  │  Saisie libre = /info[/{C.DIM}]"
    )
    console.print()


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
    completer = UEXCompleter(ctx=ctx)

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    session: PromptSession = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
        style=PROMPT_STYLE,
        complete_while_typing=True,   # dropdown dès la saisie
        complete_in_thread=True,       # ne bloque pas l'UI
    )

    _banner()

    while True:
        try:
            line = session.prompt([("class:prompt", "> ")])
        except KeyboardInterrupt:
            continue
        except EOFError:
            console.print(f"\n[{C.DIM}]Au revoir, fly safe o7[/{C.DIM}]")
            break

        line = line.strip()
        if not line:
            continue

        stripped = line.lstrip()
        if not stripped.startswith("/"):
            # Commande par défaut : /info <texte>
            try:
                words = shlex.split(stripped)
            except ValueError:
                words = stripped.split()
            dispatch("info", words, ctx)
            continue

        cmd, args = parse_line(stripped)
        if not cmd:
            continue

        if cmd in ("exit", "quit", "bye"):
            console.print(f"[{C.DIM}]Au revoir, fly safe o7[/{C.DIM}]")
            break

        dispatch(cmd, args, ctx)
