"""Tests de l'analyse offensive Doubles (matrice de menaces 2v2)."""

from __future__ import annotations

from simupoke.doubles import analyze_doubles
from simupoke.model import FieldState, PokemonState


def _p(species, nature="serious", moves=None, sp=None, item=None, hp=1.0):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        moves=moves or [], item=item, current_hp_pct=hp)


def test_focus_fire_ko_detected():
    # Deux attaquants qui, combinés, garantissent un KO sur une cible robuste.
    mine = [_p("garchomp", "jolly", ["dragonclaw"], {"atk": 32}, item="choiceband"),
            _p("incineroar", "adamant", ["flareblitz"], {"atk": 32})]
    opp = [_p("landorustherian", "jolly", ["earthquake"], {"atk": 32, "spe": 32})]
    rep = analyze_doubles(mine, opp, FieldState())
    t = rep.targets[0]
    assert len(t.hits) == 2
    assert t.focus_ko is True                      # focus fire = KO garanti
    assert sum(h.min_dmg for h in t.hits) >= t.hp


def test_single_move_ko_flagged():
    mine = [_p("garchomp", "jolly", ["earthquake"], {"atk": 32}, item="choiceband")]
    opp = [_p("fluttermane", "timid", ["moonblast"], {"spa": 32, "spe": 32})]
    rep = analyze_doubles(mine, opp, FieldState())
    hit = rep.targets[0].hits[0]
    assert hit.ko is True                          # EQ OHKO un Flutter Mane frêle


def test_immunity_gives_zero_and_no_ko():
    # Séisme (Sol) sur Landorus-Therian (Vol) : 0 dégât, pas de menace.
    mine = [_p("garchomp", "jolly", ["earthquake"], {"atk": 32})]
    opp = [_p("landorustherian", "jolly", ["uturn"])]
    rep = analyze_doubles(mine, opp, FieldState())
    hit = rep.targets[0].hits[0]
    assert hit.max_pct == 0.0 and hit.ko is False


def test_spread_move_listed_with_penalty():
    mine = [_p("garchomp", "jolly", ["rockslide", "dragonclaw"], {"atk": 32})]
    opp = [_p("fluttermane", "timid", ["moonblast"], {"spa": 32}),
           _p("tornadustherian", "timid", ["hurricane"], {"spa": 32})]
    rep = analyze_doubles(mine, opp, FieldState())
    # Rock Slide (zone) doit apparaître avec un dégât par cible.
    rs = [s for s in rep.spreads if s.move == "Rock Slide"]
    assert rs and len(rs[0].per_target) == 2
