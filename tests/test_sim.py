"""Tests du simulateur de tour (sim.py)."""

from __future__ import annotations

from simupoke.model import FieldState, PokemonState
from simupoke.sim import (
    Mon,
    Side,
    action_order,
    rollout,
    simulate_turn,
    simulate_turn_actions,
)


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
    joined = "\n".join(line for tr in res for line in tr.log)
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


# --- Changements (actions complètes) ---------------------------------------

def test_switch_brings_in_bench_and_takes_the_hit():
    me = Side(active=mon("gengar", "timid", {"spa": 32}, moves=["shadowball"]),
              bench=[mon("skarmory", "impish", {"hp": 32, "def": 32})])
    opp = Side(active=mon("garchomp", "jolly", {"atk": 32, "spe": 32},
                          item="choiceband", moves=["earthquake"]))
    r = simulate_turn_actions(me, opp, ("switch", 0), ("move", "earthquake"))
    # Skarmory entre (Acier/Vol) : immunisé au Séisme.
    assert r.me.active.build.species == "skarmory"
    assert r.me.active.hp == r.me.active.max_hp


def test_switch_resets_boosts_of_outgoing():
    active = mon("garchomp", "jolly", {"spe": 32})
    active.boosts = {"atk": 2}
    me = Side(active=active, bench=[mon("tyranitar", "adamant")])
    opp = Side(active=mon("amoonguss", "sassy"))
    r = simulate_turn_actions(me, opp, ("switch", 0), ("move", None))
    # Garchomp est renvoyé au banc, ses boosts remis à zéro.
    benched = next(b for b in r.me.bench if b.build.species == "garchomp")
    assert benched.boosts == {}


def test_recoil_damages_attacker():
    me = mon("incineroar", "adamant", {"atk": 32})
    opp = mon("tyranitar", "careful", {"hp": 32, "def": 32})
    r = simulate_turn(me, opp, "flareblitz", None, roll=0.5)
    assert r.me.hp < r.me.max_hp
    assert any("recul" in ln for ln in r.log)


def test_rock_head_negates_recoil():
    me = PokemonState(species="aggron", nature="adamant",
                      stat_points={"atk": 32}, ability="rockhead")
    r = simulate_turn(Mon.from_state(me),
                      mon("tyranitar", "careful", {"hp": 32}), "doubleedge", None)
    assert r.me.hp == r.me.max_hp
    assert not any("recul" in ln for ln in r.log)


def test_drain_heals_attacker():
    me = mon("ironhands", "adamant", {"atk": 32}, hp=0.5)
    before = me.hp
    r = simulate_turn(me, mon("blissey", "calm"), "drainpunch", None, roll=0.5)
    assert r.me.hp > before
    assert any("draine" in ln for ln in r.log)


def test_drain_capped_by_damage_dealt():
    # Cible presque morte : le drain ne dépasse pas les dégâts réellement infligés.
    me = mon("ironhands", "adamant", {"atk": 32}, hp=0.5)
    opp = mon("flutter mane", "timid", hp=0.02)      # ~ presque KO
    r = simulate_turn(me, opp, "drainpunch", None, roll=1.0)
    # dégâts réels faibles -> soin faible (pas un demi-Drain Punch plein).
    assert r.me.hp - me.max_hp // 2 <= me.max_hp // 4


def test_switch_into_weakness_takes_damage():
    me = Side(active=mon("gengar", "timid", {"spa": 32}, moves=["shadowball"]),
              bench=[mon("charizard", "timid", {"hp": 0})])
    opp = Side(active=mon("garchomp", "jolly", {"atk": 32, "spe": 32},
                          item="choiceband", moves=["stoneedge"]))
    r = simulate_turn_actions(me, opp, ("switch", 0), ("move", "stoneedge"))
    # Charizard entre et encaisse Lance-Pierre (×4) : gros dégâts.
    assert r.me.active.build.species == "charizard"
    assert r.me.active.hp < r.me.active.max_hp


# --- Conditions de camp / champ --------------------------------------------

