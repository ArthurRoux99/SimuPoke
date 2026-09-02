"""Tests du solveur de Nash (regret matching) et de la résolution de tour."""

from __future__ import annotations

from simupoke.nash import solve_matrix, solve_bayesian, solve_turn
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


# --- Jeu bayésien par-monde ------------------------------------------------

def test_bayesian_informed_opponent_is_stronger():
    # Deux mondes équiprobables. Dans le monde A, l'adversaire punit mon
    # action 0 ; dans le monde B, il punit mon action 1. S'il CONNAÎT son monde
    # (info privée), il exploite : ma valeur tombe sous celle du jeu « moyen ».
    U_a = [[0.0, 1.0], [1.0, 1.0]]
    U_b = [[1.0, 1.0], [1.0, 0.0]]
    worlds = [(0.5, U_a, ["x", "y"]), (0.5, U_b, ["x", "y"])]
    my_strat, value, opp_marg, br = solve_bayesian(2, worlds, iters=6000)

    # Jeu « moyen » (adversaire non informé) : matrice moyenne.
    U_avg = [[(U_a[i][j] + U_b[i][j]) / 2 for j in range(2)] for i in range(2)]
    _, _, avg_val = solve_matrix(U_avg, iters=6000)

    assert value < avg_val - 0.1                 # l'info privée renforce l'adversaire
    assert abs(value - 0.5) < 0.05               # valeur bayésienne attendue
    assert abs(sum(my_strat) - 1.0) < 1e-6
    assert abs(sum(p for _, p in opp_marg) - 1.0) < 1e-6


def test_bayesian_single_world_matches_matrix():
    U = [[0.7, -0.2], [0.1, 0.4]]
    ms, val, _, _ = solve_bayesian(2, [(1.0, U, ["a", "b"])], iters=4000)
    rst, _, mval = solve_matrix(U, iters=4000)
    assert abs(val - mval) < 0.02
    assert abs(ms[0] - rst[0]) < 0.05


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


def test_horizon_lookahead_affects_evaluation():
    # La profondeur doit influer sur l'évaluation : face à un mur qui se soigne,
    # regarder plus loin change la valeur du jeu (le soin est pris en compte).
    me = _mon("garchomp", "adamant", ["earthquake", "swordsdance"], {"atk": 32})
    opp = _mon("corviknight", "impish", ["bodypress", "roost"])
    v0 = solve_turn(me, opp, horizon=0).value
    v2 = solve_turn(me, opp, horizon=2).value
    assert abs(v2 - v0) > 0.01                    # la profondeur a un effet mesurable
    r2 = solve_turn(me, opp, horizon=2)
    assert abs(sum(p for _, p in r2.strategy) - 1.0) < 1e-6
