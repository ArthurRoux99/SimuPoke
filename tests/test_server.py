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


def test_roster_get_returns_owned():
    out = server.api_roster_get()
    assert isinstance(out["roster"], list)
    assert any(e["species"] == "tyranitar" for e in out["roster"])


def test_roster_save_roundtrip(tmp_path):
    target = tmp_path / "my_roster.json"
    entries = [{"species": "garchomp", "nature": "jolly",
                "stat_points": {"atk": 32, "spe": 32}, "moves": ["earthquake"]}]
    res = server.api_roster_save({"roster": entries}, path=target)
    assert res["ok"] and res["count"] == 1 and res["unknown"] == []
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["owned"][0]["species"] == "garchomp"


def test_roster_save_flags_unknown_species(tmp_path):
    target = tmp_path / "r.json"
    res = server.api_roster_save({"roster": [{"species": "notamon", "nature": "serious"}]},
                                 path=target)
    assert "notamon" in res["unknown"]


def test_draft_endpoint_applies_usage():
    out = server.api_draft({"lineup": _sample("sample_lineup.json")["lineup"]})
    assert out["usageApplied"] is True


def test_likely_endpoint():
    out = server.api_likely("incineroar")
    assert out["item"] == "assaultvest"
    assert out["known"] is True
    assert server.api_likely("magikarp")["known"] is False
