"""Tests de parité du calculateur de dégâts contre @smogon/calc.

Les valeurs de référence (min/max sur les 16 rolls) ont été générées avec
@smogon/calc (gen 9, niveau 50) par `scripts/calc_reference.mjs`. Les EVs de
référence sont des multiples de 8 (≤ 248), donc SP = EV/8 produit des stats
strictement identiques (cf. modèle figé §8.3).
"""

from __future__ import annotations

import pytest

from simupoke.model import PokemonState, FieldState
from simupoke.damage import calculate, poke_round


def mk(species, nature="serious", sp=None, item=None, ability=None,
       boosts=None, status=None, hp=1.0):
    return PokemonState(
        species=species, nature=nature, item=item, ability=ability,
        stat_points=sp or {}, boosts=boosts or {}, status=status,
        current_hp_pct=hp,
    )


# species/natures fréquents
TTAR = lambda **kw: mk("tyranitar", "jolly", {}, **kw)          # noqa: E731
CHOMP_AD = lambda **kw: mk("garchomp", "adamant", {"atk": 31}, **kw)   # noqa: E731
CHOMP_SP = lambda **kw: mk("garchomp", "modest", {"spa": 31}, **kw)    # noqa: E731


# (nom, attaquant, défenseur, move, kwargs calculate, min, max)
CASES = [
    ("eq_stab_se",        CHOMP_AD(), TTAR(), "earthquake", {}, 174, 206),
    ("crunch_stab_neutral", mk("tyranitar", "adamant", {"atk": 31}),
     mk("garchomp", "jolly"), "crunch", {}, 81, 96),
    ("flareblitz_resisted", mk("incineroar", "adamant", {"atk": 31}),
     TTAR(), "flareblitz", {}, 47, 56),
    ("fireblast_special",  CHOMP_SP(), TTAR(), "fireblast", {}, 25, 30),
    ("eq_crit",            CHOMP_AD(), TTAR(), "earthquake", {"crit": True}, 260, 308),
    ("eq_burned",          CHOMP_AD(status="brn"), TTAR(), "earthquake", {}, 87, 103),
    ("waterfall_rain",     CHOMP_AD(), TTAR(), "waterfall",
     {"field": FieldState(weather="rain")}, 138, 164),
    ("eq_band",            CHOMP_AD(item="choiceband"), TTAR(), "earthquake", {}, 258, 306),
    ("fireblast_lo",       CHOMP_SP(item="lifeorb"), TTAR(), "fireblast", {}, 32, 39),
    ("eq_plus2",           CHOMP_AD(boosts={"atk": 2}), TTAR(), "earthquake", {}, 344, 408),
    ("fireblast_av",       CHOMP_SP(),
     mk("tyranitar", "careful", {}, item="assaultvest"), "fireblast", {}, 15, 18),
    ("eq_spread",          CHOMP_AD(), TTAR(), "earthquake", {"apply_spread": True}, 132, 156),
    ("thickfat_fireblast", CHOMP_SP(),
     mk("snorlax", "careful", {}, ability="thickfat"), "fireblast", {}, 22, 26),
    ("thickfat_ice",       mk("mamoswine", "adamant", {"atk": 31}),
     mk("snorlax", "impish", {}, ability="thickfat"), "iciclecrash", {}, 51, 61),
    ("levitate_eq",        CHOMP_AD(),
     mk("rotomwash", "serious", {}, ability="levitate"), "earthquake", {}, 0, 0),
    ("flashfire",          CHOMP_SP(),
     mk("heatran", "serious", {}, ability="flashfire"), "fireblast", {}, 0, 0),
]


@pytest.mark.parametrize("name,atk,dfn,move,kw,exp_min,exp_max",
                         CASES, ids=[c[0] for c in CASES])
def test_parity_with_smogon_calc(name, atk, dfn, move, kw, exp_min, exp_max):
    r = calculate(atk, dfn, move, **kw)
    assert (r.min_damage, r.max_damage) == (exp_min, exp_max), (
        f"{name}: obtenu {r.min_damage}-{r.max_damage}, attendu {exp_min}-{exp_max}"
    )
    assert len(r.rolls) == 16
    assert r.rolls == sorted(r.rolls)


def test_poke_round_ties_go_down():
    assert poke_round(2.5) == 2
    assert poke_round(2.51) == 3
    assert poke_round(2.49) == 2
    assert poke_round(3.0) == 3


def test_immunity_is_zero():
    # Terre sur un type Vol (Tornadus est Vol pur) -> 0.
    r = calculate(CHOMP_AD(), mk("tornadus"), "earthquake")
    assert r.max_damage == 0
    assert r.type_effectiveness == 0
    assert r.guaranteed_ko_hits is None


def test_status_move_rejected():
    with pytest.raises(ValueError):
        calculate(CHOMP_AD(), TTAR(), "swordsdance")


def test_ko_hits_and_percentages():
    r = calculate(CHOMP_AD(), TTAR(), "earthquake")  # 174-206 sur 175 PV
    assert r.defender_max_hp == 175
    assert r.possible_ko_hits == 1          # le roll max (206) tue d'un coup
    # le roll min (174) ne tue pas tout à fait : garanti en ceil(175/174) = 2
    assert r.guaranteed_ko_hits == 2
    assert 99 < r.max_pct <= 118


def test_describe_runs():
    r = calculate(CHOMP_AD(), TTAR(), "earthquake")
    txt = r.describe()
    assert "Earthquake" in txt and "%" in txt
