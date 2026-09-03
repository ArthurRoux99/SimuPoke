"""Tests du simulateur de tour Doubles (sim_doubles.py)."""

from __future__ import annotations

from simupoke.model import FieldState, PokemonState
from simupoke.sim import Mon
from simupoke.sim_doubles import (
    DoublesSide,
    action_order_doubles,
    simulate_turn_doubles,
)


def st(species, nature="serious", sp=None, item=None, ability=None,
       moves=None, hp=1.0, status=None):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        item=item, ability=ability, moves=moves or [],
                        current_hp_pct=hp, status=status)


def mon(*a, **k):
    return Mon.from_state(st(*a, **k))


def side(*mons, **kw):
    return DoublesSide(active=list(mons), **kw)


def mv(move_id, target=None):
    return ("move", move_id, target)


PASS = ("pass", None, None)


# --- Ordre d'action ---------------------------------------------------------

def test_order_sorts_four_actors_by_speed():
    me = side(mon("garchomp", "jolly", {"spe": 32}), mon("snorlax", "brave"))
    opp = side(mon("dragapult", "timid", {"spe": 32}), mon("torkoal", "quiet"))
    order = action_order_doubles(me, opp, (mv("earthquake"), mv("bodyslam")),
                                 (mv("dragondarts"), mv("eruption")), None)
    assert order[0] == ("opp", 0)          # Dragapult, le plus rapide
    assert order[-1] in (("me", 1), ("opp", 1))   # les deux lents ferment


def test_order_priority_beats_speed():
    me = side(mon("snorlax", "brave"), mon("snorlax", "brave"))
    opp = side(mon("dragapult", "timid", {"spe": 32}), mon("torkoal", "quiet"))
    order = action_order_doubles(me, opp, (mv("protect"), PASS),
                                 (mv("dragondarts"), PASS), None)
    assert order[0] == ("me", 0)           # Protect, priorité +4


def test_order_trick_room_reverses():
    # Quatre vitesses distinctes : Dragapult > Garchomp > Snorlax > Torkoal.
    me = side(mon("garchomp", "jolly", {"spe": 32}), mon("snorlax", "brave"))
    opp = side(mon("dragapult", "timid", {"spe": 32}), mon("torkoal", "quiet"))
    actions = ((mv("dragonclaw"), mv("bodyslam")),
               (mv("dragondarts"), mv("eruption")))
    normal = action_order_doubles(me, opp, *actions, None)
    reversed_ = action_order_doubles(me, opp, *actions, FieldState(trick_room=True))
    assert normal == [("opp", 0), ("me", 0), ("me", 1), ("opp", 1)]
    assert reversed_ == list(reversed(normal))   # Trick Room inverse l'ordre


def test_order_tailwind_doubles_speed():
    me = side(mon("snorlax", "brave"), mon("snorlax", "brave"), tailwind=3)
    opp = side(mon("snorlax", "brave"), mon("snorlax", "brave"))
    order = action_order_doubles(me, opp, (mv("bodyslam"), PASS),
                                 (mv("bodyslam"), PASS), None)
    assert order[0] == ("me", 0)


def test_order_is_stable_on_speed_tie():
    me = side(mon("snorlax", "brave"), mon("snorlax", "brave"))
    opp = side(mon("snorlax", "brave"), mon("snorlax", "brave"))
    order = action_order_doubles(me, opp, (mv("bodyslam"), mv("bodyslam")),
                                 (mv("bodyslam"), mv("bodyslam")), None)
    assert order == [("me", 0), ("me", 1), ("opp", 0), ("opp", 1)]


# --- Résolution du tour -----------------------------------------------------

def test_single_target_hits_the_named_slot():
    # Griffe Dragon est mono-cible (`normal`) : la cible nommée est respectée.
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (mv("dragonclaw", ("foe", 1)), PASS),
                                (PASS, PASS), None)
    assert res.opp.active[1].hp < res.opp.active[1].max_hp   # le slot 1 encaisse
    assert res.opp.active[0].hp == res.opp.active[0].max_hp  # le slot 0 est intact


