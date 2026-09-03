#!/usr/bin/env python3
"""Assemble l'app SimuPoke **hors-ligne dans le navigateur** (`web/pyodide/dist/`).

Le moteur Python (calc + delta, B1/B2/B3, seuils, recherche) tourne côté client
via **Pyodide** (WASM) — plus de serveur, plus de port JS. Deux pages :

- ``index.html`` — l'**application complète** : le frontend hébergé
  (`web/server/`) dont les appels ``/api/*`` sont routés vers le dispatcher
  Python par ``web/pyodide/bootstrap.js`` (shim de ``fetch``).
- ``parity.html`` — la preuve de parité du moteur (calc vs valeurs de référence).

Ce que fait ce script :

- construit la wheel pure-Python de `simupoke` (`pip wheel`) ;
- copie les données de jeu sous ``dist/data/`` (jamais ``my_roster.json`` : perso) ;
- copie la feuille de style et `app.js` sous ``dist/static/``, plus le bootstrap ;
- compose ``dist/index.html`` depuis ``web/server/index.html`` (chemins relatifs
  + injection de Pyodide et du bootstrap) et copie ``parity.html`` ;
- écrit ``dist/manifest.json`` (wheel + liste des fichiers data).

Servir ensuite (n'importe quel serveur statique) :

    python scripts/build_pyodide.py
    python -m http.server -d web/pyodide/dist 8123   # http://127.0.0.1:8123

Stdlib + `pip` seulement. ``dist/`` et ``*.whl`` sont gitignorés.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_icons import make_icons

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PYO = WEB / "pyodide"
DIST = PYO / "dist"
DATA = ROOT / "data"

PYODIDE_CDN = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js"

# Données requises par l'app entière (calc + B1/B2/B3 + usage + exemples).
# my_roster.json est VOLONTAIREMENT exclu (personnel, §3) : « Mon Box » démarre
# vide côté navigateur.
DATA_FILES = [
    "pokedex.json", "moves.json", "typechart.json",
    "reg_m_b/abilities.json", "reg_m_b/items.json", "reg_m_b/moves_overrides.json",
    "reg_m_b/roster.json", "reg_m_b/clauses.json",
    "usage/reg_m_b.json",
    "sample_team.json", "sample_opponent.json", "sample_lineup.json",
]


def _build_wheel() -> str:
    DIST.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(ROOT),
         "--no-deps", "--wheel-dir", str(DIST)],
        check=True,
    )
    wheels = sorted(DIST.glob("simupoke-*.whl"))
    if not wheels:
        raise SystemExit("Échec : aucune wheel produite.")
    latest = wheels[-1]
    for w in wheels[:-1]:
        w.unlink()
    return latest.name


def _compose_app() -> None:
    """Compose dist/index.html depuis le frontend hébergé + bootstrap Pyodide."""
    html = (WEB / "server" / "index.html").read_text(encoding="utf-8")
    html = html.replace("/static/", "./static/")

    # En-tête PWA (manifest, thème, icône iOS, mode application plein écran).
    head = (
        '<link rel="manifest" href="./manifest.webmanifest">\n'
        '<meta name="theme-color" content="#0E141B">\n'
        '<link rel="apple-touch-icon" href="./icon-192.png">\n'
        '<meta name="apple-mobile-web-app-capable" content="yes">\n'
        '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">\n'
        '<meta name="apple-mobile-web-app-title" content="SimuPoke">\n'
    )
    vp = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    if vp not in html:
        raise SystemExit("Gabarit inattendu : balise viewport introuvable.")
    html = html.replace(vp, vp + "\n" + head)

    inject = (f'<script src="{PYODIDE_CDN}"></script>\n'
              '<script src="./bootstrap.js"></script>\n')
    marker = '<script src="./static/app.js"></script>'
    if marker not in html:
        raise SystemExit("Gabarit inattendu : balise app.js introuvable.")
    html = html.replace(marker, inject + marker)
    (DIST / "index.html").write_text(html, encoding="utf-8")


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

    static = DIST / "static"
    static.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(WEB / "style.css", static / "style.css")
    shutil.copyfile(WEB / "server" / "app.js", static / "app.js")
    shutil.copyfile(PYO / "bootstrap.js", DIST / "bootstrap.js")
    shutil.copyfile(PYO / "parity.html", DIST / "parity.html")
    shutil.copyfile(PYO / "manifest.webmanifest", DIST / "manifest.webmanifest")
    shutil.copyfile(PYO / "sw.js", DIST / "sw.js")
    make_icons(DIST)  # icon-192.png / icon-512.png (PWA)
    _compose_app()

    (DIST / "manifest.json").write_text(
        json.dumps({"wheel": wheel, "data": DATA_FILES}, indent=2),
        encoding="utf-8")

    total_kb = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1024
    print(f"Assemblé {DIST.relative_to(ROOT)} — app + parité, wheel {wheel}, "
          f"{len(DATA_FILES)} fichiers data, {total_kb:.0f} Ko au total.")
    return DIST


if __name__ == "__main__":
    build()
