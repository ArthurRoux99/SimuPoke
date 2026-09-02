"""Tests de la couche d'affichage / i18n (§0.5) — bascule FR/EN effective."""

from __future__ import annotations

import pytest

from simupoke import i18n
from simupoke.i18n import label, stat_label, set_language, get_language


@pytest.fixture(autouse=True)
def _restore_lang():
    # Chaque test repart en FR (état de processus).
    yield
    set_language("fr")


def test_default_is_french():
    assert get_language() == "fr"
    assert label("species", "garchomp") == "Carchacrok"
    assert label("nature", "jolly") == "Jovial"
    assert stat_label("spa") == "Atq. Spé."


def test_english_toggle_uses_data_names_not_french():
    set_language("en")
    assert label("species", "garchomp") == "Garchomp"      # pas « Carchacrok »
    assert label("nature", "jolly") == "Jolly"
    assert stat_label("spa") == "Sp. Atk"


def test_untranslated_french_falls_back_to_data_english():
    # Espèce sans traduction FR -> nom anglais du Pokédex (pas l'ID brut).
    assert label("species", "pikachu") == "Pikachu"
    # Nature complète en FR désormais.
    assert label("nature", "bashful") == "Pudique"


def test_explicit_lang_overrides_current():
    set_language("fr")
    assert label("species", "tyranitar", lang="en") == "Tyranitar"
    assert label("species", "tyranitar", lang="fr") == "Tyranocif"


def test_moves_are_english_in_both_langs():
    # Les capacités n'ont que des noms anglais (données) : cohérent FR/EN.
    assert label("move", "earthquake") == "Earthquake"
    set_language("en")
    assert label("move", "earthquake") == "Earthquake"


def test_item_ability_prettified():
    set_language("en")
    assert label("item", "lifeorb") == "Lifeorb"
    assert label("ability", "roughskin") == "Roughskin"


def test_set_language_normalises():
    set_language("English")
    assert get_language() == "en"
    set_language("fr-FR")
    assert get_language() == "fr"
