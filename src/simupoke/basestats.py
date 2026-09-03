"""Fournisseur de stats de base (base stats) et de métadonnées d'espèces.

Source : `data/pokedex.json`, généré **hors-ligne** depuis `@pkmn/dex`
(§12 du document socle) par `scripts/gen_pokedex.mjs`. Le runtime du projet
reste 100 % hors-ligne : on ne lit que ce fichier versionné.

Les identifiants d'espèce sont normalisés en « ID Showdown » (minuscule,
alphanumérique) : 'tyranitar', 'mrmime', 'tyranitarmega'...

Si `data/pokedex.json` est absent (données pas encore générées), on retombe
sur un petit stub en dur afin que le package reste utilisable.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .paths import DATA_DIR

POKEDEX_PATH = DATA_DIR / "pokedex.json"

# Ordre canonique des stats (doit rester cohérent avec stats.STAT_KEYS).
_STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")

# Stub de secours si data/pokedex.json est absent (mode dégradé hors-ligne).
_FALLBACK_BASE_STATS: dict[str, dict[str, int]] = {
    "tyranitar":  {"hp": 100, "atk": 134, "def": 110, "spa": 95, "spd": 100, "spe": 61},
    "garchomp":   {"hp": 108, "atk": 130, "def": 95,  "spa": 80, "spd": 85,  "spe": 102},
    "incineroar": {"hp": 95,  "atk": 115, "def": 90,  "spa": 80, "spd": 90,  "spe": 60},
}


def to_id(species: str) -> str:
    """Normalise un nom/ID d'espèce en ID Showdown (minuscule, alphanumérique).

    Ex. 'Mr. Mime' -> 'mrmime', 'Tyranitar-Mega' -> 'tyranitarmega'.
    """
    return re.sub(r"[^a-z0-9]", "", species.lower())


@lru_cache(maxsize=1)
def _load_dex() -> dict[str, dict[str, Any]]:
    """Charge et met en cache la table d'espèces (clé = ID Showdown)."""
    if POKEDEX_PATH.exists():
        with POKEDEX_PATH.open(encoding="utf-8") as fh:
            return json.load(fh).get("species", {})
    # Mode dégradé : on fabrique des enregistrements minimaux depuis le stub.
    return {
        sid: {"baseStats": bs, "name": sid, "types": [], "num": None}
        for sid, bs in _FALLBACK_BASE_STATS.items()
    }


def get_species(species: str) -> dict[str, Any]:
    """Renvoie l'enregistrement complet d'une espèce (base stats + méta).

    Lève KeyError avec un message explicite si l'espèce est inconnue.
    """
    sid = to_id(species)
    dex = _load_dex()
    try:
        return dex[sid]
    except KeyError as exc:
        raise KeyError(
            f"Espèce inconnue : {species!r} (ID {sid!r}). "
            "Vérifier l'orthographe ou régénérer data/pokedex.json "
            "(`cd scripts && npm install && node gen_pokedex.mjs`)."
        ) from exc


def get_base_stats(species: str) -> dict[str, int]:
    """Renvoie les base stats {hp, atk, def, spa, spd, spe} d'une espèce."""
    bs = get_species(species)["baseStats"]
    # Garantit l'ordre canonique et des entiers.
    return {k: int(bs[k]) for k in _STAT_KEYS}


def get_types(species: str) -> list[str]:
    """Types de l'espèce (ex. ['Rock', 'Dark']). Liste vide si inconnu."""
    return list(get_species(species).get("types") or [])


def is_known(species: str) -> bool:
    return to_id(species) in _load_dex()
