"""Registre et dispatcher des commandes CLI."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from uexinfo.cli.main import AppContext

_registry: dict[str, Callable] = {}


def register(*names: str):
    """Décorateur pour enregistrer un handler de commande."""
    def decorator(func: Callable) -> Callable:
        for name in names:
            _registry[name.lower()] = func
        return func
    return decorator


def dispatch(name: str, args: list[str], ctx: "AppContext") -> None:
    # /cmd help  →  /help cmd
    if args and args[0].lower() == "help":
        dispatch("help", [name], ctx)
        return

    handler = _registry.get(name.lower())
    if handler is None:
        from uexinfo.display.formatter import print_error
        print_error(f"Commande inconnue : /{name}  —  tapez /help")
        return
    try:
        handler(args, ctx)
    except Exception as e:
        from uexinfo.display.formatter import print_error
        print_error(f"Erreur dans /{name} : {e}")


def get_names() -> list[str]:
    return sorted(_registry.keys())
