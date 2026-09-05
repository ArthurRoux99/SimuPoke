"""Recherche à **coups simultanés sous budget** — SM-MCTS avec regret matching.

Ferme le cran 2 de l'échelle SOTA (`docs/recherche_sota_ismcts.md`). Le lookahead
de `nash._sm_nash_value` développe **toutes** les paires d'actions à chaque étage :
son coût est en `(|A|·|B|)^profondeur`, ce qui force à brider l'horizon à 3 tours.

Ce module échantillonne l'arbre au lieu de le développer. À chaque nœud, les deux
camps tirent leur action selon une stratégie de **regret matching** — la même
primitive que `nash.solve_matrix`, appliquée nœud par nœud. C'est le SM-MCTS-RM
de Lisý, Kovařík et Bošanský (*MCTS in Simultaneous Move Games*, NeurIPS 2013),
qui **converge vers l'équilibre de Nash** du jeu à coups simultanés, alors que
DUCT (UCB découplé) peut converger ailleurs.

Le coût devient **linéaire** : `budget × profondeur` simulations de tour au plus,
au lieu d'exponentiel. On peut donc regarder loin sans faire exploser le temps.

Une seule source de vérité : les transitions passent par
`sim.simulate_turn_actions` (via `search._child`) et les feuilles par
`search.evaluate_side`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .model import FieldState
from .moves import is_known as move_known
from .search import GAMMA, _child, _my_actions, _terminal, evaluate_side
from .sim import Side


@dataclass
class SearchStats:
    """Compteurs d'une recherche — sert aux tests et au diagnostic de coût."""
    iterations: int = 0
    simulations: int = 0
    nodes: int = 0


@dataclass
class _Node:
    """Un nœud de l'arbre : regrets cumulés des deux camps et enfants visités."""
    my_actions: list[tuple]
    opp_actions: list[str | None]
    my_regret: list[float] = field(default_factory=list)
    opp_regret: list[float] = field(default_factory=list)
    my_sum: list[float] = field(default_factory=list)
    visits: int = 0
    children: dict = field(default_factory=dict)     # (i, j) -> (Side, Side, _Node|None)

    def __post_init__(self) -> None:
        self.my_regret = [0.0] * len(self.my_actions)
        self.opp_regret = [0.0] * len(self.opp_actions)
        self.my_sum = [0.0] * len(self.my_actions)


def _strategy(regret: list[float]) -> list[float]:
    """Regret matching : proportionnel aux regrets positifs, uniforme sinon."""
    pos = [r if r > 0 else 0.0 for r in regret]
    total = sum(pos)
    if total <= 0:
        return [1.0 / len(regret)] * len(regret)
    return [p / total for p in pos]


def _sample(strategy: list[float], rng: random.Random) -> int:
    x = rng.random()
    acc = 0.0
    for i, p in enumerate(strategy):
        acc += p
        if x < acc:
            return i
    return len(strategy) - 1


def _opp_actions(opp: Side) -> list[str | None]:
    return [m for m in opp.active.build.moves if move_known(m)] or [None]


def _make_node(me: Side, opp: Side, stats: SearchStats | None) -> _Node:
    if stats is not None:
        stats.nodes += 1
    return _Node(my_actions=_my_actions(me, allow_switch=False),
                 opp_actions=_opp_actions(opp))


