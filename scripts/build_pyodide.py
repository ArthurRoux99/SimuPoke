#!/usr/bin/env python3
"""Assemble la preuve de concept **Pyodide** dans `web/pyodide/dist/`.

Prépare un dossier statique **auto-suffisant** qui fait tourner le moteur
Python de SimuPoke *dans le navigateur* (WASM), sans port JS :

- construit la wheel pure-Python du paquet `simupoke` (`pip wheel`) ;
- copie les données de jeu nécessaires au calc (`pokedex`/`moves`/`typechart`
  + la régulation courante) sous `dist/data/` ;
- copie la page `index.html` ;
- écrit `dist/manifest.json` (nom de la wheel + liste des fichiers data) que la
  page lit au démarrage.

Servir ensuite le dossier (n'importe quel serveur statique) :

    python scripts/build_pyodide.py
    python -m http.server -d web/pyodide/dist 8123
    # puis ouvrir http://127.0.0.1:8123

Aucune dépendance hors stdlib + `pip` (déjà présent). La wheel et `dist/` sont
gitignorés : seuls la page et ce script sont versionnés.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "pyodide"
DIST = WEB / "dist"
DATA = ROOT / "data"

# Fichiers de données requis par le calc de dégâts (delta Champions inclus).
DATA_FILES = [
    "pokedex.json",
    "moves.json",
    "typechart.json",
    "reg_m_b/abilities.json",
    "reg_m_b/items.json",
    "reg_m_b/moves_overrides.json",
    "reg_m_b/roster.json",
    "reg_m_b/clauses.json",
]


def _build_wheel() -> str:
    """Construit la wheel pure-Python et renvoie son nom de fichier."""
    DIST.mkdir(parents=True, exist_ok=True)
    # `pip wheel` n'a besoin d'aucune dépendance de build supplémentaire.
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(ROOT),
         "--no-deps", "--wheel-dir", str(DIST)],
        check=True,
    )
    wheels = sorted(DIST.glob("simupoke-*.whl"))
    if not wheels:
        raise SystemExit("Échec : aucune wheel produite.")
    # Ne garder que la plus récente (nettoie les builds précédents).
    latest = wheels[-1]
    for w in wheels[:-1]:
        w.unlink()
    return latest.name


def build() -> Path:
    if DIST.exists():
        shutil.rmtree(DIST)
    wheel = _build_wheel()

    for rel in DATA_FILES:
        src = DATA / rel
        if not src.exists():
            raise SystemExit(f"Donnée manquante : {src} (régénère data/ ?).")
        dst = DIST / "data" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    shutil.copyfile(WEB / "index.html", DIST / "index.html")

    manifest = {"wheel": wheel, "data": DATA_FILES}
    (DIST / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    total_kb = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1024
    print(f"Assemblé {DIST.relative_to(ROOT)} — wheel {wheel}, "
          f"{len(DATA_FILES)} fichiers data, {total_kb:.0f} Ko au total.")
    return DIST


if __name__ == "__main__":
    build()
