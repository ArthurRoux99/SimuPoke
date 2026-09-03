"""Tests du simulateur de tour Doubles (sim_doubles.py)."""

from __future__ import annotations

from simupoke.model import FieldState, PokemonState
from simupoke.sim import Mon
from simupoke.sim_doubles import DoublesSide, action_order_doubles


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
