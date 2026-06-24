"""Calculateur de dégâts (§11.1) — fondation réutilisée par B1/B2/B3.

Implémente la formule de dégâts Génération 5+ telle qu'utilisée par Pokémon
Showdown / `@smogon/calc` : modificateurs chaînés en base 4096, `pokeRound`
(arrondi au plus proche, départage vers le bas) et 16 « rolls » aléatoires
(85 %…100 %). Objectif : un calc **fiable et explicable** (§1).

Couverture Phase 0 (documentée, extensible pour le « delta » Champions §7.2) :
  - STAB (×1.5, ×2 avec Adaptability), efficacité des types, coup critique,
    brûlure, météo (soleil/pluie/sable/neige), terrains, esquive multi-cibles
    (spread), boosts de stats.
  - Items : Choice Band/Specs, Life Orb, Expert Belt, Assault Vest.
  - Talents : Huge/Pure Power, Guts, Technician, Adaptability, Tinted Lens,
    Neuroforce, Multiscale/Shadow Shield, Filter/Solid Rock/Prism Armor.

Tout le reste (autres items/talents, Tera, etc.) viendra par extension des
mêmes points d'accroche (listes de modificateurs).
"""

from __future__ import annotations

from dataclasses import dataclass

from .basestats import get_base_stats, get_species, to_id
from .stats import STAT_KEYS, compute_stat, nature_multipliers
from .moves import Move, get_move
from .typechart import effectiveness
from .model import PokemonState, FieldState

LEVEL = 50

# Talents accordant une immunité à un type d'attaque (annulent les dégâts).
_ABILITY_IMMUNITY: dict[str, str] = {
    "levitate": "Ground", "eartheater": "Ground",
    "flashfire": "Fire",
    "voltabsorb": "Electric", "lightningrod": "Electric", "motordrive": "Electric",
    "waterabsorb": "Water", "stormdrain": "Water", "dryskin": "Water",
    "sapsipper": "Grass",
}


# ---------------------------------------------------------------------------
# Primitives arithmétiques Showdown
# ---------------------------------------------------------------------------

