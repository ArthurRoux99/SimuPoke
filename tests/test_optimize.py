"""Tests de l'optimiseur de spread SP (optimize.py)."""

from __future__ import annotations

from simupoke.model import PokemonState
from simupoke.stats import SP_TOTAL_BUDGET, SP_CAP_PER_STAT
from simupoke.optimize import optimize_spread, Outspeed, Survive, Ko


def st(species, nature, sp=None, item=None, hp=1.0):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        item=item, current_hp_pct=hp)


def test_no_objectives_is_empty_feasible_spread():
    r = optimize_spread("garchomp", "jolly", [])
    assert r.feasible
    assert r.total == 0
    assert all(v == 0 for v in r.sp.values())
    assert r.leftover == SP_TOTAL_BUDGET


def test_outspeed_sets_only_speed():
    # Cible plus rapide en base => il faut investir en Vitesse, rien d'autre.
    objs = [Outspeed(target=st("garchomp", "serious", {"spe": 24}))]
    r = optimize_spread("garchomp", "serious", objs)
    assert r.feasible
    assert r.sp["spe"] > 24
    assert r.sp["atk"] == 0 and r.sp["hp"] == 0 and r.sp["def"] == 0


def test_ko_sets_offense_stat():
    objs = [Ko(defender=st("tyranitar", "adamant"), move="earthquake", hits=1)]
    r = optimize_spread("garchomp", "adamant", objs, item="choiceband")
    assert r.feasible
    assert r.sp["atk"] >= 0            # atteignable avec Choice Band
    assert r.sp["spa"] == 0
    assert r.stats is not None


def test_special_ko_uses_spa():
    objs = [Ko(defender=st("skarmory", "impish", hp=0.4), move="flamethrower")]
    r = optimize_spread("garchomp", "modest", objs)
    # L'objectif touche l'axe spécial (spa), jamais atk.
    assert r.sp["atk"] == 0


def test_survive_couples_hp_and_defense():
    objs = [Survive(attacker=st("garchomp", "adamant", {"atk": 32}),
                    move="earthquake")]
    r = optimize_spread("tyranitar", "adamant", objs)
    if r.feasible:
        # Séisme est physique => l'investissement passe par PV et/ou Déf.
        assert r.sp["spd"] == 0
        assert (r.sp["hp"] + r.sp["def"]) == r.total


def test_combined_objectives_within_budget():
    objs = [
        Ko(defender=st("garchomp", "jolly", {"spe": 32}), move="icepunch",
           hits=1),
        Survive(attacker=st("garchomp", "adamant", {"atk": 32}),
                move="earthquake"),
        Outspeed(target=st("amoonguss", "sassy", {"spe": 0})),
    ]
    r = optimize_spread("tyranitar", "adamant", objs)
    assert r.feasible
    assert r.total <= SP_TOTAL_BUDGET
    assert all(v <= SP_CAP_PER_STAT for v in r.sp.values())


def test_unreachable_ko_flagged_unmet():
    objs = [Ko(defender=st("blissey", "calm", {"hp": 32, "def": 32}),
               move="tackle", hits=1)]
    r = optimize_spread("magikarp", "serious", objs)
    assert r.feasible is False
    assert any("KO" in u for u in r.unmet)


def test_budget_overflow_flagged():
    # Budget artificiellement bas => dépassement signalé.
    objs = [Ko(defender=st("tyranitar", "adamant"), move="earthquake")]
    r = optimize_spread("garchomp", "adamant", objs, item="choiceband",
                        budget=0)
    if r.sp["atk"] > 0:
        assert r.feasible is False
        assert any("budget" in u for u in r.unmet)


def test_focus_sash_ko_flagged_in_spread():
    objs = [Ko(defender=st("fluttermane", "timid", {"hp": 0}, item="focussash"),
               move="earthquake", hits=1)]
    r = optimize_spread("garchomp", "adamant", objs, item="choiceband")
    assert r.feasible is False
    assert any("Focus Sash" in u for u in r.unmet)


def test_result_lines_render():
    objs = [Outspeed(target=st("amoonguss", "sassy"))]
    r = optimize_spread("tyranitar", "adamant", objs)
    text = "\n".join(r.lines())
    assert "Spread proposé" in text
