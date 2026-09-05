"""Tests de la recherche à coups simultanés sous budget (ismcts.py)."""

from __future__ import annotations

import time

from simupoke.ismcts import SearchStats, sm_mcts_strategy, sm_mcts_value
from simupoke.model import PokemonState
from simupoke.nash import _sm_nash_value
from simupoke.sim import Mon, Side


def st(species, nature="serious", sp=None, item=None, moves=None, hp=1.0):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        item=item, moves=moves or [], current_hp_pct=hp)


def side(species, nature="serious", sp=None, moves=None, hp=1.0, bench=()):
    return Side(active=Mon.from_state(st(species, nature, sp, moves=moves, hp=hp)),
                bench=[Mon.from_state(st(*b)) for b in bench])


# --- Correction ------------------------------------------------------------

def test_single_action_matches_the_exact_lookahead():
    # Un seul coup de chaque côté : la recherche n'a rien à arbitrer, elle doit
    # retrouver la valeur du développement complet.
    me = side("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"])
    opp = side("tyranitar", "jolly", moves=["crunch"])
    exact = _sm_nash_value(me, opp, None, 2, 0.5)
    approx = sm_mcts_value(me, opp, None, depth=2, roll=0.5, budget=60)
    assert abs(exact - approx) < 1e-6


def test_converges_towards_the_exact_nash_value():
    me = side("garchomp", "adamant", {"atk": 31},
              moves=["dragonclaw", "earthquake", "protect"])
    opp = side("tyranitar", "jolly", moves=["crunch", "rockslide", "protect"])
    exact = _sm_nash_value(me, opp, None, 1, 0.5)
    approx = sm_mcts_value(me, opp, None, depth=1, roll=0.5, budget=1500)
    assert abs(exact - approx) < 0.15, f"exact={exact:.3f} mcts={approx:.3f}"


def test_terminal_state_is_evaluated_without_search():
    me = side("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"])
    opp = side("tyranitar", "jolly", moves=["crunch"], hp=0.01)
    opp.active.hp = 0
    assert sm_mcts_value(me, opp, None, depth=3, roll=0.5, budget=50) > 0


# --- Budget ----------------------------------------------------------------

def test_budget_bounds_the_number_of_simulations():
    me = side("garchomp", "adamant", {"atk": 31},
              moves=["dragonclaw", "earthquake", "rockslide", "protect"])
    opp = side("tyranitar", "jolly",
               moves=["crunch", "rockslide", "protect", "stealthrock"])
    stats = SearchStats()
    sm_mcts_value(me, opp, None, depth=4, roll=0.5, budget=100, stats=stats)
    # Une itération descend au plus `depth` fois : le coût est linéaire en
    # budget × profondeur, pas exponentiel en profondeur.
    assert stats.simulations <= 100 * 4
    assert stats.iterations == 100


def test_deep_search_stays_cheap():
    me = side("garchomp", "adamant", {"atk": 31},
              moves=["dragonclaw", "earthquake", "rockslide", "protect"])
    opp = side("tyranitar", "jolly",
               moves=["crunch", "rockslide", "protect", "stealthrock"])
    start = time.perf_counter()
    sm_mcts_value(me, opp, None, depth=8, roll=0.5, budget=300)
    assert time.perf_counter() - start < 10.0


# --- Stratégie racine ------------------------------------------------------

def test_root_strategy_is_a_distribution():
    me = side("garchomp", "adamant", {"atk": 31},
              moves=["dragonclaw", "earthquake", "protect"])
    opp = side("tyranitar", "jolly", moves=["crunch", "protect"])
    strat, value = sm_mcts_strategy(me, opp, None, depth=2, roll=0.5, budget=400)
    assert abs(sum(p for _, p in strat) - 1.0) < 1e-6
    assert all(p >= 0.0 for _, p in strat)
    assert isinstance(value, float)


def test_search_is_deterministic_with_a_seed():
    def run():
        me = side("garchomp", "adamant", {"atk": 31},
                  moves=["dragonclaw", "earthquake", "protect"])
        opp = side("tyranitar", "jolly", moves=["crunch", "protect"])
        return sm_mcts_strategy(me, opp, None, depth=2, roll=0.5, budget=300,
                                seed=7)

    assert run() == run()


def test_a_lethal_action_gets_most_of_the_mass():
    # L'adversaire est à un souffle et n'a pas Protect : la frappe qui tue doit
    # dominer le mélange. (Avec Protect en face, temporiser vaut autant que
    # frapper — le mélange 50/50 serait alors la bonne réponse.)
    me = side("garchomp", "adamant", {"atk": 31},
              moves=["dragonclaw", "protect"])
    opp = side("tyranitar", "jolly", moves=["crunch"], hp=0.05)
    strat, _ = sm_mcts_strategy(me, opp, None, depth=2, roll=0.5, budget=800)
    top = max(strat, key=lambda t: t[1])
    assert top[0] == ("move", "dragonclaw"), strat
    assert top[1] > 0.6, strat