def _iterate(node: _Node, me: Side, opp: Side, field: FieldState | None,
             depth: int, roll: float, rng: random.Random,
             stats: SearchStats | None) -> float:
    """Une descente : tire une paire d'actions, récurse, remonte la valeur.

    Les regrets sont mis à jour **contrefactuellement** sur l'action adverse
    échantillonnée : pour chaque action `a` du camp, on compare l'utilité de `a`
    face à l'action adverse tirée à celle réellement obtenue. C'est la variante
    de regret matching qui donne la convergence vers Nash.
    """
    if depth <= 0 or _terminal(me, opp):
        return evaluate_side(me, opp.active)

    my_strategy = _strategy(node.my_regret)
    opp_strategy = _strategy(node.opp_regret)
    i = _sample(my_strategy, rng)
    j = _sample(opp_strategy, rng)
    node.visits += 1
    for a in range(len(node.my_actions)):
        node.my_sum[a] += my_strategy[a]

    # Utilité de CHACUNE de mes actions face à l'action adverse tirée : c'est ce
    # qui rend les regrets contrefactuels, donc la convergence correcte.
    my_utils: list[float] = []
    for a in range(len(node.my_actions)):
        value = _child_value(node, me, opp, field, a, j, depth, roll, rng, stats,
                             expand=(a == i))
        my_utils.append(value)
    played = my_utils[i]

    # Utilité de chaque action adverse face à MON action jouée (il minimise).
    opp_utils: list[float] = []
    for b in range(len(node.opp_actions)):
        if b == j:
            opp_utils.append(played)
        else:
            opp_utils.append(
                _child_value(node, me, opp, field, i, b, depth, roll, rng,
                             stats, expand=False))

    for a in range(len(node.my_actions)):
        node.my_regret[a] += my_utils[a] - played
    for b in range(len(node.opp_actions)):
        node.opp_regret[b] += played - opp_utils[b]      # il maximise -u
    return GAMMA * played


def _child_value(node: _Node, me: Side, opp: Side, field: FieldState | None,
                 i: int, j: int, depth: int, roll: float, rng: random.Random,
                 stats: SearchStats | None, *, expand: bool) -> float:
    """Valeur de l'enfant `(i, j)`. `expand` : on descend récursivement (branche
    effectivement jouée) ; sinon on se contente de l'évaluation immédiate, qui
    sert de baseline aux regrets sans coûter une descente complète."""
    key = (i, j)
    entry = node.children.get(key)
    if entry is None:
        child_me, child_opp = _child(me, opp, node.my_actions[i],
                                     node.opp_actions[j], field, roll)
        if stats is not None:
            stats.simulations += 1
        entry = [child_me, child_opp, None]
        node.children[key] = entry
    child_me, child_opp, child_node = entry
    if not expand or depth <= 1 or _terminal(child_me, child_opp):
        return evaluate_side(child_me, child_opp.active)
    if child_node is None:
        child_node = _make_node(child_me, child_opp, stats)
        entry[2] = child_node
    return _iterate(child_node, child_me, child_opp, field, depth - 1, roll,
                    rng, stats)


def sm_mcts_strategy(me: Side, opp: Side, field: FieldState | None = None, *,
                     depth: int = 3, roll: float = 0.5, budget: int = 400,
                     seed: int | None = 0,
                     stats: SearchStats | None = None
                     ) -> tuple[list[tuple[tuple, float]], float]:
    """Recherche sous budget et renvoie (stratégie racine, valeur du jeu).

    La stratégie est la **moyenne** des stratégies de regret matching visitées à
    la racine — c'est elle qui converge vers l'équilibre, pas la dernière.
    """
    rng = random.Random(seed)
    if depth <= 0 or _terminal(me, opp):
        value = evaluate_side(me, opp.active)
        actions = _my_actions(me, allow_switch=False)
        return [(a, 1.0 / len(actions)) for a in actions], value
    root = _make_node(me, opp, stats)
    total = 0.0
    for _ in range(max(1, budget)):
        total += _iterate(root, me, opp, field, depth, roll, rng, stats)
        if stats is not None:
            stats.iterations += 1
    norm = sum(root.my_sum) or 1.0
    strategy = [(a, s / norm) for a, s in zip(root.my_actions, root.my_sum)]
    strategy.sort(key=lambda t: t[1], reverse=True)
    return strategy, total / max(1, budget)


def sm_mcts_value(me: Side, opp: Side, field: FieldState | None = None, *,
                  depth: int = 3, roll: float = 0.5, budget: int = 400,
                  seed: int | None = 0,
                  stats: SearchStats | None = None) -> float:
    """Valeur d'un état à coups simultanés, estimée sous budget.

    Remplaçant échantillonné de `nash._sm_nash_value` : même sémantique (les deux
    camps jouent au mieux), coût linéaire au lieu d'exponentiel.
    """
    _, value = sm_mcts_strategy(me, opp, field, depth=depth, roll=roll,
                                budget=budget, seed=seed, stats=stats)
    return value
