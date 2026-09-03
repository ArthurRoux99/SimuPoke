"""Tests du delta Champions (§7.2) branché sur le calc.

Les talents Champions-originaux (Dragonize, Mega Sol) n'existent pas dans
@smogon/calc ; on teste donc le *mécanisme* (changement de type + boost,
soleil personnel), la famille -ate générique étant déjà validée à l'identique
contre @smogon/calc dans test_damage.py (Pixilate).
"""

from __future__ import annotations

from simupoke.damage import calculate
from simupoke.delta import ate_type_map, personal_weather_for, type_change_for
from simupoke.model import PokemonState


def mk(species, nature="serious", sp=None, ability=None):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        ability=ability)


def test_dragonize_loaded_from_regulation_data():
    # Dragonize est défini dans data/reg_m_b/abilities.json (catégorie B).
    assert type_change_for("dragonize") == "Dragon"
    # La famille intégrée est présente aussi.
    assert ate_type_map()["pixilate"] == "Fairy"


def test_dragonize_changes_move_type_and_boosts():
    # Double-Edge (Normal) devient Dragon -> super efficace sur Garchomp (Dragon).
    drag = calculate(mk("feraligatr", "adamant", {"atk": 31}, "dragonize"),
                     mk("garchomp", "jolly"), "doubleedge")
    plain = calculate(mk("feraligatr", "adamant", {"atk": 31}, "torrent"),
                      mk("garchomp", "jolly"), "doubleedge")
    assert drag.type_effectiveness == 2.0
    assert plain.type_effectiveness == 1.0
    assert drag.max_damage > plain.max_damage


def test_ate_only_affects_normal_moves():
    # Un move non-Normal n'est pas transformé par un -ate.
    r = calculate(mk("sylveon", "modest", {"spa": 31}, "pixilate"),
                  mk("garchomp", "jolly"), "shadowball")
    assert r.type_effectiveness == 1.0      # Spectre vs Dragon/Sol = neutre


def test_mega_sol_personal_sun_boosts_fire():
    assert personal_weather_for("megasol") == "sun"
    sun = calculate(mk("meganium", "modest", {"spa": 31}, "megasol"),
                    mk("garchomp", "jolly"), "flamethrower")
    plain = calculate(mk("meganium", "modest", {"spa": 31}, "overgrow"),
                      mk("garchomp", "jolly"), "flamethrower")
    assert sun.max_damage > plain.max_damage      # ~1.5x


def test_no_ability_no_change():
    assert type_change_for(None) is None
    assert type_change_for("intimidate") is None
    assert personal_weather_for("overgrow") is None
