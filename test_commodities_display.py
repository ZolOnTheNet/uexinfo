#!/usr/bin/env python
"""Script pour tester l'affichage des commodités avec price_buy à 0."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from uexinfo.cache.manager import CacheManager
from uexinfo.cli.commands.info import _show_terminal
from uexinfo.cli.context import AppContext
from uexinfo.display.formatter import console

# Rediriger la sortie vers un fichier pour éviter les problèmes d'encodage
sys.stdout.reconfigure(encoding='utf-8')

# Charger le cache local
cm = CacheManager()
try:
    cm.load(force=False)
    print("Cache chargé depuis le disque.")
except Exception as e:
    print(f"Erreur lors du chargement : {e}")
    sys.exit(1)

# Trouver Terra Gateway dans les terminaux
terra_gateway = None
for t in cm.terminals:
    if "Terra Gateway" in t.name:
        terra_gateway = t
        break

if terra_gateway:
    print(f"\nTerminal trouvé : {terra_gateway.name} (ID: {terra_gateway.id})")
    
    # Créer un contexte pour le test
    ctx = AppContext()
    ctx.cache = cm
    ctx.player = type('Player', (), {
        'active_ship': None,
        'ships': [],
        'destination': None,
        'location': None,
    })()
    
    # Afficher les informations du terminal
    try:
        _show_terminal(terra_gateway, ctx)
    except Exception as e:
        print(f"Erreur lors de l'affichage : {e}")
else:
    print("Terminal Terra Gateway non trouvé dans le cache.")
