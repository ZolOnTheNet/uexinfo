"""Test du flux complet dans main.py pour 'help config'."""
import shlex

# Imports pour déclencher l'enregistrement des commandes
import uexinfo.cli.commands.help
import uexinfo.cli.commands.config
import uexinfo.cli.commands.info

from uexinfo.cli.main import normalize_command, AppContext
from uexinfo.cli.parser import parse_line
from uexinfo.cli.commands import get_names, dispatch
from uexinfo.cache.manager import CacheManager
from uexinfo.display import colors as C

print("=== TEST FLUX COMPLET 'help config' ===\n")

# Setup minimal
ctx = AppContext()
ctx.cache = CacheManager()

# Simuler exactement le flux de main.py
line = "help config"
print(f"1. Input utilisateur: '{line}'")

line = line.strip()
print(f"2. Apres strip(): '{line}'")

# Normaliser la saisie
known_cmds = set(get_names())
print(f"3. Commandes connues: {len(known_cmds)}")
print(f"   'help' in known_cmds: {'help' in known_cmds}")
print(f"   'config' in known_cmds: {'config' in known_cmds}")

normalized = normalize_command(line, known_cmds)
print(f"4. Apres normalize_command(): '{normalized}'")

# Parser la ligne normalisée
cmd, args = parse_line(normalized)
print(f"5. Apres parse_line():")
print(f"   cmd = '{cmd}'")
print(f"   args = {args}")

# Vérifier la condition ligne 247
if not cmd:
    print(f"\n[!] ATTENTION: cmd est vide!")
    print(f"    Le code va dispatch vers 'info' au lieu de '{cmd}'")
    print(f"    Ligne 247-253 de main.py")
    try:
        words = shlex.split(line)
    except ValueError:
        words = line.split()
    print(f"    dispatch('info', {words}, ctx)")
else:
    print(f"\n6. cmd n'est pas vide, dispatch normal:")
    print(f"   dispatch('{cmd}', {args}, ctx)")

print("\n=== EXECUTION REELLE ===\n")

# Exécuter réellement pour voir
if not cmd:
    try:
        words = shlex.split(line)
    except ValueError:
        words = line.split()
    print(f"[DISPATCH] 'info' avec args={words}")
    dispatch("info", words, ctx)
else:
    print(f"[DISPATCH] '{cmd}' avec args={args}")
    dispatch(cmd, args, ctx)
