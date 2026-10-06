"""Script pour debugger le flux de 'help config' et 'help ship'"""

import uexinfo.cli.commands.help
import uexinfo.cli.commands.config
import uexinfo.cli.commands.info

from uexinfo.cli.main import normalize_command, AppContext
from uexinfo.cli.parser import parse_line
from uexinfo.cli.commands import get_names, dispatch
from uexinfo.cache.manager import CacheManager

print("=== ALGORITHME DE TRAITEMENT 'help config' SANS / ===\n")

# Étape 1 : Saisie utilisateur
user_input = "help config"
print(f"ÉTAPE 1 : Saisie utilisateur")
print(f"  Input brut : '{user_input}'")
print()

# Étape 2 : Récupération des commandes connues
known_cmds = set(get_names())
print(f"ÉTAPE 2 : Commandes connues")
print(f"  Nombre de commandes : {len(known_cmds)}")
print(f"  'help' dans known_cmds ? {('help' in known_cmds)}")
print(f"  'config' dans known_cmds ? {('config' in known_cmds)}")
print()

# Étape 3 : Normalisation
normalized = normalize_command(user_input, known_cmds)
print(f"ÉTAPE 3 : Normalisation (normalize_command)")
print(f"  Input : '{user_input}'")
print(f"  Premier mot : '{user_input.split()[0] if user_input.split() else ''}'")
print(f"  Premier mot est une commande ? {(user_input.split()[0].lower() in known_cmds)}")
print(f"  Output normalisé : '{normalized}'")
print()

# Étape 4 : Parsing
cmd, args = parse_line(normalized)
print(f"ÉTAPE 4 : Parsing (parse_line)")
print(f"  Input : '{normalized}'")
print(f"  Commence par / ? {normalized.startswith('/')}")
print(f"  Commande extraite : '{cmd}'")
print(f"  Arguments extraits : {args}")
print()

# Étape 5 : Dispatch
print(f"ÉTAPE 5 : Dispatch")
print(f"  Appel : dispatch('{cmd}', {args}, ctx)")
print(f"  Vérification spéciale : args[0] == 'help' ?")
if args:
    print(f"    args[0] = '{args[0]}'")
    print(f"    args[0].lower() == 'help' ? {args[0].lower() == 'help'}")
    if args[0].lower() == "help":
        print(f"  [!] REDIRECTION : dispatch('help', ['{cmd}'], ctx)")
    else:
        print(f"  OK PAS de redirection, appel normal")
else:
    print(f"    args est vide")
print()

# Étape 6 : Handler help
print(f"ÉTAPE 6 : Handler 'help'")
print(f"  Handler appelé avec : args = {args}")
if args:
    topic = args[0].lstrip("/").lower()
    print(f"  Topic extrait : '{topic}'")

    # Vérifier _COMMANDS et _DETAILS
    from uexinfo.cli.commands.help import _COMMANDS, _DETAILS
    print(f"  Topic dans _DETAILS ? {topic in _DETAILS}")
    print(f"  Topic dans _COMMANDS ? {topic in _COMMANDS}")

    if topic in _DETAILS:
        print(f"  -> Affichera l'aide detaillee de '{topic}'")
    elif topic in _COMMANDS:
        print(f"  -> Affichera : /{topic}  {_COMMANDS[topic]}")
    else:
        print(f"  -> Affichera : Pas d'aide pour << {topic} >>")
else:
    print(f"  -> Affichera l'aide generale (liste des commandes)")

print("\n" + "="*60)
print("\nMAINTENANT EXÉCUTION RÉELLE:\n")

# Exécution réelle
ctx = AppContext()
ctx.cache = CacheManager()
ctx.cache.load()

print(f">>> {user_input}")
dispatch(cmd, args, ctx)
