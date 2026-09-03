"""Tests des helpers d'analyse (typage défensif/offensif, rôles)."""

from __future__ import annotations

from simupoke.analysis import (
    STANDARD_TYPES,
    base_stat_total,
    coverage_count,
    defensive_profile,
    infer_role,
    offensive_types,
)


def test_standard_types_count():
    assert len(STANDARD_TYPES) == 18
    assert "Stellar" not in STANDARD_TYPES


def test_defensive_profile_tyranitar():
    p = defensive_profile("tyranitar")  # Rock/Dark
    # Faiblesse 4x au Combat (Roche x2 ... en fait Dark x2, Rock x0.5 -> 2x ; mais
    # Fighting: Rock x0.5? non, Fighting>Rock x2, Fighting>Dark x2 -> 4x).
    assert p.weaknesses.get("Fighting") == 4
    assert "Psychic" in p.immunities         # Dark immunise Psychic
    assert p.n_weak == 7


def test_defensive_profile_from_types():
    p = defensive_profile(["Water"])
    assert p.weaknesses.get("Grass") == 2
    assert p.weaknesses.get("Electric") == 2
    assert p.resistances.get("Fire") == 0.5


def test_offensive_types_from_moves():
    types = offensive_types("garchomp", ["earthquake", "fireblast", "swordsdance"])
    assert "Ground" in types and "Fire" in types
    assert "Normal" not in types             # Swords Dance (status) ignoré


def test_offensive_types_fallback_to_stab():
    # Build sans moves connus -> proxy = types de l'espèce.
    assert set(offensive_types("garchomp", [])) == {"Dragon", "Ground"}


def test_coverage_count_range():
    cov = coverage_count(["Ground", "Fire", "Ice"])
    assert 0 < cov <= 18


def test_infer_role_sweeper_vs_wall():
    assert infer_role("dragapult").role == "sweeper"     # rapide, offensif
    assert infer_role("blissey").role == "wall"          # gros PV, lent


def test_base_stat_total():
    assert base_stat_total("tyranitar") == 600


def test_defensive_profile_ability_immunity():
    # Rotom-Wash (Eau/Électrik) est faible au Sol par typage, mais Lévitation immunise.
    by_type = defensive_profile("rotomwash")
    assert by_type.takes("Ground") == 2.0
    assert "Ground" in by_type.weaknesses
    with_levitate = defensive_profile("rotomwash", "levitate")
    assert with_levitate.takes("Ground") == 0.0
    assert "Ground" in with_levitate.immunities
    assert "Ground" not in with_levitate.weaknesses


def test_defensive_profile_ability_none_unchanged():
    assert defensive_profile("garchomp").weaknesses == \
        defensive_profile("garchomp", "roughskin").weaknesses
