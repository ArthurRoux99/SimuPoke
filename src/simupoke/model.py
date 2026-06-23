"""Modèles de données du projet (Phase 0).

Regroupe :
  - OwnedPokemon : un Pokémon de « mon Box » (§0.3 du document socle).
  - L'état de combat « Doubles-ready » (§9) : PokemonState, SideState,
    FieldState, BattleState.

Principe directeur (§0.4) : on démarre en Singles, mais le schéma n'interdit
jamais le Doubles. `SideState.active` est donc une LISTE (1 en singles, 2 en
doubles), et les actions porteront des champs `target` / `spread` plus tard.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .stats import STAT_KEYS, compute_all_stats, validate_sp
from .basestats import get_base_stats, is_known


# ---------------------------------------------------------------------------
# Mon Box — Pokémon possédés (§0.3)
# ---------------------------------------------------------------------------

@dataclass
class OwnedPokemon:
    """Un Pokémon possédé, saisi manuellement (cf. §3 : aucune lecture du jeu)."""
    species: str
    nature: str
    stat_points: dict[str, int]              # SP Champions (0..32 par stat)
    item: str | None = None
    ability: str | None = None
    moves: list[str] = field(default_factory=list)
    status_ownership: str = "permanent"      # "trial" | "permanent" | "home_visitor"
    trial_expires_in_days: int | None = None
    source: str = "ranch"                    # "ranch" | "home" | "event"
    is_shiny: bool = False
    has_title: bool = False
    display_fr: str | None = None            # nom FR optionnel pour l'affichage

    def final_stats(self) -> dict[str, int]:
        """Stats finales si l'espèce est connue, sinon lève KeyError explicite."""
        return compute_all_stats(get_base_stats(self.species), self.stat_points,
                                 self.nature)

    def validate(self) -> list[str]:
        """Liste des problèmes du build (vide = OK). Tolère une espèce inconnue."""
        problems = validate_sp(self.stat_points)
        if self.status_ownership == "trial" and self.trial_expires_in_days is None:
            problems.append("status 'trial' sans trial_expires_in_days")
        if not is_known(self.species):
            problems.append(f"espèce inconnue dans la base : {self.species!r}")
        return problems


# ---------------------------------------------------------------------------
# État d'un tour de combat (§9) — esquisse Doubles-ready
# ---------------------------------------------------------------------------

@dataclass
class PokemonState:
    species: str
    ability: str | None = None
    item: str | None = None
    mega: bool = False                    # méga déjà déclenchée ?
    nature: str = "serious"
    stat_points: dict[str, int] = field(default_factory=lambda: {k: 0 for k in STAT_KEYS})
    moves: list[str] = field(default_factory=list)
    current_hp_pct: float = 1.0           # 0..1 (PV restants)
    status: str | None = None             # brn/par/slp/psn/tox/frz
    boosts: dict[str, int] = field(default_factory=dict)  # {"atk":+1,"spe":-1,...}
    tera_type: str | None = None          # réservé futur
    revealed: bool = True                 # info connue de l'adversaire ?


@dataclass
class SideState:
    # LISTE volontairement : 1 actif en singles, 2 en doubles (cf. §0.4).
    active: list[PokemonState] = field(default_factory=list)
    bench: list[PokemonState] = field(default_factory=list)
    hazards: dict[str, int] = field(default_factory=dict)        # stealth rock, spikes...
    side_conditions: dict[str, int] = field(default_factory=dict)  # tailwind, reflect...


@dataclass
class FieldState:
    weather: str | None = None
    terrain: str | None = None
    trick_room: bool = False
    turn: int = 1


@dataclass
class BattleState:
    format: str = "singles"               # "singles" | "doubles"
    me: SideState = field(default_factory=SideState)
    opp: SideState = field(default_factory=SideState)
    field: FieldState = field(default_factory=FieldState)
