# sc-trade.tools — Stratégie d'accès aux données

> URL de base : `https://sc-trade.tools`
> Type : Single Page Application (SPA) React/JavaScript
> Affichage dans uexinfo : **orange** (données croisées)

---

## Problématique

Le site sc-trade.tools est une **SPA JavaScript**. Le HTML brut ne contient pas
les données — tout est chargé dynamiquement via des requêtes XHR/fetch après
le rendu JS côté client.

**WebFetch et requests classiques ne suffisent pas** pour récupérer les données.

---

## Stratégies d'accès (par ordre de préférence)

### Stratégie 1 — API interne (XHR) ⭐ Recommandée

En analysant les requêtes réseau de sc-trade.tools, on peut identifier
les endpoints d'API interne utilisés par la SPA.

**Méthode :** Inspecter dans un navigateur (DevTools > Network > XHR/Fetch)
lors de la navigation vers une page commodité.

URL à investiguer (à confirmer via inspection navigateur) :
```
https://sc-trade.tools/api/v1/commodities
https://sc-trade.tools/api/v1/commodities/{slug}
https://sc-trade.tools/api/v1/prices
```

Si ces endpoints existent et retournent du JSON, c'est la méthode idéale.

### Stratégie 2 — Playwright (rendu JS complet)

Utiliser `playwright` pour ouvrir un vrai navigateur headless, laisser la SPA
se charger, puis extraire le DOM rendu.

```python
from playwright.async_api import async_playwright

async def fetch_commodity(slug: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"https://sc-trade.tools/commodities/{slug}")
        await page.wait_for_selector("table")  # attendre le tableau de prix
        content = await page.content()
        await browser.close()
        return content
```

**Avantages :** Fiable, données complètes
**Inconvénients :** Lent (~5-10s), dépendance lourde

### Stratégie 3 — Cache local + refresh manuel

Stocker les données sc-trade.tools localement et permettre à l'utilisateur
de déclencher un refresh via `/refresh sctrade`.

---

## URLs connues

| Page                          | URL                                                     |
|-------------------------------|----------------------------------------------------------|
| Accueil                       | `https://sc-trade.tools`                                 |
| Commodité par slug            | `https://sc-trade.tools/commodities/{Slug}`              |
| Exemple Copper                | `https://sc-trade.tools/commodities/Copper`              |
| Exemple Gold                  | `https://sc-trade.tools/commodities/Gold`                |
| Exemple Agricium               | `https://sc-trade.tools/commodities/Agricium`            |

---

## Données attendues par commodité

D'après la structure de l'API UEX (source sous-jacente commune), les données
disponibles sur sc-trade.tools sont :

```
Prix d'achat par terminal (min/max/avg)
Prix de vente par terminal (min/max/avg)
Stock SCU disponible
Localisation (système / planète / station / terminal)
Meilleur lieu d'achat
Meilleur lieu de vente
Routes commerciales rentables (marge, ROI, profit/SCU)
Historique des prix / volatilité
Métadonnées commodité (poids, catégorie, légalité, raffinabilité)
```

---

## Mapping des slugs

Les slugs utilisés dans les URLs correspondent au nom anglais de la commodité.

| Commodité         | Slug sc-trade.tools |
|-------------------|---------------------|
| Copper            | `Copper`            |
| Gold              | `Gold`              |
| Agricium          | `Agricium`          |
| Laranite          | `Laranite`          |
| Diamond           | `Diamond`           |
| Quantainium       | `Quantainium`       |
| Widow             | `Widow`             |

Le slug est identique au `code` ou `name` UEX dans la plupart des cas.

---

## Affichage dans uexinfo

Quand des données sc-trade.tools sont disponibles, elles sont affichées
**en orange** à côté des données UEX (blanc/cyan) pour bien les différencier.

Exemple d'affichage :

```
COPPER — Prix de vente
┌─────────────────────────────┬──────────┬──────────┐
│ Terminal                    │ UEX      │ SC-Trade │
├─────────────────────────────┼──────────┼──────────┤
│ Tram & Myers Mining         │ 1700 aUEC│ 1695 aUEC│  ← orange
│ Shubin Mining Facility SAL  │ 1680 aUEC│ 1682 aUEC│  ← orange
└─────────────────────────────┴──────────┴──────────┘
```

---

## Implémentation recommandée

```python
# uexinfo/api/sctrade_client.py

class SCTradeClient:
    BASE_URL = "https://sc-trade.tools"

    def get_commodity(self, slug: str) -> dict | None:
        """
        Tente d'abord l'API interne JSON (rapide),
        fallback sur Playwright si nécessaire.
        """
        # 1. Essai API interne
        data = self._try_api(slug)
        if data:
            return data
        # 2. Fallback Playwright
        return self._scrape_with_playwright(slug)

    def _try_api(self, slug: str) -> dict | None:
        """Tente de récupérer via l'API JSON interne (à confirmer)."""
        try:
            r = requests.get(f"{self.BASE_URL}/api/v1/commodities/{slug}",
                             timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def _scrape_with_playwright(self, slug: str) -> dict | None:
        """Scraping via navigateur headless (fallback)."""
        # Implémentation Playwright
        pass
```

---

*Référence sc-trade.tools — uexinfo v0.1*
