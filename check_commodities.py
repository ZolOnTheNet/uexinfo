#!/usr/bin/env python
"""Script pour vérifier les commodités dans le cache."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from uexinfo.cache.manager import CacheManager

# Désactiver l'affichage Rich pour éviter les problèmes d'encodage
import logging
logging.basicConfig(level=logging.WARNING)

cm = CacheManager()
try:
    cm.load(force=False)  # Charger depuis le disque
    print("Commodités chargées depuis le cache.")
except Exception as e:
    print(f"Erreur lors du chargement : {e}")
    sys.exit(1)

# Chercher les commodités spécifiques
iron = [c for c in cm.commodities if 'iron' in c.name.lower()]
envelope = [c for c in cm.commodities if 'envelope' in c.name.lower()]
gift = [c for c in cm.commodities if 'gift' in c.name.lower()]

print(f"\nIron : {len(iron)}")
for c in iron:
    print(f"  - {c.name} (ID: {c.id})")

print(f"\nEnvelope : {len(envelope)}")
for c in envelope:
    print(f"  - {c.name} (ID: {c.id})")

print(f"\nGift : {len(gift)}")
for c in gift:
    print(f"  - {c.name} (ID: {c.id})")
