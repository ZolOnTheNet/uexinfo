"""Test simple pour dispatcher help config sans lancer le REPL."""
import sys
import io

# Importer les commandes pour déclencher leur enregistrement
import uexinfo.cli.commands.help
import uexinfo.cli.commands.config
import uexinfo.cli.commands.info

from uexinfo.cli.main import normalize_command, AppContext
from uexinfo.cli.parser import parse_line
from uexinfo.cli.commands import get_names, dispatch
from uexinfo.cache.manager import CacheManager

# Capturer stdout pour éviter les erreurs d'encodage
old_stdout = sys.stdout
sys.stdout = io.StringIO()

try:
    print("\n=== TEST 'help config' (sans /) ===\n")

    # Contexte minimal
    ctx = AppContext()
    ctx.cache = CacheManager()

    # Commandes connues
    known_cmds = set(get_names())
    print(f"Commandes connues: {len(known_cmds)}")
    print(f"'help' present: {'help' in known_cmds}")
    print(f"'config' present: {'config' in known_cmds}")
    print()

    # Test 1: help config
    user_input = "help config"
    print(f"Input utilisateur: '{user_input}'")

    normalized = normalize_command(user_input, known_cmds)
    print(f"Apres normalisation: '{normalized}'")

    cmd, args = parse_line(normalized)
    print(f"Apres parsing: cmd='{cmd}', args={args}")
    print()

    # Maintenant dispatch - la sortie ira dans le buffer
    print("=== SORTIE DE LA COMMANDE ===")
    sys.stdout = old_stdout  # Restaurer pour voir la sortie réelle

    dispatch(cmd, args, ctx)

    print("\n=== FIN DU TEST ===")

except Exception as e:
    sys.stdout = old_stdout
    print(f"ERREUR: {e}")
    import traceback
    traceback.print_exc()
finally:
    sys.stdout = old_stdout
