"""Simule le flux complet de main.py pour 'help config' avec tous les logs."""
import shlex

# Imports pour enregistrement
import uexinfo.cli.commands.help
import uexinfo.cli.commands.config
import uexinfo.cli.commands.info

from uexinfo.cli.main import normalize_command, AppContext
from uexinfo.cli.parser import parse_line
from uexinfo.cli.commands import dispatch, get_names
from uexinfo.cache.manager import CacheManager

print("=== SIMULATION COMPLETE DU FLUX MAIN.PY ===\n")

# Setup
ctx = AppContext()
ctx.cache = CacheManager()

# Simuler l'input utilisateur
line = "help config"
print(f"[INPUT] '{line}'")
print()

# == EXACTEMENT LE CODE DE main.py lignes 220-260 ==

line = line.strip()
if not line:
    print("Line vide, continue")
else:
    # Normaliser la saisie : ajouter / si c'est une commande
    known_cmds = set(get_names())
    normalized = normalize_command(line, known_cmds)

    # DEBUG (ajouté dans main.py)
    if line.startswith("help"):
        print(f"[DEBUG main.py L228] line='{line}' -> normalized='{normalized}'")

    # Traitement spécial pour @lieu
    if normalized.startswith("@"):
        print("[BRANCH] @lieu")
    else:
        # Parser la ligne normalisée
        cmd, args = parse_line(normalized)

        # DEBUG (ajouté dans main.py)
        if line.startswith("help"):
            print(f"[DEBUG main.py L250] parse_line('{normalized}') -> cmd='{cmd}', args={args}")

        # Si pas de commande → recherche libre via /info
        if not cmd:
            print(f"[BRANCH] cmd vide, dispatch vers 'info'")
            try:
                words = shlex.split(line)
            except ValueError:
                words = line.split()
            print(f"[CALL] dispatch('info', {words}, ctx)")
            dispatch("info", words, ctx)
        else:
            if cmd in ("exit", "quit", "bye"):
                print("[BRANCH] exit")
            else:
                # DEBUG (ajouté dans main.py)
                if line.startswith("help"):
                    print(f"[DEBUG main.py L268] Avant dispatch: cmd='{cmd}', args={args}")

                print(f"\n[CALL] dispatch('{cmd}', {args}, ctx)\n")
                dispatch(cmd, args, ctx)

print("\n=== FIN ===")
