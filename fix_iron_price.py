#!/usr/bin/env python
"""Script pour corriger le price_buy pour Iron à Terra Gateway."""
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

# Chemin vers le fichier de cache des prix
CACHE_DIR = Path("C:/Users/garrigues/AppData/Local/uexinfo/uexinfo")
PRICE_CACHE_FILE = CACHE_DIR / "price_cache.json"

# Charger le cache des prix
if not PRICE_CACHE_FILE.exists():
    print(f"Fichier de cache introuvable : {PRICE_CACHE_FILE}")
    sys.exit(1)

with open(PRICE_CACHE_FILE, "r", encoding="utf-8") as f:
    price_cache = json.load(f)

# Trouver l'entrée pour Terra Gateway (ID: 251)
terminal_key = "t251"
if terminal_key not in price_cache:
    print(f"Terminal {terminal_key} non trouvé dans le cache.")
    sys.exit(1)

# Récupérer les données du terminal
timestamp, prices = price_cache[terminal_key]

# Trouver l'entrée pour Iron (ID: 44)
iron_entry = None
for entry in prices:
    if entry.get("id_commodity") == 44 and entry.get("commodity_name") == "Iron":
        iron_entry = entry
        break

if not iron_entry:
    print("Entrée pour Iron non trouvée.")
    sys.exit(1)

# Mettre à jour le price_buy (par exemple, le définir à 2364 comme dans les données statiques)
old_price_buy = iron_entry.get("price_buy", 0)
iron_entry["price_buy"] = 2364  # Prix d'achat mis à jour

print(f"Ancien price_buy pour Iron : {old_price_buy}")
print(f"Nouveau price_buy pour Iron : {iron_entry['price_buy']}")

# Sauvegarder les modifications
with open(PRICE_CACHE_FILE, "w", encoding="utf-8") as f:
    json.dump(price_cache, f, ensure_ascii=False, indent=2)

print("Mise à jour terminée. Le cache des prix a été corrigé.")