def poke_round(x: float) -> int:
    """Arrondi « Pokémon » : au plus proche, départage des .5 vers le bas."""
    frac = x - int(x // 1)
    return int(x // 1) + (1 if frac > 0.5 else 0)


def _chain_mods(mods: list[int]) -> int:
    """Combine des modificateurs base-4096 (comme `chainMods` de @smogon)."""
    m = 4096
    for mod in mods:
        if mod != 4096:
            m = (m * mod + 2048) >> 12
    return m


def _apply_mod(value: int, mod: int) -> int:
    """Applique un modificateur base-4096 avec pokeRound."""
    return poke_round(value * mod / 4096)


def _boost_multiplier(stage: int, *, ignore_negative: bool = False,
                      ignore_positive: bool = False) -> float:
    if stage > 0 and ignore_positive:
        stage = 0
    if stage < 0 and ignore_negative:
        stage = 0
    if stage >= 0:
        return (2 + stage) / 2
    return 2 / (2 - stage)


# ---------------------------------------------------------------------------
# Stats de combat d'un PokemonState
# ---------------------------------------------------------------------------

def battle_stats(state: PokemonState) -> dict[str, int]:
    """Stats finales (sans boosts) d'un PokemonState, via le modèle figé."""
    base = get_base_stats(state.species)
    mult = nature_multipliers(state.nature)
    return {
        k: compute_stat(base[k], state.stat_points.get(k, 0),
                        is_hp=(k == "hp"), nature_mult=mult[k])
        for k in STAT_KEYS
    }


def _norm_ability(state: PokemonState) -> str:
    return to_id(state.ability) if state.ability else ""


def _norm_item(state: PokemonState) -> str:
    return to_id(state.item) if state.item else ""


def _is_grounded(state: PokemonState) -> bool:
    types = get_species(state.species).get("types") or []
    return "Flying" not in types and _norm_ability(state) != "levitate"


# ---------------------------------------------------------------------------
# Météo / terrain
# ---------------------------------------------------------------------------

_WEATHER_ALIASES = {
    "sun": "sun", "sunnyday": "sun", "harshsunlight": "sun", "desolateland": "sun",
    "rain": "rain", "raindance": "rain", "primordialsea": "rain",
    "sand": "sand", "sandstorm": "sand",
    "snow": "snow", "hail": "snow",
}

_TERRAIN_ALIASES = {
    "electric": "electric", "electricterrain": "electric",
    "grassy": "grassy", "grassyterrain": "grassy",
    "psychic": "psychic", "psychicterrain": "psychic",
    "misty": "misty", "mistyterrain": "misty",
}


def _weather(field: FieldState | None) -> str | None:
    if not field or not field.weather:
        return None
    return _WEATHER_ALIASES.get(to_id(field.weather))


def _terrain(field: FieldState | None) -> str | None:
    if not field or not field.terrain:
        return None
    return _TERRAIN_ALIASES.get(to_id(field.terrain))


# ---------------------------------------------------------------------------
# Résultat
# ---------------------------------------------------------------------------

@dataclass
class DamageResult:
    move: str
    rolls: list[int]              # 16 valeurs croissantes
    defender_max_hp: int
    defender_current_hp: int
    type_effectiveness: float
    is_stab: bool
    crit: bool

    @property
    def min_damage(self) -> int:
        return self.rolls[0]

    @property
    def max_damage(self) -> int:
        return self.rolls[-1]

    @property
    def min_pct(self) -> float:
        return 100.0 * self.min_damage / self.defender_max_hp

    @property
    def max_pct(self) -> float:
        return 100.0 * self.max_damage / self.defender_max_hp

    @property
    def guaranteed_ko_hits(self) -> int | None:
        """Nb de coups pour KO garanti (roll min). None si le move ne tue pas."""
        if self.min_damage <= 0:
            return None
        import math
        return math.ceil(self.defender_current_hp / self.min_damage)

    @property
    def possible_ko_hits(self) -> int | None:
        """Nb de coups pour KO possible (roll max)."""
        if self.max_damage <= 0:
            return None
        import math
        return math.ceil(self.defender_current_hp / self.max_damage)

    def describe(self, lang: str = "fr") -> str:
        eff = self.type_effectiveness
        eff_txt = {0: "aucun effet", 0.25: "très peu efficace (×0.25)",
                   0.5: "peu efficace (×0.5)", 1: "neutre",
                   2: "super efficace (×2)", 4: "super efficace (×4)"}.get(
                       eff, f"×{eff:g}")
        lines = [
            f"{self.move} : {self.min_damage}–{self.max_damage} "
            f"({self.min_pct:.1f}–{self.max_pct:.1f} %) — {eff_txt}"
            + (" — STAB" if self.is_stab else "")
            + (" — CRIT" if self.crit else ""),
        ]
        g, p = self.guaranteed_ko_hits, self.possible_ko_hits
        if g is None:
            lines.append("  aucun dégât")
        elif g == p:
            lines.append(f"  KO garanti en {g} coup(s)")
        else:
            lines.append(f"  KO possible en {p}, garanti en {g} coup(s)")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Calcul principal
# ---------------------------------------------------------------------------

def calculate(attacker: PokemonState, defender: PokemonState,
              move: str | Move, field: FieldState | None = None, *,
              crit: bool = False, apply_spread: bool = False) -> DamageResult:
    """Calcule les dégâts d'un `move` de `attacker` sur `defender`.

    `apply_spread` : pénalité ×0.75 des attaques de zone en doubles.
    """
    mv = move if isinstance(move, Move) else get_move(move)
    if mv.is_status or mv.base_power <= 0:
        raise ValueError(f"{mv.name} n'inflige pas de dégâts directs.")

    atk_ability = _norm_ability(attacker)
    def_ability = _norm_ability(defender)
    atk_item = _norm_item(attacker)
    def_item = _norm_item(defender)

    a_stats = battle_stats(attacker)
    d_stats = battle_stats(defender)
    def_types = get_species(defender.species).get("types") or []
    atk_types = get_species(attacker.species).get("types") or []

    physical = mv.is_physical
    atk_key = "atk" if physical else "spa"
    def_key = "def" if physical else "spd"

    # --- Stat offensive (boosts ; le crit ignore les baisses) ---
    atk_stage = attacker.boosts.get(atk_key, 0)
    attack = int(a_stats[atk_key] * _boost_multiplier(atk_stage, ignore_negative=crit))

    at_mods: list[int] = []
    if physical and atk_item == "choiceband":
        at_mods.append(6144)
    if not physical and atk_item == "choicespecs":
        at_mods.append(6144)
    if physical and atk_ability in ("hugepower", "purepower"):
        at_mods.append(8192)
    if atk_ability == "guts" and attacker.status:
        at_mods.append(6144)
    # Talents défensifs réduisant la stat offensive (Thick Fat, Heatproof).
    if def_ability == "thickfat" and mv.type in ("Fire", "Ice"):
        at_mods.append(2048)
    if def_ability == "heatproof" and mv.type == "Fire":
        at_mods.append(2048)
    if at_mods:
        attack = _apply_mod(attack, _chain_mods(at_mods))
    attack = max(1, attack)

    # --- Stat défensive (boosts ; le crit ignore les hausses) ---
    def_stage = defender.boosts.get(def_key, 0)
    defense = int(d_stats[def_key] * _boost_multiplier(def_stage, ignore_positive=crit))

    df_mods: list[int] = []
    if not physical and def_item == "assaultvest":
        df_mods.append(6144)
    weather = _weather(field)
    if not physical and weather == "sand" and "Rock" in def_types:
        df_mods.append(6144)            # boost SpD du Roche sous tempête de sable
    if physical and weather == "snow" and "Ice" in def_types:
        df_mods.append(6144)            # boost Déf de la Glace sous neige (Gen 9)
    if df_mods:
        defense = _apply_mod(defense, _chain_mods(df_mods))
    defense = max(1, defense)

    # --- Puissance de base (modificateurs) ---
    base_power = mv.base_power
    bp_mods: list[int] = []
    if atk_ability == "technician" and base_power <= 60:
        bp_mods.append(6144)
    if bp_mods:
        base_power = max(1, _apply_mod(base_power, _chain_mods(bp_mods)))

    # --- Dégâts de base ---
    base_damage = (((2 * LEVEL) // 5 + 2) * base_power * attack // defense) // 50 + 2

    # Spread (doubles)
    if apply_spread:
        base_damage = _apply_mod(base_damage, 3072)

    # Météo (offensive : soleil/Feu, pluie/Eau, et inversement)
    if weather == "sun":
        if mv.type == "Fire":
            base_damage = _apply_mod(base_damage, 6144)
        elif mv.type == "Water":
            base_damage = _apply_mod(base_damage, 2048)
    elif weather == "rain":
        if mv.type == "Water":
            base_damage = _apply_mod(base_damage, 6144)
        elif mv.type == "Fire":
            base_damage = _apply_mod(base_damage, 2048)

    # Terrain (attaquant au sol)
    terrain = _terrain(field)
    if terrain and _is_grounded(attacker):
        if terrain == "electric" and mv.type == "Electric":
            base_damage = _apply_mod(base_damage, 5325)
        elif terrain == "grassy" and mv.type == "Grass":
            base_damage = _apply_mod(base_damage, 5325)
        elif terrain == "psychic" and mv.type == "Psychic":
            base_damage = _apply_mod(base_damage, 5325)
    if terrain == "misty" and mv.type == "Dragon" and _is_grounded(defender):
        base_damage = _apply_mod(base_damage, 2048)

    # Coup critique
    if crit:
        base_damage = int(base_damage * 1.5)

    # --- Facteurs finaux ---
    is_stab = mv.type in atk_types
    if is_stab:
        stab_mod = 8192 if atk_ability == "adaptability" else 6144
    else:
        stab_mod = 4096

    eff = effectiveness(mv.type, def_types)
    # Immunités de talent du défenseur (annulent les dégâts).
    if _ABILITY_IMMUNITY.get(def_ability) == mv.type:
        eff = 0.0
    is_burned = (physical and defender is not None and attacker.status == "brn"
                 and atk_ability != "guts")

    final_mods: list[int] = []
    if atk_item == "lifeorb":
        final_mods.append(5324)
    if atk_item == "expertbelt" and eff > 1:
        final_mods.append(4915)
    if atk_ability == "tintedlens" and 0 < eff < 1:
        final_mods.append(8192)
    if atk_ability == "neuroforce" and eff > 1:
        final_mods.append(5120)
    if def_ability in ("multiscale", "shadowshield") and defender.current_hp_pct >= 1.0:
        final_mods.append(2048)
    if def_ability in ("filter", "solidrock", "prismarmor") and eff > 1:
        final_mods.append(3072)
    final_mod = _chain_mods(final_mods)

    # --- 16 rolls ---
    rolls: list[int] = []
    for i in range(16):
        d = (base_damage * (85 + i)) // 100
        if stab_mod != 4096:
            d = poke_round(d * stab_mod / 4096)
        d = int(d * eff)
        if is_burned:
            d = d // 2
        if final_mod != 4096:
            d = poke_round(max(1, d * final_mod / 4096))
        if eff > 0:
            d = max(1, d)
        rolls.append(d)

    rolls.sort()

    def_max_hp = d_stats["hp"]
    def_cur_hp = max(0, int(def_max_hp * max(0.0, min(1.0, defender.current_hp_pct))))
    if defender.current_hp_pct >= 1.0:
        def_cur_hp = def_max_hp

    return DamageResult(
        move=mv.name,
        rolls=rolls,
        defender_max_hp=def_max_hp,
        defender_current_hp=def_cur_hp,
        type_effectiveness=eff,
        is_stab=is_stab,
        crit=crit,
    )
