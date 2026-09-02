"""B3 — Constructeur d'équipe et assistant team preview (§11.2, §11.4).

Deux volets, tous deux construits sur `analysis.py` (aucune dépendance
externe) :

  - Analyse d'équipe (§11.4) : trous défensifs (faiblesses partagées),
    couverture offensive, distribution de rôles, vérification des clauses
    (Species / Item).
  - Assistant team preview (§11.2) : à partir de mes 6 et des 6 adverses
    visibles, choisir les 4 (doubles) / 3 (singles) à amener et l'ordre
    d'envoi, selon les matchups de types et la vitesse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .model import OwnedPokemon, PokemonState
from .basestats import is_known, get_base_stats, get_species
from .typechart import effectiveness
from .moves import get_move, is_known as move_known
from .damage import calculate
from .analysis import (
    STANDARD_TYPES, defensive_profile, offensive_types, infer_role, ROLE_FR,
)

BRING_BY_FORMAT = {"singles": 3, "doubles": 4}


# ===========================================================================
# Volet 1 — Analyse d'équipe (§11.4)
# ===========================================================================

@dataclass
class TeamReport:
    size: int
    shared_weaknesses: dict[str, int]      # type -> nb de membres faibles (trous)
    offensive_gaps: list[str]              # types non touchés super efficacement
    roles: dict[str, int]                  # rôle -> compte
    clause_violations: list[str]
    unknown_species: list[str]

    def lines(self) -> list[str]:
        out: list[str] = []
        if self.clause_violations:
            out.append("Clauses :")
            out += [f"  ✗ {v}" for v in self.clause_violations]
        else:
            out.append("Clauses : OK (Species + Item)")
        if self.shared_weaknesses:
            holes = ", ".join(f"{t} ({n})" for t, n in
                              sorted(self.shared_weaknesses.items(),
                                     key=lambda kv: -kv[1]))
            out.append(f"Trous défensifs (≥ moitié faible) : {holes}")
        else:
            out.append("Trous défensifs : aucun majeur")
        if self.offensive_gaps:
            out.append("Couverture offensive manquante (non touché ×2) : "
                       + ", ".join(self.offensive_gaps))
        else:
            out.append("Couverture offensive : complète")
        roles = ", ".join(f"{ROLE_FR.get(r, r)}×{n}" for r, n in self.roles.items())
        out.append(f"Rôles : {roles}")
        return out


def team_defensive_weaknesses(team: list[OwnedPokemon]) -> dict[str, int]:
    """Pour chaque type, nb de membres qui y sont faibles."""
    counts: dict[str, int] = {}
    for atk in STANDARD_TYPES:
        n = sum(1 for m in team
                if is_known(m.species)
                and defensive_profile(m.species, m.ability).takes(atk) > 1)
        if n:
            counts[atk] = n
    return counts


def team_shared_weaknesses(team: list[OwnedPokemon]) -> dict[str, int]:
    """Faiblesses partagées par au moins la moitié de l'équipe (trous)."""
    known = [m for m in team if is_known(m.species)]
    if not known:
        return {}
    threshold = math.ceil(len(known) / 2)
    return {t: n for t, n in team_defensive_weaknesses(known).items()
            if n >= threshold}


def team_offensive_gaps(team: list[OwnedPokemon]) -> list[str]:
    """Types (mono) que l'équipe ne touche jamais super efficacement."""
    atk_types: set[str] = set()
    for m in team:
        if is_known(m.species):
            atk_types.update(offensive_types(m.species, m.moves))
    gaps = []
    for d in STANDARD_TYPES:
        if not any(effectiveness(a, [d]) > 1 for a in atk_types):
            gaps.append(d)
    return gaps


