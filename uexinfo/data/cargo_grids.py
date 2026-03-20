"""
Grilles cargo des vaisseaux Star Citizen.

Ce module définit les contraintes physiques des grilles cargo et les règles
de subdivision des conteneurs.

Système d'extension :
- Grids de base : SHIP_CARGO_GRIDS (fourni avec le programme)
- Overrides utilisateur : ~/.uexinfo/cargo_grids_ext.json
"""

from __future__ import annotations

import json
from pathlib import Path

# ── Hauteur physique des conteneurs ──────────────────────────────────────────

# Hauteur physique (cellules) par taille de caisse
CONTAINER_HEIGHT: dict[int, int] = {
    1: 1,
    2: 1,
    4: 1,
    8: 2,
    16: 2,
    24: 2,
    32: 2,
}

# ── Règles de subdivision ────────────────────────────────────────────────────

# Règles de subdivision : chaque taille → liste de subdivisions possibles
# Format : taille_source → [[(taille1, qté1), (taille2, qté2), ...], ...]
SUBDIVISION_RULES: dict[int, list[list[tuple[int, int]]]] = {
    32: [[(16, 2)], [(24, 1), (8, 1)]],  # 32 → 2×16 OU 24+8
    24: [[(12, 2)]],  # Théorique, 12 SCU n'existe pas encore
    16: [[(8, 2)]],
    8: [[(4, 2)]],
    4: [[(2, 2)]],
    2: [[(1, 2)]],
}

# Tailles de conteneurs valides (en SCU)
VALID_SIZES = {1, 2, 4, 8, 16, 24, 32}

# ── Grilles cargo par vaisseau ───────────────────────────────────────────────

# Configuration cargo par vaisseau (nom → {taille_scu: quantité})
# Données extraites de docs/grids_ships_study.md section "Nouvelle notation des cargos"
# Format : nom du vaisseau → configuration cargo
SHIP_CARGO_GRIDS: dict[str, dict[int, int]] = {
    # Crusader Industries
    "Crusader Mercury Star Runner": {24: 3, 4: 9, 2: 2, 1: 2},
    "Crusader M2 Hercules": {32: 10, 4: 40, 2: 21},
    "Crusader A2 Hercules": {32: 6, 24: 1},
    "Crusader C2 Hercules": {32: 20, 2: 28},
    "Crusader C1 Spirit": {32: 2},
    "Crusader Intrepid": {2: 4},

    # Drake Interplanetary
    "Drake Caterpillar": {24: 16, 16: 3, 4: 4, 2: 56, 1: 16},
    "Drake Corsair": {32: 2, 2: 4},
    "Drake Cutter": {1: 4},
    "Drake Clipper": {2: 6},
    "Drake Cutlass Red": {2: 4, 1: 4},
    "Drake Cutlass Blue": {2: 4, 1: 4},
    "Drake Cutlass Black": {16: 2, 2: 6},
    "Drake Golem X": {32: 2},

    # MISC
    "MISC Starlancer TAC": {32: 2, 4: 8},
    "MISC Starlancer MAX": {32: 6, 4: 8},
    "MISC Hull A": {16: 4},
    "MISC Hull C": {32: 144},
    "MISC Starfarer": {24: 4, 16: 4, 8: 2, 4: 10, 2: 35, 1: 5},
    "MISC Starfarer Gemini": {24: 4, 16: 4, 8: 2, 4: 10, 2: 35, 1: 5},
    "MISC Freelancer": {32: 1, 4: 4, 2: 9},
    "MISC Freelancer MAX": {32: 2, 8: 4, 2: 12},
    "MISC Freelancer DUR": {16: 1, 4: 2, 2: 6},
    "MISC Reliant Kore": {2: 2, 1: 2},
    "MISC Fortune": {4: 3, 2: 2},

    # Origin Jumpworks
    "Origin 325a": {4: 1},
    "Origin 350r": {4: 1},
    "Origin 300i": {4: 2},
    "Origin 315p": {4: 3},
    "Origin 400i": {24: 1, 2: 8, 1: 2},
    "Origin 100i": {2: 1},
    "Origin 125a": {2: 1},
    "Origin 135c": {2: 3},
    "Origin 600i Touring": {2: 8, 1: 4},
    "Origin 600i Explorer": {2: 20, 1: 4},
    "Origin 890 Jump": {32: 6, 24: 4, 16: 2, 2: 28, 1: 12},

    # RSI
    "RSI Zeus Mk II CL": {32: 2, 4: 8, 2: 16},
    "RSI Zeus Mk II ES": {16: 2},
    "RSI Perseus": {32: 3},
    "RSI Aurora CL": {3: 2},
    "RSI Aurora ES": {2: 1, 1: 1},
    "RSI Aurora LN": {2: 1, 1: 1},
    "RSI Aurora LX": {2: 1, 1: 1},
    "RSI Aurora MR": {2: 1, 1: 1},
    "RSI Constellation Taurus": {32: 2, 24: 2, 4: 14, 2: 3},
    "RSI Constellation Andromeda": {32: 2, 4: 8},
    "RSI Constellation Aquila": {32: 2, 4: 8},
    "RSI Constellation Phoenix": {32: 2, 2: 8},
    "RSI Hermes": {32: 8, 16: 2},
    "RSI Polaris": {},  # 576 SCU mais pas de détails
    "RSI Salvation": {4: 1, 2: 1},
    "RSI Apollo Triage": {2: 16},
    "RSI Apollo Medivac": {2: 16},

    # Anvil Aerospace
    "Anvil Paladin": {2: 2},
    "Anvil Carrack": {24: 16, 6: 6, 2: 12},
    "Anvil Terrapin": {2: 2},
    "Anvil Valkyrie": {24: 2, 6: 4, 9: 2},
    "Anvil Hornet F7C Mk II": {2: 1},

    # Aegis Dynamics
    "Aegis Asgard": {32: 4, 24: 2, 1: 4},

    # Argo Astronautics
    "Argo Pisces C8": {1: 4},
    "Argo Pisces C8X": {1: 4},
}

