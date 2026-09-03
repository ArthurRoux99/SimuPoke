"""SimuPoke — outil hors-ligne d'aide à la décision pour Pokémon Champions.

Phase 0 : socle de données et calcul de stats (modèle figé).
Voir docs/conception_socle.md pour le document de conception complet.
"""

from __future__ import annotations

__version__ = "0.1.0"

from . import i18n
from .analysis import (
    DefensiveProfile,
    RoleAssessment,
    base_stat_total,
    coverage_count,
    defensive_profile,
    infer_role,
    offensive_types,
)
from .basestats import get_base_stats, get_species, get_types, is_known, to_id
from .bench import (
    KoResult,
    OutspeedResult,
    SpeedEntry,
    SurviveResult,
    compute_speed,
    min_sp_to_ko,
    min_sp_to_outspeed,
    min_sp_to_survive,
    speed_tiers,
)
from .combat import (
    MoveEval,
    SwitchEval,
    TurnAnalysis,
    analyze_turn,
    effective_speed,
    evaluate_switches,
    moves_first,
)
from .damage import DamageResult, battle_stats, calculate
from .draft import DraftEvaluation, evaluate_candidate, rank_lineup, team_threats
from .loaders import load_lineup, load_my_roster, load_regulation, load_team
from .model import (
    BattleState,
    FieldState,
    OwnedPokemon,
    PokemonState,
    SideState,
)
from .moves import Move, get_move
from .optimize import (
    Ko,
    Outspeed,
    SpreadResult,
    Survive,
    optimize_spread,
)
from .search import (
    ActionValue,
    SearchResult,
    evaluate_side,
    evaluate_state,
    opponent_moves,
    rank_actions,
    rank_actions_sampled,
)
from .showdown import format_team as format_showdown
from .showdown import parse_team as parse_showdown
from .sim import (
    ActionResult,
    Mon,
    Side,
    TurnResult,
    action_order,
    rollout,
    simulate_turn,
    simulate_turn_actions,
)
from .stats import (
    IV,
    LEVEL,
    NATURES,
    SP_CAP_PER_STAT,
    SP_TOTAL_BUDGET,
    STAT_KEYS,
    Build,
    compute_all_stats,
    compute_stat,
    nature_multipliers,
    validate_sp,
)
from .team import (
    PreviewResult,
    TeamReport,
    analyze_team,
    check_clauses,
    damage_matchup_score,
    matchup_score,
    select_team_preview,
)
from .typechart import effectiveness
from .usage import LikelySet, has_usage, likely_set, load_usage, sample_set, usage_prior

__all__ = [
    "IV",
    "LEVEL",
    "NATURES",
    "SP_CAP_PER_STAT",
    "SP_TOTAL_BUDGET",
    "STAT_KEYS",
    "ActionResult",
    "ActionValue",
    "BattleState",
    "Build",
    "DamageResult",
    "DefensiveProfile",
    "DraftEvaluation",
    "FieldState",
    "Ko",
    "KoResult",
    "LikelySet",
    "Mon",
    "Move",
    "MoveEval",
    "Outspeed",
    "OutspeedResult",
    "OwnedPokemon",
    "PokemonState",
    "PreviewResult",
    "RoleAssessment",
    "SearchResult",
    "Side",
    "SideState",
    "SpeedEntry",
    "SpreadResult",
    "Survive",
    "SurviveResult",
    "SwitchEval",
    "TeamReport",
    "TurnAnalysis",
    "TurnResult",
    "__version__",
    "action_order",
    "analyze_team",
    "analyze_turn",
    "base_stat_total",
    "battle_stats",
    "calculate",
    "check_clauses",
    "compute_all_stats",
    "compute_speed",
    "compute_stat",
    "coverage_count",
    "damage_matchup_score",
    "defensive_profile",
    "effective_speed",
    "effectiveness",
    "evaluate_candidate",
    "evaluate_side",
    "evaluate_state",
    "evaluate_switches",
    "format_showdown",
    "get_base_stats",
    "get_move",
    "get_species",
    "get_types",
    "has_usage",
    "i18n",
    "infer_role",
    "is_known",
    "likely_set",
    "load_lineup",
    "load_my_roster",
    "load_regulation",
    "load_team",
    "load_usage",
    "matchup_score",
    "min_sp_to_ko",
    "min_sp_to_outspeed",
    "min_sp_to_survive",
    "moves_first",
    "nature_multipliers",
    "offensive_types",
    "opponent_moves",
    "optimize_spread",
    "parse_showdown",
    "rank_actions",
    "rank_actions_sampled",
    "rank_lineup",
    "rollout",
    "sample_set",
    "select_team_preview",
    "simulate_turn",
    "simulate_turn_actions",
    "speed_tiers",
    "team_threats",
    "to_id",
    "usage_prior",
    "validate_sp",
]
