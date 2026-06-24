"""Données de moves.

Source : `data/moves.json`, généré depuis `@pkmn/dex` (`scripts/gen_moves.mjs`).
IDs normalisés en ID Showdown (cf. basestats.to_id).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .basestats import to_id

REPO_ROOT = Path(__file__).resolve().parents[2]
MOVES_PATH = REPO_ROOT / "data" / "moves.json"


@dataclass(frozen=True)
class Move:
    id: str
    name: str
    type: str
    category: str            # 'Physical' | 'Special' | 'Status'
    base_power: int
    priority: int = 0
    target: str = "normal"
    is_spread: bool = False
    makes_contact: bool = False

    @property
    def is_status(self) -> bool:
        return self.category == "Status"

    @property
    def is_physical(self) -> bool:
        return self.category == "Physical"

    @property
    def is_special(self) -> bool:
        return self.category == "Special"


@lru_cache(maxsize=1)
def _load_moves() -> dict[str, dict]:
    with MOVES_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)["moves"]


@lru_cache(maxsize=None)
def get_move(move: str) -> Move:
    """Renvoie un Move. Lève KeyError explicite si inconnu."""
    mid = to_id(move)
    data = _load_moves()
    try:
        m = data[mid]
    except KeyError as exc:
        raise KeyError(
            f"Move inconnu : {move!r} (ID {mid!r}). "
            "Vérifier l'orthographe ou régénérer data/moves.json."
        ) from exc
    return Move(
        id=mid,
        name=m["name"],
        type=m["type"],
        category=m["category"],
        base_power=m["basePower"],
        priority=m.get("priority", 0),
        target=m.get("target", "normal"),
        is_spread=m.get("isSpread", False),
        makes_contact=m.get("makesContact", False),
    )


def is_known(move: str) -> bool:
    return to_id(move) in _load_moves()
