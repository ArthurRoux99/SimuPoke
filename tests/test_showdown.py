"""Tests de l'import/export Showdown paste (showdown.py)."""

from __future__ import annotations

from simupoke.showdown import (
    ev_to_sp,
    format_team,
    parse_pokemon,
    parse_team,
    sp_to_ev,
)

PASTE = """Garchomp (M) @ Life Orb
Ability: Rough Skin
Level: 50
EVs: 4 HP / 252 Atk / 252 Spe
Adamant Nature
IVs: 0 SpA
- Earthquake
- Dragon Claw
- Stone Edge
- Swords Dance

Incineroar @ Assault Vest
Ability: Intimidate
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
Tera Type: Grass
Shiny: Yes
- Fake Out
- Knock Off
- Flare Blitz
- Parting Shot"""


def test_ev_sp_conversion():
    assert ev_to_sp(252) == 32          # round(31.5) -> 32
    assert ev_to_sp(0) == 0
    assert ev_to_sp(256) == 32          # plafonné
    assert sp_to_ev(32) == 256


def test_parse_team_size_and_species():
    team = parse_team(PASTE)
    assert [m.species for m in team] == ["garchomp", "incineroar"]


def test_parse_header_item_gender_ability_nature():
    team = parse_team(PASTE)
    g = team[0]
    assert g.item == "lifeorb"          # « @ Life Orb » -> id
    assert g.ability == "roughskin"
    assert g.nature == "adamant"
    assert g.species == "garchomp"      # le « (M) » (genre) n'est pas l'espèce


def test_parse_evs_to_sp():
    g = parse_team(PASTE)[0]
    assert g.stat_points["atk"] == 32
    assert g.stat_points["spe"] == 32
    assert g.stat_points.get("hp", 0) == 0      # 4 EV -> 0 SP


def test_parse_moves_normalised():
    g = parse_team(PASTE)[0]
    assert g.moves == ["earthquake", "dragonclaw", "stoneedge", "swordsdance"]


def test_parse_shiny_flag():
    inc = parse_team(PASTE)[1]
    assert inc.is_shiny is True


def test_nickname_species_in_parens():
    mon = parse_pokemon("Chompy (Garchomp) @ Choice Scarf\nJolly Nature\n- Earthquake")
    assert mon.species == "garchomp"
    assert mon.item == "choicescarf"


def test_species_only_header():
    mon = parse_pokemon("Amoonguss")
    assert mon.species == "amoonguss"
    assert mon.item is None


def test_empty_block_is_none():
    assert parse_pokemon("   \n  ") is None


def test_export_roundtrips_through_parser():
    team = parse_team(PASTE)
    text = format_team(team)
    reparsed = parse_team(text)
    assert [m.species for m in reparsed] == [m.species for m in team]
    assert reparsed[0].stat_points["atk"] == 32
    assert reparsed[0].item == "lifeorb"
    # Les EV exportés restent Showdown-légaux (≤ 252).
    assert "256" not in text
