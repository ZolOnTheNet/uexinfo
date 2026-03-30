 # recopie mission pour test
 #Get-ChildItem "ScreenShot-2026-03-21_*.jpg" | Rename-Item -NewName { $_.Name -replace '2026-03-21', (Get-Date -Format 'yyyy-MM-dd') }

  $src   = "C:\Users\garrigues\Documents\devlog\python\uexinfo\extprg\SC-images\OLD"
  $dst   = "C:\Users\garrigues\Documents\devlog\python\uexinfo\extprg\SC-images"
  #$src = "OLD"
  #$dst = "."
  $today = Get-Date -Format 'yyyy-MM-dd'

  # Noms déjà présents dans SC-images (hors OLD)
  $existants = Get-ChildItem $dst -Filter "*.jpg" | Select-Object -ExpandProperty Name

  Get-ChildItem $src -Filter "*.jpg" | Where-Object { $existants -contains $_.Name } | ForEach-Object {
      $nouveauNom = $_.Name -replace '\d{4}-\d{2}-\d{2}', $today
      Copy-Item $_.FullName -Destination (Join-Path $dst $nouveauNom)
      Write-Host "$($_.Name)  →  $nouveauNom"
  }

 # Dry-run d'abord (pour voir sans copier) :

#  $src   = "C:\Users\garrigues\Documents\devlog\python\uexinfo\extprg\SC-images\OLD"
#  $dst   = "C:\Users\garrigues\Documents\devlog\python\uexinfo\extprg\SC-images"
#  $today = Get-Date -Format 'yyyy-MM-dd'

#  $existants = Get-ChildItem $dst -Filter "*.jpg" | Select-Object -ExpandProperty Name

#  Get-ChildItem $src -Filter "*.jpg" | Where-Object { $existants -contains $_.Name } | ForEach-Object {
#      "$($_.Name)  →  $($_.Name -replace '\d{4}-\d{2}-\d{2}', $today)"
#  }