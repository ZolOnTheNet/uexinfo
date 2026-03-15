"""Commande /= — calculatrice arithmétique simple."""
from __future__ import annotations

import ast
import operator
import re

from uexinfo.cli.commands import register
from uexinfo.display.formatter import console, print_error
from uexinfo.display import colors as C

# Opérations autorisées (pas d'exponentielle)
_BINOPS: dict[type, object] = {
    ast.Add:      operator.add,
    ast.Sub:      operator.sub,
    ast.Mult:     operator.mul,
    ast.Div:      operator.truediv,
    ast.Mod:      operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_UNOPS: dict[type, object] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval(node: ast.expr) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("Valeur non numérique")
    if isinstance(node, ast.BinOp):
        fn = _BINOPS.get(type(node.op))
        if fn is None:
            raise ValueError("Opération non supportée (pas d'exposant)")
        return fn(_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp):
        fn = _UNOPS.get(type(node.op))
        if fn is None:
            raise ValueError("Opération unaire non supportée")
        return fn(_eval(node.operand))
    raise ValueError(f"Syntaxe non supportée : {ast.dump(node)}")


def _fmt(val: float) -> str:
    """Affiche proprement : entier si possible, sinon max 4 décimales sans zéros inutiles."""
    if val == int(val) and abs(val) < 1e15:
        return str(int(val))
    s = f"{round(val, 4):.4f}".rstrip("0").rstrip(".")
    return s


def _prepare(expr: str) -> str:
    """Normalise l'expression avant parsing."""
    # Virgule décimale FR : 16,5 → 16.5
    expr = re.sub(r"(\d),(\d)", r"\1.\2", expr)
    # x ou X → *  (multiplication)
    expr = re.sub(r"[xX]", "*", expr)
    # Supprimer les espaces autour de // pour éviter confusion
    expr = expr.strip()
    return expr


@register("=", "calc", "calculette", "calcul")
def cmd_calc(args: list[str], ctx) -> None:
    if not args:
        console.print(
            f"[{C.LABEL}]/=[/{C.LABEL}]  [{C.DIM}]Calculatrice — ex: [bold]= 16x6[/bold]  "
            f"= 100/3  = (12+8)*5  = 1234 % 7[/{C.DIM}]"
        )
        return

    raw = " ".join(args)
    expr = _prepare(raw)

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        print_error(f"Syntaxe invalide : {raw!r}")
        return

    try:
        result = _eval(tree.body)
    except ZeroDivisionError:
        print_error("Division par zéro")
        return
    except ValueError as e:
        print_error(str(e))
        return

    display_expr = raw.replace("*", "×").replace("/", "÷").replace("%", " mod ")
    console.print(
        f"  [{C.NEUTRAL}]{display_expr}[/{C.NEUTRAL}]"
        f"  [bold {C.UEX}]= {_fmt(result)}[/bold {C.UEX}]"
    )
