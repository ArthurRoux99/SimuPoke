"""Tests du modèle d'usage (§0.2) et de son câblage dans B2."""

from __future__ import annotations

import random

from simupoke.draft import evaluate_candidate
from simupoke.model import OwnedPokemon
from simupoke.usage import (
    has_usage,
    likely_set,
    load_usage,
    sample_set,
    usage_prior,
)

# Fixture contrôlée : teste la *logique* du modèle indépendamment des données
# réelles (qui sont remplacées par des imports d'usage successifs).
FIX = {
    "incineroar": {
        "usage": 0.40,
        "items": {"assaultvest": 0.5, "sitrusberry": 0.3},
        "abilities": {"intimidate": 1.0},
        "natures": {"careful": 0.6, "adamant": 0.4},
        "moves": {"fakeout": 0.95, "partingshot": 0.8, "flareblitz": 0.7,
                  "knockoff": 0.6, "darkestlariat": 0.3},
    },
    "tyranitar": {"usage": 0.20, "items": {"choiceband": 0.4},
                  "abilities": {"sandstream": 1.0}},
    "fluttermane": {"usage": 0.10, "items": {"choicespecs": 0.7}},
}


def test_sample_set_draws_from_distributions():
    rng = random.Random(0)
    ls = sample_set("incineroar", rng=rng, table=FIX)
    assert ls.item in FIX["incineroar"]["items"]
    assert ls.ability == "intimidate"
    assert ls.nature in FIX["incineroar"]["natures"]
    assert 1 <= len(ls.moves) <= 4
    assert all(m in FIX["incineroar"]["moves"] for m in ls.moves)
    assert len(set(ls.moves)) == len(ls.moves)          # sans doublon


def test_sample_set_reproducible_and_varies():
    a = sample_set("incineroar", rng=random.Random(1), table=FIX)
    b = sample_set("incineroar", rng=random.Random(1), table=FIX)
    assert (a.item, a.nature, a.moves) == (b.item, b.nature, b.moves)
    # Des graines différentes explorent des builds différents (au moins parfois).
    variants = {tuple(sample_set("incineroar", rng=random.Random(s), table=FIX).moves)
                for s in range(20)}
    assert len(variants) > 1


def test_sample_set_absent_species_is_empty():
    ls = sample_set("magikarp", rng=random.Random(0), table=FIX)
    assert ls.item is None and ls.moves == []


def test_usage_file_present_and_loaded():
    # Intégration : le fichier réel se charge et contient des espèces.
    assert has_usage("reg_m_b")
    table = load_usage("reg_m_b")
    assert "incineroar" in table


def test_prior_normalised_top_is_one():
    prior = usage_prior(table=FIX)
    assert max(prior.values()) == 1.0
    # Incineroar est le plus joué dans la fixture.
    assert prior["incineroar"] == 1.0
    assert 0 < prior["tyranitar"] < 1


def test_prior_absent_regulation_empty():
    assert usage_prior("reg_inexistante") == {}


def test_likely_set_picks_argmax_and_topn():
    ls = likely_set("incineroar", table=FIX)
    assert ls.item == "assaultvest"      # poids max
    assert ls.ability == "intimidate"
    assert ls.nature == "careful"
    assert ls.moves[0] == "fakeout"      # plus probable en premier
    assert len(ls.moves) <= 4


def test_likely_set_name_insensitive():
    assert likely_set("Flutter Mane", table=FIX).item == "choicespecs"


def test_likely_set_unknown_species_empty():
    ls = likely_set("magikarp", table=FIX)
    assert ls.item is None and ls.moves == []


def test_usage_prior_influences_draft_score():
    prior = usage_prior(table=FIX)
    cand = OwnedPokemon(species="incineroar", nature="careful", stat_points={})
    with_usage = evaluate_candidate(cand, usage_prior=prior)
    without = evaluate_candidate(cand)
    # Incineroar a l'usage max -> sous-score « usage » plus élevé que le neutre 0.5.
    assert with_usage.subscores["usage"] > without.subscores["usage"]
    assert with_usage.total > without.total


def test_real_usage_model_smoke():
    # Le vrai fichier importé doit produire un set probable plausible.
    ls = likely_set("garchomp", reg_id="reg_m_b")
    assert ls.ability == "roughskin"
    assert "earthquake" in ls.moves
