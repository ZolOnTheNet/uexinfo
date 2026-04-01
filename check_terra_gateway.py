#!/usr/bin/env python
"""Script pour vérifier les prix de Terra Gateway dans le cache local."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from uexinfo.cache.manager import CacheManager
from uexinfo.api.uex_client import UEXClient

# Désactiver l'affichage Rich pour éviter les problèmes d'encodage
import logging
logging.basicConfig(level=logging.WARNING)

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
    
    # Vérifier les prix dans le cache local
    client = UEXClient()
    try:
        prices = client.get_prices(id_terminal=terra_gateway.id)
        iron_prices = [p for p in prices if 'iron' in p.get('commodity_name', '').lower()]
        
        print(f"\nPrix pour 'Iron' à Terra Gateway :")
        for p in iron_prices:
            print(f"  - {p.get('commodity_name')} : Achat={p.get('price_buy')}, Vente={p.get('price_sell')}")
    except Exception as e:
        print(f"Erreur lors de la récupération des prix : {e}")
else:
    print("Terminal Terra Gateway non trouvé dans le cache.")
