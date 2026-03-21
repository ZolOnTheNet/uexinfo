"""Modèles résultat de scan — ScanResult et ScannedCommodity."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScannedCommodity:
    name: str
    commodity_id: int = 0
    quantity: int | None = None
    stock: str = ""
    stock_status: int = 0   # 1=out, 2=very low, 3=low, 4=medium, 5=high, 7=max
    price: int = 0          # aUEC/SCU
    in_demand: bool = False  # True = section INDEMAND (terminal veut mais joueur n'a pas)


@dataclass
class ScanResult:
    terminal: str
    timestamp: datetime = field(default_factory=datetime.now)
    commodities: list[ScannedCommodity] = field(default_factory=list)
    source: str = "ocr"     # "ocr" | "log"
    mode: str = "buy"       # "buy" = IN STOCK (achat) | "sell" = IN DEMAND / SELLABLE CARGO (vente)
    validated: bool = False  # True = soumis à l'API UEX par l'utilisateur (données confirmées)
    image_path: str = ""     # Chemin absolu du screenshot source (source="ocr" uniquement)
