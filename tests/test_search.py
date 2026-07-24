"""Tests de la recherche à coups simultanés (search.py)."""

from __future__ import annotations

from simupoke.model import PokemonState, FieldState
from simupoke.sim import Mon
from simupoke.search import (
    rank_actions, evaluate_state, opponent_moves,
)


def st(species, nature="serious", sp=None, item=None, ability=None,
       moves=None, hp=1.0, status=None):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        item=item, ability=ability, moves=moves or [],
                        current_hp_pct=hp, status=status)


def mon(*a, **k):
    return Mon.from_state(st(*a, **k))


# --- Évaluation -------------------------------------------------------------

def test_eval_faint_dominates():
    me = mon("garchomp", "jolly")
    opp = mon("tyranitar", "jolly", hp=0.0)
    opp.hp = 0
    assert evaluate_state(me, opp) == 2.0
    me2 = mon("garchomp", "jolly")
    me2.hp = 0
    assert evaluate_state(me2, mon("tyranitar", "jolly")) == -2.0


def test_eval_hp_differential():
    me = mon("garchomp", "jolly")
    opp = mon("garchomp", "jolly")
    opp.hp = opp.max_hp // 2
    assert evaluate_state(me, opp) > 0        # j'ai plus de PV


def test_eval_status_penalty():
    healthy = mon("garchomp", "jolly")
    burned = mon("garchomp", "jolly", status="brn")
    opp = mon("tyranitar", "careful")
    assert evaluate_state(burned, opp) < evaluate_state(healthy, opp)


# --- Candidats adverses -----------------------------------------------------

def test_opponent_moves_from_known():
    opp = mon("tyranitar", "adamant", moves=["crunch", "stoneedge"])
    assert opponent_moves(opp) == ["crunch", "stoneedge"]


def test_opponent_moves_from_usage():
    opp = mon("incineroar", "careful")
    cands = opponent_moves(opp)
    assert cands and cands != [None]          # comblé via l'usage


def test_opponent_moves_inactive_fallback():
    opp = mon("magikarp", "serious")          # hors usage, sans moves
    assert opponent_moves(opp) == [None]


# --- Classement -------------------------------------------------------------

def test_best_action_is_super_effective():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32},
             moves=["earthquake", "dragonclaw", "stoneedge"])
    opp = mon("tyranitar", "adamant", {"atk": 32}, moves=["crunch"])
    r = rank_actions(me, opp)
    assert r.actions[0].move == "Earthquake"
    assert "Earthquake" in r.recommendation


def test_ko_chance_flagged():
    me = mon("garchomp", "adamant", {"atk": 32}, item="choiceband",
             moves=["earthquake"])
    opp = mon("tyranitar", "jolly", moves=["crunch"], hp=0.5)
    r = rank_actions(me, opp, roll=1.0)
    assert r.actions[0].ko_chance is True


def test_expected_and_worst_consistent():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32},
             moves=["earthquake", "swordsdance"])
    opp = mon("tyranitar", "adamant", {"atk": 32},
              moves=["crunch", "earthquake"])
    r = rank_actions(me, opp)
    for a in r.actions:
        assert a.worst <= a.expected          # le pire cas ≤ la moyenne


def test_safe_compromise_recommendation():
    # Face à une menace, une option qui ne se fait pas KO peut primer.
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32},
             moves=["earthquake", "dragonclaw"])
    opp = mon("dragapult", "timid", {"spa": 32, "spe": 32},
              moves=["dracometeor", "shadowball"])
    r = rank_actions(me, opp)
    assert r.actions                          # au moins classé sans erreur
    assert isinstance(r.recommendation, str)