def test_default_target_is_first_living_foe():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"]),
              mon("snorlax", "brave"))
    opp = side(mon("torkoal", "quiet"), mon("tyranitar", "jolly"))
    res = simulate_turn_doubles(me, opp, (mv("dragonclaw"), PASS),
                                (PASS, PASS), None)
    assert res.opp.active[0].hp < res.opp.active[0].max_hp


def test_fainted_target_wastes_the_move():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"]),
              mon("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"]))
    opp = side(mon("torkoal", "quiet", hp=0.02), mon("tyranitar", "jolly"))
    # Les deux visent le slot 0 ; le premier le met K.O., le second perd son coup.
    res = simulate_turn_doubles(
        me, opp, (mv("dragonclaw", ("foe", 0)), mv("dragonclaw", ("foe", 0))),
        (PASS, PASS), None)
    assert res.opp.active[0].fainted
    assert res.opp.active[1].hp == res.opp.active[1].max_hp
    assert any("coup perdu" in line for line in res.log)


def test_switch_resolves_before_moves():
    me = side(mon("garchomp", "jolly", {"spe": 32}, moves=["dragonclaw"]),
              mon("snorlax", "brave"),
              bench=[mon("tyranitar", "jolly", moves=["crunch"])])
    opp = side(mon("torkoal", "quiet", moves=["eruption"]), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (("switch", 0, None), PASS),
                                (PASS, PASS), None)
    assert res.me.active[0].build.species == "tyranitar"


def test_end_of_turn_applies_to_all_four():
    me = side(mon("garchomp", "jolly", item="leftovers", hp=0.5),
              mon("snorlax", "brave", item="leftovers", hp=0.5))
    opp = side(mon("tyranitar", "jolly", item="leftovers", hp=0.5),
               mon("torkoal", "quiet", item="leftovers", hp=0.5))
    res = simulate_turn_doubles(me, opp, (PASS, PASS), (PASS, PASS), None)
    for camp in (res.me, res.opp):
        for m in camp.active:
            assert m.hp > m.max_hp // 2      # Vestiges ont soigné les quatre


# --- Coups de zone ----------------------------------------------------------

def test_spread_penalty_only_with_two_targets():
    def damage_to_slot0(second_foe_alive):
        me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["rockslide"]),
                  mon("snorlax", "brave"))
        opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
        if not second_foe_alive:
            opp.active[1].hp = 0
        res = simulate_turn_doubles(me, opp, (mv("rockslide"), PASS),
                                    (PASS, PASS), None)
        return res.opp.active[0].max_hp - res.opp.active[0].hp

    deux_cibles = damage_to_slot0(True)
    une_cible = damage_to_slot0(False)
    assert une_cible > deux_cibles, "pas de pénalité ×0.75 sur une cible unique"


def test_all_adjacent_move_hits_the_ally():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["earthquake"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (mv("earthquake"), PASS),
                                (PASS, PASS), None)
    assert res.me.active[1].hp < res.me.active[1].max_hp, "Séisme touche l'allié"


def test_foe_spread_move_spares_the_ally():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["rockslide"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (mv("rockslide"), PASS),
                                (PASS, PASS), None)
    assert res.me.active[1].hp == res.me.active[1].max_hp


# --- Protect / Wide Guard ---------------------------------------------------

