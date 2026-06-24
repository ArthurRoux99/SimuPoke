"""Modèle d'adversaire — stats d'usage (§0.2, §10.3).

Importeur qui transforme des stats d'usage agrégées en table exploitable :
priors de popularité (pour pondérer B2) et set le plus probable d'une espèce
(pour combler les inconnues adverses pendant l'analyse/la recherche).

**Source des données.** Le format est volontairement simple (un JSON par
régulation, `data/usage/<reg>.json`). Il est alimenté par `usage_import` depuis
les stats d'usage **Showdown/Smogon « chaos »** (§0.2) — aucune connexion réseau
*ici* (l'import, lui, est réseau et tourne séparément). Ce module ne fait que
**lire** la table déjà importée.

Format attendu :
    {
      "_meta": {...},
      "species": {
        "<id>": {
          "usage": 0.0..1.0,                  # part d'usage (popularité)
          "items":     {"<id>": poids, ...},
          "abilities": {"<id>": poids, ...},
          "moves":     {"<id>": poids, ...},
          "natures":   {"<id>": poids, ...},
          "teammates": {"<id>": poids, ...}
        }, ...
      }
    }

`poids` ∈ [0,1] = probabilité conditionnelle (sachant l'espèce). Le joueur peut
toujours surcharger un prior dès qu'il observe une info réelle (cf. §10.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from .basestats import to_id

REPO_ROOT = Path(__file__).resolve().parents[2]
USAGE_DIR = REPO_ROOT / "data" / "usage"


def usage_path(reg_id: str = "reg_m_b") -> Path:
    return USAGE_DIR / f"{reg_id}.json"


def has_usage(reg_id: str = "reg_m_b") -> bool:
    return usage_path(reg_id).exists()


@lru_cache(maxsize=None)
def load_usage(reg_id: str = "reg_m_b") -> dict[str, dict]:
    """Charge la table d'usage d'une régulation (clé = id d'espèce). {} si absent."""
    path = usage_path(reg_id)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {to_id(k): v for k, v in raw.get("species", {}).items()}


def usage_prior(reg_id: str = "reg_m_b", *,
                table: dict[str, dict] | None = None) -> dict[str, float]:
    """Popularité normalisée par espèce (0..1, l'espèce la plus jouée = 1.0).

    Convient comme `usage_prior` de `draft.rank_lineup` (sous-score « méta »).
    `table` permet d'injecter une table déjà chargée (sinon lue par `reg_id`).
    """
    if table is None:
        table = load_usage(reg_id)
    raw = {sid: float(v.get("usage", 0.0)) for sid, v in table.items()}
    top = max(raw.values(), default=0.0)
    if top <= 0:
        return {}
    return {sid: val / top for sid, val in raw.items()}


def _argmax(weights: dict[str, float] | None) -> str | None:
    if not weights:
        return None
    return max(weights, key=weights.get)


def _top_n(weights: dict[str, float] | None, n: int) -> list[str]:
    if not weights:
        return []
    return [k for k, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:n]]


@dataclass
class LikelySet:
    species: str
    item: str | None = None
    ability: str | None = None
    nature: str | None = None
    moves: list[str] = None             # type: ignore[assignment]
    teammates: list[str] = None         # type: ignore[assignment]

    def __post_init__(self):
        if self.moves is None:
            self.moves = []
        if self.teammates is None:
            self.teammates = []


def likely_set(species: str, reg_id: str = "reg_m_b", *, n_moves: int = 4,
               table: dict[str, dict] | None = None) -> LikelySet:
    """Set le plus probable d'une espèce d'après l'usage (modèle d'adversaire).

    Sert à combler les inconnues côté adverse (objet/talent/nature/moves) tant
    que le joueur n'a rien observé. Champs à None/[] si l'espèce est absente.
    `table` permet d'injecter une table déjà chargée (sinon lue par `reg_id`).
    """
    if table is None:
        table = load_usage(reg_id)
    rec = table.get(to_id(species), {})
    return LikelySet(
        species=to_id(species),
        item=_argmax(rec.get("items")),
        ability=_argmax(rec.get("abilities")),
        nature=_argmax(rec.get("natures")),
        moves=_top_n(rec.get("moves"), n_moves),
        teammates=_top_n(rec.get("teammates"), 3),
    )
