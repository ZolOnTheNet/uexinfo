# Étude pour un mode simplifié dans uexinfo

## Objectif
Créer une interface simplifiée pour les utilisateurs néophytes ou ceux qui préfèrent une approche moins orientée CLI. L'idée est de rendre uexinfo plus accessible tout en conservant la puissance de l'interface existante.

## Propositions d'interface simplifiée

### 1. Interface graphique avec boutons
**Concept** : Ajouter une barre latérale ou un panneau avec des boutons pour les commandes courantes.

**Exemple de disposition** :
```
+---------------------------------------------------+
| [Position] [Vaisseau] [Trading] [Navigation]     |
|                                                   |
| +-------------------------------+                 |
| | Terminal actuel : Port Tressler |                 |
| +-------------------------------+                 |
|                                                   |
| [Achat] [Vente] [Meilleures routes] [Scan]        |
|                                                   |
| +---------------------------------------------+ |
| | Résultats de la recherche...               | |
| |                                             | |
| | - Copper : 1500 aUEC/□ (Profit : 500 aUEC) | |
| | - Diamonds : 3000 aUEC/□ (Profit : 1000 aUEC)| |
| +---------------------------------------------+ |
+---------------------------------------------------+
```

**Avantages** :
- Accès rapide aux commandes fréquentes.
- Réduction de la saisie manuelle.
- Interface plus intuitive pour les débutants.

**Implémentation** :
- Utiliser la bibliothèque `Textual` pour créer des boutons interactifs.
- Associer chaque bouton à une commande CLI existante (ex: bouton "Achat" → `/trade buy`).
- Permettre la personnalisation des boutons (ajout/suppression).

---

### 2. Menus déroulants contextuels
**Concept** : Ajouter des menus déroulants pour guider l'utilisateur dans la sélection des options.

**Exemple** :
```
+---------------------------------------------------+
| Trading > [Achat ▼] [Vente ▼] [Route ▼]          |
|                                                   |
| Achat : [Commodité ▼] [Terminal ▼] [Prix min ▼]   |
|                                                   |
| +---------------------------------------------+ |
| | Résultats :                                  | |
| | - Port Tressler : 1500 aUEC/□               | |
| | - Levski : 1450 aUEC/□                      | |
| +---------------------------------------------+ |
+---------------------------------------------------+
```

**Avantages** :
- Guidage pas à pas pour les commandes complexes.
- Réduction des erreurs de saisie.
- Interface plus visuelle.

**Implémentation** :
- Utiliser des widgets `Dropdown` dans `Textual`.
- Lier chaque option du menu à une commande CLI.
- Permettre la saisie libre en plus des menus.

---

### 3. Interface en onglets
**Concept** : Organiser les fonctionnalités en onglets pour une navigation plus intuitive.

**Exemple** :
```
+---------------------------------------------------+
| [Position] [Vaisseau] [Trading] [Navigation]     |
|                                                   |
| +-------------------------------+                 |
| | Onglet : Trading                              | |
| |                                               | |
| | Achat : [Copper]                              | |
| | Vente : [Levski]                              | |
| |                                               | |
| | +---------------------------+                 | |
| | | Résultats :               |                 | |
| | | - Profit : 500 aUEC/□     |                 | |
| | | - Distance : 10 km        |                 | |
| | +---------------------------+                 | |
| +-----------------------------------------------+ |
+---------------------------------------------------+
```

**Avantages** :
- Séparation claire des fonctionnalités.
- Navigation plus intuitive.
- Réduction de la complexité perçue.

**Implémentation** :
- Utiliser des onglets (`TabbedContent` dans `Textual`).
- Chaque onglet correspond à une catégorie de commandes (ex: Trading, Navigation).
- Permettre la personnalisation des onglets.

---

### 4. Interface tactile (pour overlay in-game)
**Concept** : Adapter l'interface pour une utilisation tactile ou avec une manette.

**Exemple** :
```
+---------------------------------------------------+
| [A] Position  [B] Vaisseau  [X] Trading  [Y] Nav |
|                                                   |
| +-------------------------------+                 |
| | Terminal actuel : Port Tressler |                 |
| +-------------------------------+                 |
|                                                   |
| [LB] Achat  [RB] Vente  [Menu] Options           |
|                                                   |
| +---------------------------------------------+ |
| | Résultats...                               | |
| +---------------------------------------------+ |
+---------------------------------------------------+
```

**Avantages** :
- Utilisation plus intuitive avec une manette ou un écran tactile.
- Adapté pour l'overlay in-game.
- Réduction de la dépendance au clavier.

**Implémentation** :
- Utiliser des raccourcis clavier personnalisables.
- Adapter l'interface pour les écrans tactiles.
- Permettre la navigation avec une manette.

---

### 5. Assistant interactif
**Concept** : Ajouter un assistant qui guide l'utilisateur pas à pas.

**Exemple** :
```
+---------------------------------------------------+
| Assistant : Que souhaitez-vous faire ?             |
|                                                   |
| 1. Trouver les meilleurs prix d'achat            |
| 2. Planifier une route de trading                  |
| 3. Configurer mon vaisseau                         |
| 4. Scanner un terminal                             |
|                                                   |
| > 1                                                |
|                                                   |
| Commodité : [Copper]                              |
| Terminal : [Port Tressler]                        |
|                                                   |
| +---------------------------------------------+ |
| | Résultats :                                  | |
| | - Prix : 1500 aUEC/□                         | |
| +---------------------------------------------+ |
+---------------------------------------------------+
```

