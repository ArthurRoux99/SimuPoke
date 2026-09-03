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


# --- Dispatcher partagé serveur/Pyodide (garde le pont navigateur en CI) ---

def test_dispatch_api_get_meta():
    meta = server.dispatch_api("GET", "/api/meta")
    assert len(meta["species"]) > 1000


def test_dispatch_api_post_damage():
    out = server.dispatch_api("POST", "/api/damage", {
        "attacker": {"species": "garchomp", "nature": "adamant",
                     "sp": {"atk": 31}, "item": "choiceband"},
        "defender": {"species": "tyranitar", "nature": "jolly"},
        "move": "earthquake"})
    assert (out["min"], out["max"]) == (258, 306)


def test_dispatch_api_unknown_route_raises():
    with pytest.raises(KeyError):
        server.dispatch_api("POST", "/api/nope", {})


def test_nash_endpoint_returns_mixed_strategy():
    out = server.api_nash({
        "me": {"species": "garchomp", "nature": "jolly",
               "sp": {"atk": 32, "spe": 32},
               "moves": ["earthquake", "dragonclaw", "stoneedge"]},
        "opp": {"species": "tyranitar", "nature": "adamant",
                "moves": ["crunch", "rockslide"]},
    })
    assert abs(sum(s["prob"] for s in out["strategy"]) - 1.0) < 1e-6
    assert out["bestResponse"]
    assert "value" in out


def test_nash_endpoint_exposes_belief():
    out = server.api_nash({
        "me": {"species": "garchomp", "nature": "jolly",
               "moves": ["earthquake", "dragonclaw"]},
        "opp": {"species": "tyranitar", "moves": ["crunch"]},
    })
    assert len(out["belief"]) > 1
    assert abs(sum(b["weight"] for b in out["belief"]) - 1.0) < 1e-6
    assert all("crunch" in b["moves"] for b in out["belief"])


def test_nash_endpoint_updates_belief_on_observed_move():
    # Set adverse partiellement connu ; on observe Rock Slide → la croyance a
    # posteriori ne garde que les mondes cohérents et expose le prior.
    out = server.api_nash({
        "me": {"species": "garchomp", "nature": "jolly",
               "moves": ["earthquake", "dragonclaw"]},
        "opp": {"species": "tyranitar", "moves": ["crunch"]},
        "oppObserved": "rockslide",
    })
    assert out["oppObserved"] == "rockslide"
    assert "beliefPrior" in out and len(out["beliefPrior"]) > 1
    assert abs(sum(b["weight"] for b in out["belief"]) - 1.0) < 1e-6
    # Après avoir vu Rock Slide, la masse se concentre sur les sets qui l'ont.
    with_rs = sum(b["weight"] for b in out["belief"] if "rockslide" in b["moves"])
    assert with_rs > 0.6


def test_nash_endpoint_updates_belief_on_move_order():
    # Rotom-Wash (106) vs Tyranitar : observer que l'adversaire agit avant moi
    # concentre la croyance sur les mondes rapides (Choice Scarf).
    out = server.api_nash({
        "me": {"species": "rotomwash", "nature": "bold", "moves": ["hydropump"]},
        "opp": {"species": "tyranitar", "moves": ["crunch"]},
        "oppFaster": True,
    })
    assert out["oppFaster"] is True
    assert "beliefPrior" in out
    scarf = sum(b["weight"] for b in out["belief"] if b["item"] == "choicescarf")
    assert scarf > 0.8                               # le dépassement révèle le Scarf


def test_nash_endpoint_updates_belief_on_damage_taken():
    # L'adversaire me frappe avec Crunch ; les dégâts subis reconditionnent la
    # croyance sur son investissement offensif. On vérifie le plumbing : drapeaux
    # exposés et croyance a posteriori normalisée.
    out = server.api_nash({
        "me": {"species": "garchomp", "nature": "jolly", "moves": ["earthquake"]},
        "opp": {"species": "tyranitar", "moves": ["crunch"]},
        "oppObserved": "crunch",
        "meDamagePct": 41.0,
    })
    assert out["meDamagePct"] == 41.0
    assert "beliefPrior" in out
    assert abs(sum(b["weight"] for b in out["belief"]) - 1.0) < 1e-6


def test_belief_endpoint():
    out = server.api_belief({"opp": {"species": "tyranitar", "moves": ["crunch"]}})
    assert out["belief"] and all("moves" in b for b in out["belief"])
    out2 = server.dispatch_api("POST", "/api/belief",
                               {"opp": {"species": "tyranitar", "moves": ["crunch"]}})
    assert out2["belief"]


def test_dispatch_api_routes_nash():
    out = server.dispatch_api("POST", "/api/nash", {
        "me": {"species": "garchomp", "nature": "jolly",
               "moves": ["earthquake", "dragonclaw"]},
        "opp": {"species": "tyranitar", "moves": ["crunch", "rockslide"]},
    })
    assert out["strategy"] and "recommendation" in out


def test_dispatch_json_wraps_status():
    ok = json.loads(server.dispatch_json("GET", "/api/meta"))
    assert ok["status"] == 200 and len(ok["body"]["species"]) > 1000

    missing = json.loads(server.dispatch_json("GET", "/api/nope"))
    assert missing["status"] == 404 and missing["body"]["error"]

    bad = json.loads(server.dispatch_json("POST", "/api/stats",
                                          json.dumps({"species": "notamon"})))
    assert bad["status"] == 400 and "notamon" in bad["body"]["error"]


