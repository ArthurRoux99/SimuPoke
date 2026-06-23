"""Fournisseur de stats de base (base stats).

Phase 0 : table en dur (stub). À remplacer en phase suivante par une source
de données réelle (`@pkmn/dex` côté JS, ou PokéAPI / un dump versionné),
conformément à §7 et §12 du document socle.

Les identifiants d'espèce sont en anglais minuscule, style Showdown.
"""

from __future__ import annotations

# species -> {hp, atk, def, spa, spd, spe}
BASE_STATS: dict[str, dict[str, int]] = {
    "tyranitar":  {"hp": 100, "atk": 134, "def": 110, "spa": 95, "spd": 100, "spe": 61},
    "garchomp":   {"hp": 108, "atk": 130, "def": 95,  "spa": 80, "spd": 85,  "spe": 102},
    "incineroar": {"hp": 95,  "atk": 115, "def": 90,  "spa": 80, "spd": 90,  "spe": 60},
}


def get_base_stats(species: str) -> dict[str, int]:
    """Renvoie les base stats d'une espèce (clé Showdown, minuscule).

    Lève KeyError avec un message explicite si l'espèce est inconnue, plutôt
    qu'un KeyError nu — pour faciliter le diagnostic tant que la table est un stub.
    """
    key = species.lower()
    try:
        return BASE_STATS[key]
    except KeyError as exc:
        raise KeyError(
            f"Base stats inconnues pour {species!r}. "
            "Stub Phase 0 — ajouter l'espèce dans basestats.BASE_STATS "
            "ou brancher une source de données (@pkmn/dex / PokéAPI)."
        ) from exc


def is_known(species: str) -> bool:
    return species.lower() in BASE_STATS
