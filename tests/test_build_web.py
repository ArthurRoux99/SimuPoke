"""Test léger du builder de l'UI autonome.

Vérifie que le build produit un fichier HTML autonome contenant les données
embarquées et le moteur, et que la carte -ate de Champions y figure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_web  # noqa: E402


def test_build_produces_standalone_html():
    out = build_web.build()
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    # Tout est inliné : plus de placeholders.
    assert "/* @DATA */" not in html
    assert "/* @ENGINE */" not in html
    assert "/* @APP */" not in html
    # Données embarquées + moteur présents.
    assert "window.SIMUPOKE_DATA=" in html
    assert "makeEngine" in html


def test_ate_map_includes_dragonize():
    # Le delta Champions (catégorie B) doit être présent dans les données embarquées.
    assert build_web._ate_map().get("dragonize") == "Dragon"


def test_compact_data_keeps_required_fields():
    dex = build_web._compact_pokedex()
    ttar = dex["tyranitar"]
    assert ttar["baseStats"]["atk"] == 134
    assert ttar["types"] == ["Rock", "Dark"]
    moves = build_web._compact_moves()
    assert moves["earthquake"]["basePower"] == 100
    assert moves["earthquake"]["category"] == "Physical"
