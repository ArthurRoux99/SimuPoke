"""Tests de B1 — assistant de combat (mode analyse, 1 tour)."""

from __future__ import annotations

from simupoke.model import PokemonState, FieldState
from simupoke.combat import analyze_turn, effective_speed, moves_first


def mk(species, nature="serious", sp=None, moves=None, item=None,
       status=None, hp=1.0, boosts=None):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        moves=moves or [], item=item, status=status,
                        current_hp_pct=hp, boosts=boosts or {})


def test_best_option_is_super_effective_move():
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32},
            ["earthquake", "dragonclaw", "stoneedge"])
    opp = mk("tyranitar", "adamant", {"atk": 32}, ["crunch"])
    a = analyze_turn(me, opp, opp_move="crunch")
    assert a.options[0].move == "Earthquake"     # 2x sur Tyranitar
    assert a.options[0].first is True            # Garchomp plus rapide


def test_guaranteed_ko_first_tops_ranking_and_is_safe():
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"],
            item="choiceband")
    opp = mk("tyranitar", "adamant", {"atk": 32}, ["crunch"], hp=0.6)
    a = analyze_turn(me, opp, opp_move="crunch")
    best = a.options[0]
    assert best.ko == "KO garanti"
    assert "premier" in a.recommendation
    assert any("tue avant" in n for n in best.notes)


def test_status_move_listed_not_ranked():
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32},
            ["earthquake", "swordsdance"])
    opp = mk("tyranitar", "adamant", {"atk": 32}, ["crunch"])
    a = analyze_turn(me, opp, opp_move="crunch")
    assert all(e.kind == "damage" for e in a.options)
    assert any(e.move == "Swords Dance" for e in a.other)


def test_speed_order_and_paralysis():
    fast = mk("garchomp", "jolly", {"spe": 32})
    slow = mk("snorlax", "brave", {})
    assert moves_first(fast, slow, "earthquake", "bodyslam", None) is True
    # Priorité l'emporte sur la vitesse.
    assert moves_first(slow, fast, "extremespeed", "earthquake", None) is True
    # Paralysie divise la vitesse par deux.
    par = mk("garchomp", "jolly", {"spe": 32}, status="par")
    assert effective_speed(par) < effective_speed(fast)


def test_trick_room_reverses_order():
    fast = mk("garchomp", "jolly", {"spe": 32})
    slow = mk("snorlax", "brave", {})
    field = FieldState(trick_room=True)
    # Sous Trick Room, le plus lent agit en premier.
    assert moves_first(slow, fast, "bodyslam", "earthquake", field) is True


def test_incoming_unknown_when_no_opp_moves():
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    opp = mk("tyranitar", "adamant", {"atk": 32}, [])
    a = analyze_turn(me, opp)
    assert a.incoming.known is False
