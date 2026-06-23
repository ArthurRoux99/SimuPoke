"""SimuPoke — outil hors-ligne d'aide à la décision pour Pokémon Champions.

Phase 0 : socle de données et calcul de stats (modèle figé).
Voir docs/conception_socle.md pour le document de conception complet.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .stats import (
    LEVEL, IV, SP_CAP_PER_STAT, SP_TOTAL_BUDGET, STAT_KEYS, NATURES,
    Build, compute_stat, compute_all_stats, nature_multipliers, validate_sp,
)
from .basestats import get_base_stats, is_known
from .model import (
    OwnedPokemon, PokemonState, SideState, FieldState, BattleState,
)
from .loaders import load_my_roster, load_regulation
from . import i18n

__all__ = [
    "__version__",
    "LEVEL", "IV", "SP_CAP_PER_STAT", "SP_TOTAL_BUDGET", "STAT_KEYS", "NATURES",
    "Build", "compute_stat", "compute_all_stats", "nature_multipliers", "validate_sp",
    "get_base_stats", "is_known",
    "OwnedPokemon", "PokemonState", "SideState", "FieldState", "BattleState",
    "load_my_roster", "load_regulation",
    "i18n",
]
