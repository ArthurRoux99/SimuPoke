"""Tests du module B2 (aide au tirage)."""

from __future__ import annotations

from simupoke.model import OwnedPokemon
from simupoke.loaders import load_lineup, load_my_roster
from simupoke.draft import (
    rank_lineup, evaluate_candidate, team_threats, DEFAULT_WEIGHTS,
    INVEST_THRESHOLD,
)


def _cand(species, **kw):
    return OwnedPokemon(species=species, nature=kw.pop("nature", "serious"),
                        stat_points=kw.pop("sp", {}), **kw)


def test_weights_sum_to_one():
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9


def test_sample_lineup_ranks_strong_over_weak():
    lineup = load_lineup("data/sample_lineup.json")
    ranked = rank_lineup(lineup, roster=load_my_roster())
    names = [e.species for e in ranked]
    # Magikarp (BST 200) doit être dernier ; un sweeper BST 600 devant Blissey.
    assert names[-1] == "magikarp"
    assert names.index("dragapult") < names.index("blissey")
    # Scores décroissants.
    totals = [e.total for e in ranked]
    assert totals == sorted(totals, reverse=True)


def test_unknown_species_scored_zero():
    e = evaluate_candidate(_cand("notapokemon"))
    assert e.total == 0.0
    assert "inconnue" in e.recommendation.lower()


def test_shiny_adds_collection_note_when_below_invest():
    e = evaluate_candidate(_cand("magikarp", is_shiny=True))
    assert e.total < INVEST_THRESHOLD
    assert "collection" in e.recommendation.lower()
    assert e.is_shiny


def test_team_threats_for_tyranitar_roster():
    roster = load_my_roster()              # Tyranitar seul
    threats = team_threats(roster)
    # Tyranitar est faible au Combat -> menace présente.
    assert "Fighting" in threats


def test_synergy_changes_with_roster():
    cand = _cand("garchomp", sp={"atk": 31}, moves=["earthquake"])
    with_roster = evaluate_candidate(cand, roster=load_my_roster())
    without = evaluate_candidate(cand, roster=[])
    # Sans roster, la synergie est neutre (0.5).
    assert without.subscores["synergy"] == 0.5
    assert with_roster.subscores["synergy"] != 0.5


def test_usage_prior_influences_score():
    cand = _cand("garchomp", sp={"atk": 31})
    low = evaluate_candidate(cand, usage_prior={"garchomp": 0.0})
    high = evaluate_candidate(cand, usage_prior={"garchomp": 1.0})
    assert high.total > low.total
