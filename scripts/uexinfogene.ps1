<#
Lance l'overlay UEXInfo sous Windows, sur n'importe quel poste (aucun chemin en dur).

Au premier lancement, prépare l'environnement Python (.venv) et installe les
dépendances. Il les réinstalle si .venv est cassé (mise à jour de Python) ou si
pyproject.toml a changé. Ensuite, il lance l'overlay.

Usage (PowerShell, depuis n'importe quel dossier) :
  scripts\uexinfogene.ps1                    lance l'overlay
  scripts\uexinfogene.ps1 --hotkey f9        options transmises à « python -m uexinfo »
  scripts\uexinfogene.ps1 -Installer         prépare l'environnement sans lancer
  scripts\uexinfogene.ps1 -Reinstaller       recrée l'environnement de zéro

Si Windows refuse d'exécuter le script, ou pour un raccourci sur le bureau :
  powershell -ExecutionPolicy Bypass -File "<dossier uexinfo>\scripts\uexinfogene.ps1"

Prérequis : Python 3.11 ou plus (python.org, case « Add python.exe to PATH »).
#>
param(
    [switch]$Installer,
    [switch]$Reinstaller,
    [Parameter(ValueFromRemainingArguments = $true)] [string[]]$UexArgs
)
# Pas de $ErrorActionPreference = 'Stop' : sous Windows PowerShell 5.1, la moindre ligne
# écrite sur stderr par python ou pip deviendrait une erreur bloquante. Chaque étape
# vérifie $LASTEXITCODE à la place.

function Erreur([string]$msg) { Write-Host "✗ $msg" -ForegroundColor Red; exit 1 }
function Info([string]$msg)   { Write-Host "→ $msg" }

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root '.venv'
# Un .venv sans dossier Scripts a été créé par Linux (dossier partagé) : on n'y touche pas.
if ((Test-Path $Venv) -and -not (Test-Path (Join-Path $Venv 'Scripts'))) {
    $Venv = Join-Path $Root '.venv-win'
}
$Py    = Join-Path $Venv 'Scripts\python.exe'
$Stamp = Join-Path $Venv '.uexinfo-installe'

# ── Python du système ────────────────────────────────────────────────────────
# Lanceur « py » d'abord, sinon « python ». L'alias du Microsoft Store (WindowsApps)
# ouvre le Store au lieu de lancer Python : il est ignoré.
function Find-Python {
    foreach ($c in @(@{ Exe = 'py'; Args = @('-3') }, @{ Exe = 'python'; Args = @() })) {
        $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
        if (-not $cmd -or $cmd.Source -like '*\WindowsApps\*') { continue }
        & $cmd.Source @($c.Args) -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>$null
        if ($LASTEXITCODE -eq 0) { return @{ Exe = $cmd.Source; Args = $c.Args } }
    }
    return $null
}

# ── Environnement Python ─────────────────────────────────────────────────────
function Test-Venv {
    if (-not (Test-Path $Py)) { return $false }
    & $Py -m pip --version *> $null
    return ($LASTEXITCODE -eq 0)
}

if ($Reinstaller -or ((Test-Path $Venv) -and -not (Test-Venv))) {
    Info "Suppression de l'ancien environnement $Venv"
    Remove-Item -Recurse -Force -ErrorAction Stop $Venv
}
if (-not (Test-Path $Venv)) {
    $sys = Find-Python
    if (-not $sys) { Erreur 'Python 3.11 ou plus introuvable : installez-le depuis python.org (case « Add python.exe to PATH »).' }
    Info "Création de l'environnement Python ($(& $sys.Exe @($sys.Args) --version))"
    & $sys.Exe @($sys.Args) -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Erreur "Création de $Venv impossible." }
}
$pyproject = Join-Path $Root 'pyproject.toml'
if (-not (Test-Path $Stamp) -or (Get-Item $pyproject).LastWriteTime -gt (Get-Item -Force $Stamp).LastWriteTime) {
    Info 'Installation des dépendances (pip install -e .)'
    & $Py -m pip install --quiet --disable-pip-version-check -e $Root
    if ($LASTEXITCODE -ne 0) { Erreur 'Échec de pip install : relancer avec -Reinstaller.' }
    New-Item -ItemType File -Force $Stamp | Out-Null
}
& $Py -c 'import webview, pynput, websockets'
if ($LASTEXITCODE -ne 0) { Erreur 'Dépendances incomplètes : relancer avec -Reinstaller.' }

if ($Installer -or $Reinstaller) { Info 'Environnement prêt.'; exit 0 }

# ── Lancement ────────────────────────────────────────────────────────────────
# Sortie en UTF-8 : évite les caractères illisibles (✓, ★, accents) dans la console.
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $Root
& $Py -m uexinfo @UexArgs
exit $LASTEXITCODE
