"""Chargement des données versionnées (roster perso + régulation).

Stockage = fichiers JSON versionnés (§7.3, §12). Aucune dépendance externe en
Phase 0 : on lit ce qui se trouve dans `data/`.
"""

from __future__ import annotations

import json
from pathlib import Path

from .model import OwnedPokemon
from .paths import DATA_DIR  # ré-exporté : plusieurs modules l'importent d'ici


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Mon Box
# ---------------------------------------------------------------------------

def _parse_owned(entry: dict) -> OwnedPokemon:
    """Construit un OwnedPokemon depuis une entrée JSON (schéma my_roster)."""
    return OwnedPokemon(
        species=entry["species"],
        nature=entry["nature"],
        stat_points=entry.get("stat_points", {}),
        item=entry.get("item"),
        ability=entry.get("ability"),
        moves=entry.get("moves", []),
        status_ownership=entry.get("status_ownership", "permanent"),
        trial_expires_in_days=entry.get("trial_expires_in_days"),
        source=entry.get("source", "ranch"),
        is_shiny=entry.get("is_shiny", False),
        has_title=entry.get("has_title", False),
        display_fr=entry.get("display_fr"),
    )


def load_my_roster(path: str | Path | None = None) -> list[OwnedPokemon]:
    """Charge « mon Box » depuis un JSON (clé `owned`).

    Les clés `_help`/`_*` sont ignorées (documentation du schéma).
    """
    path = Path(path) if path else DATA_DIR / "my_roster.json"
    raw = _read_json(path)
    return [_parse_owned(e) for e in raw.get("owned", [])]


def load_lineup(path: str | Path) -> list[OwnedPokemon]:
    """Charge un lineup de tirage (clé `lineup`) — même schéma que `owned`.

    Les builds préréglés du jour sont représentés comme des OwnedPokemon
    (statut d'ownership ignoré ici).
    """
    raw = _read_json(Path(path))
    entries = raw.get("lineup", raw.get("owned", []))
    return [_parse_owned(e) for e in entries]


def load_team(path: str | Path) -> list[OwnedPokemon]:
    """Charge une équipe (clé `team`, à défaut `lineup`/`owned`)."""
    raw = _read_json(Path(path))
    entries = raw.get("team", raw.get("lineup", raw.get("owned", [])))
    return [_parse_owned(e) for e in entries]


# ---------------------------------------------------------------------------
# Régulation courante
# ---------------------------------------------------------------------------

def load_regulation(reg_id: str = "reg_m_b") -> dict[str, dict]:
    """Charge les fichiers de données d'une régulation (§7.3).

    Renvoie un dict { 'roster': ..., 'abilities': ..., 'items': ...,
    'moves_overrides': ..., 'clauses': ... }. Les fichiers absents sont omis.
    """
    reg_dir = DATA_DIR / reg_id
    if not reg_dir.is_dir():
        raise FileNotFoundError(f"Régulation introuvable : {reg_dir}")
    files = {
        "roster": "roster.json",
        "abilities": "abilities.json",
        "moves_overrides": "moves_overrides.json",
        "items": "items.json",
        "clauses": "clauses.json",
    }
    out: dict[str, dict] = {}
    for key, fname in files.items():
        fpath = reg_dir / fname
        if fpath.exists():
            out[key] = _read_json(fpath)
    return out
