# Installation et lancement de UEXInfo

> Mis à jour le 2026-10-29. Lanceurs : `scripts/uexinfogene.ps1` (Windows) et `scripts/uexinfolnx.sh` (Linux).

## En bref

| Système | Commande, depuis le dossier `uexinfo` |
|---|---|
| Windows | `powershell -ExecutionPolicy Bypass -File scripts\uexinfogene.ps1` |
| Linux | `scripts/uexinfolnx.sh` |

Au premier lancement, le script crée l'environnement Python (`.venv`), installe les
dépendances, puis lance l'overlay. Les lancements suivants partent tout de suite.

Le script réinstalle tout seul quand il le faut :
- `pyproject.toml` a changé (nouvelle dépendance après un `git pull`) ;
- `.venv` est cassé, par exemple après une mise à jour de Python.

Au premier démarrage de l'overlay, les données UEX (terminaux, commodités, systèmes)
sont téléchargées puis gardées en cache.

---

## Windows

### Prérequis

- **Python 3.11 ou plus**, depuis [python.org](https://www.python.org/downloads/).
  Cocher « Add python.exe to PATH » pendant l'installation. Le script cherche d'abord
  le lanceur `py`, puis `python`. Il ignore l'alias du Microsoft Store, qui ouvre le
  Store au lieu de lancer Python.
- Le dossier du projet : `git clone https://github.com/ZolOnTheNet/uexinfo.git`, ou le
  zip de GitHub.

### Lancer

```powershell
cd uexinfo
powershell -ExecutionPolicy Bypass -File scripts\uexinfogene.ps1
```

`-ExecutionPolicy Bypass` évite le refus de Windows d'exécuter un script téléchargé.
Si tes réglages PowerShell l'autorisent déjà, `scripts\uexinfogene.ps1` suffit.

### Bouton sur le bureau

Clic droit sur le bureau → Nouveau → Raccourci, avec pour cible :

```
powershell.exe -ExecutionPolicy Bypass -File "C:\chemin\vers\uexinfo\scripts\uexinfogene.ps1"
```

La console reste ouverte à côté de l'overlay et affiche son journal.

### Bon à savoir

- Le script lance Python en UTF-8 (`PYTHONUTF8=1`) : les `✓`, `★` et les accents
  s'affichent correctement dans la console.
- Si le dossier est partagé avec un poste Linux et que son `.venv` vient de Linux, le
  script Windows n'y touche pas : il utilise `.venv-win` à la place.
- `scripts/uexinfo.ps1` est l'ancien lanceur, avec le chemin de Python d'un poste
  précis écrit en dur. Sur un autre poste, utiliser `uexinfogene.ps1`.

---

## Linux

Testé le 2026-10-29 sous GNOME (Wayland) : la fenêtre s'ouvre, la page se connecte au
serveur, la copie et l'enregistrement de la position marchent.

### Prérequis (Debian, Ubuntu et dérivés)

```bash
sudo apt install python3-venv python3-gi gir1.2-webkit2-4.1 tesseract-ocr xclip
```

| Paquet | Pourquoi |
|---|---|
| `python3-venv` | Créer l'environnement Python. Python 3.11 ou plus. |
| `python3-gi`, `gir1.2-webkit2-4.1` | La fenêtre de l'overlay (WebKitGTK). Pip ne peut pas l'installer, elle vient du système. |
| `tesseract-ocr` | Lire les captures d'écran du jeu (OCR). Facultatif. |
| `xclip` | Boutons « copier ». `wl-clipboard` (`wl-copy`) ou `xsel` conviennent aussi. |

### Lancer

```bash
cd uexinfo
scripts/uexinfolnx.sh
```

Le script vérifie ces prérequis et dit quel paquet installer s'il en manque un. Il crée
`.venv` avec `--system-site-packages`, pour que Python voie WebKitGTK installé par le
système.

### Bouton dans le menu des applications

Créer `~/.local/share/applications/uexinfo.desktop` (adapter le chemin) :

```ini
[Desktop Entry]
Type=Application
Name=UEXInfo
Comment=Overlay Star Citizen
Exec=/chemin/vers/uexinfo/scripts/uexinfolnx.sh
Terminal=false
Categories=Game;
```

Avec `Terminal=true`, un terminal s'ouvre et affiche le journal de l'overlay.

### Différences avec Windows

- **Raccourci clavier global** (alt+shift+u par défaut) : il ne répond que si la
  fenêtre active passe par X11/XWayland. Star Citizen sous Wine/Proton est dans ce cas ;
  une application Wayland native ne l'est pas. Sous Wayland, le script lance donc
  l'overlay via XWayland (`GDK_BACKEND=x11`), ce qui garde aussi « toujours au-dessus ».
- Pas de focus forcé quand l'overlay réapparaît : cliquer dans la fenêtre si la saisie
  ne répond pas.
- La retouche de transparence propre à Windows (DWM) n'existe pas sous Linux.

---

## Options des scripts

| Windows | Linux | Effet |
|---|---|---|
| `--hotkey f9`, `--port 8091` | idem | Options transmises à `python -m uexinfo` |
| `-Installer` | `--installer` | Prépare l'environnement sans lancer l'overlay |
| `-Reinstaller` | `--reinstaller` | Supprime et recrée l'environnement |

`--help` affiche les options de l'overlay lui-même.

---

## OCR des captures d'écran (facultatif)

L'OCR lit les écrans de terminaux et de contrats. Il lui faut Tesseract et le modèle
`eng_sc.traineddata`, entraîné sur les polices de Star Citizen par le projet
SC-Datarunner-UEX. Ce modèle n'est pas libre : il n'est pas dans le dépôt.

| Système | Tesseract | Modèle `eng_sc.traineddata` |
|---|---|---|
| Windows | `extprg\tesseract\Tesseract-OCR\tesseract.exe` (voir `extprg\tesseract\LISEZMOI.txt`), sinon celui de SC-Datarunner-UEX | `extprg\tesseract\data\`, sinon `extprg\SC-Datarunner-UEX\data\` |
| Linux | `/usr/bin/tesseract` (paquet `tesseract-ocr`) | à copier dans `extprg/tesseract/data/` depuis le poste Windows |

Au démarrage, la ligne `[OCR]` du journal indique ce qui a été trouvé et ce qui manque.
Sans le modèle, l'overlay fonctionne, mais l'OCR est indisponible ou peu fiable.

---

## Game.log (position automatique)

Dans l'overlay :

```
/config gamelog.install_path_live <dossier LIVE du jeu, celui qui contient Game.log>
/config gamelog.enabled on
```

`/game` affiche ensuite ce que l'overlay lit dans le journal du jeu.

---

## Où sont les données

| | Linux | Windows |
|---|---|---|
| Réglages (`config.toml`) | `~/.config/uexinfo/` | `%LOCALAPPDATA%\uexinfo\uexinfo\` |
| Caches UEX, scans, missions, notes, historique | `~/.local/share/uexinfo/` | `%LOCALAPPDATA%\uexinfo\uexinfo\` |

Le journal de l'overlay affiche le chemin exact de `config.toml` au démarrage
(`Config chargée : …`).

---

## Mettre à jour

```bash
git pull
```

Puis relancer avec le script : il réinstalle les dépendances si `pyproject.toml` a changé.

---

## En cas de problème

| Message ou symptôme | Solution |
|---|---|
| `Python 3.11 ou plus introuvable` | Installer Python (Windows : python.org ; Linux : `sudo apt install python3 python3-venv`). |
| `WebKitGTK introuvable` (Linux) | `sudo apt install python3-gi gir1.2-webkit2-4.1` |
| `Dépendances incomplètes` ou erreur de `pip` | Relancer avec `-Reinstaller` / `--reinstaller`. |
| Windows refuse d'exécuter le script | Passer par `powershell -ExecutionPolicy Bypass -File …` |
| Accents ou `✓` illisibles dans la console Windows | Lancer avec `uexinfogene.ps1`, qui passe Python en UTF-8. |
| `Presse-papiers indisponible` (Linux) | `sudo apt install xclip` |
| Le raccourci clavier ne fait rien (Linux) | La fenêtre active n'est pas une fenêtre X11 : cliquer sur l'overlay ou sur le jeu, puis réessayer. |
| Le port 8090 est déjà pris | Si c'est un autre UEXInfo (même masqué), rien à faire : il est fermé au lancement et le nouveau prend le relais. Si c'est un autre programme : `--port 8091`. |

---

## Installation manuelle (sans script)

```bash
python -m venv .venv               # Linux : python3 -m venv --system-site-packages .venv
.venv\Scripts\activate             # Linux : source .venv/bin/activate
pip install -e .
uexinfo                            # ou : python -m uexinfo
```
