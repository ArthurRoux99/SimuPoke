"""Tests du solveur de Nash (regret matching) et de la résolution de tour."""

from __future__ import annotations

from simupoke.nash import solve_matrix, solve_turn
from simupoke.sim import Mon
from simupoke.model import PokemonState


# --- Solveur matriciel : jeux à équilibre connu ---------------------------

def test_matching_pennies_is_uniform():
    # U (gain de la ligne) : pile/face -> Nash = 50/50, valeur 0.
    rst, cst, val = solve_matrix([[1, -1], [-1, 1]], iters=4000)
    assert abs(rst[0] - 0.5) < 0.05 and abs(rst[1] - 0.5) < 0.05
    assert abs(cst[0] - 0.5) < 0.05
    assert abs(val) < 0.05


def test_rock_paper_scissors_is_uniform():
    U = [[0, -1, 1], [1, 0, -1], [-1, 1, 0]]
    rst, _, val = solve_matrix(U, iters=6000)
    for p in rst:
        assert abs(p - 1 / 3) < 0.06
    assert abs(val) < 0.05


def test_dominant_row_is_pure():
    # La ligne 0 domine : la stratégie doit s'y concentrer, valeur 1.
    rst, _, val = solve_matrix([[1.0, 1.0], [0.0, 0.0]], iters=2000)
    assert rst[0] > 0.95
    assert abs(val - 1.0) < 0.05


def test_solve_matrix_strategies_sum_to_one():
    rst, cst, _ = solve_matrix([[0.3, -0.2, 0.5], [-0.1, 0.4, 0.0]], iters=1500)
    assert abs(sum(rst) - 1.0) < 1e-6
    assert abs(sum(cst) - 1.0) < 1e-6


# --- Résolution de tour ----------------------------------------------------

def _mon(species, nature="serious", moves=None, sp=None, hp=1.0, item=None):
    return Mon.from_state(PokemonState(
        species=species, nature=nature, stat_points=sp or {},
        moves=moves or [], item=item, current_hp_pct=hp))


def test_solve_turn_returns_valid_distribution():
    me = _mon("garchomp", "jolly", ["earthquake", "dragonclaw", "stoneedge"],
              {"atk": 32, "spe": 32})
    opp = _mon("tyranitar", "adamant", ["crunch", "rockslide"])  # set connu
    res = solve_turn(me, opp)
    assert abs(sum(p for _, p in res.strategy) - 1.0) < 1e-6
    labels = {lbl for lbl, _ in res.strategy}
    assert {"Earthquake", "Dragon Claw", "Stone Edge"} <= labels
    assert res.best_response in labels


def test_solve_turn_favors_ko_when_opponent_cannot_stall():
    # Set adverse ENTIÈREMENT connu, sans Protect : rien ne bloque le KO, donc
    # la stratégie se concentre sur le coup qui achève (pas de hedge possible).
    me = _mon("garchomp", "jolly", ["earthquake", "swordsdance"],
              {"atk": 32, "spe": 32}, item="choiceband")
    opp = _mon("tyranitar", "jolly",
               ["crunch", "rockslide", "icepunch", "lowkick"], hp=0.15)
    res = solve_turn(me, opp)
    top_label, top_p = res.strategy[0]
    assert top_label == "Earthquake"
    assert top_p > 0.8
    assert res.value > 0.5


def test_solve_turn_mixes_against_protect():
    # Quand l'adversaire peut Protéger pour esquiver le KO, la réponse de Nash
    # est une stratégie MIXTE (hedge) — pas une action pure exploitable.
    me = _mon("garchomp", "jolly", ["earthquake", "swordsdance"],
              {"atk": 32, "spe": 32}, item="choiceband")
    opp = _mon("tyranitar", "jolly",
               ["crunch", "rockslide", "protect", "icepunch"], hp=0.15)
    res = solve_turn(me, opp)
    top_p = res.strategy[0][1]
    assert top_p < 0.95                                   # mélange, pas pur
    assert abs(sum(p for _, p in res.strategy) - 1.0) < 1e-6
    # Protect apparaît dans la stratégie adverse (elle sert à punir le KO).
    opp_protect = next((p for m, p in res.opp_strategy if m == "protect"), 0.0)
    assert opp_protect > 0.05
