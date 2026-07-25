#!/usr/bin/env python3
"""Construit l'UI HTML autonome (un seul fichier) à partir de web/ + data/.

Inline le CSS, les données (pokedex/moves/typechart + carte -ate de la
régulation) et le moteur/app JS dans web/dist/simupoke.html. Le fichier produit
fonctionne hors-ligne, sans serveur (§12 « page HTML autonome »).

Aucune dépendance externe (stdlib seule).

    python scripts/build_web.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DATA = ROOT / "data"
DIST = WEB / "dist"


def _compact_pokedex() -> dict:
    """Pokédex réduit aux champs utiles à l'UI (allège le fichier)."""
    full = json.loads((DATA / "pokedex.json").read_text(encoding="utf-8"))["species"]
    return {sid: {"name": s["name"], "types": s["types"], "baseStats": s["baseStats"]}
            for sid, s in full.items()}


def _compact_moves() -> dict:
    full = json.loads((DATA / "moves.json").read_text(encoding="utf-8"))["moves"]
    return {mid: {"name": m["name"], "type": m["type"], "category": m["category"],
                  "basePower": m["basePower"], "isSpread": m.get("isSpread", False)}
            for mid, m in full.items()}


def _ate_map() -> dict:
    abilities = json.loads((DATA / "reg_m_b" / "abilities.json").read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for ab in abilities.get("abilities", []):
        params = ab.get("params") or {}
        if params.get("from_type") == "Normal" and params.get("to_type"):
            out[ab["id"]] = params["to_type"]
    return out


def build() -> Path:
    template = (WEB / "index.html").read_text(encoding="utf-8")
    style = (WEB / "style.css").read_text(encoding="utf-8")
    engine = (WEB / "engine.js").read_text(encoding="utf-8")
    bench = (WEB / "bench.js").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")

    data = {
        "pokedex": _compact_pokedex(),
        "moves": _compact_moves(),
        "typechart": json.loads((DATA / "typechart.json").read_text(encoding="utf-8"))["chart"],
        "ateMap": _ate_map(),
    }
    data_js = "window.SIMUPOKE_DATA=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";"

    html = (template
            .replace("/* @STYLE */", style)
            .replace("/* @DATA */", data_js)
            .replace("/* @ENGINE */", engine)
            .replace("/* @BENCH */", bench)
            .replace("/* @APP */", app))

    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / "simupoke.html"
    out.write_text(html, encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"Écrit {out.relative_to(ROOT)} ({kb:.0f} Ko, "
          f"{len(data['pokedex'])} espèces, {len(data['moves'])} capacités).")
    return out


if __name__ == "__main__":
    build()
