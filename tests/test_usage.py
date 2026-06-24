"""Tests du modèle d'usage (§0.2) et de son câblage dans B2."""

from __future__ import annotations

from simupoke.usage import (
    load_usage, usage_prior, likely_set, has_usage,
)
from simupoke.model import OwnedPokemon
from simupoke.draft import evaluate_candidate


def test_usage_file_present_and_loaded():
    assert has_usage("reg_m_b")
    table = load_usage("reg_m_b")
    assert "incineroar" in table


def test_prior_normalised_top_is_one():
    prior = usage_prior("reg_m_b")
    assert max(prior.values()) == 1.0
    # Incineroar est le plus joué dans l'échantillon.
    assert prior["incineroar"] == 1.0
    assert 0 < prior["tyranitar"] < 1


def test_prior_absent_regulation_empty():
    assert usage_prior("reg_inexistante") == {}


def test_likely_set_picks_argmax_and_topn():
    ls = likely_set("incineroar")
    assert ls.item == "assaultvest"      # poids max
    assert ls.ability == "intimidate"
    assert ls.nature == "careful"
    assert ls.moves[0] == "fakeout"      # plus probable en premier
    assert len(ls.moves) <= 4


def test_likely_set_name_insensitive():
    assert likely_set("Flutter Mane").item == "choicespecs"


def test_likely_set_unknown_species_empty():
    ls = likely_set("magikarp")
    assert ls.item is None and ls.moves == []


def test_usage_prior_influences_draft_score():
    cand = OwnedPokemon(species="incineroar", nature="careful", stat_points={})
    with_usage = evaluate_candidate(cand, usage_prior=usage_prior("reg_m_b"))
    without = evaluate_candidate(cand)
    # Incineroar a l'usage max -> sous-score « usage » plus élevé que le neutre 0.5.
    assert with_usage.subscores["usage"] > without.subscores["usage"]
    assert with_usage.total > without.total
