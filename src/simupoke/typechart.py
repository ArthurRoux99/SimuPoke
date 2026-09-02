"""Efficacité des types.

Source : `data/typechart.json`, généré depuis `@pkmn/dex`
(`scripts/gen_moves.mjs`). `chart[type_attaquant][type_defenseur]` donne le
multiplicateur élémentaire (0, 0.5, 1, 2).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .paths import DATA_DIR

TYPECHART_PATH = DATA_DIR / "typechart.json"


@lru_cache(maxsize=1)
def _load_chart() -> dict[str, dict[str, float]]:
    with TYPECHART_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)["chart"]


def effectiveness(move_type: str, defender_types: list[str]) -> float:
    """Multiplicateur d'efficacité d'un type d'attaque contre un ou deux types.

    Renvoie le produit des multiplicateurs (ex. 4× double faiblesse, 0×
    immunité). Un type d'attaque inconnu ou neutre (None) renvoie 1.0.
    """
    if not move_type:
        return 1.0
    chart = _load_chart()
    row = chart.get(move_type)
    if row is None:
        return 1.0
    mult = 1.0
    for d in defender_types:
        mult *= row.get(d, 1.0)
    return mult
