"""Tests des endpoints du serveur local (fonctions pures, sans socket)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simupoke import server

ROOT = Path(__file__).resolve().parents[1]


def _sample(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_meta_lists_populated():
    meta = server.api_meta()
    assert len(meta["species"]) > 1000
    assert "Earthquake" in meta["moves"]
    assert "jolly" in meta["natures"]


def test_damage_endpoint_matches_core():
    out = server.api_damage({
        "attacker": {"species": "garchomp", "nature": "adamant",
                     "sp": {"atk": 31}, "item": "choiceband"},
        "defender": {"species": "tyranitar", "nature": "jolly"},
        "move": "earthquake",
    })
    assert (out["min"], out["max"]) == (258, 306)
    assert out["eff"] == 2.0
    assert out["koGuaranteed"] == 1


def test_damage_endpoint_champions_delta():
    out = server.api_damage({
        "attacker": {"species": "feraligatr", "nature": "adamant",
                     "sp": {"atk": 31}, "ability": "dragonize"},
        "defender": {"species": "garchomp", "nature": "jolly"},
        "move": "doubleedge",
    })
    assert out["eff"] == 2.0          # Normal -> Dragon


def test_analyze_endpoint():
    out = server.api_analyze({
        "me": {"species": "garchomp", "nature": "jolly",
               "sp": {"atk": 32, "spe": 32},
               "moves": ["earthquake", "dragonclaw", "stoneedge"]},
        "opp": {"species": "tyranitar", "nature": "adamant", "moves": ["crunch"]},
        "opp_move": "crunch",
    })
    assert out["options"][0]["move"] == "Earthquake"
    assert "lines" in out


def test_draft_endpoint():
    out = server.api_draft({"lineup": _sample("sample_lineup.json")["lineup"]})
    names = [e["species"] for e in out["ranking"]]
    assert names[-1] == "magikarp"


def test_team_endpoint():
    out = server.api_team({"team": _sample("sample_team.json")["team"]})
    assert out["clauseViolations"] == []
    assert "Ground" in out["sharedWeaknesses"]


def test_preview_endpoint():
    out = server.api_preview({
        "my_team": _sample("sample_team.json")["team"],
        "opp_team": _sample("sample_opponent.json")["team"],
        "format": "doubles",
    })
    assert out["bring"] == 4
    assert len(out["picks"]) == 4


def test_stats_endpoint_flags_illegal_spread():
    out = server.api_stats({"species": "tyranitar", "nature": "jolly",
                            "sp": {"hp": 33}})
    assert out["problems"]


def test_unknown_species_raises():
    with pytest.raises(ValueError):
        server.api_stats({"species": "notamon"})
