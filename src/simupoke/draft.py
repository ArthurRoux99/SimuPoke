"""B2 — Aide au tirage (Roster Ranch) (§11.3).

Entrée : les 10 Pokémon proposés du jour (build préréglé), + éventuellement
mon Box pour la synergie. Sortie : classement justifié + reco essai/permanent.

Le scoring combine des sous-scores normalisés (0..1) puis pondérés :
  - stats        : puissance brute (BST normalisé) ;
  - defense      : qualité du typage défensif (résistances vs faiblesses) ;
  - coverage     : largeur de la couverture offensive ;
  - role         : netteté du rôle (sweeper/mur/pivot/support) ;
  - synergy      : complémentarité avec mon Box (couvre des menaces, n'empile
                   pas les faiblesses) ;
  - usage        : présence dans le méta (prior d'usage, §0.2) — neutre (0.5)
                   tant qu'aucune source d'usage n'est branchée ;
  - rarity       : shiny / titre.

Les priors d'usage se brancheront via `usage_prior` (dict espèce -> 0..1) une
fois l'importeur limitless/pokedata écrit (§0.2). Rien d'autre ne change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import OwnedPokemon
from .basestats import is_known, to_id
from .analysis import (
    STANDARD_TYPES, defensive_profile, offensive_types, coverage_count,
    infer_role, base_stat_total,
)

# Pondérations par défaut (somme = 1.0). Ajustables via rank_lineup(weights=...).
DEFAULT_WEIGHTS: dict[str, float] = {
    "stats": 0.22,
    "defense": 0.15,
    "coverage": 0.15,
    "role": 0.10,
    "synergy": 0.20,
    "usage": 0.13,
    "rarity": 0.05,
}

# Seuils de recommandation sur le score total (0..1).
INVEST_THRESHOLD = 0.62
TRY_THRESHOLD = 0.45


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Synergie avec mon Box
# ---------------------------------------------------------------------------

def team_threats(roster: list[OwnedPokemon]) -> set[str]:
    """Types de menace pour l'équipe : ceux où >= 1/3 des membres sont faibles."""
    if not roster:
        return set()
    threshold = max(1, (len(roster) + 2) // 3)
    threats: set[str] = set()
    for atk in STANDARD_TYPES:
        weak = sum(
            1 for m in roster
            if is_known(m.species) and defensive_profile(m.species).takes(atk) > 1
        )
        if weak >= threshold:
            threats.add(atk)
    return threats


def _synergy_score(species: str, threats: set[str],
                   roster: list[OwnedPokemon]) -> tuple[float, list[str]]:
    if not roster:
        return 0.5, []
    prof = defensive_profile(species)
    covered = [t for t in threats
               if prof.takes(t) < 1]               # résiste/immunise une menace
    stacked = [t for t in prof.weaknesses
               if t in threats]                    # empile une faiblesse commune
    score = _clamp(0.5 + 0.12 * (len(covered) - len(stacked)))
    reasons = []
    if covered:
        reasons.append(f"couvre une menace d'équipe ({', '.join(covered[:3])})")
    if stacked:
        reasons.append(f"empile une faiblesse {', '.join(stacked[:2])}")
    return score, reasons


# ---------------------------------------------------------------------------
# Évaluation d'un candidat
# ---------------------------------------------------------------------------

@dataclass
class DraftEvaluation:
    species: str
    total: float                                   # 0..1
    subscores: dict[str, float]
    role: str
    role_fr: str
    recommendation: str
    reasons: list[str] = field(default_factory=list)
    is_shiny: bool = False
    has_title: bool = False

    @property
    def score100(self) -> int:
        return round(self.total * 100)


def evaluate_candidate(cand: OwnedPokemon, *, roster: list[OwnedPokemon] | None = None,
                       threats: set[str] | None = None,
                       usage_prior: dict[str, float] | None = None,
                       weights: dict[str, float] | None = None) -> DraftEvaluation:
    weights = weights or DEFAULT_WEIGHTS
    roster = roster or []
    if threats is None:
        threats = team_threats(roster)

    species = cand.species
    if not is_known(species):
        return DraftEvaluation(
            species=species, total=0.0, subscores={}, role="?", role_fr="?",
            recommendation="Espèce inconnue (données manquantes)",
            reasons=[f"espèce {species!r} absente du Pokédex"],
            is_shiny=cand.is_shiny, has_title=cand.has_title,
        )

    bst = base_stat_total(species)
    prof = defensive_profile(species)
    off_types = offensive_types(species, cand.moves)
    cov = coverage_count(off_types)
    role = infer_role(species, cand.moves)

    sub: dict[str, float] = {}
    sub["stats"] = _clamp((bst - 300) / 400)
    sub["defense"] = _clamp(0.5 + 0.08 * (prof.n_resist - prof.n_weak))
    sub["coverage"] = _clamp(cov / 12)
    sub["role"] = _clamp(role.score)
    syn_score, syn_reasons = _synergy_score(species, threats, roster)
    sub["synergy"] = syn_score
    if usage_prior and to_id(species) in {to_id(k): k for k in usage_prior}:
        # tolère des clés en nom d'affichage ou ID
        key = next(k for k in usage_prior if to_id(k) == to_id(species))
        sub["usage"] = _clamp(usage_prior[key])
    else:
        sub["usage"] = 0.5                          # neutre tant qu'aucun usage
    sub["rarity"] = (0.7 if cand.is_shiny else 0.0) + (0.3 if cand.has_title else 0.0)

    total = sum(weights.get(k, 0.0) * v for k, v in sub.items())

    # Justification : meilleurs facteurs au-dessus du neutre.
    reasons: list[str] = []
    reasons.append(f"BST {bst}")
    reasons.append(f"typage {prof.n_resist} rés. / {prof.n_weak} faibl.")
    if sub["coverage"] >= 0.66:
        reasons.append(f"couverture large ({cov}/18 types)")
    reasons.extend(syn_reasons)
    if cand.is_shiny:
        reasons.append("✨ shiny")
    if cand.has_title:
        reasons.append("titre")

    recommendation = _recommend(total, cand)

    return DraftEvaluation(
        species=species, total=total, subscores=sub,
        role=role.role, role_fr=role.label_fr,
        recommendation=recommendation, reasons=reasons,
        is_shiny=cand.is_shiny, has_title=cand.has_title,
    )


def _recommend(total: float, cand: OwnedPokemon) -> str:
    if total >= INVEST_THRESHOLD:
        rec = "Investir (permanent, 2 500 VP)"
    elif total >= TRY_THRESHOLD:
        rec = "Tester d'abord (essai 7 j)"
    else:
        rec = "Passer"
    if cand.is_shiny and total < INVEST_THRESHOLD:
        rec += " — mais valeur collection (shiny)"
    return rec


# ---------------------------------------------------------------------------
# Classement du lineup
# ---------------------------------------------------------------------------

def rank_lineup(lineup: list[OwnedPokemon], *,
                roster: list[OwnedPokemon] | None = None,
                usage_prior: dict[str, float] | None = None,
                weights: dict[str, float] | None = None) -> list[DraftEvaluation]:
    """Classe les candidats du tirage, meilleur en premier."""
    roster = roster or []
    threats = team_threats(roster)
    evals = [
        evaluate_candidate(c, roster=roster, threats=threats,
                           usage_prior=usage_prior, weights=weights)
        for c in lineup
    ]
    evals.sort(key=lambda e: e.total, reverse=True)
    return evals
