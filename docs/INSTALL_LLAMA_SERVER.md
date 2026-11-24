# Installer llama-server (poste de développement, Windows et Linux)

> Vérifié le 2026-11-24.
> llama-server est un exécutable du projet **llama.cpp** (ggml-org, licence MIT) : un serveur HTTP compatible OpenAI. Pas besoin de compiler sous Windows ; sous Linux, seulement pour CUDA.

## 1. Choisir la variante

| Machine | Windows | Linux |
|---|---|---|
| GPU NVIDIA | `llama-bNNNNN-bin-win-cuda-12.4-x64.zip` **et** `cudart-llama-bin-win-cuda-12.4-x64.zip` (ou les variantes 13.x si le pilote les prend en charge) | Compilation CUDA (§3.2), ou l'archive Vulkan |
| Autre GPU (AMD, Intel) ou NVIDIA sans CUDA | `llama-bNNNNN-bin-win-vulkan-x64.zip` | `llama-bNNNNN-bin-ubuntu-vulkan-x64.tar.gz` |
| CPU seul (par exemple pendant une session de jeu) | `llama-bNNNNN-bin-win-cpu-x64.zip` | `llama-bNNNNN-bin-ubuntu-x64.tar.gz` |

`NNNNN` est le numéro de build. Prendre le build le plus récent sur https://github.com/ggml-org/llama.cpp/releases, puis **noter ce numéro** : il sera épinglé dans `uexinfo/ai/versions.toml`. Un build récent est nécessaire pour la lecture des appels d'outils de LFM2.5.

## 2. Windows

### 2.1 Installation par archive (recommandée : version maîtrisée)

```powershell
# Dossier de travail (adapter au besoin)
$dst = "$env:LOCALAPPDATA\llama.cpp\bNNNNN"
New-Item -ItemType Directory -Force $dst | Out-Null
# Décompresser l'archive principale, puis (variante CUDA) cudart dans le MÊME dossier
Expand-Archive .\llama-bNNNNN-bin-win-cuda-12.4-x64.zip -DestinationPath $dst
Expand-Archive .\cudart-llama-bin-win-cuda-12.4-x64.zip -DestinationPath $dst
& "$dst\llama-server.exe" --version
```

Pour le `PATH` (modification **permanente**, de l'utilisateur seulement) :
```powershell
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$dst", "User")
```
Pour revenir en arrière, retirer `$dst` de la variable `Path` de l'utilisateur (Paramètres → Variables d'environnement).

### 2.2 Alternative : winget

```powershell
winget install llama.cpp
```
Plus simple, mais la variante installée et la version suivent le paquet winget. Pour uexinfo, on préfère l'archive épinglée (§2.1).

## 3. Linux

### 3.1 Archive CPU ou Vulkan

```bash
dst=~/.local/opt/llama.cpp/bNNNNN
mkdir -p "$dst" && tar -xzf llama-bNNNNN-bin-ubuntu-vulkan-x64.tar.gz -C "$dst" --strip-components=1
# Vulkan : pilote et chargeur nécessaires
sudo apt install libvulkan1 mesa-vulkan-drivers vulkan-tools   # vulkaninfo pour vérifier
"$dst/llama-server" --version     # si le binaire est dans un sous-dossier : ls "$dst"
```
Vérifier l'arborescence de l'archive : selon le build, les binaires sont à la racine ou dans `build/bin/`. Adapter `--strip-components` ou le chemin en conséquence.

### 3.2 Compilation CUDA (GPU NVIDIA)

```bash
sudo apt install build-essential cmake git nvidia-cuda-toolkit   # ou le CUDA Toolkit de NVIDIA
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
git checkout bNNNNN                       # même build que celui épinglé
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j
./build/bin/llama-server --version
```

## 4. Télécharger le modèle LFM2.5-8B-A1B

**Option A** : laisser llama-server télécharger le modèle (pratique en développement).
```bash
llama-server -hf LiquidAI/LFM2.5-8B-A1B-GGUF:Q4_K_M --port 8085
```
`-hf` télécharge depuis Hugging Face ; la quantification par défaut est Q4_K_M. `llama-server --cache-list` affiche les modèles en cache, et `--offline` force l'utilisation du cache.

**Option B** (celle que uexinfo utilisera) : télécharger le fichier `.gguf` dans un dossier connu, puis lancer avec `-m <chemin>`. Prendre un fichier **récent** : les GGUF ont été reconvertis après un correctif du tokenizer pour l'appel d'outils.

Avant de télécharger, vérifier la licence de LFM2.5 sur la fiche Hugging Face du modèle.

## 5. Lancer

```bash
# GPU (profil « libre »)
llama-server -m <chemin>/LFM2.5-8B-A1B-Q4_K_M.gguf --host 127.0.0.1 --port 8085 -c 16384 -ngl all --jinja
# CPU seul (profil « jeu »)
llama-server -m <chemin>/LFM2.5-8B-A1B-Q4_K_M.gguf --host 127.0.0.1 --port 8085 -c 8192 -ngl 0 -t 6 --jinja
```

| Option | Rôle |
|---|---|
| `--port` | **Toujours la préciser** : le port par défaut a changé selon les versions |
| `--host 127.0.0.1` | Écoute locale seulement (valeur par défaut) |
| `-c` | Taille du contexte : plus elle est grande, plus il faut de RAM ou de VRAM |
| `-ngl` | Couches placées en VRAM : `0`, un nombre, `auto` ou `all` |
| `--n-cpu-moe N` | Garde sur le CPU les poids MoE des N premières couches (pour une VRAM limitée) |
| `-t` | Nombre de threads CPU |
| `--jinja` | Gabarit de chat et lecture des appels d'outils (activé par défaut dans les versions récentes) |
| `--api-key-file` | Clé exigée par le serveur, à utiliser si on l'expose au-delà de la machine |

## 6. Vérifier

```bash
curl -s http://127.0.0.1:8085/health          # 503 pendant le chargement, puis {"status":"ok"}
curl -s http://127.0.0.1:8085/v1/models
curl -s http://127.0.0.1:8085/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "LFM2.5-8B-A1B",
  "messages": [{"role":"user","content":"Quel temps fait-il à Lyon ?"}],
  "tools": [{"type":"function","function":{"name":"meteo","description":"Météo d une ville",
             "parameters":{"type":"object","properties":{"ville":{"type":"string"}},"required":["ville"]}}}]
}'
```
Attendu : `choices[0].message.tool_calls[0].function.name == "meteo"`. Si l'appel arrive en texte brut dans `content`, c'est que le build est trop ancien, ou que le GGUF date d'avant le correctif du tokenizer.

Sous PowerShell : `Invoke-RestMethod http://127.0.0.1:8085/health`.

## 7. Usage depuis une autre machine du réseau local (optionnel, TEMPORAIRE)

1. Lancer avec `--host 0.0.0.0 --api-key-file <fichier>`.
2. Ouvrir le port. **Cette modification est temporaire.**
   - Windows : `New-NetFirewallRule -DisplayName "llama-server dev" -Direction Inbound -Protocol TCP -LocalPort 8085 -Action Allow -Profile Private`
   - Linux (ufw) : `sudo ufw allow from 192.168.0.0/16 to any port 8085 proto tcp`
3. **Remise en état** après les essais :
   - Windows : `Remove-NetFirewallRule -DisplayName "llama-server dev"`
   - Linux : `sudo ufw delete allow from 192.168.0.0/16 to any port 8085 proto tcp`
   - relancer llama-server sans `--host 0.0.0.0`.
   