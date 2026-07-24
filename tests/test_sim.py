"""Tests du simulateur de tour (sim.py)."""

from __future__ import annotations

from simupoke.model import PokemonState, FieldState
from simupoke.sim import Mon, simulate_turn, rollout, action_order


def st(species, nature="serious", sp=None, item=None, ability=None,
       moves=None, hp=1.0, status=None):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        item=item, ability=ability, moves=moves or [],
                        current_hp_pct=hp, status=status)


def mon(*a, **k):
    return Mon.from_state(st(*a, **k))


# --- Ordre d'action ---------------------------------------------------------

def test_faster_mon_acts_first():
    fast = mon("garchomp", "jolly", {"spe": 32})
    slow = mon("snorlax", "brave")
    assert action_order(fast, slow, "earthquake", "bodyslam", None)[0] == "me"


def test_priority_beats_speed():
    slow = mon("snorlax", "brave")
    fast = mon("garchomp", "jolly", {"spe": 32})
    # Slow mon avec priorité (me) agit avant.
    assert action_order(slow, fast, "extremespeed", "earthquake", None)[0] == "me"


def test_trick_room_reverses():
    fast = mon("garchomp", "jolly", {"spe": 32})
    slow = mon("snorlax", "brave")
    field = FieldState(trick_room=True)
    assert action_order(fast, slow, "earthquake", "bodyslam", field)[0] == "opp"


# --- Dégâts & KO ------------------------------------------------------------

def test_ko_removes_hp_and_flags():
    me = mon("garchomp", "adamant", {"atk": 32}, item="choiceband")
    opp = mon("tyranitar", "jolly")
    r = simulate_turn(me, opp, "earthquake", "crunch", roll=1.0)
    assert r.opp_fainted and r.opp.hp == 0
    # L'adversaire K.O. ne riposte pas.
    assert r.me.hp == r.me.max_hp


def test_faster_ko_prevents_retaliation():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32}, item="choiceband")
    opp = mon("tyranitar", "adamant", {"atk": 32}, hp=0.5)
    r = simulate_turn(me, opp, "earthquake", "crunch", roll=1.0)
    if r.opp_fainted:
        assert r.me.hp == r.me.max_hp        # pas de dégâts subis


def test_life_orb_recoil():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32}, item="lifeorb")
    opp = mon("skarmory", "impish", {"hp": 32, "def": 32})
    r = simulate_turn(me, opp, "dragonclaw", None, roll=0.5)
    # Orbe Vie : 1/10 des PV max en recul après un coup qui touche.
    assert r.me.hp == r.me.max_hp - r.me.max_hp // 10


def test_copy_leaves_inputs_untouched():
    me = mon("garchomp", "adamant", {"atk": 32})
    opp = mon("tyranitar", "jolly")
    before = opp.hp
    simulate_turn(me, opp, "earthquake", None, roll=1.0, copy=True)
    assert opp.hp == before                  # entrée intacte


# --- Coups de soutien -------------------------------------------------------

def test_setup_boost_applied():
    me = mon("garchomp", "jolly", {"spe": 32})
    opp = mon("amoonguss", "sassy")
    r = simulate_turn(me, opp, "swordsdance", "spore", roll=0.5)
    assert r.me.boosts.get("atk") == 2


def test_protect_blocks_damage():
    me = mon("incineroar", "careful", {"hp": 32, "spd": 32})
    opp = mon("garchomp", "jolly", {"atk": 32, "spe": 32}, item="choiceband")
    # Protect a +priorité : il passe avant et bloque le Séisme.
    r = simulate_turn(me, opp, "protect", "earthquake", roll=1.0)
    assert r.me.hp == r.me.max_hp


def test_status_move_applies_status():
    me = mon("rotomwash", "bold", {"hp": 32, "def": 32})
    opp = mon("tyranitar", "adamant", {"atk": 32})
    r = simulate_turn(me, opp, "willowisp", "crunch", roll=0.5)
    assert r.opp.status == "brn"


def test_burn_chip_at_end_of_turn():
    me = mon("garchomp", "jolly", {"spe": 32}, status="brn", hp=1.0)
    opp = mon("amoonguss", "sassy")
    r = simulate_turn(me, opp, "dragonclaw", None, roll=0.5)
    assert r.me.hp < r.me.max_hp             # subit la brûlure


# --- Sommeil & rollout ------------------------------------------------------

def test_sleep_prevents_action_then_wakes():
    me = mon("garchomp", "jolly", {"atk": 32, "spe": 32})
    opp = mon("amoonguss", "sassy", {"hp": 32, "spd": 32})
    res = rollout(me, opp, ["dragonclaw"] * 6, ["spore"] + ["sludgebomb"] * 5,
                  max_turns=6)
    # Tour 1 : Spore endort. Tours suivants : Garchomp dort puis se réveille.
    joined = "\n".join(l for tr in res for l in tr.log)
    assert "est maintenant slp" in joined
    assert "se réveille" in joined


def test_rollout_stops_on_faint():
    me = mon("garchomp", "adamant", {"atk": 32}, item="choiceband")
    opp = mon("tyranitar", "jolly", hp=0.3)
    res = rollout(me, opp, ["earthquake"], ["crunch"], roll=1.0, max_turns=10)
    assert res[-1].opp_fainted
    assert len(res) == 1                     # KO au premier tour


def test_leftovers_heals():
    me = mon("garchomp", "jolly", {"spe": 32}, item="leftovers", hp=0.5)
    opp = mon("amoonguss", "sassy")
    r = simulate_turn(me, opp, "dragonclaw", None, roll=0.0)
    # Vestiges soigne 1/16 en fin de tour (pas de dégâts subis ici).
    assert r.me.hp > int(r.me.max_hp * 0.5)