def test_speed_endpoint_sorts_and_tags():
    out = server.api_speed({"mons": [
        {"species": "snorlax", "nature": "brave"},
        {"species": "garchomp", "nature": "jolly", "sp": {"spe": 32},
         "item": "choicescarf"},
    ]})
    assert out["tiers"][0]["species"] == "garchomp"
    assert "Choice Scarf" in out["tiers"][0]["notes"]


def test_outspeed_endpoint():
    out = server.api_outspeed({
        "me": {"species": "garchomp", "nature": "serious"},
        "target": {"species": "garchomp", "nature": "serious", "sp": {"spe": 20}},
    })
    assert out["feasible"] is True
    assert out["sp"] > 20


def test_survive_endpoint():
    out = server.api_survive({
        "defender": {"species": "tyranitar", "nature": "careful"},
        "attacker": {"species": "garchomp", "nature": "adamant",
                     "item": "choiceband", "sp": {"atk": 32}},
        "move": "earthquake",
    })
    # Séisme est physique -> côté Déf sollicité.
    assert out["stat"] == "def"
    assert "feasible" in out


def test_ko_endpoint():
    out = server.api_ko({
        "attacker": {"species": "garchomp", "nature": "adamant",
                     "item": "choiceband"},
        "defender": {"species": "tyranitar", "nature": "adamant"},
        "move": "earthquake", "hits": 1,
    })
    assert out["feasible"] is True
    assert out["stat"] == "atk"
    assert out["minPct"] >= 100.0


def test_spread_endpoint_combines_objectives():
    out = server.api_spread({
        "species": "tyranitar", "nature": "adamant",
        "objectives": [
            {"kind": "ko", "defender": {"species": "garchomp", "nature": "jolly",
             "sp": {"spe": 32}}, "move": "icepunch", "hits": 1},
            {"kind": "survive", "attacker": {"species": "garchomp",
             "nature": "adamant", "sp": {"atk": 32}}, "move": "earthquake"},
            {"kind": "outspeed", "target": {"species": "amoonguss",
             "nature": "sassy", "sp": {"spe": 0}}},
        ],
    })
    assert out["feasible"] is True
    assert out["total"] <= out["budget"]
    assert "sp" in out and "lines" in out


def test_spread_endpoint_flags_unmet():
    out = server.api_spread({
        "species": "magikarp", "nature": "serious",
        "objectives": [{"kind": "ko", "defender": {"species": "blissey",
                        "nature": "calm"}, "move": "tackle"}],
    })
    assert out["feasible"] is False
    assert out["unmet"]


def test_paste_endpoint_parses_and_converts():
    out = server.api_paste({"paste":
        "Garchomp @ Life Orb\nAbility: Rough Skin\n"
        "EVs: 252 Atk / 252 Spe\nAdamant Nature\n- Earthquake\n- Dragon Claw"})
    assert out["count"] == 1
    e = out["team"][0]
    assert e["species"] == "garchomp"
    assert e["stat_points"]["atk"] == 32          # 252 EV -> 32 SP
    assert e["item"] == "lifeorb"
    assert out["unknown"] == []


def test_export_endpoint_roundtrips():
    entries = [{"species": "garchomp", "nature": "adamant",
                "stat_points": {"atk": 32, "spe": 32}, "item": "lifeorb",
                "moves": ["earthquake"]}]
    paste = server.api_export({"team": entries})["paste"]
    assert "Garchomp" in paste
    assert server.api_paste({"paste": paste})["team"][0]["species"] == "garchomp"


def test_decide_endpoint():
    out = server.api_decide({
        "me": {"species": "garchomp", "nature": "jolly",
               "sp": {"atk": 32, "spe": 32},
               "moves": ["earthquake", "dragonclaw", "stoneedge"]},
        "opp": {"species": "tyranitar", "nature": "adamant", "moves": ["crunch"]},
    })
    assert out["actions"][0]["move"] == "Earthquake"
    assert "recommendation" in out and "lines" in out


def test_decide_endpoint_with_switch():
    out = server.api_decide({
        "me": {"species": "gengar", "nature": "timid",
               "sp": {"spa": 32, "spe": 32}, "moves": ["shadowball"]},
        "opp": {"species": "garchomp", "nature": "jolly",
                "sp": {"atk": 32, "spe": 32}, "item": "choiceband",
                "moves": ["earthquake"]},
        "bench": [{"species": "skarmory", "nature": "impish",
                   "sp": {"hp": 32, "def": 32}, "moves": ["bravebird"]}],
    })
    assert out["actions"][0]["kind"] == "switch"
    assert "Changer pour skarmory" in out["recommendation"]


def test_likely_endpoint():
    # Agnostique aux données importées : on valide le comportement de l'endpoint.
    out = server.api_likely("incineroar")
    assert out["known"] is True
    assert isinstance(out["item"], str) and out["item"]
    assert out["ability"] == "intimidate"     # vrai quelle que soit la source
    assert server.api_likely("magikarp")["known"] is False