**Avantages** :
- Guidage pas à pas pour les nouveaux utilisateurs.
- Réduction de la courbe d'apprentissage.
- Interface plus conviviale.

**Implémentation** :
- Utiliser un système de questions/réponses.
- Lier chaque réponse à une commande CLI.
- Permettre de sauter l'assistant pour les utilisateurs expérimentés.

---

### 6. Interface hybride (CLI + boutons)
**Concept** : Combiner une interface CLI avec des boutons pour les commandes fréquentes.

**Exemple** :
```
+---------------------------------------------------+
| > /trade buy Copper                                |
| [Achat] [Vente] [Route] [Scan] [Aide]             |
|                                                   |
| +---------------------------------------------+ |
| | Résultats :                                  | |
| | - Port Tressler : 1500 aUEC/□               | |
| | - Levski : 1450 aUEC/□                      | |
| +---------------------------------------------+ |
+---------------------------------------------------+
```

**Avantages** :
- Conservation de la puissance de la CLI.
- Ajout de raccourcis pour les commandes fréquentes.
- Interface plus flexible.

**Implémentation** :
- Ajouter une barre de boutons en bas de l'interface CLI.
- Chaque bouton insère une commande dans la ligne de saisie.
- Permettre la personnalisation des boutons.

---

## Recommandations pour l'implémentation

### 1. Utiliser Textual pour l'interface
- **Pourquoi** : Textual est déjà utilisé dans uexinfo pour le mode TUI. Il est bien adapté pour créer des interfaces riches dans le terminal.
- **Exemple de code** :
  ```python
  from textual.app import App
  from textual.widgets import Button, Input

  class SimplifiedUI(App):
      def compose(self):
          yield Button("Achat", id="buy")
          yield Button("Vente", id="sell")
          yield Input(placeholder="Entrez une commande...")
  ```

### 2. Conserver la compatibilité avec la CLI
- **Pourquoi** : Permettre aux utilisateurs expérimentés de continuer à utiliser la CLI.
- **Comment** : 
  - Ajouter un bouton pour basculer entre le mode simplifié et le mode CLI.
  - Permettre l'exécution de commandes CLI dans le mode simplifié.

### 3. Ajouter des raccourcis clavier
- **Pourquoi** : Faciliter la navigation pour les utilisateurs expérimentés.
- **Exemple** :
  - `Ctrl+B` : Basculer vers le mode simplifié.
  - `Ctrl+C` : Basculer vers le mode CLI.
  - `Ctrl+S` : Sauvegarder la configuration.

### 4. Permettre la personnalisation
- **Pourquoi** : Permettre aux utilisateurs d'adapter l'interface à leurs besoins.
- **Comment** :
  - Ajouter une commande `/config ui mode simple/advanced`.
  - Permettre la personnalisation des boutons et des menus.
  - Sauvegarder les préférences dans le fichier de configuration.

### 5. Ajouter des tutoriels interactifs
- **Pourquoi** : Aider les nouveaux utilisateurs à prendre en main l'interface.
- **Comment** :
  - Ajouter un tutoriel au premier lancement.
  - Permettre de relancer le tutoriel via une commande (`/help tutorial`).
  - Utiliser des infobulles pour expliquer les fonctionnalités.

---

## Étapes pour l'implémentation

### Phase 1 : Conception
1. **Créer des maquettes** : Utiliser des outils comme `Figma` ou `Draw.io` pour concevoir l'interface.
2. **Recueillir des feedbacks** : Partager les maquettes avec des utilisateurs pour obtenir des retours.
3. **Affiner le design** : Ajuster les maquettes en fonction des retours.

### Phase 2 : Développement
1. **Créer une nouvelle branche** : `git checkout -b feature/simplified-ui`.
2. **Ajouter les widgets** : Utiliser `Textual` pour créer les boutons et menus.
3. **Lier les widgets aux commandes** : Associer chaque bouton à une commande CLI.
4. **Ajouter la personnalisation** : Permettre aux utilisateurs de configurer l'interface.

### Phase 3 : Tests
1. **Tests unitaires** : Vérifier que chaque widget fonctionne correctement.
2. **Tests d'intégration** : Vérifier que l'interface simplifiée fonctionne avec le reste du programme.
3. **Tests utilisateurs** : Faire tester l'interface par des utilisateurs réels pour obtenir des retours.

### Phase 4 : Déploiement
1. **Documentation** : Mettre à jour la documentation pour inclure le mode simplifié.
2. **Merge** : Fusionner la branche dans `main`.
3. **Release** : Publier une nouvelle version avec le mode simplifié.

---

## Conclusion
L'ajout d'un mode simplifié dans uexinfo peut grandement améliorer l'accessibilité du programme pour les utilisateurs néophytes ou ceux qui préfèrent une approche moins orientée CLI. En utilisant des boutons, des menus déroulants, et des onglets, il est possible de créer une interface plus intuitive tout en conservant la puissance de la CLI pour les utilisateurs expérimentés. L'utilisation de `Textual` pour l'interface et la conservation de la compatibilité avec la CLI sont des éléments clés pour une implémentation réussie.
