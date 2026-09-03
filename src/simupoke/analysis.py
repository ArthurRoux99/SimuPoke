"""Analyse de types et de rôles — briques partagées par B2 (tirage) et B3 (team).

Tout est calculé à partir des données déjà branchées (base stats, table des
types, moves). Pas de dépendance externe ni réseau.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .basestats import get_base_stats, get_types, to_id
from .moves import get_move
from .moves import is_known as move_known
from .typechart import effectiveness

# Les 18 types « jouables » (on exclut Stellar, lié à la Téra-cristallisation).
STANDARD_TYPES = [
    "Bug", "Dark", "Dragon", "Electric", "Fairy", "Fighting", "Fire", "Flying",
    "Ghost", "Grass", "Ground", "Ice", "Normal", "Poison", "Psychic", "Rock",
    "Steel", "Water",
]

# Talents accordant une immunité à un type d'attaque (partagé avec le calc).
ABILITY_TYPE_IMMUNITY: dict[str, str] = {
    "levitate": "Ground", "eartheater": "Ground", "flashfire": "Fire",
    "voltabsorb": "Electric", "lightningrod": "Electric", "motordrive": "Electric",
    "waterabsorb": "Water", "stormdrain": "Water", "dryskin": "Water",
    "sapsipper": "Grass",
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Profil défensif
# ---------------------------------------------------------------------------

@dataclass
class DefensiveProfile:
    types: list[str]
    weaknesses: dict[str, float] = field(default_factory=dict)   # mult > 1
    resistances: dict[str, float] = field(default_factory=dict)  # 0 < mult < 1
    immunities: list[str] = field(default_factory=list)          # mult == 0

    @property
    def n_weak(self) -> int:
        return len(self.weaknesses)

    @property
    def n_resist(self) -> int:
        return len(self.resistances) + len(self.immunities)

    def takes(self, attacking_type: str) -> float:
        """Multiplicateur subi face à un type d'attaque (talents inclus)."""
        if attacking_type in self.immunities:
            return 0.0
        if attacking_type in self.weaknesses:
            return self.weaknesses[attacking_type]
        if attacking_type in self.resistances:
            return self.resistances[attacking_type]
        return 1.0


def defensive_profile(species_or_types: str | list[str],
                      ability: str | None = None) -> DefensiveProfile:
    """Profil défensif d'une espèce (ID) ou d'une liste de types.

    Si `ability` accorde une immunité de type (Lévitation, Torche…), le type
    concerné est traité comme immunité quelle que soit la composition de types.
    """
    types = (get_types(species_or_types) if isinstance(species_or_types, str)
             else list(species_or_types))
    prof = DefensiveProfile(types=types)
    immune_type = ABILITY_TYPE_IMMUNITY.get(to_id(ability)) if ability else None
    for atk in STANDARD_TYPES:
        if atk == immune_type:
            prof.immunities.append(atk)
            continue
        mult = effectiveness(atk, types)
        if mult > 1:
            prof.weaknesses[atk] = mult
        elif mult == 0:
            prof.immunities.append(atk)
        elif mult < 1:
            prof.resistances[atk] = mult
    return prof


# ---------------------------------------------------------------------------
# Couverture offensive
# ---------------------------------------------------------------------------

def offensive_types(species: str, moves: list[str]) -> list[str]:
    """Types des attaques offensives ; à défaut, les types STAB de l'espèce."""
    types: list[str] = []
    for mid in moves:
        if not move_known(mid):
            continue
        mv = get_move(mid)
        if not mv.is_status and mv.base_power > 0 and mv.type not in types:
            types.append(mv.type)
    if not types:                       # build sans moves connus -> proxy STAB
        types = list(get_types(species))
    return types


def coverage_count(attacking_types: list[str]) -> int:
    """Nb de types (parmi les 18 mono-types) touchés super efficacement."""
    hit = 0
    for d in STANDARD_TYPES:
        if any(effectiveness(a, [d]) > 1 for a in attacking_types):
            hit += 1
    return hit


# ---------------------------------------------------------------------------
# Inférence de rôle (heuristique sur base stats + moves)
# ---------------------------------------------------------------------------

ROLE_FR = {
    "sweeper": "Sweeper", "wall": "Mur", "pivot": "Pivot", "support": "Support",
}


@dataclass
class RoleAssessment:
    role: str
    score: float
    label_fr: str


def _status_ratio(moves: list[str]) -> float:
    known = [get_move(m) for m in moves if move_known(m)]
    if not known:
        return 0.0
    status = sum(1 for m in known if m.is_status)
    return status / len(known)


def infer_role(species: str, moves: list[str] | None = None) -> RoleAssessment:
    """Déduit le rôle dominant d'un Pokémon à partir de ses base stats/moves."""
    bs = get_base_stats(species)
    moves = moves or []

    n_off = _clamp((max(bs["atk"], bs["spa"]) - 60) / 70)
    n_spe = _clamp((bs["spe"] - 50) / 70)
    n_hp = _clamp((bs["hp"] - 50) / 60)
    n_def = _clamp(((bs["def"] + bs["spd"]) / 2 - 60) / 70)
    n_sup = _status_ratio(moves)

    scores = {
        "sweeper": n_off * n_spe,
        "wall": n_hp * n_def * (1 - n_spe),
        "pivot": n_hp * n_def * n_off,
        "support": n_sup * (0.5 + 0.5 * n_def),
    }
    role = max(scores, key=scores.get)
    return RoleAssessment(role=role, score=scores[role], label_fr=ROLE_FR[role])


def base_stat_total(species: str) -> int:
    return sum(get_base_stats(species).values())