def role_distribution(team: list[OwnedPokemon]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for m in team:
        if is_known(m.species):
            r = infer_role(m.species, m.moves).role
            dist[r] = dist.get(r, 0) + 1
    return dist


def check_clauses(team: list[OwnedPokemon]) -> list[str]:
    """Vérifie Species Clause (n° Dex unique) et Item Clause (objet unique)."""
    violations: list[str] = []
    seen_num: dict[int, str] = {}
    for m in team:
        if not is_known(m.species):
            continue
        num = get_species(m.species).get("num")
        if num in seen_num and seen_num[num] != m.species:
            violations.append(f"Species Clause : {seen_num[num]} et {m.species} "
                              f"(même n° Dex {num})")
        elif num in seen_num:
            violations.append(f"Species Clause : {m.species} en double")
        else:
            seen_num[num] = m.species
    seen_item: set[str] = set()
    for m in team:
        if m.item:
            if m.item in seen_item:
                violations.append(f"Item Clause : {m.item} tenu plusieurs fois")
            seen_item.add(m.item)
    return violations


def analyze_team(team: list[OwnedPokemon]) -> TeamReport:
    unknown = [m.species for m in team if not is_known(m.species)]
    return TeamReport(
        size=len(team),
        shared_weaknesses=team_shared_weaknesses(team),
        offensive_gaps=team_offensive_gaps(team),
        roles=role_distribution(team),
        clause_violations=check_clauses(team),
        unknown_species=unknown,
    )


# ===========================================================================
# Volet 2 — Assistant team preview (§11.2)
# ===========================================================================

def _offensive_pressure(attacker: OwnedPokemon, defender: OwnedPokemon) -> float:
    """log2 de la meilleure efficacité de type de l'attaquant sur le défenseur.

    +1 = super efficace (×2), -1 = résisté (×0.5), -3 = ne touche pas (×0).
    """
    atk_types = offensive_types(attacker.species, attacker.moves)
    def_types = get_species(defender.species).get("types") or []
    best = max((effectiveness(a, def_types) for a in atk_types), default=1.0)
    if best <= 0:
        return -3.0
    return math.log2(best)


def _base_speed(mon: OwnedPokemon) -> int:
    return get_base_stats(mon.species)["spe"] if is_known(mon.species) else 0


def matchup_score(mine: OwnedPokemon, opp: OwnedPokemon) -> float:
    """Score de matchup par TYPES (positif = favorable à `mine`)."""
    off = _offensive_pressure(mine, opp)
    incoming = _offensive_pressure(opp, mine)
    score = off - incoming
    # Bonus de vitesse (départage léger).
    sm, so = _base_speed(mine), _base_speed(opp)
    if sm > so:
        score += 0.5
    elif sm < so:
        score -= 0.5
    return score


# --- Matchup affiné par le calculateur de dégâts ---------------------------

def _resolve_moves(mon: OwnedPokemon) -> list[str]:
    """Capacités connues du Pokémon, sinon son set le plus probable (usage §10.3)."""
    if mon.moves:
        return mon.moves
    if is_known(mon.species):
        from .usage import likely_set
        ls = likely_set(mon.species)
        if ls.moves:
            return ls.moves
    return []


def _to_state(mon: OwnedPokemon, moves: list[str]) -> PokemonState:
    return PokemonState(species=mon.species, nature=mon.nature or "serious",
                        stat_points=mon.stat_points or {}, item=mon.item,
                        ability=mon.ability, moves=moves)


def _best_damage_pct(attacker: OwnedPokemon, defender: OwnedPokemon) -> float | None:
    """Meilleur % de PV moyen que `attacker` inflige à `defender` en un coup.

    None si aucune capacité offensive n'est estimable (ni connue, ni via usage).
    """
    amoves = _resolve_moves(attacker)
    if not amoves:
        return None
    atk = _to_state(attacker, amoves)
    dfd = _to_state(defender, _resolve_moves(defender))
    best = 0.0
    seen = False
    for mv in amoves:
        if not move_known(mv) or get_move(mv).is_status:
            continue
        try:
            r = calculate(atk, dfd, mv)
        except (ValueError, KeyError):
            continue
        seen = True
        best = max(best, (r.min_pct + r.max_pct) / 2)
    return best if seen else None


def damage_matchup_score(mine: OwnedPokemon, opp: OwnedPokemon) -> float | None:
    """Score de matchup par DÉGÂTS : qui met KO le plus vite (+ vitesse).

    Compare les « coups pour KO » (100 / meilleur % moyen) des deux côtés. None
    si aucun des deux camps n'a de capacité estimable (on retombe sur les types).
    """
    my = _best_damage_pct(mine, opp)
    their = _best_damage_pct(opp, mine)
    if my is None and their is None:
        return None
    my = my or 0.0
    their = their or 0.0
    my_ttk = math.ceil(100 / my) if my > 0 else 99
    opp_ttk = math.ceil(100 / their) if their > 0 else 99
    # Positif = je tue en moins de coups que l'adversaire. Borné pour rester
    # comparable à l'échelle du score par types.
    score = float(max(-4, min(4, opp_ttk - my_ttk)))
    sm, so = _base_speed(mine), _base_speed(opp)
    if sm > so:
        score += 0.5
    elif sm < so:
        score -= 0.5
    return score


def _pair_score(mine: OwnedPokemon, opp: OwnedPokemon, use_damage: bool) -> float:
    """Matchup d'une paire : par dégâts si possible, sinon repli sur les types."""
    if use_damage:
        dmg = damage_matchup_score(mine, opp)
        if dmg is not None:
            return dmg
    return matchup_score(mine, opp)


@dataclass
class PreviewPick:
    species: str
    value: float                          # matchup moyen vs équipe adverse
    beats: list[str] = field(default_factory=list)
    threatened_by: list[str] = field(default_factory=list)


@dataclass
class PreviewResult:
    fmt: str
    bring: int
    picks: list[PreviewPick]              # sélection ordonnée (lead en premier)
    bench: list[PreviewPick]
    by_damage: bool = False               # matchups affinés par le calc ?

    def lines(self) -> list[str]:
        method = "dégâts" if self.by_damage else "types"
        out = [f"Format {self.fmt} — amener {self.bring} (matchups par {method}) :"]
        for i, p in enumerate(self.picks):
            tag = "  (lead)" if i == 0 else ""
            out.append(f"  {i+1}. {p.species}{tag}  matchup {p.value:+.2f}")
            if p.beats:
                out.append(f"       domine : {', '.join(p.beats)}")
            if p.threatened_by:
                out.append(f"       menacé par : {', '.join(p.threatened_by)}")
        if self.bench:
            out.append("  Banc : " + ", ".join(p.species for p in self.bench))
        return out


def select_team_preview(my_team: list[OwnedPokemon], opp_team: list[OwnedPokemon],
                        fmt: str = "singles", *,
                        use_damage: bool = True) -> PreviewResult:
    """Choisit les Pokémon à amener et l'ordre d'envoi selon les matchups.

    `use_damage` : affine les matchups avec le calculateur de dégâts (moves
    connus, sinon set le plus probable §10.3) ; repli automatique sur les types
    quand aucune capacité n'est estimable.
    """
    bring = BRING_BY_FORMAT.get(fmt, 3)
    opp_known = [o for o in opp_team if is_known(o.species)]

    picks: list[PreviewPick] = []
    for mine in my_team:
        if not is_known(mine.species):
            picks.append(PreviewPick(species=mine.species, value=-99.0))
            continue
        scores = [(o, _pair_score(mine, o, use_damage)) for o in opp_known]
        value = sum(s for _, s in scores) / len(scores) if scores else 0.0
        beats = [o.species for o, s in scores if s > 0.5]
        threatened = [o.species for o, s in scores if s < -0.5]
        picks.append(PreviewPick(species=mine.species, value=value,
                                 beats=beats, threatened_by=threatened))

    picks.sort(key=lambda p: p.value, reverse=True)
    return PreviewResult(fmt=fmt, bring=bring,
                         picks=picks[:bring], bench=picks[bring:],
                         by_damage=use_damage)