# Par vaisseau : [(hauteur_dispo, scu_dans_cette_zone), ...]
# Zones triées par hauteur décroissante
# OBSOLÈTE : Utilisez SHIP_CARGO_GRIDS à la place
SHIP_CARGO_ZONES: dict[str, list[tuple[int, int]]] = {
    # Crusader Industries
    "Crusader M2 Hercules": [(2, 320), (1, 202)],
    "Crusader C2 Hercules": [(4, 696)],
    "Crusader A2 Hercules": [(2, 234)],

    # Drake Interplanetary
    "Drake Caterpillar": [(2, 576)],
    "Drake Cutlass Black": [(2, 46)],

    # MISC
    "MISC Freelancer": [(2, 66)],
    "MISC Freelancer MAX": [(2, 120)],
    "MISC Hull A": [(2, 64)],

    # Anvil Aerospace
    "Anvil Carrack": [(2, 456)],

    # RSI
    "RSI Constellation Taurus": [(2, 174)],

    # ARGO
    "ARGO RAFT": [(2, 96)],
}

# ── Fonctions utilitaires ────────────────────────────────────────────────────


def effective_scu(ship_name: str, min_container_scu: int) -> int | None:
    """
    Retourne le SCU effectivement chargeable si le terminal impose
    des caisses de taille >= min_container_scu.

    Retourne None si le vaisseau n'est pas dans la table.

    Exemples :
        >>> effective_scu("Crusader M2 Hercules", 8)
        320
        >>> effective_scu("Crusader C2 Hercules", 8)
        696
        >>> effective_scu("Crusader M2 Hercules", 1)
        522
    """
    zones = SHIP_CARGO_ZONES.get(ship_name)
    if zones is None:
        return None
    min_h = CONTAINER_HEIGHT.get(min_container_scu, 1)
    return sum(scu for h, scu in zones if h >= min_h)


def calculate_total_scu(config: dict[int, int]) -> int:
    """
    Calcule le SCU total d'une configuration de cargo.

    Args:
        config: dict {taille_scu: quantité}

    Returns:
        SCU total

    Exemples :
        >>> calculate_total_scu({32: 10, 16: 4})
        384
        >>> calculate_total_scu({8: 20})
        160
    """
    return sum(size * qty for size, qty in config.items())


def parse_cargo_spec(spec: str) -> tuple[int, int] | None:
    """
    Parse une spécification de cargo au format "<taille>x<quantité>".

    Args:
        spec: chaîne au format "32x4" ou "16x2"

    Returns:
        (taille, quantité) ou None si invalide

    Exemples :
        >>> parse_cargo_spec("32x4")
        (32, 4)
        >>> parse_cargo_spec("16x2")
        (16, 2)
        >>> parse_cargo_spec("invalid")
        None
    """
    if "x" not in spec:
        return None
    parts = spec.lower().split("x")
    if len(parts) != 2:
        return None
    try:
        size = int(parts[0])
        qty = int(parts[1])
        if size not in VALID_SIZES:
            return None
        if qty < 0:
            return None
        return (size, qty)
    except ValueError:
        return None


