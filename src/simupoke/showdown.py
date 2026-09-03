"""Import / export au format « Showdown paste » (§0.5, confort de saisie).

Le format texte de Pokémon Showdown est le standard de fait pour partager une
équipe. Ce module le **parse** en `OwnedPokemon` et le **regénère**, en faisant
le pont avec le modèle Champions :

  - **EV ⇄ SP** : Champions remplace les EV par des SP (§8.3, 1 SP ≈ 8 EV). À
    l'import on convertit `SP = round(EV / 8)` (plafonné à 32) ; à l'export
    l'inverse `EV = SP × 8`. La `validate()` d'OwnedPokemon signalera un spread
    hors budget (66) le cas échéant.
  - **IV / Niveau** : ignorés (toujours 31 / 50 en Champions).
  - **Tera Type** : parsé mais informatif (absent de Champions au lancement, §4.6).

Exemple accepté ::

    Garchomp @ Life Orb
    Ability: Rough Skin
    Level: 50
    EVs: 4 HP / 252 Atk / 252 Spe
    Adamant Nature
    - Earthquake
    - Dragon Claw
"""

from __future__ import annotations

import re

from .basestats import get_species, is_known, to_id
from .model import OwnedPokemon
from .moves import get_move
from .moves import is_known as move_known

# Libellés de stats Showdown -> clés internes.
_EV_KEYS = {"hp": "hp", "atk": "atk", "def": "def", "spa": "spa",
            "spd": "spd", "spe": "spe"}
_STAT_ORDER = [("hp", "HP"), ("atk", "Atk"), ("def", "Def"),
               ("spa", "SpA"), ("spd", "SpD"), ("spe", "Spe")]

_NATURES = {
    "hardy", "lonely", "brave", "adamant", "naughty", "bold", "docile",
    "relaxed", "impish", "lax", "timid", "hasty", "serious", "jolly", "naive",
    "modest", "mild", "quiet", "bashful", "rash", "calm", "gentle", "sassy",
    "careful", "quirky",
}

_EV_TO_SP_DIV = 8            # 1 SP ≈ 8 EV (§8.3)
_SP_CAP = 32


def ev_to_sp(ev: int) -> int:
    return min(_SP_CAP, round(ev / _EV_TO_SP_DIV))


def sp_to_ev(sp: int) -> int:
    return sp * _EV_TO_SP_DIV


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _parse_header(line: str) -> tuple[str, str | None]:
    """Extrait (espèce, objet) de la 1re ligne d'un bloc."""
    item = None
    if "@" in line:
        line, _, item_part = line.partition("@")
        item = item_part.strip() or None
    line = line.strip()
    # Retire un genre final « (M) » / « (F) ».
    line = re.sub(r"\s*\((?:M|F)\)\s*$", "", line).strip()
    # « Surnom (Espèce) » -> l'espèce est entre parenthèses.
    m = re.match(r"^.*\(([^)]+)\)\s*$", line)
    species = m.group(1).strip() if m else line
    return species, item


def parse_pokemon(block: str) -> OwnedPokemon | None:
    """Parse un bloc (un Pokémon). Renvoie None si le bloc est vide."""
    lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return None
    species, item = _parse_header(lines[0])
    ability = None
    nature = "serious"
    sp: dict[str, int] = {}
    moves: list[str] = []
    is_shiny = False

    for ln in lines[1:]:
        s = ln.strip()
        low = s.lower()
        if s.startswith("-"):
            mv = s[1:].strip()
            if mv:
                moves.append(mv)
        elif low.startswith("ability:"):
            ability = s.split(":", 1)[1].strip() or None
        elif low.startswith("evs:"):
            for part in s.split(":", 1)[1].split("/"):
                mt = re.match(r"\s*(\d+)\s+([A-Za-z]+)", part)
                if mt:
                    key = _EV_KEYS.get(mt.group(2).lower())
                    if key:
                        sp[key] = ev_to_sp(int(mt.group(1)))
        elif low.startswith(("ivs:", "level:", "tera type:", "happiness:",
                             "gigantamax:", "dynamax level:", "hidden power:")):
            continue
        elif low.startswith("shiny:"):
            is_shiny = "yes" in low
        elif low.endswith("nature"):
            cand = low.replace("nature", "").strip()
            if cand in _NATURES:
                nature = cand

    return OwnedPokemon(
        species=to_id(species), nature=nature, stat_points=sp,
        item=to_id(item) if item else None,
        ability=to_id(ability) if ability else None,
        moves=[to_id(m) for m in moves], is_shiny=is_shiny)


def parse_team(text: str) -> list[OwnedPokemon]:
    """Parse un paste complet (plusieurs blocs séparés par une ligne vide)."""
    blocks = re.split(r"\n\s*\n", text.strip())
    out: list[OwnedPokemon] = []
    for b in blocks:
        mon = parse_pokemon(b)
        if mon is not None:
            out.append(mon)
    return out


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _display_species(sid: str) -> str:
    return get_species(sid).get("name", sid) if is_known(sid) else sid


def _display_move(mid: str) -> str:
    try:
        return get_move(mid).name if move_known(mid) else mid
    except KeyError:
        return mid


def _prettify(idstr: str) -> str:
    """Approche « joli » d'un id (objet/talent) : mots capitalisés."""
    return " ".join(w.capitalize() for w in re.split(r"[\s_]+", idstr)) if idstr else ""


def format_pokemon(mon: OwnedPokemon) -> str:
    head = _display_species(mon.species)
    if mon.item:
        head += f" @ {_prettify(mon.item)}"
    lines = [head]
    if mon.ability:
        lines.append(f"Ability: {_prettify(mon.ability)}")
    lines.append("Level: 50")
    # Export : on plafonne à 252 (limite Showdown ; 32 SP ≈ 256 EV-équivalent).
    evs = [(min(252, sp_to_ev(mon.stat_points.get(k, 0))), lab)
           for k, lab in _STAT_ORDER]
    ev_str = " / ".join(f"{v} {lab}" for v, lab in evs if v)
    if ev_str:
        lines.append(f"EVs: {ev_str}")
    if mon.nature and mon.nature != "serious":
        lines.append(f"{mon.nature.capitalize()} Nature")
    for mv in mon.moves:
        lines.append(f"- {_display_move(mv)}")
    return "\n".join(lines)


def format_team(mons: list[OwnedPokemon]) -> str:
    return "\n\n".join(format_pokemon(m) for m in mons)
