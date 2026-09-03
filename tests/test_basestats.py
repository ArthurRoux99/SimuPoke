"""Tests de la couche base stats (source réelle : data/pokedex.json)."""

from __future__ import annotations

import pytest

from simupoke.basestats import (
    get_base_stats,
    get_species,
    get_types,
    is_known,
    to_id,
)


def test_to_id_normalisation():
    assert to_id("Tyranitar") == "tyranitar"
    assert to_id("Mr. Mime") == "mrmime"
    assert to_id("Tyranitar-Mega") == "tyranitarmega"
    assert to_id("Type: Null") == "typenull"


def test_base_stats_match_reference():
    # Valeurs canoniques (identiques en Champions, §4.3).
    assert get_base_stats("tyranitar") == {
        "hp": 100, "atk": 134, "def": 110, "spa": 95, "spd": 100, "spe": 61,
    }
    assert get_base_stats("garchomp")["spe"] == 102
    assert get_base_stats("incineroar")["atk"] == 115


def test_mega_form_has_own_stats():
    base = get_base_stats("tyranitar")
    mega = get_base_stats("tyranitarmega")
    assert mega["atk"] > base["atk"]   # 164 > 134
    assert mega["def"] > base["def"]   # 150 > 110


def test_lookup_is_name_insensitive():
    assert get_base_stats("Tyranitar") == get_base_stats("tyranitar")
    assert get_base_stats("Mr. Mime")["spd"] == 120


def test_types_available():
    assert get_types("tyranitar") == ["Rock", "Dark"]
    assert get_types("incineroar") == ["Fire", "Dark"]


def test_coverage_is_broad():
    # On a basculé du stub (3 espèces) à une vraie source : beaucoup d'espèces.
    assert is_known("landorustherian")
    assert is_known("greatTusk".lower())
    assert is_known("fluttermane")


def test_unknown_species_raises_explicit():
    assert not is_known("notapokemon")
    with pytest.raises(KeyError, match="Espèce inconnue"):
        get_base_stats("notapokemon")


def test_species_record_fields():
    rec = get_species("tyranitar")
    assert rec["num"] == 248
    assert rec["name"] == "Tyranitar"
    assert set(rec["baseStats"]) == {"hp", "atk", "def", "spa", "spd", "spe"}
