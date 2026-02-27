"""Point d'entrée — boucle REPL interactive."""
from __future__ import annotations

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

# Imports des modules de commandes pour déclencher leur enregistrement
import uexinfo.cli.commands.help     # noqa: F401
import uexinfo.cli.commands.config   # noqa: F401
import uexinfo.cli.commands.refresh  # noqa: F401
import uexinfo.cli.commands.go       # noqa: F401
import uexinfo.cli.commands.select   # noqa: F401

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


def _banner() -> None:
    console.print(
        f"[bold cyan]UEXInfo[/bold cyan] [dim]v{__version__}[/dim]"
        "  —  Star Citizen Trade CLI\n"
        f"[{C.DIM}]Tapez [bold]/help[/bold] pour l'aide  │  [bold]/exit[/bold] pour quitter  │  Tab = autocomplétion[/{C.DIM}]"
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
    completer = UEXCompleter(ctx=ctx)

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    session: PromptSession = PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
        style=PROMPT_STYLE,
        complete_while_typing=False,
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
            console.print(f"[{C.DIM}]Les commandes commencent par /  —  tapez /help[/{C.DIM}]")
            continue

        cmd, args = parse_line(stripped)
        if not cmd:
            continue

        if cmd in ("exit", "quit"):
            console.print(f"[{C.DIM}]Au revoir, fly safe o7[/{C.DIM}]")
            break

        dispatch(cmd, args, ctx)
