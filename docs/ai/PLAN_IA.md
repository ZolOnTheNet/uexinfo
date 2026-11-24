# PLAN_IA — Architecture MVC et assistant IA de uexinfo

> Document de conception.
> Validé par Olivier le 2026-11-24 (session d'étude). Source de vérité du chantier « IA ».
> À relire avant chaque étape, avec `docs/ai/NOTES.md` et `docs/ai/DECISIONS.md`.

---

## 0. Objectifs

1. **Séparer le cœur de l'affichage (MVC).** Les vues doivent être aussi indépendantes que possible du code cœur et des sources de données.
2. **Un format interne unique.** Chaque fonction métier renvoie un résultat canonique, sérialisable en JSON. Toute la boucle interne utilise ce même format, avec ou sans dialogue avec l'IA.
3. **Brancher une IA, quelle que soit sa source.** Au départ, une IA locale légère : **LFM2.5-8B-A1B** sur **llama-server**. Ensuite, tout serveur compatible OpenAI (Ollama, LM Studio, vLLM, API Mistral, etc.) ou l'API Anthropic.
4. **Exposer les outils de uexinfo en MCP**, pour l'agent interne comme pour les clients externes (Claude Code, OpenCode, Vibe…).
5. **Gérer le moteur d'inférence** : le détecter, le lancer selon la configuration, l'arrêter s'il a été lancé par uexinfo.
6. **Ne jamais toucher aux identifiants.** uexinfo ne stocke ni clé ni jeton. Pour une API distante, il lit seulement le **nom** d'une variable d'environnement définie par l'utilisateur.

## 1. Principes non négociables

| # | Principe | Comment c'est imposé |
|---|---|---|
| P1 | **Une seule implémentation par règle métier** (déjà la règle du projet) | Les calculs vivent dans `uexinfo/rules/` ou `uexinfo/core/services/`. Les vues ne calculent **aucune** valeur métier. |
| P2 | **Un objet garde son identité** (D11) | Les services n'acceptent **jamais** un `str` pour désigner un objet. Ils prennent des objets résolus ou des `Ref`. Un test parcourt les signatures pour le vérifier. |
| P3 | **La saisie ne devine pas** (D11, règle 3) | Une ambiguïté n'est jamais tranchée par le code ni par l'IA. Elle devient le statut `ambigu`, avec la liste des candidats. |
| P4 | **Un seul format de résultat** | Toute fonction de service renvoie un `Resultat[T]` (Pydantic v2). Les vues le lisent et ne le modifient pas. |
| P5 | **Les vues sont des projections** | La vue IA sélectionne des champs, la vue HTML met en forme. Ni l'une ni l'autre ne relit une source de données. |
| P6 | **Priorité des sources fixée par le code** | Scan joueur ★ > UEX > sc-trade. Chaque valeur porte sa `source` et son `age_s`. L'IA rapporte ces valeurs, elle ne choisit pas entre elles. |
| P7 | **Aucun identifiant stocké** | La configuration ne contient que des noms de variables d'environnement (`api_key_env = "MISTRAL_API_KEY"`), jamais de valeur. |

Ajouter dans `DECISIONS.md` une décision **D13** qui reprend P2 à P5 (format canonique, réfs et vues), au moment où l'étape 1 est codée.

## 2. Architecture cible (MVC)

```
            ┌───────────────────────── CONTRÔLEURS ─────────────────────────┐
            │ overlay/server.py (WebSocket) · cli/runner.py (commandes)      │
            │ ai/agent.py (boucle IA) · ai/mcp_server.py (clients MCP)       │
            └───────────────┬───────────────────────────────┬───────────────┘
                            │ appelle                       │ reçoit Resultat[T]
                            ▼                               │
┌──────────────────────── MODÈLE ────────────────────────┐  │  ┌──────────── VUES ────────────┐
│ core/services/*.py  : opérations métier → Resultat[T]  │──┼─►│ views/html/*.py → Rich/HTML  │
│ core/schemas/*.py   : modèles Pydantic (format unique) │  │  │ views/ai.py → JSON réduit    │
│ rules/*.py          : règles pures (existant)          │  │  │ (views/text.py → tests, CLI) │
│ names/              : résolution texte → objet (exist.)│  │  └──────────────────────────────┘
│ sources/ (dépôts)   : UEX · sc-trade · scans · Game.log│
│                       · OCR · base locale (existant :  │
│                       api/, cache/, gamelog/, ocr/)    │
└────────────────────────────────────────────────────────┘
```

- **Modèle** : les sources multiples sont derrière des dépôts (les classes existantes `DataManager`, `ScanPriceStore`, `MissionManager`… sont conservées et regroupées progressivement sous `sources/`). Les services combinent les sources et les règles, et produisent le format canonique.
- **Contrôleurs** : ils transforment une entrée (ligne de commande, clic, appel d'outil IA ou MCP) en appel de service, puis choisissent la vue.
- **Vues** : `views/html` produit le rendu Rich/HTML actuel, `views/ai` le JSON réduit pour le LLM. Une vue n'importe jamais `api/` ni `cache/`.

Contrôle automatique : un test importe chaque module de `views/` et échoue s'il dépend de `uexinfo.api`, `uexinfo.cache` ou `uexinfo.sources`.

## 3. Format canonique

Fichier `uexinfo/core/schemas/base.py`. Ajout de la dépendance : `pydantic>=2` dans `pyproject.toml` et `requirements.txt`.

```python
from typing import Generic, Literal, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

class Ref(BaseModel):
    """Désignation exacte d'un objet (D11). `ref` = "type:id" (voir names/refs.py)."""
    ref: str
    nom: str

class Valeur(BaseModel):
    """Valeur issue d'une source, avec sa provenance et son âge."""
    v: float | int | None
    source: Literal["scan", "uex", "sctrade", "calcul", "stale", "vide"]
    age_s: int | None = None

class Resultat(BaseModel, Generic[T]):
    statut: Literal["ok", "ambigu", "erreur", "vide"]
    donnees: T | None = None
    candidats: list[Ref] = []      # si ambigu : sélecteur (joueur) ou demander_choix (IA)
    alertes: list[str] = []        # remplace les print_warn intermédiaires
    erreur: str | None = None
```

Règles :
- Un objet du domaine est toujours représenté par un `Ref` dans un schéma, jamais par son nom seul.
- Un champ inutile à l'IA est marqué `Field(json_schema_extra={"ia": False})`, et `views/ai.py` l'omet. La sélection est déclarée à côté de la donnée.
- `views/ai.py` peut aussi limiter le nombre de lignes (`top_n`) et arrondir les valeurs, rien d'autre.
- Les messages intermédiaires (`print_warn`, `print_error`, progression) des commandes migrées passent dans `alertes` ou `erreur`. La progression reste un rappel (callback) séparé, hors du format.
- L'ambiguïté : le service utilise `names.resolve` ou `choose.decide(..., ask=False)` et renvoie `statut="ambigu"` avec la liste des candidats. C'est le contrôleur qui décide d'ouvrir le sélecteur de l'overlay.

### Premier schéma (modèle pour la suite) : le bilan `/trade`

```python
class LigneBilan(BaseModel):
    commodite: Ref
    quantite: int
    prix_achat: Valeur
    prix_vente: Valeur
    profit: int
    profit_gm: float | None
    risque: int | None                     # rules/risk.py
    decoupe: dict[int, int] = Field(default={}, json_schema_extra={"ia": False})

class BilanRoute(BaseModel):
    origine: Ref
    destination: Ref
    vaisseau: Ref | None
    scu: int
    distance_gm: float | None
    lignes: list[LigneBilan]
```

Service : `core/services/trade.py: bilan_route(ctx, origine: Terminal, destination: Terminal, vaisseau: Vehicle | None, scu: int | None) -> Resultat[BilanRoute]`.
Le calcul vient de `cli/commands/trade.py:_trade_bilan` et des fonctions d'empaquetage cargo (`_pack_grid`…), **déplacé et non dupliqué**. `/trade` devient : résolution → service → `views/html/trade.py`.

## 4. Couche IA (`uexinfo/ai/`)

| Fichier | Rôle |
|---|---|
| `ai/config.py` | Lit `[ia]` dans `config.toml` (§6) et valide la configuration |
| `ai/runtime.py` | Gestionnaire du moteur d'inférence : détecter, lancer, attendre, arrêter (§5) |
| `ai/providers.py` | Adaptateurs : `openai_compat` (llama-server, Ollama, LM Studio, vLLM, Mistral, OpenRouter…) et `anthropic` |
| `ai/tools.py` | Registre d'outils : chaque outil = un service + `views/ai`. Schémas d'entrée générés par Pydantic |
| `ai/mcp_server.py` | Expose `ai/tools.py` en MCP (HTTP local `127.0.0.1`, jeton comme `overlay/auth.py`) |
| `ai/agent.py` | Orchestrateur : boucle LLM ↔ outils, limite de 6 étapes, délai maximal, annulation, journal des appels |
| `ai/prompts/system_fr.md` | Prompt système |

**Le modèle ne parle pas MCP.** L'orchestrateur envoie les schémas d'outils au LLM, exécute les `tool_calls` qu'il reçoit et renvoie les résultats. Le serveur MCP sert aux clients externes, et en particulier à **tester les outils avec Claude Code** avant d'accuser le petit modèle.

### Outils v1 (lecture seule)

`etat_joueur`, `chercher(nom, types)`, `prix_terminal(ref)`, `meilleurs_achats(ref_commodite, systeme?)`, `meilleures_ventes(...)`, `bilan_route(origine, destination, vaisseau?)`, `itineraire(de, vers)`, `missions(filtre?)`, `calcul(expression)`, `demander_choix(candidats)` (ouvre le sélecteur de l'overlay et renvoie le choix du joueur).

- 8 à 10 outils au maximum, avec des descriptions courtes, en français.
- Les arguments désignant un objet sont des réfs (`"terminal:88"`). Un nom reçu passe par `names.resolve`.
- Les actions (`definir_destination`, `definir_position`) viennent en v2, **toujours avec confirmation dans l'overlay**.

### Prompt système (principes)

Rôle : assistant de commerce Star Citizen. Ne jamais inventer un prix, une quantité ou un lieu : tout passe par les outils. Utiliser les réfs reçues. En cas d'ambiguïté, appeler `demander_choix`. Répondre court, en français, en citant la source et l'âge des prix.

### Points techniques vérifiés (novembre 2026)

- llama-server convertit les appels d'outils de LFM2.5 en `tool_calls` au format OpenAI. Il faut une version récente (détection du modèle dans `common/chat.cpp`). `--jinja` est activé par défaut dans les versions récentes, et l'option est sans effet néfaste sur les anciennes.
- Un bug de llama-server renvoie parfois `function.arguments` sous forme d'objet au lieu d'une chaîne : l'orchestrateur doit accepter les deux.
- Le prompt système et les outils, identiques à chaque étape, sont mis en cache par llama-server : on ne les envoie qu'une fois par conversation.
- Les fichiers GGUF de LFM2.5-8B-A1B ont été reconvertis après un correctif du tokenizer pour l'appel d'outils : utiliser une version récente.

### Intégration à l'overlay

- Nouveaux messages WebSocket :
  - `ia` (question) ;
  - `ia_etape` (outil appelé, replié dans l'affichage) ;
  - `ia_reponse` (texte et réfs, rendu cliquable via `names.link`) ;
  - `ia_annuler`.
- L'agent s'exécute dans un thread, comme `_handle_cmd`. Il **n'utilise pas** la console de capture globale : il appelle directement les services.
- Dans `overlay/menus.py`, un thème « IA » propose des demandes prêtes (« Que vendre ici ? », « Meilleure route vers ma destination »).

## 5. Gestionnaire du moteur d'inférence (`ai/runtime.py`)

### Machine d'états

```
DÉSACTIVÉ ─(ia.mode != off)─► DÉTECTION ─ joignable ─► PRÊT
                                 │ non joignable
                                 ├─ mode = externe ─► INDISPONIBLE (message + bouton Réessayer)
                                 └─ mode = gere ─► LANCEMENT ─ /health 200 ─► PRÊT
                                                     │ échec/délai
                                                     └► ÉCHEC (journal, message)
PRÊT ─(fin de uexinfo, si lancé par uexinfo)─► ARRÊT
```

### Détection, selon le moteur configuré

| Moteur | Sonde | Prêt si |
|---|---|---|
| llama-server | `GET {base_url}/health` | 200 `{"status":"ok"}` (renvoie 503 pendant le chargement) |
| Ollama | `GET {base_url}/api/tags` | 200, et le modèle configuré présent dans la liste |
| Compatible OpenAI (générique) | `GET {base_url}/v1/models` | 200 |
| Anthropic | aucune sonde réseau au démarrage | la variable d'environnement nommée existe (sans lire sa valeur dans les journaux) |

### Lancement (mode `gere`, moteur llama-server seulement)

- Binaire : `ia.gere.binaire`. Sinon, la copie installée par uexinfo dans `<data>/ia/llama/<version>/`. Sinon, `llama-server` trouvé dans le `PATH`.
- Commande construite à partir de la configuration : `-m <gguf> --host 127.0.0.1 --port <port> -c <ctx> -t <threads> -ngl <couches> [--n-cpu-moe N] [--api-key-file <fichier>] [args_extra…]`. **Toujours passer `--port`**, car le port par défaut a changé selon les versions.
- Si le port est occupé par autre chose qu'un llama-server, uexinfo **n'en lance pas** un autre : il passe à l'état ÉCHEC avec un message explicite.
- `subprocess.Popen` dans un nouveau groupe de processus (`CREATE_NEW_PROCESS_GROUP` sous Windows, `start_new_session=True` sous Linux), sortie redirigée vers `<data>/logs/llama-server.log`.
- Attente de `/health` = 200, avec une limite configurable (120 s par défaut). Pendant ce temps, l'overlay affiche « Chargement du modèle… ».
- **Arrêt seulement si c'est uexinfo qui l'a lancé** : on conserve le PID, et à la sortie on termine proprement (SIGTERM, ou `CTRL_BREAK_EVENT` sous Windows), puis on tue le processus au bout de 10 s.
- Politique de démarrage `ia.demarrage` :
  - `au_lancement` : au démarrage de uexinfo ;
  - `a_la_demande` (par défaut) : à la première question ;
  - `jamais` : jamais de lancement automatique.

### Profils de ressources

`ia.profil = "jeu" | "libre"` change `ngl`, `threads` et `ctx`. Par exemple, « jeu » = `-ngl 0`, 6 threads, 8 000 tokens de contexte ; « libre » = `-ngl all`, 16 000 tokens.
On peut ensuite basculer automatiquement selon la présence de `StarCitizen.exe`. C'est optionnel, pour une v2.

## 6. Configuration (`config.toml`, section `[ia]`)

```toml
[ia]
mode = "gere"                 # off | externe | gere
moteur = "llama-server"       # llama-server | ollama | openai_compat | anthropic
base_url = "http://127.0.0.1:8085"
modele = "LFM2.5-8B-A1B"      # nom envoyé dans les requêtes (ou nom Ollama)
demarrage = "a_la_demande"    # au_lancement | a_la_demande | jamais
profil = "jeu"                # jeu | libre
api_key_env = ""              # NOM d'une variable d'environnement, jamais la valeur
max_etapes = 6
delai_s = 90

[ia.gere]
binaire = ""                  # vide = copie installée par uexinfo, puis PATH
gguf = ""                     # vide = <data>/ia/models/LFM2.5-8B-A1B-Q4_K_M.gguf
port = 8085
args_extra = []

[ia.profils.jeu]
ngl = "0"
threads = 6
ctx = 8192

[ia.profils.libre]
ngl = "all"
threads = 8
ctx = 16384
```

`/config ia` affiche l'état du gestionnaire (moteur, URL, état, PID si lancé par uexinfo) et propose « Tester », « Lancer » et « Arrêter ».

## 7. Distribution

uexinfo est distribué aujourd'hui par `git clone` et les scripts `scripts/uexinfogene.ps1` (Windows) et `scripts/uexinfolnx.sh` (Linux). Le volet IA est **optionnel** et **ne s'installe qu'avec l'accord de l'utilisateur**.

1. **Ne rien embarquer dans le dépôt** : ni binaire llama.cpp, ni modèle GGUF d'environ 5 Go.
2. **Commande `/config ia installer`**, ou option `-WithIA` / `--with-ia` des scripts. Elle :
   - détecte la plateforme et le GPU (`nvidia-smi` présent → CUDA ; sinon Vulkan ; sinon CPU), avec le choix proposé à l'utilisateur ;
   - télécharge l'archive llama.cpp **à une version épinglée** dans `uexinfo/ai/versions.toml` (numéro de build et SHA-256 relevé à l'épinglage) ;
   - vérifie le SHA-256 et décompresse dans `<data>/ia/llama/<build>/` (sous Windows, avec la variante CUDA, décompresser aussi l'archive `cudart` dans le même dossier) ;
   - télécharge le GGUF épinglé (dépôt, fichier et SHA-256 dans `versions.toml`) dans `<data>/ia/models/`, avec une barre de progression ;
   - écrit `[ia]` avec `mode = "gere"`.
3. **Désinstallation** : `/config ia desinstaller` supprime `<data>/ia/` et remet `mode = "off"`.
4. **Licences** : llama.cpp est sous licence MIT. Vérifier la licence de LFM2.5 au moment de l'épinglage et l'afficher avant le téléchargement. Le modèle est téléchargé par l'utilisateur, il n'est pas redistribué par uexinfo.
5. **Linux** : les archives officielles couvrent le CPU et Vulkan. Pour CUDA, il faut compiler (voir `docs/INSTALL_LLAMA_SERVER.md`) et renseigner `ia.gere.binaire`.
6. **Ollama déjà installé** : `moteur = "ollama"`, `mode = "externe"`. Le gestionnaire vérifie seulement la présence du modèle.

## 8. Ordre de réalisation

| Étape | Contenu | Critère de fin |
|---|---|---|
| 0 | Test de faisabilité de l'inférence : llama-server + LFM2.5 + 2 outils factices (script hors de l'application) | `tool_calls` structurés reçus ; latence CPU et GPU mesurée |
| 1 | Socle MVC : `core/schemas/base.py`, `Resultat`, `Ref`, `views/ai.py`, tests d'architecture (P2, vues sans dépendance aux sources) | Tests au vert |
| 2 | Migration de `/trade` (bilan) : service, schéma, `views/html/trade.py` | Affichage identique avant/après (test de comparaison), 160+ tests au vert |
| 3 | Migrations suivantes, une commande par session : `/trade buy/sell`, `/info`, `/nav route`, `/mission` (liste) | Même critère |
| 4 | `ai/runtime.py` + `[ia]` + `/config ia` | Détection, lancement et arrêt testés avec un faux serveur HTTP |
| 5 | `ai/tools.py` + `ai/mcp_server.py` | Outils validés depuis Claude Code |
| 6 | `ai/agent.py` + `ai/providers.py` | Boucle testée avec un LLM simulé, puis avec LFM2.5 |
| 7 | Overlay : messages `ia_*`, thème IA dans `menus.py` | Essai en jeu |
| 8 | Installation (`/config ia installer`, options des scripts) | Installation propre sous Windows et Linux |
| 9 | Évaluation : 30 questions réelles (`tests/ia_eval/`), score par modèle | Rapport comparatif |

Chaque étape = une session, des commits atomiques, une entrée dans `ACTIVITY_LOG.md` et la mise à jour de `_ANNUAIRE_UEXINFO.md`.
