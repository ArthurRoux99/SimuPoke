"""Tests de la croyance sur le set adverse et de sa mise à jour inter-tours."""

from __future__ import annotations

from simupoke.belief import (
    Particle,
    update_belief,
    update_belief_damage,
    update_belief_speed,
)
from simupoke.bench import compute_speed
from simupoke.damage import calculate
from simupoke.model import PokemonState


def _part(moves, weight, item=None):
    return Particle(build=PokemonState(species="tyranitar", nature="adamant",
                                       moves=list(moves), item=item),
                    weight=weight)


def _spart(weight, *, nature="adamant", item=None, sp=None, status=None):
    return Particle(build=PokemonState(species="tyranitar", nature=nature,
                                       stat_points=sp or {}, item=item,
                                       status=status, moves=["crunch"]),
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


# --- Mise à jour sur l'ordre d'action (scouting de vitesse) ----------------

def test_speed_update_favors_scarf_world_when_outsped():
    # Deux mondes : sans objet vs Choice Scarf (×1.5). Si l'adversaire me
    # dépasse alors que ma vitesse égale la sienne sans Scarf, le monde Scarf
    # devient nettement plus probable.
    slow = _spart(0.5)                                   # tyranitar adamant, no item
    scarf = _spart(0.5, item="choicescarf")
    # Ma vitesse : au-dessus de la base, en-dessous du Scarf (×1.5).
    me_speed = compute_speed(slow.build) + 1
    assert compute_speed(scarf.build) > me_speed
    post = update_belief_speed([slow, scarf], opp_faster=True, me_speed=me_speed)
    w_scarf = next(p for p in post if p.build.item == "choicescarf")
    w_slow = next(p for p in post if p.build.item is None)
    assert w_scarf.weight > 0.9                           # seul le Scarf me dépasse
    assert w_slow.weight < 0.1                            # base plus lente → incohérent


def test_speed_update_slower_observation_eliminates_scarf():
    # Si l'adversaire agit APRÈS moi alors que je suis à sa vitesse de base,
    # le monde Scarf (plus rapide) devient incohérent.
    slow = _spart(0.5)
    scarf = _spart(0.5, item="choicescarf")
    me_speed = compute_speed(slow.build) + 1             # je suis un poil plus rapide que la base
    post = update_belief_speed([slow, scarf], opp_faster=False, me_speed=me_speed)
    w_scarf = next(p for p in post if p.build.item == "choicescarf")
    assert w_scarf.weight < 0.1                           # Scarf l'aurait rendu plus rapide


def test_speed_tie_is_consistent_with_both_orders():
    # Vitesse exactement égale : cohérent quel que soit l'ordre observé.
    a = _spart(0.5)
    b = _spart(0.5)
    me_speed = compute_speed(a.build)
    for faster in (True, False):
        post = update_belief_speed([a, b], opp_faster=faster, me_speed=me_speed)
        assert abs(post[0].weight - 0.5) < 1e-9


def test_speed_update_trick_room_inverts_order():
    # En Trick Room, le plus LENT agit d'abord : « l'adversaire agit avant moi »
    # favorise le monde le plus lent, pas le plus rapide.
    slow = _spart(0.5)
    fast = _spart(0.5, nature="jolly")                   # +Vitesse
    me_speed = compute_speed(slow.build) + 1
    post = update_belief_speed([slow, fast], opp_faster=True, me_speed=me_speed,
                               trick_room=True)
    w_slow = next(p for p in post if p.build.nature == "adamant")
    assert w_slow.weight > 0.9                            # sous TR, le lent passe devant


# --- Mise à jour sur les dégâts observés -----------------------------------

def _dpart(weight, *, nature="adamant", item=None):
    return Particle(build=PokemonState(species="tyranitar", nature=nature,
                                       item=item, moves=["crunch"]),
                    weight=weight)


def test_damage_update_reveals_assault_vest():
    # J'attaque Tyranitar au spécial. Deux mondes : nu vs Assault Vest (SpD ×1.5).
    # Observer ~71 % (dans l'intervalle AV, bien sous le monde nu) révèle l'AV.
    atk = PokemonState(species="ironvaliant", nature="modest",
                       stat_points={"spa": 32}, moves=["moonblast"])
    plain = _dpart(0.5)
    av = _dpart(0.5, item="assaultvest")
    r_av = calculate(atk, av.build, "moonblast")
    observed = (r_av.min_pct + r_av.max_pct) / 200.0     # fraction, milieu AV
    post = update_belief_damage([plain, av], atk, "moonblast", observed,
                                opp_role="defender")
    w_av = next(p for p in post if p.build.item == "assaultvest")
    w_plain = next(p for p in post if p.build.item is None)
    assert w_av.weight > 0.9                              # dégâts faibles → AV
    assert w_plain.weight < 0.1


def test_damage_update_attacker_role_reveals_choice_band():
    # L'adversaire ME frappe. Deux mondes : nu vs Choice Band (Atq ×1.5).
    # Observer les gros dégâts (milieu CB) révèle le Band.
    me = PokemonState(species="garchomp", nature="jolly", moves=["earthquake"])
    plain = Particle(build=PokemonState(species="tyranitar", nature="adamant",
                                        stat_points={"atk": 32}, moves=["crunch"]),
                     weight=0.5)
    band = Particle(build=PokemonState(species="tyranitar", nature="adamant",
                                       stat_points={"atk": 32}, item="choiceband",
                                       moves=["crunch"]), weight=0.5)
    r_band = calculate(band.build, me, "crunch")
    observed = (r_band.min_pct + r_band.max_pct) / 200.0
    post = update_belief_damage([plain, band], me, "crunch", observed,
                                opp_role="attacker")
    w_band = next(p for p in post if p.build.item == "choiceband")
    assert w_band.weight > 0.9                            # gros dégâts → Band


def test_damage_update_non_damaging_move_is_left_unchanged():
    # Coup sans dégâts direct (statut / puissance variable non évaluable) : la
    # croyance ne bouge pas (vraisemblance 1 partout).
    atk = PokemonState(species="garchomp", nature="jolly", moves=["swordsdance"])
    a = _dpart(0.6)
    b = _dpart(0.4)
    post = update_belief_damage([a, b], atk, "swordsdance", 0.3,
                                opp_role="defender")
    assert abs(post[0].weight - 0.6) < 1e-9
    assert abs(post[1].weight - 0.4) < 1e-9
