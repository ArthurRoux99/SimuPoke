"""Tests de la recherche à coups simultanés (search.py)."""

from __future__ import annotations

from simupoke.model import PokemonState, FieldState
from simupoke.sim import Mon
from simupoke.search import (
    rank_actions, rank_actions_sampled, evaluate_state, opponent_moves,
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


def test_switch_ranked_and_recommended_when_active_is_lost():
    # Gengar SAIN mais condamné (OHKO Séisme Choice Band) : le préserver via un
    # switch vers Skarmory (immunisé Sol) vaut mieux que le sacrifier.
    me = mon("gengar", "timid", {"spa": 32, "spe": 32}, moves=["shadowball"])
    opp = mon("garchomp", "jolly", {"atk": 32, "spe": 32}, item="choiceband",
              moves=["earthquake"])
    bench = [mon("skarmory", "impish", {"hp": 32, "def": 32}, moves=["bravebird"])]
    r = rank_actions(me, opp, my_bench=bench)
    top = r.actions[0]
    assert top.kind == "switch"
    assert "skarmory" in top.move
    assert "Changer pour skarmory" in r.recommendation


def test_switch_not_preferred_when_attacking_is_better():
    # Garchomp domine Tyranitar ; le switch défensif ne doit pas primer.
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32},
             moves=["earthquake"])
    opp = mon("tyranitar", "adamant", {"atk": 32}, moves=["crunch"])
    bench = [mon("amoonguss", "sassy", {"hp": 32, "spd": 32}, moves=["sludgebomb"])]
    r = rank_actions(me, opp, my_bench=bench)
    assert r.actions[0].kind == "move"
    assert r.actions[0].move == "Earthquake"


def test_deep_search_runs_and_prefers_winning_line():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32},
             moves=["earthquake", "swordsdance"])
    opp = mon("amoonguss", "sassy", {"hp": 32, "spd": 32},
              moves=["sludgebomb", "gigadrain"])
    r1 = rank_actions(me, opp, depth=1)
    r2 = rank_actions(me, opp, depth=2)
    # En profondeur, la valeur reflète l'issue (Garchomp gagne) -> plus haute.
    assert r2.actions[0].expected > r1.actions[0].expected
    assert r2.actions[0].expected <= 2.0


def test_depth_is_clamped():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32}, moves=["earthquake"])
    opp = mon("tyranitar", "adamant", {"atk": 32}, moves=["crunch"])
    # depth=99 est ramené dans [1,5] : ne doit pas exploser ni lever.
    r = rank_actions(me, opp, depth=99)
    assert r.actions


def test_worst_model_ranks_by_worst_case():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32},
             moves=["earthquake", "dragonclaw", "swordsdance"])
    opp = mon("dragapult", "timid", {"spa": 32, "spe": 32},
              moves=["dracometeor", "shadowball", "thunderbolt"])
    r = rank_actions(me, opp, depth=2, opp_model="worst")
    # En mode minimax, les actions sont triées par pire cas décroissant.
    worsts = [a.worst for a in r.actions]
    assert worsts == sorted(worsts, reverse=True)
    assert "pire cas" in r.recommendation


def test_worst_and_expected_may_differ_in_recommendation():
    # Setup risqué : bonne espérance en profondeur, mauvais pire cas.
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32},
             moves=["earthquake", "swordsdance"])
    opp = mon("tyranitar", "adamant", {"atk": 32}, moves=["crunch", "earthquake"])
    exp = rank_actions(me, opp, depth=2, opp_model="expected")
    wor = rank_actions(me, opp, depth=2, opp_model="worst")
    # Les deux modes produisent des classements valides (peuvent coïncider ou non).
    assert exp.actions and wor.actions
    assert all(a.worst <= a.expected for a in exp.actions)


def test_deep_ko_move_tops_when_lethal():
    me = mon("garchomp", "adamant", {"atk": 32}, item="choiceband",
             moves=["earthquake", "swordsdance"])
    opp = mon("tyranitar", "jolly", moves=["crunch"], hp=0.5)
    r = rank_actions(me, opp, depth=2, roll=1.0)
    assert r.actions[0].move == "Earthquake"
    assert r.actions[0].ko_chance is True


def test_sampled_search_determinizes_unknown_opponent():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32},
             moves=["earthquake", "dragonclaw", "stoneedge"])
    opp = mon("incineroar", "careful", {"hp": 32, "spd": 32})  # build inconnu
    r = rank_actions_sampled(me, opp, n_samples=6, seed=1)
    assert r.actions[0].move == "Earthquake"          # 2x sur Feu/Ténèbres
    assert "échantillonné" in r.opp_moves[0]


def test_sampled_search_reproducible_with_seed():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32}, moves=["earthquake"])
    opp = mon("incineroar", "careful")
    a = rank_actions_sampled(me, opp, n_samples=6, seed=42)
    b = rank_actions_sampled(me, opp, n_samples=6, seed=42)
    assert [round(x.expected, 6) for x in a.actions] == \
           [round(x.expected, 6) for x in b.actions]


def test_sampled_falls_back_when_opp_moves_known():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32}, moves=["earthquake"])
    opp = mon("incineroar", "careful", moves=["knockoff", "flareblitz"])
    r = rank_actions_sampled(me, opp, n_samples=6)
    # Coups connus -> pas d'échantillonnage, la distribution vient des coups.
    assert r.opp_moves == ["knockoff", "flareblitz"]


def test_sampled_falls_back_for_species_absent_from_usage():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32}, moves=["earthquake"])
    opp = mon("magikarp", "serious")                  # hors usage
    r = rank_actions_sampled(me, opp, n_samples=6)
    assert r.actions                                  # ne lève pas, reste utilisable


def test_safe_compromise_recommendation():
    # Face à une menace, une option qui ne se fait pas KO peut primer.
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32},
             moves=["earthquake", "dragonclaw"])
    opp = mon("dragapult", "timid", {"spa": 32, "spe": 32},
              moves=["dracometeor", "shadowball"])
    r = rank_actions(me, opp)
    assert r.actions                          # au moins classé sans erreur
    assert isinstance(r.recommendation, str)
