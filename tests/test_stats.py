"""Tests du modèle de stats figé (§8.3 — données Tyranocif vérifiées en jeu)."""

from __future__ import annotations

import pytest

from simupoke.basestats import get_base_stats
from simupoke.stats import (
    SP_CAP_PER_STAT,
    SP_TOTAL_BUDGET,
    Build,
    compute_all_stats,
    nature_multipliers,
    validate_sp,
)


def test_tyranitar_jolly_reference():
    """Cas de référence vérifié exact (4/4) en jeu le 23/06/2026."""
    ttar = Build(
        species="tyranitar",
        nature="jolly",
        sp={"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
    )
    got = ttar.final_stats()
    assert got["hp"] == 177
    assert got["atk"] == 186
    assert got["def"] == 130
    assert got["spe"] == 124


def test_total_sp_at_budget_is_legal():
    sp = {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}
    assert sum(sp.values()) == SP_TOTAL_BUDGET
    assert validate_sp(sp) == []


def test_over_budget_is_rejected():
    sp = {"hp": 33, "atk": 32, "def": 32}  # cap par stat + budget total dépassés
    problems = validate_sp(sp)
    assert problems  # non vide
    assert any("hors bornes" in p for p in problems)
    assert any("budget" in p for p in problems)


def test_per_stat_cap():
    assert validate_sp({"atk": SP_CAP_PER_STAT}) == []
    assert validate_sp({"atk": SP_CAP_PER_STAT + 1})


def test_nature_multipliers_jolly():
    mult = nature_multipliers("jolly")  # +spe / -spa
    assert mult["spe"] == pytest.approx(1.1)
    assert mult["spa"] == pytest.approx(0.9)
    assert mult["hp"] == pytest.approx(1.0)


def test_nature_never_affects_hp():
    base = get_base_stats("tyranitar")
    sp = {"hp": 4, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    neutral = compute_all_stats(base, sp, "serious")
    plus_def = compute_all_stats(base, sp, "bold")  # +def / -atk
    assert neutral["hp"] == plus_def["hp"]


def test_unknown_nature_raises():
    with pytest.raises(ValueError):
        nature_multipliers("nonexistent")
