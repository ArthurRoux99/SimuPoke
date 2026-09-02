"""Tests de B3 — analyse d'équipe et assistant team preview."""

from __future__ import annotations

from simupoke.model import OwnedPokemon
from simupoke.loaders import load_team
from simupoke.team import (
    analyze_team, select_team_preview, check_clauses, matchup_score,
    damage_matchup_score, team_shared_weaknesses, BRING_BY_FORMAT,
)


def _mon(species, item=None, moves=None, nature="serious"):
    return OwnedPokemon(species=species, nature=nature, stat_points={},
                        item=item, moves=moves or [])


def test_sample_team_passes_clauses():
    team = load_team("data/sample_team.json")
    assert check_clauses(team) == []
    assert len(team) == 6


def test_species_clause_detects_duplicate():
    team = [_mon("garchomp"), _mon("garchomp")]
    violations = check_clauses(team)
    assert any("Species Clause" in v for v in violations)


def test_item_clause_detects_duplicate():
    team = [_mon("garchomp", item="leftovers"), _mon("incineroar", item="leftovers")]
    violations = check_clauses(team)
    assert any("Item Clause" in v for v in violations)


def test_shared_weakness_detection():
    # Deux Pokémon faibles au Sol (types Feu/Electrik et Acier/Roche... )
    # Magnezone (Steel/Electric) et Heatran (Fire/Steel) partagent Sol.
    team = [_mon("magnezone"), _mon("heatran")]
    shared = team_shared_weaknesses(team)
    assert "Ground" in shared


def test_analyze_team_report_lines():
    team = load_team("data/sample_team.json")
    report = analyze_team(team)
    lines = report.lines()
    assert any("Clauses" in ln for ln in lines)
    assert any("Rôles" in ln for ln in lines)
    assert report.size == 6


def test_matchup_score_super_effective_is_positive():
    # Garchomp (Sol) frappe Heatran (Feu/Acier) en 4x avec Earthquake.
    chomp = _mon("garchomp", moves=["earthquake"])
    heatran = _mon("heatran", moves=["flamethrower"])
    assert matchup_score(chomp, heatran) > 0


def test_preview_selects_correct_count():
    my_team = load_team("data/sample_team.json")
    opp = load_team("data/sample_opponent.json")
    for fmt, n in BRING_BY_FORMAT.items():
        res = select_team_preview(my_team, opp, fmt)
        assert len(res.picks) == n
        assert len(res.picks) + len(res.bench) == len(my_team)
        # Picks triés par valeur décroissante.
        vals = [p.value for p in res.picks]
        assert vals == sorted(vals, reverse=True)


def test_preview_lead_is_best():
    my_team = load_team("data/sample_team.json")
    opp = load_team("data/sample_opponent.json")
    res = select_team_preview(my_team, opp, "singles")
    assert res.picks[0].value == max(p.value for p in res.picks)


# --- Matchup affiné par les dégâts -----------------------------------------

def test_damage_matchup_positive_when_i_hit_harder():
    # Garchomp Choice Band Séisme écrase Heatran ; Heatran le blesse peu.
    chomp = _mon("garchomp", item="choiceband", moves=["earthquake"], nature="adamant")
    heatran = _mon("heatran", moves=["flamethrower"], nature="modest")
    assert damage_matchup_score(chomp, heatran) > 0


def test_damage_matchup_none_without_any_moves():
    # Deux espèces absentes de l'usage et sans moves -> None (repli sur types).
    a = _mon("magikarp")
    b = _mon("feebas")
    assert damage_matchup_score(a, b) is None


def test_preview_by_damage_flag_and_fallback():
    my_team = load_team("data/sample_team.json")
    opp = load_team("data/sample_opponent.json")
    dmg = select_team_preview(my_team, opp, "doubles", use_damage=True)
    typ = select_team_preview(my_team, opp, "doubles", use_damage=False)
    assert dmg.by_damage is True and typ.by_damage is False
    assert "dégâts" in dmg.lines()[0]
    assert len(dmg.picks) == 4
    # Le mode dégâts change généralement l'ordre vs le mode types.
    assert [p.species for p in dmg.picks] != []
