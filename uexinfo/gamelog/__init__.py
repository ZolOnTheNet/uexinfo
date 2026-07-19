"""Lecture en direct de Game.log (le log natif de Star Citizen), en lecture seule.

Distinct de `uexinfo.ocr` qui lit le log de SC-Datarunner (app.log) — ici on lit
directement le fichier écrit par le jeu lui-même, sans toucher au process
StarCitizen.exe (pas de lecture mémoire, pas de hook). Voir `docs/` pour le
détail de la démarche.
"""
