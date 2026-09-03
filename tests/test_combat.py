"""Tests de B1 — assistant de combat (mode analyse, 1 tour)."""

from __future__ import annotations

from simupoke.combat import (
    analyze_turn,
    effective_speed,
    evaluate_switches,
    moves_first,
)
from simupoke.model import FieldState, PokemonState


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


# --- Coups de soutien évalués ----------------------------------------------

def test_setup_recommended_when_safe():
    # Face à une menace faible et lente, Danse-Lames prime (offense doublée).
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32},
            ["earthquake", "swordsdance"])
    opp = mk("amoonguss", "sassy", {"hp": 32, "spd": 32}, ["sludgebomb"])
    a = analyze_turn(me, opp, opp_move="sludgebomb")
    sd = next(e for e in a.other if e.move == "Swords Dance")
    assert sd.value > 0
    assert "Swords Dance" in a.recommendation


def test_setup_penalized_when_ohko_incoming():
    me = mk("gengar", "timid", {"spa": 32, "spe": 32},
            ["shadowball", "nastyplot"], hp=0.4)
    opp = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    a = analyze_turn(me, opp, opp_move="earthquake")
    np = next(e for e in a.other if e.move == "Nasty Plot")
    assert np.value < 0
    assert "Nasty Plot" not in a.recommendation      # on n'setup pas sous OHKO


def test_status_move_no_effect_on_immune_target():
    # Cage-Éclair (paralysie) est sans effet sur un type Sol.
    me = mk("rotomwash", "bold", {"hp": 32, "def": 32},
            ["hydropump", "thunderwave"])
    opp = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    a = analyze_turn(me, opp, opp_move="earthquake")
    tw = next(e for e in a.other if e.move == "Thunder Wave")
    assert tw.value == 0.0
    assert any("sans effet" in n for n in tw.notes)


def test_protect_valued_higher_under_ohko():
    me = mk("incineroar", "careful", {"hp": 32, "spd": 32},
            ["knockoff", "protect"], hp=0.3)
    opp = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"],
             item="choiceband")
    a = analyze_turn(me, opp, opp_move="earthquake")
    prot = next(e for e in a.other if e.move == "Protect")
    assert prot.value >= 0.4


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


def test_incoming_unknown_when_no_opp_moves_and_no_usage():
    # Magikarp est absent de la table d'usage -> menace inconnue.
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    a = analyze_turn(me, mk("magikarp", "serious", {}, []))
    assert a.incoming.known is False
    assert a.incoming.estimated is False


def test_incoming_estimated_via_usage():
    # Incineroar est dans l'échantillon d'usage : menace estimée via son set probable.
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    a = analyze_turn(me, mk("incineroar", "careful", {}, []))
    assert a.incoming.known is True
    assert a.incoming.estimated is True
    assert a.incoming.move is not None


def test_explicit_opp_moves_not_marked_estimated():
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    a = analyze_turn(me, mk("incineroar", "careful", {}, ["knockoff"]))
    assert a.incoming.estimated is False


def test_usage_disabled_falls_back_to_unknown():
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    a = analyze_turn(me, mk("incineroar", "careful", {}, []), use_usage=False)
    assert a.incoming.known is False


# --- Changements (switch) ---------------------------------------------------

def test_variable_power_move_listed_not_crashing():
    # Un coup à puissance variable dans mon moveset ne fait pas planter l'analyse.
    me = mk("hariyama", "adamant", {"atk": 32}, ["lowkick", "closecombat"])
    opp = mk("tyranitar", "adamant", {"atk": 32}, ["crunch"])
    a = analyze_turn(me, opp, opp_move="crunch")
    assert any(e.move == "Close Combat" for e in a.options)
    assert any("Low Kick" in e.move for e in a.other)


def test_no_bench_means_no_switches():
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    opp = mk("tyranitar", "adamant", {"atk": 32}, ["crunch"])
    a = analyze_turn(me, opp, opp_move="crunch")
    assert a.switches == []


def test_switches_ranked_by_value():
    me = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    opp = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    # Skarmory (immunisé Sol) doit primer Rotom-W (au sol, encaisse) à l'entrée.
    bench = [mk("rotomwash", "bold", {"hp": 32, "def": 32}, ["hydropump"]),
             mk("skarmory", "impish", {"hp": 32, "def": 32}, ["bravebird"])]
    a = analyze_turn(me, opp, opp_move="earthquake", bench=bench)
    assert a.switches[0].species == "skarmory"
    assert a.switches[0].incoming_pct == 0.0        # immunité Sol
    assert a.switches[0].value >= a.switches[1].value


def test_pivot_recommended_when_active_is_lost():
    # Gengar entamé, ne tue pas, se fait OHKO au Sol ; Skarmory y est immunisé.
    me = mk("gengar", "timid", {"spa": 32, "spe": 32}, ["shadowball"], hp=0.3)
    opp = mk("garchomp", "jolly", {"atk": 32, "spe": 32}, ["earthquake"])
    bench = [mk("skarmory", "impish", {"hp": 32, "def": 32}, ["bravebird"])]
    a = analyze_turn(me, opp, opp_move="earthquake", bench=bench)
    assert "Changer pour skarmory" in a.recommendation


def test_evaluate_switches_flags_ohko_entry():
    opp = mk("garchomp", "adamant", {"atk": 32}, ["earthquake"], item="choiceband")
    bench = [mk("fluttermane", "timid", {"hp": 0}, ["moonblast"])]
    sw = evaluate_switches(bench, opp, None, "earthquake")
    assert sw[0].survives is False
    assert any("KO à l'entrée" in n for n in sw[0].notes)
