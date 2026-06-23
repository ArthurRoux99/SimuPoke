"""Calcul des statistiques Champions (Phase 0 — modèle figé).

Modèle de stats (FIGÉ — confirmé sur données en jeu le 23/06/2026) :
  - Niveau toujours = 50.
  - IV = 31 sur toutes les stats (auto-maximisés, plus de génétique).
  - SP (Stat Points) : entiers, plafond 32 PAR stat, budget TOTAL de 66 à répartir.
  - Nature : ±10 % sur une stat (hausse) et −10 % sur une autre (baisse).

Formule (niveau 50, IV 31) :
  I       = 2*Base + 31 + 2*SP
  PV      = floor(I / 2) + 60
  Autres  = floor( (floor(I / 2) + 5) * multiplicateur_nature )

Vérifié exact (4/4) sur Tyranocif (Jovial) : PV 177, Atq 186, Déf 130, Vit 124.

Conventions (cf. §0.5 du document socle) :
  - Les IDENTIFIANTS internes sont en anglais, style Pokémon Showdown
    ('tyranitar', 'jolly', 'spe'...) pour s'aligner sur les sources de données.
  - L'affichage FR/EN se fait dans une couche séparée (voir simupoke.i18n).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .basestats import get_base_stats

# ---------------------------------------------------------------------------
# Constantes du modèle
# ---------------------------------------------------------------------------

LEVEL = 50
IV = 31
SP_CAP_PER_STAT = 32
SP_TOTAL_BUDGET = 66

# Ordre canonique des stats (style Showdown)
STAT_KEYS = ["hp", "atk", "def", "spa", "spd", "spe"]

# ---------------------------------------------------------------------------
# Natures : (stat augmentée, stat diminuée). None = nature neutre.
# ---------------------------------------------------------------------------

NATURES: dict[str, tuple[str | None, str | None]] = {
    # Neutres
    "hardy": (None, None), "docile": (None, None), "bashful": (None, None),
    "quirky": (None, None), "serious": (None, None),
    # +Attaque
    "lonely": ("atk", "def"), "brave": ("atk", "spe"),
    "adamant": ("atk", "spa"), "naughty": ("atk", "spd"),
    # +Défense
    "bold": ("def", "atk"), "relaxed": ("def", "spe"),
    "impish": ("def", "spa"), "lax": ("def", "spd"),
    # +Atq. Spé.
    "modest": ("spa", "atk"), "mild": ("spa", "def"),
    "quiet": ("spa", "spe"), "rash": ("spa", "spd"),
    # +Déf. Spé.
    "calm": ("spd", "atk"), "gentle": ("spd", "def"),
    "sassy": ("spd", "spe"), "careful": ("spd", "spa"),
    # +Vitesse
    "timid": ("spe", "atk"), "hasty": ("spe", "def"),
    "jolly": ("spe", "spa"), "naive": ("spe", "spd"),
}


def nature_multipliers(nature: str) -> dict[str, float]:
    """Renvoie le multiplicateur (0.9 / 1.0 / 1.1) pour chaque stat."""
    nature = nature.lower()
    if nature not in NATURES:
        raise ValueError(f"Nature inconnue : {nature!r}")
    plus, minus = NATURES[nature]
    mult = {k: 1.0 for k in STAT_KEYS}
    if plus:
        mult[plus] = 1.1
    if minus:
        mult[minus] = 0.9
    return mult  # la nature n'affecte jamais les PV


# ---------------------------------------------------------------------------
# Calcul d'une stat
# ---------------------------------------------------------------------------

def compute_stat(base: int, sp: int, *, is_hp: bool = False,
                 nature_mult: float = 1.0, level: int = LEVEL, iv: int = IV) -> int:
    """Calcule une stat finale. `sp` = Stat Points Champions (0..32)."""
    intermediate = 2 * base + iv + 2 * sp
    core = (intermediate * level) // 100  # = floor(I/2) au niveau 50
    if is_hp:
        return core + level + 10
    return math.floor((core + 5) * nature_mult)


def compute_all_stats(base_stats: dict[str, int], sp: dict[str, int],
                      nature: str) -> dict[str, int]:
    """Calcule les 6 stats finales d'un build."""
    mult = nature_multipliers(nature)
    out = {}
    for k in STAT_KEYS:
        out[k] = compute_stat(
            base_stats[k], sp.get(k, 0),
            is_hp=(k == "hp"), nature_mult=mult[k],
        )
    return out


# ---------------------------------------------------------------------------
# Validation d'une répartition de SP
# ---------------------------------------------------------------------------

def validate_sp(sp: dict[str, int]) -> list[str]:
    """Renvoie la liste des problèmes (vide = build légal)."""
    problems = []
    for k in STAT_KEYS:
        v = sp.get(k, 0)
        if v < 0 or v > SP_CAP_PER_STAT:
            problems.append(f"{k}: {v} SP hors bornes (0..{SP_CAP_PER_STAT})")
    total = sum(sp.get(k, 0) for k in STAT_KEYS)
    if total > SP_TOTAL_BUDGET:
        problems.append(f"total {total} SP > budget {SP_TOTAL_BUDGET}")
    return problems


@dataclass
class Build:
    """Un build Champions minimal (sera étendu par OwnedPokemon / PokemonState)."""
    species: str
    nature: str = "serious"
    sp: dict[str, int] = field(default_factory=lambda: {k: 0 for k in STAT_KEYS})

    def final_stats(self) -> dict[str, int]:
        return compute_all_stats(get_base_stats(self.species), self.sp, self.nature)