def format_cargo_config(config: dict[int, int]) -> str:
    """
    Formate une configuration de cargo pour l'affichage.

    Args:
        config: dict {taille_scu: quantité}

    Returns:
        Chaîne formatée "32x4 16x2 8x1"

    Exemples :
        >>> format_cargo_config({32: 4, 16: 2, 8: 1})
        '32×4  16×2  8×1'
    """
    if not config:
        return "(vide)"
    # Trier par taille décroissante
    sorted_items = sorted(config.items(), key=lambda x: -x[0])
    return "  ".join(f"{size}×{qty}" for size, qty in sorted_items)


# ── Gestionnaire de grilles cargo ───────────────────────────────────────────


class CargoGridManager:
    """
    Gestionnaire de grilles cargo avec système d'extension.

    - Grids de base : SHIP_CARGO_GRIDS (fourni avec le programme)
    - Overrides utilisateur : ~/.uexinfo/cargo_grids_ext.json
    """

    def __init__(self, config_dir: Path | None = None):
        """
        Initialise le gestionnaire.

        Args:
            config_dir: Répertoire de configuration (défaut: ~/.uexinfo)
        """
        if config_dir is None:
            config_dir = Path.home() / ".uexinfo"
        self.config_dir = Path(config_dir)
        self.ext_file = self.config_dir / "cargo_grids_ext.json"
        self.overrides: dict[str, dict[int, int]] = {}
        self.load()

    def load(self) -> None:
        """Charge les overrides depuis le fichier d'extension."""
        if not self.ext_file.exists():
            self.overrides = {}
            return

        try:
            with open(self.ext_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Convertir les clés de str → int pour les tailles SCU
            self.overrides = {
                ship_name: {int(size): qty for size, qty in config.items()}
                for ship_name, config in data.items()
            }
        except (json.JSONDecodeError, ValueError, OSError):
            self.overrides = {}

    def save(self) -> None:
        """Sauvegarde les overrides dans le fichier d'extension."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        # Convertir les clés int → str pour JSON
        data = {
            ship_name: {str(size): qty for size, qty in config.items()}
            for ship_name, config in self.overrides.items()
        }
        with open(self.ext_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalise : minuscules + underscores→espaces + espaces multiples collapsés."""
        return " ".join(name.lower().replace("_", " ").split())

    def get_grid(self, ship_name: str) -> dict[int, int] | None:
        """
        Retourne la grid cargo d'un vaisseau (override ou base).

        Matching par ordre de priorité :
        1. Override exact
        2. Override normalisé (casse + underscores)
        3. Grid de base exacte
        4. Grid de base normalisée
        5. Grid dont la clé est un préfixe du nom vaisseau
           (ex: "Crusader M2 Hercules" ⊂ "Crusader M2 Hercules Starlifter")
        """
        # 1. Override exact
        if ship_name in self.overrides:
            return self.overrides[ship_name]

        norm = self._normalize(ship_name)

        # 2. Override normalisé
        for key, val in self.overrides.items():
            if self._normalize(key) == norm:
                return val

        # 3. Grid de base exacte
        if ship_name in SHIP_CARGO_GRIDS:
            return SHIP_CARGO_GRIDS[ship_name]

        # 4. Grid de base normalisée exacte
        for key, val in SHIP_CARGO_GRIDS.items():
            if self._normalize(key) == norm:
                return val

        # 5. Grid dont la clé normalisée est contenue dans le nom du vaisseau
        #    (variante avec suffixe supplémentaire, ex: "Starlifter", "Best In Show…")
        best_key: str | None = None
        best_len = 0
        for key in SHIP_CARGO_GRIDS:
            key_norm = self._normalize(key)
            if key_norm in norm and len(key_norm) > best_len:
                best_key = key
                best_len = len(key_norm)
        if best_key:
            return SHIP_CARGO_GRIDS[best_key]

        return None

    def set_grid(self, ship_name: str, config: dict[int, int]) -> None:
        """
        Définit la grid cargo d'un vaisseau (override).

        Args:
            ship_name: Nom du vaisseau
            config: dict {taille_scu: quantité}
        """
        self.overrides[ship_name] = config
        self.save()

    def clear_grid(self, ship_name: str) -> bool:
        """
        Supprime l'override d'un vaisseau et revient à la grid de base.

        Args:
            ship_name: Nom du vaisseau

        Returns:
            True si un override a été supprimé, False sinon
        """
        if ship_name in self.overrides:
            del self.overrides[ship_name]
            self.save()
            return True
        return False

    def has_override(self, ship_name: str) -> bool:
        """Vérifie si un vaisseau a un override."""
        return ship_name in self.overrides
