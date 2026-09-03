"""Importeur de stats d'usage (§0.2) — partie « réseau ».

Récupère des statistiques d'usage agrégées et les convertit au format local
(`data/usage/<reg>.json`, voir `usage.py`). Le format d'entrée privilégié est
le **JSON « chaos » de Pokémon Showdown / Smogon** (le standard de fait des
stats d'usage), structuré ainsi :

    { "info": {...},
      "data": {
        "Incineroar": {
          "Raw count": 12345,
          "usage": 0.42,
          "Abilities": {"Intimidate": 12000, ...},
          "Items":     {"Assault Vest": 4000, ...},
          "Moves":     {"Fake Out": 11000, "": 200, ...},
          "Spreads":   {"Careful:252/0/.../4": 3000, ...},
          "Teammates": {"Rillaboom": 1500, ...}
        }, ...
      } }

Les comptes bruts sont normalisés en probabilités conditionnelles (divisées par
le `Raw count` de l'espèce). Sortie alignée sur `usage.py`.

⚠️ Réseau : `fetch()` utilise `urllib` (et respecte les variables de proxy de
l'environnement). Sur un environnement sans accès aux sites de stats, lancer
l'import depuis un **fichier déjà téléchargé** plutôt qu'une URL.

Usage :
    python -m simupoke.usage_import <url|fichier.json> [--reg reg_m_b]
    # ex. Showdown : .../stats/2024-XX/chaos/gen9vgc2024-1760.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.request import urlopen

from .basestats import to_id
from .usage import usage_path

# Seuils de filtrage (garde la sortie compacte et lisible).
_MIN_PCT = 0.03
_TOP = {"items": 6, "abilities": 4, "moves": 10, "natures": 4, "teammates": 6}
# Clés « vides » à ignorer (emplacement de move/objet non renseigné).
_EMPTY = {"", "nothing", "none", "other"}


def fetch(url: str, timeout: float = 30.0) -> str:
    """Télécharge le contenu texte d'une URL (proxy-aware via l'environnement)."""
    with urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _pct(counts: dict[str, float], denom: float, *, top: int) -> dict[str, float]:
    """Normalise des comptes bruts en probabilités, filtre et tronque au top N."""
    if denom <= 0:
        return {}
    out: list[tuple[str, float]] = []
    for k, v in counts.items():
        if to_id(k) in _EMPTY or v <= 0:
            continue
        p = v / denom
        if p >= _MIN_PCT:
            out.append((to_id(k), round(p, 4)))
    out.sort(key=lambda kv: -kv[1])
    return dict(out[:top])


def _natures_from_spreads(spreads: dict[str, float], denom: float) -> dict[str, float]:
    """Agrège les natures depuis les clés de spread « Nature:ev/ev/... »."""
    agg: dict[str, float] = {}
    for key, v in spreads.items():
        nature = key.split(":", 1)[0]
        agg[nature] = agg.get(nature, 0.0) + v
    return _pct(agg, denom, top=_TOP["natures"])


def _teammates(counts: dict[str, float], top: int) -> dict[str, float]:
    """Coéquipiers : déltas de corrélation -> poids relatifs 0..1 (positifs)."""
    pos = {to_id(k): v for k, v in counts.items() if v > 0 and to_id(k) not in _EMPTY}
    if not pos:
        return {}
    hi = max(pos.values())
    out = sorted(((k, round(v / hi, 4)) for k, v in pos.items()), key=lambda kv: -kv[1])
    return dict(out[:top])


def from_showdown_chaos(obj: dict) -> dict[str, dict]:
    """Convertit un JSON « chaos » Showdown en table d'usage (format local)."""
    data = obj.get("data", obj)            # tolère un dict déjà « data »
    species: dict[str, dict] = {}
    for name, d in data.items():
        # Dans le format chaos, Items/Abilities/Moves/Spreads sont *pondérés*
        # (weighted), alors que « Raw count » est *non pondéré*. Le bon
        # dénominateur pour des probabilités conditionnelles est donc le total
        # pondéré de l'espèce = somme des talents (chaque set a exactement un
        # talent). On ne retombe sur « Raw count » que si les talents manquent.
        denom = sum(
            v for v in d.get("Abilities", {}).values() if v > 0
        ) or float(d.get("Raw count") or 0)
        entry = {
            "usage": round(float(d.get("usage", 0.0)), 4),
            "items": _pct(d.get("Items", {}), denom, top=_TOP["items"]),
            "abilities": _pct(d.get("Abilities", {}), denom, top=_TOP["abilities"]),
            "moves": _pct(d.get("Moves", {}), denom, top=_TOP["moves"]),
            "natures": _natures_from_spreads(d.get("Spreads", {}), denom),
            "teammates": _teammates(d.get("Teammates", {}), _TOP["teammates"]),
        }
        species[to_id(name)] = entry
    return species


def build_usage(obj: dict, *, source: str = "import") -> dict:
    """Construit le document d'usage complet (avec _meta) à partir d'un chaos."""
    return {
        "_meta": {
            "source": source,
            "format": "showdown-chaos",
            "note": "Généré par simupoke.usage_import. Comptes normalisés en probabilités.",
        },
        "species": from_showdown_chaos(obj),
    }


def import_usage(source: str, reg_id: str = "reg_m_b",
                 out_path: Path | None = None) -> Path:
    """Importe depuis une URL ou un fichier local et écrit data/usage/<reg>.json."""
    if source.startswith(("http://", "https://")):
        text = fetch(source)
    else:
        text = Path(source).read_text(encoding="utf-8")
    obj = json.loads(text)
    doc = build_usage(obj, source=source)
    out = Path(out_path) if out_path else usage_path(reg_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Importeur de stats d'usage (Showdown chaos)")
    p.add_argument("source", help="URL ou chemin d'un JSON chaos")
    p.add_argument("--reg", default="reg_m_b", help="identifiant de régulation")
    p.add_argument("--out", default=None, help="chemin de sortie (sinon data/usage/<reg>.json)")
    args = p.parse_args(argv)
    try:
        out = import_usage(args.source, args.reg, args.out)
    except Exception as exc:
        print(f"Échec de l'import : {exc}", file=sys.stderr)
        return 1
    doc = json.loads(out.read_text(encoding="utf-8"))
    print(f"Importé {len(doc['species'])} espèces -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
