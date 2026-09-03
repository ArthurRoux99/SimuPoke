"""Tests de la couverture étendue du calc : items/talents VGC (base-4096).

On vérifie les **ratios** attendus (Showdown / @smogon/calc) par rapport au même
calcul sans le modificateur — approche robuste au bruit des 16 rolls (on compare
le roll max). Les valeurs base-4096 sont celles de Showdown.
"""

from __future__ import annotations

from simupoke.damage import calculate
from simupoke.model import FieldState, PokemonState


def st(species, nature="serious", sp=None, item=None, ability=None):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        item=item, ability=ability)


def ratio(species_atk, move, defender, *, item=None, ability=None,
          field=None, atk_nature="modest", sp=None):
    sp = sp or {"atk": 32, "spa": 32}
    base = calculate(st(species_atk, atk_nature, sp), defender, move, field)
    mod = calculate(st(species_atk, atk_nature, sp, item=item, ability=ability),
                    defender, move, field)
    return mod.max_damage / base.max_damage


# --- Items type-boost / band-glasses ---------------------------------------

def test_type_item_boosts_matching_type():
    r = ratio("charizard", "flamethrower", st("venusaur", "bold"),
              item="charcoal")
    assert abs(r - 1.2) < 0.03


def test_type_item_no_effect_on_other_type():
    # Charbon ne booste pas un move Sol.
    base = calculate(st("garchomp", "adamant", {"atk": 32}),
                     st("snorlax", "careful"), "earthquake")
    with_item = calculate(st("garchomp", "adamant", {"atk": 32}, item="charcoal"),
                          st("snorlax", "careful"), "earthquake")
    assert with_item.max_damage == base.max_damage


def test_muscle_band_physical():
    r = ratio("garchomp", "earthquake", st("snorlax", "careful"),
              item="muscleband", atk_nature="adamant", sp={"atk": 32})
    assert abs(r - 1.1) < 0.03


def test_wise_glasses_special():
    r = ratio("charizard", "flamethrower", st("venusaur", "bold"),
              item="wiseglasses")
    assert abs(r - 1.1) < 0.03


# --- Talents offensifs ------------------------------------------------------

def test_water_bubble_doubles_water():
    r = ratio("azumarill", "hydropump", st("blissey", "calm"),
              ability="waterbubble", atk_nature="modest", sp={"spa": 32})
    assert abs(r - 2.0) < 0.06


def test_transistor_boosts_electric():
    r = ratio("pikachu", "thunderbolt", st("snorlax", "careful"),
              ability="transistor", atk_nature="timid", sp={"spa": 32})
    assert abs(r - 1.3) < 0.04


def test_protosynthesis_boosts_highest_offensive_stat_in_sun():
    sun = FieldState(weather="sun")
    # Roaring Moon : l'Attaque est sa plus haute stat -> Crunch (physique) dopé.
    r = ratio("roaringmoon", "crunch", st("garchomp", "jolly"),
              ability="protosynthesis", field=sun, atk_nature="adamant",
              sp={"atk": 32})
    assert abs(r - 1.3) < 0.04


def test_protosynthesis_inactive_without_trigger():
    # Sans soleil ni Énergie Booster : aucun effet.
    r = ratio("roaringmoon", "crunch", st("garchomp", "jolly"),
              ability="protosynthesis", atk_nature="adamant", sp={"atk": 32})
    assert r == 1.0


def test_booster_energy_triggers_protosynthesis():
    atk = st("roaringmoon", "adamant", {"atk": 32}, item="boosterenergy",
             ability="protosynthesis")
    base = calculate(st("roaringmoon", "adamant", {"atk": 32}),
                     st("garchomp", "jolly"), "crunch")
    boosted = calculate(atk, st("garchomp", "jolly"), "crunch")
    assert boosted.max_damage > base.max_damage


# --- Talents défensifs ------------------------------------------------------

def _def_ratio(defender_ability, move, attacker, defender_species, def_nature,
               field=None, def_sp=None):
    base = calculate(attacker, st(defender_species, def_nature, def_sp),
                     move, field)
    mod = calculate(attacker, st(defender_species, def_nature, def_sp,
                                 ability=defender_ability), move, field)
    return mod.max_damage / base.max_damage


def test_fluffy_doubles_fire():
    r = _def_ratio("fluffy", "flamethrower",
                   st("charizard", "modest", {"spa": 32}), "snorlax", "careful")
    assert abs(r - 2.0) < 0.05


def test_fluffy_halves_contact():
    # Close Combat : contact, non-Feu -> ×0.5.
    r = _def_ratio("fluffy", "closecombat",
                   st("machamp", "adamant", {"atk": 32}), "snorlax", "careful")
    assert abs(r - 0.5) < 0.05


def test_ice_scales_halves_special():
    r = _def_ratio("icescales", "airslash",
                   st("charizard", "modest", {"spa": 32}), "blissey", "calm")
    assert abs(r - 0.5) < 0.05


def test_dry_skin_amplifies_fire():
    r = _def_ratio("dryskin", "flamethrower",
                   st("charizard", "modest", {"spa": 32}), "snorlax", "careful")
    assert abs(r - 1.25) < 0.04


def test_purifying_salt_halves_ghost():
    r = _def_ratio("purifyingsalt", "shadowball",
                   st("gengar", "modest", {"spa": 32}), "garchomp", "careful")
    assert abs(r - 0.5) < 0.05


# --- Écrans -----------------------------------------------------------------

def _base(att, mv, dfn):
    return calculate(att, dfn, mv)


def test_reflect_halves_physical():
    att = st("garchomp", "adamant", {"atk": 32}, item="choiceband")
    dfn = st("tyranitar", "careful", {"hp": 32, "def": 32})
    r = calculate(att, dfn, "earthquake", screen="reflect")
    assert abs(r.max_damage / _base(att, "earthquake", dfn).max_damage - 0.5) < 0.02


def test_lightscreen_no_effect_on_physical():
    att = st("garchomp", "adamant", {"atk": 32})
    dfn = st("tyranitar", "careful")
    assert calculate(att, dfn, "earthquake", screen="lightscreen").max_damage \
        == _base(att, "earthquake", dfn).max_damage


def test_auroraveil_halves_special():
    att = st("charizard", "modest", {"spa": 32})
    dfn = st("blissey", "calm")
    r = calculate(att, dfn, "flamethrower", screen="auroraveil")
    assert abs(r.max_damage / _base(att, "flamethrower", dfn).max_damage - 0.5) < 0.03


def test_crit_bypasses_screen():
    att = st("garchomp", "adamant", {"atk": 32}, item="choiceband")
    dfn = st("tyranitar", "careful", {"hp": 32, "def": 32})
    behind = calculate(att, dfn, "earthquake", screen="reflect", crit=True)
    plain_crit = calculate(att, dfn, "earthquake", crit=True)
    assert behind.max_damage == plain_crit.max_damage


def test_screen_doubles_is_two_thirds():
    att = st("garchomp", "adamant", {"atk": 32}, item="choiceband")
    dfn = st("tyranitar", "careful", {"hp": 32, "def": 32})
    with_screen = calculate(att, dfn, "earthquake", screen="reflect", apply_spread=True)
    no_screen = calculate(att, dfn, "earthquake", apply_spread=True)
    assert abs(with_screen.max_damage / no_screen.max_damage - 0.667) < 0.02
