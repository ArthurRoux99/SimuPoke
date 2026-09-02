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

from .model import PokemonState
from .basestats import is_known, to_id
from .moves import is_known as move_known
from .usage import sample_set, likely_set, has_usage


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
        if observed and not set(to_id(m) for m in observed) <= set(to_id(m) for m in moves):
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
