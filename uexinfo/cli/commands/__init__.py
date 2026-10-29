"""Registre et dispatcher des commandes CLI."""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from uexinfo.cli.context import AppContext

_registry: dict[str, Callable] = {}


def register(*names: str):
    """Décorateur pour enregistrer un handler de commande."""
    def decorator(func: Callable) -> Callable:
        """Inscrit la fonction sous chacun des noms (en minuscules) et la renvoie inchangée."""
        for name in names:
            _registry[name.lower()] = func
        return func
    return decorator


def dispatch(name: str, args: list[str], ctx: "AppContext") -> None:
    # /cmd help  →  /help cmd
    """Exécute la commande `name` avec ses arguments.

    « /cmd help » et « /cmd sous-commande help » sont redirigés vers /help ;
    une commande inconnue affiche une erreur.
    """
    if args and args[0].lower() in ("help", "aide", "?", "--help"):
        dispatch("help", [name] + args[1:], ctx)
        return
    # /cmd subcmd help  →  /help cmd subcmd
    if len(args) >= 2 and args[-1].lower() in ("help", "aide", "?", "--help"):
        dispatch("help", [name] + args[:-1], ctx)
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
    """Tous les noms et alias de commandes enregistrés, triés."""
    return sorted(_registry.keys())
