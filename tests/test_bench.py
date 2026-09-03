"""Tests des benchmarks & optimiseurs de SP (bench.py)."""

from __future__ import annotations

from simupoke.bench import (
    compute_speed,
    min_sp_to_ko,
    min_sp_to_outspeed,
    min_sp_to_survive,
    speed_tiers,
)
from simupoke.model import PokemonState


def mk(species, nature="serious", sp=None, moves=None, item=None,
       status=None, hp=1.0, boosts=None):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        moves=moves or [], item=item, status=status,
                        current_hp_pct=hp, boosts=boosts or {})


# --- Vitesse effective ------------------------------------------------------

def test_tailwind_doubles_speed():
    g = mk("garchomp", "jolly", {"spe": 32})
    assert compute_speed(g, tailwind=True) == 2 * compute_speed(g)


def test_scarf_beats_tailwind_free_mon():
    scarfed = mk("garchomp", "jolly", {"spe": 32}, item="choicescarf")
    plain = mk("garchomp", "jolly", {"spe": 32})
    assert compute_speed(scarfed) > compute_speed(plain, tailwind=False)


# --- Speed tiers ------------------------------------------------------------

def test_speed_tiers_sorted_fastest_first():
    fast = mk("garchomp", "jolly", {"spe": 32})
    slow = mk("snorlax", "brave", {})
    tiers = speed_tiers([slow, fast])
    assert tiers[0].species == "garchomp"
    assert tiers[0].speed > tiers[1].speed


def test_speed_tiers_trick_room_reverses():
    fast = mk("garchomp", "jolly", {"spe": 32})
    slow = mk("snorlax", "brave", {})
    tiers = speed_tiers([fast, slow], trick_room=True)
    # Sous Trick Room, le plus lent agit en premier => en tête de liste.
    assert tiers[0].species == "snorlax"


def test_speed_tiers_notes():
    scarfed = mk("garchomp", "jolly", {"spe": 32}, item="choicescarf",
                 status="par")
    tiers = speed_tiers([scarfed])
    assert "Choice Scarf" in tiers[0].notes
    assert "paralysé" in tiers[0].notes


# --- Outspeed ---------------------------------------------------------------

def test_min_sp_to_outspeed_feasible():
    # Garchomp neutre 0 SP vs Garchomp jolly max : il faut investir en vitesse.
    me = mk("garchomp", "jolly")
    target = mk("garchomp", "serious", {"spe": 0})
    res = min_sp_to_outspeed(me, target)
    assert res.feasible
    assert res.sp == 0                      # jolly base > serious base, 0 SP suffit
    assert res.my_speed > res.target_speed


def test_min_sp_to_outspeed_needs_investment():
    me = mk("garchomp", "serious")          # neutre, aucun SP
    target = mk("garchomp", "serious", {"spe": 20})
    res = min_sp_to_outspeed(me, target)
    assert res.feasible
    assert res.sp is not None and res.sp > 20


def test_min_sp_to_outspeed_impossible_against_faster_base():
    me = mk("munchlax", "serious")          # très lent
    target = mk("garchomp", "jolly", {"spe": 32})
    res = min_sp_to_outspeed(me, target)
    assert res.feasible is False
    assert res.sp is None


def test_outspeed_non_strict_allows_tie():
    me = mk("garchomp", "serious", {"spe": 20})
    target = mk("garchomp", "serious", {"spe": 20})
    strict = min_sp_to_outspeed(me, target, strict=True)
    loose = min_sp_to_outspeed(me, target, strict=False)
    assert loose.feasible                    # égaliser suffit
    assert loose.sp == 20
    # En strict, il faut au moins 1 SP de plus que la cible.
    assert strict.sp is None or strict.sp > 20


# --- Survie -----------------------------------------------------------------

def test_min_sp_to_survive_returns_minimal_total():
    attacker = mk("garchomp", "adamant", {"atk": 32}, item="choiceband")
    defender = mk("skarmory", "impish")
    res = min_sp_to_survive(defender, attacker, "earthquake")
    # Résultat cohérent : si faisable, la survie tient sur le roll haut.
    if res.feasible:
        assert res.total_sp == (res.hp_sp + res.def_sp)
        assert res.max_pct < 100.0
        assert res.stat == "def"             # Séisme est physique


