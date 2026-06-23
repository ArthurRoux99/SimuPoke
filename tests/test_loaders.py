"""Tests du chargement des données (roster perso + régulation)."""

from __future__ import annotations

from simupoke.loaders import load_my_roster, load_regulation
from simupoke.model import OwnedPokemon


def test_load_my_roster_default():
    roster = load_my_roster()
    assert len(roster) >= 1
    assert all(isinstance(m, OwnedPokemon) for m in roster)
    ttar = next(m for m in roster if m.species == "tyranitar")
    assert ttar.nature == "jolly"
    assert ttar.final_stats()["atk"] == 186


def test_load_regulation_m_b():
    reg = load_regulation("reg_m_b")
    assert "roster" in reg
    assert "abilities" in reg
    assert "clauses" in reg
    assert reg["clauses"]["level"] == 50
    assert reg["clauses"]["formats"]["singles"]["bring"] == 3
    assert reg["clauses"]["formats"]["doubles"]["bring"] == 4


def test_owned_pokemon_validate_clean():
    mon = OwnedPokemon(
        species="tyranitar", nature="jolly",
        stat_points={"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
    )
    assert mon.validate() == []


def test_owned_pokemon_trial_requires_expiry():
    mon = OwnedPokemon(
        species="tyranitar", nature="jolly",
        stat_points={"atk": 32, "spe": 32},
        status_ownership="trial", trial_expires_in_days=None,
    )
    problems = mon.validate()
    assert any("trial" in p for p in problems)
