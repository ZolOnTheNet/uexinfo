"""Palette de couleurs Rich pour uexinfo."""

# Source UEX Corp (données primaires)
UEX = "cyan"
UEX_VALUE = "bold white"

# Source sc-trade.tools (données croisées)
SCTRADE = "orange1"

# UI
TITLE = "bold cyan"
LABEL = "bright_white"
DIM = "dim"
PROMPT = "bold cyan"

# Statuts
SUCCESS = "bold green"
WARNING = "bold yellow"
ERROR = "bold red"

# Commerce
PROFIT = "bold green"
LOSS = "bold red"
NEUTRAL = "white"
ILLEGAL = "red"

# Scan — règles de gestion (/scan log)
MISMATCH  = "bold bright_red"  # commodité/mode absent du terminal côté UEX (rouge pétant, distinct de LOSS)
CORRECTED = "bold magenta"     # valeur auto-corrigée (fourchette prix, plafond SCU, prix rempli depuis UEX)

# Symboles unités (affichage compact)
SCU  = "□"   # Standard Cargo Unit  (U+25A1 WHITE SQUARE)
AUEC = "α"   # alpha UEC — monnaie in-game
