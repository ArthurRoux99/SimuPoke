"""Tests de l'importeur d'usage (parseur Showdown chaos, hors-ligne)."""

from __future__ import annotations

import json

from simupoke.usage_import import (
    from_showdown_chaos, build_usage, import_usage,
)

CHAOS = {
    "data": {
        "Incineroar": {
            "Raw count": 1000, "usage": 0.42,
            "Abilities": {"Intimidate": 1000},
            "Items": {"Assault Vest": 400, "Sitrus Berry": 300,
                      "Safety Goggles": 200, "": 10},
            "Moves": {"Fake Out": 950, "Knock Off": 700, "Parting Shot": 500,
                      "Flare Blitz": 480, "": 50},
            "Spreads": {"Careful:252/0/0/0/252/4": 450,
                        "Adamant:252/252/0/0/0/4": 300,
                        "Impish:252/0/252/0/0/4": 200},
            "Teammates": {"Rillaboom": 220, "Amoonguss": 180, "Bad Mon": -50},
        },
    },
}


def test_parser_normalises_to_probabilities():
    sp = from_showdown_chaos(CHAOS)["incineroar"]
    assert sp["usage"] == 0.42
    assert sp["items"]["assaultvest"] == 0.4        # 400/1000
    assert sp["abilities"]["intimidate"] == 1.0
    assert sp["moves"]["fakeout"] == 0.95           # 950/1000


def test_parser_drops_empty_and_negative():
    sp = from_showdown_chaos(CHAOS)["incineroar"]
    assert "" not in sp["items"] and "" not in sp["moves"]
    # Coéquipier à corrélation négative écarté.
    assert "badmon" not in sp["teammates"]
    # Coéquipiers normalisés en relatif (le plus fréquent = 1.0).
    assert sp["teammates"]["rillaboom"] == 1.0


def test_natures_from_spreads():
    sp = from_showdown_chaos(CHAOS)["incineroar"]
    assert sp["natures"]["careful"] == 0.45         # 450/1000
    assert set(sp["natures"]) == {"careful", "adamant", "impish"}


def test_ids_are_showdown_style():
    sp = from_showdown_chaos(CHAOS)["incineroar"]
    assert "knockoff" in sp["moves"]                # « Knock Off » -> knockoff
    assert "safetygoggles" in sp["items"]


def test_build_usage_has_meta_and_species():
    doc = build_usage(CHAOS, source="test")
    assert doc["_meta"]["format"] == "showdown-chaos"
    assert "incineroar" in doc["species"]


def test_weighted_counts_use_ability_sum_not_raw_count():
    # Cas réel : les sous-comptes sont *pondérés* et bien plus petits que le
    # « Raw count » non pondéré. Le dénominateur doit être la somme des talents
    # (total pondéré), sinon toutes les probabilités sont sous-estimées.
    chaos = {
        "data": {
            "Garchomp": {
                "Raw count": 1_000_000, "usage": 0.36,
                "Abilities": {"Rough Skin": 90_000, "Sand Veil": 10_000},
                "Items": {"Choice Scarf": 28_000, "Sitrus Berry": 27_000},
                "Moves": {"Earthquake": 88_000, "Dragon Claw": 70_000},
                "Spreads": {"Jolly:4/252/0/0/0/252": 60_000},
                "Teammates": {},
            },
        },
    }
    sp = from_showdown_chaos(chaos)["garchomp"]
    # denom = 90000 + 10000 = 100000 (pondéré), pas 1_000_000.
    assert sp["abilities"]["roughskin"] == 0.9
    assert sp["items"]["choicescarf"] == 0.28
    assert sp["moves"]["earthquake"] == 0.88
    assert sp["natures"]["jolly"] == 0.6


def test_import_from_file_writes_loadable_table(tmp_path):
    src = tmp_path / "chaos.json"
    src.write_text(json.dumps(CHAOS), encoding="utf-8")
    out = tmp_path / "reg.json"
    import_usage(str(src), out_path=out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["species"]["incineroar"]["moves"]["fakeout"] == 0.95
