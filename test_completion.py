"""
Script de test pour vérifier que la complétion fonctionne.
Utilisez ceci si vous rencontrez des problèmes de complétion dans l'application.

Usage :
    python test_completion.py
"""

# Imports complets comme dans main.py
import uexinfo.cli.commands.help
import uexinfo.cli.commands.config
import uexinfo.cli.commands.refresh
import uexinfo.cli.commands.go
import uexinfo.cli.commands.select
import uexinfo.cli.commands.player
import uexinfo.cli.commands.scan
import uexinfo.cli.commands.info
import uexinfo.cli.commands.explore
import uexinfo.cli.commands.trade
import uexinfo.cli.commands.nav

from uexinfo.cli.completer import UEXCompleter
from uexinfo.cli.main import AppContext
from uexinfo.cache.manager import CacheManager
from prompt_toolkit.document import Document

def test_completions():
    # Contexte complet
    print("Initialisation du contexte...")
    ctx = AppContext()
    ctx.cache = CacheManager()
    ctx.cache.load()
    print(f"Cache chargé : {len(ctx.cache.vehicles)} vaisseaux, {len(ctx.cache.commodities)} commodités, {len(ctx.cache.terminals)} terminaux\n")

    completer = UEXCompleter(ctx)

    tests = [
        ("/ship add ", "Vaisseaux après /ship add"),
        ("ship add ", "Vaisseaux après ship add (sans /)"),
        ("/ship add cut", "Vaisseaux Cutlass"),
        ("/go to ", "Terminaux après /go to"),
        ("/trade buy ", "Commodités après /trade buy"),
        ("help ", "Aide"),
    ]

    for text, description in tests:
        print(f"=== {description} ===")
        print(f'Texte tapé : "{text}"')
        doc = Document(text, len(text))
        completions = list(completer.get_completions(doc, None))
        print(f'Résultat : {len(completions)} suggestion(s)')

        if completions:
            print("Premières suggestions :")
            for i, c in enumerate(completions[:5]):
                display_meta = str(c.display_meta) if c.display_meta else ""
                print(f"  {i+1}. {c.text} — {display_meta}")
        else:
            print("  [!] AUCUNE SUGGESTION !")

        print()

    print("✓ Test terminé")
    print("\nSi vous voyez '0 suggestion(s)' pour /ship add, c'est un BUG.")
    print("Si vous voyez '30 suggestion(s)', alors la complétion FONCTIONNE.")
    print("\nSi la complétion fonctionne ici mais pas dans l'application :")
    print("  1. Redémarrez complètement l'application (fermez le terminal)")
    print("  2. Effacez le cache Python : find . -type d -name __pycache__ -exec rm -rf {} +")
    print("  3. Réinstallez : pip install -e .")

if __name__ == "__main__":
    test_completions()
