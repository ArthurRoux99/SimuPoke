"""Tests de la croyance sur le set adverse et de sa mise à jour inter-tours."""

from __future__ import annotations

from simupoke.belief import Particle, update_belief
from simupoke.model import PokemonState


def _part(moves, weight, item=None):
    return Particle(build=PokemonState(species="tyranitar", nature="adamant",
                                       moves=list(moves), item=item),
                    weight=weight)


def _weights(parts):
    return [round(p.weight, 6) for p in parts]


# --- Cas triviaux ----------------------------------------------------------

def test_update_none_returns_unchanged():
    # Aucun coup observé (l'adversaire a changé) : la croyance ne bouge pas.
    prior = [_part(["crunch", "rockslide"], 0.6), _part(["crunch", "icepunch"], 0.4)]
    post = update_belief(prior, None)
    assert _weights(post) == [0.6, 0.4]


def test_update_empty_belief():
    assert update_belief([], "crunch") == []


def test_posterior_is_normalized():
    prior = [_part(["crunch", "rockslide"], 0.5), _part(["crunch", "icepunch"], 0.5)]
    post = update_belief(prior, "rockslide")
    assert abs(sum(p.weight for p in post) - 1.0) < 1e-9


# --- Preuve dure : le coup révèle le monde ---------------------------------

def test_hard_evidence_eliminates_worlds_without_the_move():
    # Deux mondes équiprobables ; un seul possède Rock Slide. L'observer doit
    # écraser l'autre au plancher.
    prior = [_part(["crunch", "rockslide"], 0.5), _part(["crunch", "icepunch"], 0.5)]
    post = update_belief(prior, "rockslide", floor=0.02)
    with_rs = next(p for p in post if "rockslide" in p.build.moves)
    without = next(p for p in post if "rockslide" not in p.build.moves)
    assert with_rs.weight > 0.9
    assert without.weight < 0.1


def test_observed_move_in_all_worlds_keeps_prior_ratio():
    # Crunch est dans les deux mondes : sans stratégie, vraisemblance uniforme
    # 1/|coups| = 1/2 partout → le ratio a priori est conservé.
    prior = [_part(["crunch", "rockslide"], 0.7), _part(["crunch", "icepunch"], 0.3)]
    post = update_belief(prior, "crunch")
    a = next(p for p in post if "rockslide" in p.build.moves)
    assert abs(a.weight - 0.7) < 1e-9


# --- Vraisemblance stratégique (Nash par monde) ----------------------------

def test_strategic_likelihood_upweights_world_that_plays_the_move():
    # Deux mondes possèdent Protect ; le monde 0 le joue à 80 %, le monde 1 à
    # 10 %. Observer Protect doit remonter le monde 0.
    prior = [_part(["crunch", "protect"], 0.5), _part(["rockslide", "protect"], 0.5)]
    ws = [{"crunch": 0.2, "protect": 0.8}, {"rockslide": 0.9, "protect": 0.1}]
    post = update_belief(prior, "protect", world_strategies=ws)
    w0 = next(p for p in post if "crunch" in p.build.moves)
    w1 = next(p for p in post if "rockslide" in p.build.moves)
    assert w0.weight > w1.weight
    assert abs(w0.weight - 0.8 / 0.9) < 1e-6      # 0.5*0.8 / (0.5*0.8 + 0.5*0.1)


def test_strategic_zero_prob_is_floored_not_eliminated():
    # Le coup est dans le set mais la stratégie de Nash lui donne 0 % : on ne
    # l'élimine pas totalement (plancher), car l'adversaire l'a bel et bien joué.
    prior = [_part(["crunch", "protect"], 0.5), _part(["rockslide", "protect"], 0.5)]
    ws = [{"crunch": 1.0, "protect": 0.0}, {"rockslide": 0.5, "protect": 0.5}]
    post = update_belief(prior, "protect", world_strategies=ws, floor=0.02)
    w0 = next(p for p in post if "crunch" in p.build.moves)
    assert w0.weight > 0.0                         # pas éliminé
    assert w0.weight < 0.1                          # mais fortement réduit


# --- Contradiction → synthèse ---------------------------------------------

def test_contradiction_synthesizes_the_move_into_belief():
    # Le coup observé n'est dans aucun monde (croyance prise en défaut) : on
    # l'injecte partout plutôt que d'effondrer la croyance sur le plancher.
    prior = [_part(["crunch", "rockslide"], 0.6), _part(["crunch", "icepunch"], 0.4)]
    post = update_belief(prior, "earthquake")
    assert all("earthquake" in p.build.moves for p in post)
    assert abs(sum(p.weight for p in post) - 1.0) < 1e-9
    # Les poids a priori sont conservés (renormalisés).
    assert abs(_weights(post)[0] - 0.6) < 1e-9


def test_synthesis_replaces_when_set_full():
    # Set déjà plein (4 coups) : la synthèse remplace un coup, sans dépasser 4.
    prior = [_part(["crunch", "rockslide", "icepunch", "lowkick"], 1.0)]
    post = update_belief(prior, "earthquake")
    assert "earthquake" in post[0].build.moves
    assert len(post[0].build.moves) == 4
