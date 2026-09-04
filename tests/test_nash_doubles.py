"""Tests du solveur de Nash Doubles (nash_doubles.py)."""

from __future__ import annotations

from simupoke.model import PokemonState
from simupoke.nash_doubles import (
    joint_belief,
    slot_candidates,
    solve_turn_doubles,
)
from simupoke.sim import Mon
from simupoke.sim_doubles import DoublesSide


def st(species, nature="serious", sp=None, item=None, ability=None,
       moves=None, hp=1.0):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        item=item, ability=ability, moves=moves or [],
                        current_hp_pct=hp)


def mon(*a, **k):
    return Mon.from_state(st(*a, **k))


def side(*mons, **kw):
    return DoublesSide(active=list(mons), **kw)


# --- Élagage des actions par slot -------------------------------------------

def test_slot_candidates_are_capped_by_k():
    me = side(mon("garchomp", "adamant", {"atk": 31},
                  moves=["earthquake", "rockslide", "dragonclaw", "protect"]),
              mon("snorlax", "brave", moves=["bodyslam"]))
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    cands = slot_candidates(me, opp, 0, k=2)
    assert len(cands) == 2
    for action in cands:
        assert action[0] in ("move", "switch")


def test_pruning_keeps_a_guaranteed_ko():
    # Griffe Dragon tue le Dracaufeu affaibli ; l'élagage doit la garder.
    me = side(mon("garchomp", "adamant", {"atk": 31},
                  moves=["dragonclaw", "protect", "swordsdance"]),
              mon("snorlax", "brave", moves=["bodyslam"]))
    opp = side(mon("dragapult", "timid", hp=0.15), mon("torkoal", "quiet"))
    cands = slot_candidates(me, opp, 0, k=1)
    assert cands[0][:2] == ("move", "dragonclaw")


# --- Croyance jointe --------------------------------------------------------

def test_joint_belief_is_bounded_and_normalised():
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    worlds = joint_belief(opp, n_worlds=6, seed=0)
    assert 1 <= len(worlds) <= 6
    assert abs(sum(w.weight for w in worlds) - 1.0) < 1e-9
    for w in worlds:
        assert len(w.builds) == 2


def test_joint_belief_is_deterministic_with_a_seed():
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    a = joint_belief(opp, n_worlds=6, seed=1)
    b = joint_belief(opp, n_worlds=6, seed=1)
    assert [(w.weight, [x.species for x in w.builds]) for w in a] == \
           [(w.weight, [x.species for x in w.builds]) for w in b]


# --- Résolution ------------------------------------------------------------

def test_strategy_is_a_distribution():
    me = side(mon("garchomp", "adamant", {"atk": 31},
                  moves=["earthquake", "rockslide", "protect"]),
              mon("incineroar", "careful", moves=["flareblitz", "followme"]))
    opp = side(mon("tyranitar", "jolly", moves=["rockslide", "protect"]),
               mon("torkoal", "quiet", moves=["eruption", "protect"]))
    res = solve_turn_doubles(me, opp, k=2, n_worlds=2, iters=200)
    assert abs(sum(p for _, p in res.strategy) - 1.0) < 1e-6
    assert all(p >= 0.0 for _, p in res.strategy)
    assert res.strategy[0][1] >= res.strategy[-1][1]      # trié décroissant


def test_guaranteed_double_ko_dominates():
    # Les deux adversaires sont à un souffle : la paire qui les achève doit
    # concentrer la stratégie.
    me = side(mon("garchomp", "adamant", {"atk": 31},
                  moves=["dragonclaw", "protect"]),
              mon("dragapult", "timid", {"spa": 31},
                  moves=["shadowball", "protect"]))
    opp = side(mon("tyranitar", "jolly", hp=0.05, moves=["protect"]),
               mon("torkoal", "quiet", hp=0.05, moves=["protect"]))
    res = solve_turn_doubles(me, opp, k=2, n_worlds=1, iters=300)
    # Les deux répartitions « un coup par cible » sont symétriques : elles se
    # partagent la masse. Ce qui compte est que le focus fire redondant (les
    # deux coups sur la même cible) et Protect soient écartés.
    split = sum(p for lbl, p in res.strategy
                if lbl in ("Dragon Claw@0 + Shadow Ball@1",
                           "Dragon Claw@1 + Shadow Ball@0"))
    assert split > 0.9, f"le double K.O. ne domine pas : {res.strategy}"
    assert all("Protect" not in lbl for lbl, p in res.strategy if p > 0.05)


def test_solution_is_deterministic():
    def run():
        me = side(mon("garchomp", "adamant", {"atk": 31},
                      moves=["earthquake", "protect"]),
                  mon("incineroar", "careful", moves=["flareblitz", "followme"]))
        opp = side(mon("tyranitar", "jolly", moves=["rockslide", "protect"]),
                   mon("torkoal", "quiet", moves=["eruption", "protect"]))
        return solve_turn_doubles(me, opp, k=2, n_worlds=2, iters=200)

    assert run().strategy == run().strategy


def test_report_lines_mention_the_pruning():
    me = side(mon("garchomp", "adamant", {"atk": 31},
                  moves=["earthquake", "protect"]),
              mon("incineroar", "careful", moves=["flareblitz", "followme"]))
    opp = side(mon("tyranitar", "jolly", moves=["rockslide"]),
               mon("torkoal", "quiet", moves=["eruption"]))
    lines = "\n".join(solve_turn_doubles(me, opp, k=2, n_worlds=1,
                                         iters=200).lines())
    assert "considérées par slot" in lines
    assert "Valeur du jeu" in lines


def test_pruning_penalises_friendly_fire():
    # Séisme frappe fort mais touche l'allié vivant : à k=1, une frappe
    # mono-cible comparable doit passer devant.
    me = side(mon("garchomp", "adamant", {"atk": 31},
                  moves=["earthquake", "dragonclaw"]),
              mon("incineroar", "careful", moves=["flareblitz"]))
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    assert slot_candidates(me, opp, 0, k=1)[0][1] == "dragonclaw"
    # Allié déjà K.O. : plus de friendly fire, Séisme redevient le meilleur.
    me.active[1].hp = 0
    assert slot_candidates(me, opp, 0, k=1)[0][1] == "earthquake"