def test_survive_zero_when_already_bulky_enough():
    # Une attaque faible : 0 SP défensif suffit à survivre.
    attacker = mk("pikachu", "serious")
    defender = mk("snorlax", "careful")
    res = min_sp_to_survive(defender, attacker, "tackle")
    assert res.feasible
    assert res.total_sp == 0


# --- KO ---------------------------------------------------------------------

def test_min_sp_to_ko_ohko_feasible():
    attacker = mk("garchomp", "adamant", item="choiceband")
    defender = mk("tyranitar", "adamant")   # 2x faible au Sol
    res = min_sp_to_ko(attacker, defender, "earthquake", hits=1)
    assert res.feasible
    assert res.stat == "atk"
    assert res.min_pct >= 100.0             # roll bas tue à pleins PV


def test_min_sp_to_ko_special_move_uses_spa():
    attacker = mk("garchomp", "modest")
    defender = mk("skarmory", "impish", hp=0.3)
    res = min_sp_to_ko(attacker, defender, "flamethrower", hits=1)
    assert res.stat == "spa"


def test_min_sp_to_ko_impossible_reports_infeasible():
    attacker = mk("magikarp", "serious")    # Splash-tier, aucune offense
    defender = mk("snorlax", "careful", {"hp": 32, "spd": 32})
    res = min_sp_to_ko(attacker, defender, "tackle", hits=1)
    assert res.feasible is False
    assert res.sp is None


def test_ko_respects_current_hp():
    attacker = mk("garchomp", "jolly")
    full = mk("tyranitar", "adamant", hp=1.0)
    weak = mk("tyranitar", "adamant", hp=0.25)
    res_full = min_sp_to_ko(attacker, full, "earthquake", hits=1)
    res_weak = min_sp_to_ko(attacker, weak, "earthquake", hits=1)
    # Finir un adversaire entamé coûte au plus autant de SP qu'à pleins PV.
    if res_full.feasible and res_weak.feasible:
        assert res_weak.sp <= res_full.sp


# --- Focus Sash / Fermeté ---------------------------------------------------

def test_focus_sash_guarantees_survival():
    defender = mk("fluttermane", "timid", {"hp": 0}, item="focussash")
    attacker = mk("garchomp", "adamant", {"atk": 32}, item="choiceband")
    res = min_sp_to_survive(defender, attacker, "earthquake")
    assert res.feasible and res.by_endure and res.total_sp == 0


def test_sturdy_guarantees_survival():
    defender = PokemonState(species="fluttermane", nature="timid",
                            ability="sturdy", stat_points={"hp": 0})
    attacker = mk("garchomp", "adamant", {"atk": 32}, item="choiceband")
    res = min_sp_to_survive(defender, attacker, "earthquake")
    assert res.feasible and res.by_endure


def test_focus_sash_blocks_ohko():
    defender = mk("fluttermane", "timid", {"hp": 0}, item="focussash")
    attacker = mk("garchomp", "adamant", {"atk": 32}, item="choiceband")
    res = min_sp_to_ko(attacker, defender, "earthquake", hits=1)
    assert res.feasible is False
    assert res.blocked_by_endure is True


def test_focus_sash_allows_2hko():
    defender = mk("fluttermane", "timid", {"hp": 0}, item="focussash")
    attacker = mk("garchomp", "adamant", {"atk": 32}, item="choiceband")
    res = min_sp_to_ko(attacker, defender, "earthquake", hits=2)
    assert res.feasible is True


def test_sash_irrelevant_when_not_full_hp():
    # À PV entamés, Focus Sash ne se déclenche pas : OHKO possible.
    defender = mk("fluttermane", "timid", {"hp": 0}, item="focussash", hp=0.5)
    attacker = mk("garchomp", "adamant", {"atk": 32}, item="choiceband")
    res = min_sp_to_ko(attacker, defender, "earthquake", hits=1)
    assert res.feasible is True
    assert res.blocked_by_endure is False