def test_protect_blocks_a_single_target_move():
    me = side(mon("garchomp", "jolly", {"spe": 32}, moves=["dragonclaw"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly", moves=["protect"]), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (mv("dragonclaw", ("foe", 0)), PASS),
                                (mv("protect"), PASS), None)
    assert res.opp.active[0].hp == res.opp.active[0].max_hp


def test_wide_guard_blocks_spread_but_not_single_target():
    def run(attack):
        me = side(mon("garchomp", "adamant", {"atk": 31}, moves=[attack]),
                  mon("snorlax", "brave"))
        opp = side(mon("tyranitar", "jolly", moves=["wideguard"]),
                   mon("torkoal", "quiet"))
        return simulate_turn_doubles(me, opp, (mv(attack), PASS),
                                     (mv("wideguard"), PASS), None)

    zone = run("rockslide")
    assert zone.opp.active[1].hp == zone.opp.active[1].max_hp, "zone bloquée"
    mono = run("dragonclaw")
    assert mono.opp.active[0].hp < mono.opp.active[0].max_hp, "mono-cible passe"


def test_wide_guard_does_not_carry_to_the_next_turn():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["rockslide"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly", moves=["wideguard"]), mon("torkoal", "quiet"))
    # Tour 1 : l'adversaire pose Wide Guard, je ne fais rien.
    t1 = simulate_turn_doubles(me, opp, (PASS, PASS), (mv("wideguard"), PASS), None)
    # Tour 2 : il ne le repose pas — la zone doit passer.
    t2 = simulate_turn_doubles(t1.me, t1.opp, (mv("rockslide"), PASS),
                               (PASS, PASS), None)
    assert t2.opp.active[0].hp < t2.opp.active[0].max_hp
    assert t2.opp.wide_guard is False


# --- Redirection ------------------------------------------------------------

def test_follow_me_redirects_a_single_target_move():
    # Redirecteur non immunisé au coup testé (Clefairy, Fée, serait immune au Dragon).
    me = side(mon("garchomp", "jolly", {"spe": 32}, moves=["dragonclaw"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"),
               mon("incineroar", "careful", moves=["followme"]))
    res = simulate_turn_doubles(me, opp, (mv("dragonclaw", ("foe", 0)), PASS),
                                (PASS, mv("followme")), None)
    assert res.opp.active[1].hp < res.opp.active[1].max_hp, "le redirecteur encaisse"
    assert res.opp.active[0].hp == res.opp.active[0].max_hp


def test_follow_me_does_not_redirect_a_spread_move():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["rockslide"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"),
               mon("incineroar", "careful", moves=["followme"]))
    res = simulate_turn_doubles(me, opp, (mv("rockslide"), PASS),
                                (PASS, mv("followme")), None)
    assert res.opp.active[0].hp < res.opp.active[0].max_hp, "les deux sont touchés"


def test_rage_powder_has_no_effect_on_grass_type():
    me = side(mon("venusaur", "modest", {"spa": 31}, moves=["sludgebomb"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"),
               mon("amoonguss", "bold", moves=["ragepowder"]))
    res = simulate_turn_doubles(me, opp, (mv("sludgebomb", ("foe", 0)), PASS),
                                (PASS, mv("ragepowder")), None)
    assert res.opp.active[0].hp < res.opp.active[0].max_hp, "le Plante ignore la poudre"


def test_rage_powder_redirects_a_non_grass_attacker():
    me = side(mon("garchomp", "jolly", {"spe": 32}, moves=["dragonclaw"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"),
               mon("amoonguss", "bold", moves=["ragepowder"]))
    res = simulate_turn_doubles(me, opp, (mv("dragonclaw", ("foe", 0)), PASS),
                                (PASS, mv("ragepowder")), None)
    assert res.opp.active[1].hp < res.opp.active[1].max_hp


def test_lightning_rod_redirects_and_boosts():
    me = side(mon("raichu", "modest", {"spa": 31}, moves=["thunderbolt"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"),
               mon("rotomwash", "bold", ability="lightningrod"))
    res = simulate_turn_doubles(me, opp, (mv("thunderbolt", ("foe", 0)), PASS),
                                (PASS, PASS), None)
    assert res.opp.active[0].hp == res.opp.active[0].max_hp
    assert res.opp.active[1].hp == res.opp.active[1].max_hp, "immunisé"
    assert res.opp.active[1].boosts.get("spa") == 1
