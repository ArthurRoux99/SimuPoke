"""Résolution de tour **Doubles** vers l'équilibre de Nash (Phase 5).

Porte en 2v2 la machinerie de `nash.py`. Le tour Doubles reste un jeu simultané,
mais une action de camp est désormais une **paire** (slot gauche, slot droit), et
l'adversaire cache **deux** sets au lieu d'un.

Deux mécanismes rendent le problème calculable sans dénaturer la solution :

1. **Élagage top-k par slot** (`slot_candidates`) — chaque slot ne conserve que
   ses `k` meilleures actions, scorées par une passe rapide (dégâts et K.O. via
   le calc figé, note de soutien de `combat`, valeur de l'entrant pour un
   changement). Les actions de camp sont le produit des survivantes :
   `nash.solve_matrix` / `nash.solve_bayesian` résolvent alors **exactement** le
   jeu réduit. Le filtre est reporté à l'utilisateur — la recommandation reste
   explicable.
2. **Croyance jointe échantillonnée** (`joint_belief`) — un monde est un
   **couple** de sets adverses, tiré du produit des deux croyances marginales et
   borné à `n_worlds`. `nash.solve_bayesian` s'applique tel quel : l'adversaire
   connaît ses deux sets et joue au mieux dans chaque monde, je committe une
   paire mixte robuste.

Aucune règle de jeu n'est réimplémentée : la valeur d'une case de la matrice
vient de `sim_doubles.simulate_turn_doubles`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from dataclasses import field as dfield

from .belief import Particle, opponent_belief
from .combat import _evaluate_support, _incoming
from .damage import calculate
from .model import FieldState, PokemonState
from .moves import get_move
from .moves import is_known as move_known
from .nash import solve_bayesian
from .sim import Mon
from .sim_doubles import (
    PASS,
    DoublesSide,
    SlotAction,
    simulate_turn_doubles,
)

# Jets de dégâts énumérés (façon `nash.ROLLS`). Calibré au chronomètre : à k=3
# et 12 mondes, la résolution tient en ~0.6 s avec les trois jets — la marge
# sert donc la qualité plutôt que la vitesse.
ROLLS: tuple[float, ...] = (0.15, 0.5, 0.85)
_STATUSES = ("brn", "par", "slp", "frz", "tox", "psn")


# ---------------------------------------------------------------------------
# Évaluation d'un état 2v2
# ---------------------------------------------------------------------------

def evaluate_doubles(me: DoublesSide, opp: DoublesSide) -> float:
    """Évaluation d'un plateau 2v2, de mon point de vue.

    Même esprit que `search.evaluate_side` : je compare la santé **moyenne** de
    mon camp (actifs + banc) à celle des actifs adverses, avec un bonus par
    adversaire mis K.O. et des termes légers pour les boosts et les statuts.
    """
    mine = [*me.active, *me.bench]
    my_avg = sum(m.hp_pct for m in mine) / len(mine) if mine else 0.0
    foes = opp.active
    opp_avg = sum(0.0 if m.fainted else m.hp_pct for m in foes) / len(foes) \
        if foes else 0.0
    v = my_avg - opp_avg
    v += 1.0 * sum(1 for m in foes if m.fainted)      # actifs adverses battus
    v -= 1.0 * sum(1 for m in me.active if m.fainted)  # mes actifs perdus
    off = ("atk", "spa", "spe")
    for m in me.active:
        if m.fainted:
            continue
        v += 0.03 * sum(m.boosts.get(k, 0) for k in off)
        if m.status in _STATUSES:
            v -= 0.08
    for m in foes:
        if not m.fainted and m.status in _STATUSES:
            v += 0.08
    return v


# ---------------------------------------------------------------------------
# Élagage : les k meilleures actions d'un slot
# ---------------------------------------------------------------------------

def _foe_targets(opp: DoublesSide) -> list[int]:
    return [i for i, m in enumerate(opp.active) if not m.fainted]


def _score_offensive(attacker: Mon, target: Mon, move: str,
                     field: FieldState | None) -> float:
    """Dégâts attendus en fraction des PV de la cible, majorés si K.O."""
    try:
        r = calculate(attacker.snapshot(), target.snapshot(), move, field)
    except (ValueError, KeyError):
        return -1.0
    if r.max_damage <= 0:
        return -1.0
    frac = (r.min_damage + r.max_damage) / 2 / max(1, target.hp)
    return min(frac, 1.0) + (1.0 if r.min_damage >= target.hp else 0.0)


def slot_candidates(me: DoublesSide, opp: DoublesSide, slot: int, *,
                    k: int = 3, field: FieldState | None = None,
                    allow_switch: bool = True) -> list[SlotAction]:
    """Les `k` meilleures actions du slot `slot`, scorées par une passe rapide.

    Coups offensifs : dégâts attendus sur chaque cible légale (un candidat par
    cible). Coups de soutien : note de `combat._evaluate_support`, déjà utilisée
    par le mode analyse. Changements : santé de l'entrant.
    """
    mon = me.active[slot]
    if mon.fainted:
        return [PASS]
    scored: list[tuple[float, SlotAction]] = []
    foes = _foe_targets(opp)
    # Menace entrante estimée : sert à noter les coups de soutien (Protect monte
    # face à un OHKO). Prise sur le premier adversaire vivant.
    threat_from = (opp.active[foes[0]].snapshot() if foes else mon.snapshot())
    incoming = _incoming(mon.snapshot(), threat_from, field, None)
    for mid in mon.build.moves:
        if not move_known(mid):
            continue
        mv = get_move(mid)
        if mv.is_status or mv.base_power <= 0:
            note, _ = _evaluate_support(mid, mon.snapshot(), threat_from,
                                        field, incoming)
            scored.append((float(note), ("move", mid, None)))
            continue
        if mv.is_spread:
            best = max((_score_offensive(mon, opp.active[i], mid, field)
                        for i in foes), default=-1.0)
            scored.append((best * 1.5, ("move", mid, None)))   # touche les deux
            continue
        for i in foes:
            scored.append((_score_offensive(mon, opp.active[i], mid, field),
                           ("move", mid, ("foe", i))))
    if allow_switch:
        for i, b in enumerate(me.bench):
            if not b.fainted:
                scored.append((b.hp_pct - 0.6, ("switch", i, None)))
    if not scored:
        return [PASS]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [a for _, a in scored[:max(1, k)]]


# ---------------------------------------------------------------------------
# Croyance jointe : un monde = un couple de sets adverses
# ---------------------------------------------------------------------------

@dataclass
class JointWorld:
    """Un monde possible du camp adverse : un build par slot, et son poids."""
    builds: list[PokemonState]
    weight: float


def joint_belief(opp: DoublesSide, *, reg_id: str = "reg_m_b",
                 n_worlds: int = 12, belief_samples: int = 40,
                 seed: int | None = 0) -> list[JointWorld]:
    """Échantillonne jusqu'à `n_worlds` couples (set gauche, set droit).

    Les deux croyances marginales viennent de `belief.opponent_belief`. Le
    produit est **échantillonné** plutôt qu'énuméré : 6 × 6 particules feraient
    36 mondes, chacun coûtant une matrice complète de simulations.
    """
    marginals: list[list[Particle]] = [
        opponent_belief(m.build, reg_id, n_samples=belief_samples, seed=seed)
        for m in opp.active]
    if not marginals:
        return []
    # Peu de combinaisons : on énumère et on garde les plus probables.
    total = 1
    for parts in marginals:
        total *= len(parts)
    if total <= n_worlds:
        worlds: list[JointWorld] = []
        _enumerate(marginals, 0, [], 1.0, worlds)
        worlds.sort(key=lambda w: w.weight, reverse=True)
        return _normalise(worlds)
    rng = random.Random(seed)
    picked: dict[tuple, JointWorld] = {}
    for _ in range(n_worlds * 4):
        if len(picked) >= n_worlds:
            break
        builds, w = [], 1.0
        for parts in marginals:
            p = rng.choices(parts, weights=[x.weight for x in parts])[0]
            builds.append(p.build)
            w *= p.weight
        key = tuple(_build_key(b) for b in builds)
        picked.setdefault(key, JointWorld(builds=builds, weight=w))
    return _normalise(sorted(picked.values(), key=lambda w: w.weight,
                             reverse=True))


def _build_key(b: PokemonState) -> tuple:
    return (b.species, b.item, b.ability, tuple(b.moves))


def _enumerate(marginals: list[list[Particle]], i: int,
               acc: list[PokemonState], w: float,
               out: list[JointWorld]) -> None:
    if i == len(marginals):
        out.append(JointWorld(builds=list(acc), weight=w))
        return
    for p in marginals[i]:
        acc.append(p.build)
        _enumerate(marginals, i + 1, acc, w * p.weight, out)
        acc.pop()


def _normalise(worlds: list[JointWorld]) -> list[JointWorld]:
    total = sum(w.weight for w in worlds)
    if total <= 0:
        n = len(worlds) or 1
        for w in worlds:
            w.weight = 1.0 / n
        return worlds
    for w in worlds:
        w.weight /= total
    return worlds


# ---------------------------------------------------------------------------
# Résultat + résolution
# ---------------------------------------------------------------------------

@dataclass
class DoublesNashResult:
    strategy: list[tuple[str, float]]         # (libellé de paire, proba) desc
    value: float
    opp_strategy: list[tuple[str, float]]
    best_response: str
    recommendation: str
    considered: list[list[str]]               # options retenues par slot
    notes: list[str] = dfield(default_factory=list)

    def lines(self) -> list[str]:
        out = ["Stratégie mixte de Nash (Doubles 2v2, croyance jointe) :"]
        for label, p in self.strategy:
            if p >= 0.005:
                out.append(f"  {label:<38} {p*100:5.1f} %")
        out.append("")
        out.append("Options considérées par slot (élagage) :")
        for i, opts in enumerate(self.considered):
            out.append(f"  slot {i} : {', '.join(opts)}")
        out.append("")
        opp = ", ".join(f"{lbl} {p*100:.0f}%"
                        for lbl, p in self.opp_strategy[:3] if p >= 0.02)
        out.append(f"Adversaire (modèle Nash) : {opp}")
        out.append(f"Valeur du jeu : {self.value:+.2f}")
        for n in self.notes:
            out.append(f"  ({n})")
        out.append("")
        out.append(f"➤ {self.recommendation}")
        return out


def _action_label(action: SlotAction, me: DoublesSide, slot: int) -> str:
    kind, x, target = action
    if kind == "switch":
        return f"→ {me.bench[x].build.species}"
    if kind != "move" or x is None:
        return "(inactif)"
    name = get_move(x).name
    return f"{name}@{target[1]}" if target and target[0] == "foe" else name


def _pair_label(pair: tuple[SlotAction, SlotAction], side: DoublesSide) -> str:
    return " + ".join(_action_label(a, side, i) for i, a in enumerate(pair))


def _pairs(cands0: list[SlotAction],
           cands1: list[SlotAction]) -> list[tuple[SlotAction, SlotAction]]:
    return [(a, b) for a in cands0 for b in cands1]


def _payoff(me: DoublesSide, opp: DoublesSide,
            my_pair: tuple[SlotAction, SlotAction],
            opp_pair: tuple[SlotAction, SlotAction],
            field: FieldState | None, rolls: tuple[float, ...]) -> float:
    """Valeur moyenne de mon état après le tour, sur les jets retenus."""
    total = 0.0
    for roll in rolls:
        res = simulate_turn_doubles(me, opp, my_pair, opp_pair, field, roll=roll)
        total += evaluate_doubles(res.me, res.opp)
    return total / len(rolls)


def _world_side(opp: DoublesSide, world: JointWorld) -> DoublesSide:
    """Copie du camp adverse où chaque slot porte le build du monde."""
    actives = []
    for mon, build in zip(opp.active, world.builds):
        clone = Mon.from_state(build)
        clone.hp = min(clone.max_hp, max(0, mon.hp))   # PV observés conservés
        clone.status = mon.status
        clone.boosts = dict(mon.boosts)
        actives.append(clone)
    return DoublesSide(active=actives, bench=list(opp.bench),
                       screens=dict(opp.screens), tailwind=opp.tailwind,
                       hazards=dict(opp.hazards))


def solve_turn_doubles(me: DoublesSide, opp: DoublesSide,
                       field: FieldState | None = None, *,
                       k: int = 3, n_worlds: int = 12, iters: int = 800,
                       rolls: tuple[float, ...] = ROLLS,
                       reg_id: str = "reg_m_b",
                       seed: int | None = 0) -> DoublesNashResult:
    """Résout le tour Doubles courant et renvoie ma **paire mixte** de Nash.

    `k` borne les options retenues par slot, `n_worlds` le nombre de couples de
    sets adverses envisagés : le coût est `(k²)² × n_worlds × len(rolls)`
    simulations de tour.
    """
    my_cands = [slot_candidates(me, opp, i, k=k, field=field)
                for i in range(len(me.active))]
    while len(my_cands) < 2:
        my_cands.append([PASS])
    my_pairs = _pairs(my_cands[0], my_cands[1])
    my_labels = [_pair_label(p, me) for p in my_pairs]

    worlds = joint_belief(opp, reg_id=reg_id, n_worlds=n_worlds,
                          seed=seed) or [JointWorld(
                              builds=[m.build for m in opp.active], weight=1.0)]

    solved: list[tuple[float, list[list[float]], list[str]]] = []
    for world in worlds:
        w_side = _world_side(opp, world)
        opp_cands = [slot_candidates(w_side, me, i, k=k, field=field,
                                     allow_switch=False)
                     for i in range(len(w_side.active))]
        while len(opp_cands) < 2:
            opp_cands.append([PASS])
        opp_pairs = _pairs(opp_cands[0], opp_cands[1])
        U = [[_payoff(me, w_side, mp, op, field, rolls) for op in opp_pairs]
             for mp in my_pairs]
        solved.append((world.weight, U,
                       [_pair_label(p, w_side) for p in opp_pairs]))

    my_strat, value, opp_marginal, br, _ = solve_bayesian(
        len(my_pairs), solved, iters=iters)

    strat = sorted(zip(my_labels, my_strat), key=lambda t: t[1], reverse=True)
    top_label, top_p = strat[0]
    if top_p >= 0.9:
        reco = f"Joue {top_label} — paire quasi pure ({top_p*100:.0f} %)."
    else:
        mix = ", ".join(f"{lbl} {p*100:.0f}%" for lbl, p in strat[:3]
                        if p >= 0.05)
        reco = (f"Paire mixte optimale : {mix} — mélange pour ne pas être "
                f"exploité au jeu simultané.")
    notes = [f"{len(my_pairs)} paires retenues sur {len(worlds)} monde(s) "
             f"adverse(s)"]
    return DoublesNashResult(
        strategy=strat, value=value,
        opp_strategy=[(lbl or "(inactif)", p) for lbl, p in opp_marginal],
        best_response=my_labels[br], recommendation=reco,
        considered=[[_action_label(a, me, i) for a in cands]
                    for i, cands in enumerate(my_cands)],
        notes=notes)