def test_reflect_halves_physical_damage():
    # Défenseur neutre et encaissant (survit avec et sans écran) pour un ratio net.
    opp = Side(active=mon("garchomp", "adamant", {"atk": 32}))
    behind = simulate_turn_actions(
        Side(active=mon("snorlax", "careful", {"hp": 32, "def": 32}),
             screens={"reflect": 5}),
        opp, ("move", None), ("move", "bodyslam"))
    plain = simulate_turn_actions(
        Side(active=mon("snorlax", "careful", {"hp": 32, "def": 32})),
        opp, ("move", None), ("move", "bodyslam"))
    lost_behind = behind.me.active.max_hp - behind.me.active.hp
    lost_plain = plain.me.active.max_hp - plain.me.active.hp
    assert lost_plain > lost_behind > 0
    assert abs(lost_behind - lost_plain // 2) <= 2


def test_reflect_move_sets_screen():
    me = Side(active=mon("amoonguss", "sassy", {"hp": 32}))
    opp = Side(active=mon("amoonguss", "sassy", {"hp": 32}))
    r = simulate_turn_actions(me, opp, ("move", "reflect"), ("move", None))
    # Posé ce tour -> garde sa durée pleine (pas décrémenté le tour de pose).
    assert r.me.screens.get("reflect", 0) == 5


def test_tailwind_move_and_speed_flip():
    me = Side(active=mon("whimsicott", "timid", {"spe": 0}, moves=["tailwind"]))
    opp = Side(active=mon("garchomp", "jolly", {"spe": 32}))
    r = simulate_turn_actions(me, opp, ("move", "tailwind"), ("move", None))
    assert r.me.tailwind == 4


def test_stealth_rock_damages_switch_in():
    me = Side(active=mon("gengar", "timid", {"spa": 32}, moves=["shadowball"]),
              bench=[mon("charizard", "timid", {"hp": 0})],
              hazards={"stealthrock": 1})
    opp = Side(active=mon("blissey", "calm"))
    r = simulate_turn_actions(me, opp, ("switch", 0), ("move", None))
    # Charizard (Feu/Vol) : Roche ×4 -> ~ la moitié des PV à l'entrée.
    assert r.me.active.hp < r.me.active.max_hp // 2 + 5


def test_spikes_spare_flying_types():
    me = Side(active=mon("garchomp", "jolly", {"spe": 32}),
              bench=[mon("charizard", "timid", {"hp": 32})],   # Vol -> immunisé Picots
              hazards={"spikes": 3})
    opp = Side(active=mon("blissey", "calm"))
    r = simulate_turn_actions(me, opp, ("switch", 0), ("move", None))
    assert r.me.active.hp == r.me.active.max_hp
    assert not any("Picots" in ln for ln in r.log)


def test_weather_move_sets_field():
    me = Side(active=mon("torkoal", "quiet", {"spa": 32}, moves=["sunnyday"]))
    opp = Side(active=mon("garchomp", "jolly", {"spe": 32}))
    r = simulate_turn_actions(me, opp, ("move", "sunnyday"), ("move", None))
    assert any("météo -> sun" in ln for ln in r.log)


# --- Objets / talents à déclenchement --------------------------------------

def test_focus_sash_survives_at_one_hp():
    me = mon("garchomp", "adamant", {"atk": 32}, item="choiceband")
    opp = mon("fluttermane", "timid", {"hp": 0}, item="focussash")
    r = simulate_turn(me, opp, "earthquake", None, roll=1.0)
    assert r.opp.hp == 1
    assert r.opp.item is None                      # Sash consommée
    assert any("tient bon" in ln for ln in r.log)


def test_sturdy_survives_without_consuming_item():
    me = mon("garchomp", "adamant", {"atk": 32}, item="choiceband")
    opp = PokemonState(species="fluttermane", nature="timid",
                       stat_points={"hp": 0}, ability="sturdy")
    r = simulate_turn(me, Mon.from_state(opp), "earthquake", None, roll=1.0)
    assert r.opp.hp == 1


def test_rocky_helmet_chips_on_contact():
    me = mon("garchomp", "jolly", {"atk": 16})
    opp = mon("snorlax", "careful", {"hp": 32, "def": 32}, item="rockyhelmet")
    r = simulate_turn(me, opp, "dragonclaw", None)
    assert r.me.hp == r.me.max_hp - r.me.max_hp // 6


def test_rough_skin_chips_on_contact():
    me = mon("garchomp", "jolly", {"atk": 16})
    opp = mon("garchomp", "jolly", {"hp": 32, "def": 32}, ability="roughskin")
    r = simulate_turn(me, opp, "dragonclaw", None)
    assert r.me.hp == r.me.max_hp - r.me.max_hp // 8


def test_contact_punish_skipped_without_contact():
    me = mon("garchomp", "jolly", {"atk": 32})
    opp = mon("snorlax", "careful", {"hp": 32, "def": 32}, item="rockyhelmet")
    r = simulate_turn(me, opp, "earthquake", None)     # Séisme : pas de contact
    assert r.me.hp == r.me.max_hp


def test_weakness_policy_boosts_on_super_effective():
    me = mon("garchomp", "adamant", {"atk": 16})
    opp = mon("tyranitar", "careful", {"hp": 32, "def": 32}, item="weaknesspolicy")
    r = simulate_turn(me, opp, "earthquake", None)     # ×2 sur Tyranitar
    assert r.opp.boosts.get("atk") == 2 and r.opp.boosts.get("spa") == 2
    assert r.opp.item is None


def test_sitrus_berry_heals_below_half():
    me = mon("garchomp", "adamant", {"atk": 16})
    opp = mon("snorlax", "careful", {"hp": 32, "spd": 32}, item="sitrusberry",
              hp=0.55)
    r = simulate_turn(me, opp, "earthquake", None)
    assert r.opp.item is None
    assert any("Sitrus" in ln for ln in r.log)


def test_resist_berry_halves_super_effective_hit():
    me = mon("kyurem", "modest", {"spa": 32})
    plain = simulate_turn(me, mon("garchomp", "jolly", {"hp": 32}), "icebeam", None)
    berry = simulate_turn(me, mon("garchomp", "jolly", {"hp": 32},
                                  item="yacheberry"), "icebeam", None)
    lost_plain = plain.opp.max_hp - plain.opp.hp
    lost_berry = berry.opp.max_hp - berry.opp.hp
    assert lost_berry < lost_plain
    assert berry.opp.item is None


def test_resist_berry_ignores_non_matching_type():
    me = mon("garchomp", "adamant", {"atk": 32})
    # Baie Yache (Glace) n'aide pas contre un Séisme (Sol).
    r = simulate_turn(me, mon("heatran", "careful", {"hp": 32, "def": 32},
                              item="yacheberry"), "earthquake", None)
    assert r.opp.item == "yacheberry"                 # non consommée


def test_air_balloon_immune_to_ground_then_pops():
    atk = mon("garchomp", "adamant", {"atk": 32})
    balloon = mon("heatran", "calm", {"hp": 32}, item="airballoon")
    ground = simulate_turn(atk, balloon, "earthquake", None)
    assert ground.opp.hp == ground.opp.max_hp         # immunisé, aucun dégât
    assert ground.opp.item == "airballoon"            # le Ballon tient (coup Sol)
    popped = simulate_turn(atk, mon("heatran", "calm", {"hp": 32},
                                    item="airballoon"), "dragonclaw", None)
    assert popped.opp.item is None                    # percé par un coup non-Sol


def test_variable_power_move_does_not_crash():
    # Balayage (Low Kick) a une puissance variable (basePower 0 en données) :
    # le simulateur l'ignore proprement au lieu de lever.
    me = mon("hariyama", "adamant", {"atk": 32})
    opp = mon("tyranitar", "careful", {"hp": 32, "def": 32})
    r = simulate_turn(me, opp, "lowkick", None)
    assert any("non simulé" in ln for ln in r.log)
    assert r.opp.hp == r.opp.max_hp                  # aucun dégât appliqué


def test_grassy_terrain_heals_grounded():
    atk = mon("pikachu", "timid")
    opp = mon("snorlax", "careful", {"hp": 32}, hp=0.5)
    r = simulate_turn(atk, opp, "thunderbolt", None, FieldState(terrain="grassy"))
    assert any("Champ Herbu" in ln for ln in r.log)
