"""Croyance sur le set adverse (§10.3) — mixture pondérée, filtrée par l'observé.

Dans l'esprit de l'état de l'art (PokaiTrainer : mixture de sets candidats mise
à jour bayésiennement par ce qui est observé), on approxime la croyance par un
**nuage de particules** : on échantillonne des sets plausibles depuis l'usage,
on **rejette** ceux incohérents avec l'information révélée (coups vus, objet/
talent connus), et on regroupe en particules pondérées par leur fréquence.

Sans données d'usage, ou dès que le set est entièrement connu, la croyance se
réduit à une particule certaine.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from .basestats import is_known, to_id
from .model import PokemonState
from .moves import is_known as move_known
from .usage import has_usage, likely_set, sample_set


@dataclass
class Particle:
    """Un monde possible : un build adverse concret et son poids de croyance."""
    build: PokemonState
    weight: float


def _key(st: PokemonState):
    return (to_id(st.item or ""), to_id(st.ability or ""),
            st.nature or "serious", frozenset(to_id(m) for m in st.moves))


def opponent_belief(opp: PokemonState, reg_id: str = "reg_m_b", *,
                    n_samples: int = 80, k: int = 6,
                    seed: int | None = 0) -> list[Particle]:
    """Renvoie jusqu'à `k` particules (builds pondérés) cohérentes avec l'observé.

    Filtrage bayésien : on conditionne l'usage sur les coups déjà vus
    (`opp.moves`), et sur l'objet / le talent s'ils sont renseignés.
    """
    observed = [m for m in (opp.moves or []) if move_known(m)]
    obs_item = to_id(opp.item) if opp.item else None
    obs_ability = to_id(opp.ability) if opp.ability else None

    # Set entièrement connu, ou pas d'usage : une particule certaine.
    if (len(observed) >= 4 or not has_usage(reg_id) or not is_known(opp.species)):
        certain = replace(opp, moves=list(opp.moves) if opp.moves else [])
        return [Particle(build=certain, weight=1.0)]

    rng = random.Random(seed)
    counts: dict = {}
    builds: dict = {}
    for _ in range(max(1, n_samples)):
        ls = sample_set(opp.species, reg_id, rng=rng)
        moves = [m for m in (ls.moves or []) if move_known(m)]
        if not moves:
            break                                   # espèce absente de l'usage
        # Conditionnement sur l'information révélée (rejet).
        if observed and not {to_id(m) for m in observed} <= {to_id(m) for m in moves}:
            continue
        if obs_item and ls.item and to_id(ls.item) != obs_item:
            continue
        if obs_ability and ls.ability and to_id(ls.ability) != obs_ability:
            continue
        nature = (opp.nature if opp.nature not in (None, "serious")
                  else (ls.nature or "serious"))
        st = replace(opp, moves=moves, item=(opp.item or ls.item),
                     ability=(opp.ability or ls.ability), nature=nature)
        kk = _key(st)
        counts[kk] = counts.get(kk, 0) + 1
        builds[kk] = st

    if not counts:
        # Rien de cohérent : retombe sur le set le plus probable de l'espèce.
        ls = likely_set(opp.species, reg_id)
        st = replace(opp, moves=list(ls.moves or observed),
                     item=(opp.item or ls.item), ability=(opp.ability or ls.ability))
        return [Particle(build=st, weight=1.0)]

    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:k]
    total = sum(c for _, c in top)
    return [Particle(build=builds[kk], weight=c / total) for kk, c in top]


def opponent_move_support(particles: list[Particle]) -> list[str]:
    """Union ordonnée des coups possibles sur l'ensemble des particules."""
    seen: dict[str, None] = {}
    for p in particles:
        for m in p.build.moves:
            if move_known(m):
                seen.setdefault(m, None)
    return list(seen.keys())


# ---------------------------------------------------------------------------
# Mise à jour bayésienne inter-tours (§10.2, cran 3 de l'échelle SOTA)
# ---------------------------------------------------------------------------
# À l'état de l'art (PokaiTrainer), la croyance ne se construit pas seulement à
# partir de l'information révélée statique : elle se **met à jour tour après
# tour** en rebranchant l'action jointe observée. Voir l'adversaire jouer un coup
# est une observation dont on tire une vraisemblance par monde :
#
#     w'_i  ∝  w_i · P(coup observé | monde_i)
#
# On élimine (au plancher) les mondes où le coup n'existe pas — preuve dure — et,
# parmi les survivants, on **remonte** ceux dont la stratégie (de Nash, si
# fournie) jouait le plus ce coup. Si le coup n'appartient à AUCUN monde (croyance
# prise en défaut), on **synthétise** en l'injectant plutôt que d'effondrer la
# croyance sur le plancher.

def _has_move(build: PokemonState, mid: str) -> bool:
    return any(to_id(m) == mid for m in build.moves)


def _renorm(parts: list[Particle]) -> list[Particle]:
    tot = sum(p.weight for p in parts)
    if tot <= 0:                                  # tout au plancher : uniforme
        n = max(1, len(parts))
        return [Particle(build=p.build, weight=1.0 / n) for p in parts]
    return [Particle(build=p.build, weight=p.weight / tot) for p in parts]


def _strat_prob(strat: dict, mid: str) -> float:
    for k, v in strat.items():
        if k is not None and to_id(str(k)) == mid:
            return max(float(v), 0.0)
    return 0.0


def _inject_move(build: PokemonState, move: str) -> PokemonState:
    moves = [m for m in build.moves if move_known(m)]
    if any(to_id(m) == to_id(move) for m in moves):
        return build
    if len(moves) >= 4:                           # set plein : remplace le dernier
        moves = moves[:3]
    return replace(build, moves=[*moves, move])


def update_belief(particles: list[Particle], observed_move: str | None, *,
                  world_strategies: list[dict] | None = None,
                  floor: float = 0.02) -> list[Particle]:
    """Reconditionne la croyance après avoir vu l'adversaire jouer un coup.

    `observed_move` : l'id du coup adverse effectivement joué ce tour. ``None``
    (l'adversaire a changé ou était inactif) n'apprend rien sur le set actif :
    la croyance est renvoyée inchangée.

    `world_strategies` : optionnel, une stratégie par particule (``{coup: proba}``,
    typiquement la stratégie de Nash par monde de `nash.solve_turn`). Si fournie,
    la vraisemblance d'un monde qui possède le coup est sa **probabilité
    stratégique** de le jouer (plancher `floor`) ; sinon une vraisemblance
    **uniforme** ``1/|coups|`` (le monde joue au hasard).

    Renvoie une nouvelle liste de particules (poids a posteriori, normalisés).
    """
    if not particles:
        return []
    if observed_move is None or not move_known(observed_move):
        return [Particle(build=p.build, weight=p.weight) for p in particles]

    mid = to_id(observed_move)
    present = [_has_move(p.build, mid) for p in particles]

    if not any(present):                          # contradiction → synthèse
        synth = [Particle(build=_inject_move(p.build, observed_move), weight=p.weight)
                 for p in particles]
        return _renorm(synth)

    post: list[Particle] = []
    for i, p in enumerate(particles):
        if not present[i]:
            lik = floor                           # preuve dure : monde impossible
        elif world_strategies is not None and i < len(world_strategies):
            lik = max(_strat_prob(world_strategies[i], mid), floor)
        else:
            feasible = [m for m in p.build.moves if move_known(m)]
            lik = 1.0 / len(feasible) if feasible else floor
        post.append(Particle(build=p.build, weight=p.weight * lik))
    return _renorm(post)
