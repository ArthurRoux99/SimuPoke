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
from .basestats import get_base_stats, get_species, get_types, is_known, to_id
from .model import (
    OwnedPokemon, PokemonState, SideState, FieldState, BattleState,
)
from .loaders import load_my_roster, load_regulation, load_lineup, load_team
from .moves import Move, get_move
from .typechart import effectiveness
from .damage import calculate, battle_stats, DamageResult
from .analysis import (
    defensive_profile, offensive_types, coverage_count, infer_role,
    base_stat_total, DefensiveProfile, RoleAssessment,
)
from .draft import rank_lineup, evaluate_candidate, DraftEvaluation, team_threats
from .team import (
    analyze_team, select_team_preview, TeamReport, PreviewResult,
    matchup_score, check_clauses,
)
from .combat import analyze_turn, TurnAnalysis, MoveEval, effective_speed, moves_first
from .bench import (
    speed_tiers, compute_speed, min_sp_to_outspeed, min_sp_to_survive,
    min_sp_to_ko, SpeedEntry, OutspeedResult, SurviveResult, KoResult,
)
from .optimize import (
    optimize_spread, Outspeed, Survive, Ko, SpreadResult,
)
from .usage import load_usage, usage_prior, likely_set, has_usage, LikelySet
from . import i18n

__all__ = [
    "__version__",
    "LEVEL", "IV", "SP_CAP_PER_STAT", "SP_TOTAL_BUDGET", "STAT_KEYS", "NATURES",
    "Build", "compute_stat", "compute_all_stats", "nature_multipliers", "validate_sp",
    "get_base_stats", "get_species", "get_types", "is_known", "to_id",
    "OwnedPokemon", "PokemonState", "SideState", "FieldState", "BattleState",
    "load_my_roster", "load_regulation", "load_lineup", "load_team",
    "Move", "get_move", "effectiveness",
    "calculate", "battle_stats", "DamageResult",
    "defensive_profile", "offensive_types", "coverage_count", "infer_role",
    "base_stat_total", "DefensiveProfile", "RoleAssessment",
    "rank_lineup", "evaluate_candidate", "DraftEvaluation", "team_threats",
    "analyze_team", "select_team_preview", "TeamReport", "PreviewResult",
    "matchup_score", "check_clauses",
    "analyze_turn", "TurnAnalysis", "MoveEval", "effective_speed", "moves_first",
    "speed_tiers", "compute_speed", "min_sp_to_outspeed", "min_sp_to_survive",
    "min_sp_to_ko", "SpeedEntry", "OutspeedResult", "SurviveResult", "KoResult",
    "optimize_spread", "Outspeed", "Survive", "Ko", "SpreadResult",
    "load_usage", "usage_prior", "likely_set", "has_usage", "LikelySet",
    "i18n",
]
