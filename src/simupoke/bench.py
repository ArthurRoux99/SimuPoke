"""Benchmarks & optimiseur de SP (§11.1 — « seuils de survie / de KO »).

Brique de base réutilisée par B1/B3 : au lieu de juste calculer des dégâts pour
un build donné, on répond aux questions **inverses** que se pose un joueur VGC :

  - *speed tiers* : qui dépasse qui en vitesse (avec Scarf, Tailwind, paralysie,
    Trick Room) ?
  - **combien de SP en Vitesse** pour dépasser tel adversaire ?
  - **combien de SP défensifs** (PV + Déf/Déf.Spé) pour **survivre** à telle
    attaque ?
  - **combien de SP offensifs** (Atq/Atq.Spé) pour **garantir un KO** en N coups ?

Tout s'appuie sur le moteur figé (`stats` + `damage`) — aucune donnée réseau,
une seule source de vérité. Le modèle de SP Champions (§8.3) rend l'espace de
recherche trivial : chaque stat est un entier dans [0, 32], on énumère.

Note budget : ces optimiseurs raisonnent **stat par stat** (le SP minimal requis
dans la/les stat(s) concernée(s)). La contrainte de budget global (66 SP au
total, §8.3) reste à la charge du joueur qui assemble son spread — l'outil dit
« il te faut au moins X SP ici », pas « voici ton spread complet ».

Focus Sash / Fermeté (§11.1) sont pris en compte : un défenseur à PV pleins
**encaisse** un coup fatal (reste 1 PV), donc la survie est garantie sans SP et
un OHKO devient un 2HKO minimum.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .stats import SP_CAP_PER_STAT
from .basestats import to_id
from .moves import get_move
from .model import PokemonState, FieldState
from .damage import calculate
from .combat import effective_speed


# ---------------------------------------------------------------------------
# Vitesse effective (avec Tailwind, en plus de Scarf/paralysie/boosts)
# ---------------------------------------------------------------------------

def compute_speed(state: PokemonState, *, tailwind: bool = False) -> int:
    """Vitesse effective d'un Pokémon, Tailwind inclus.

    Reprend `combat.effective_speed` (base + boosts + Choice Scarf + paralysie)
    et applique le doublement de Tailwind par-dessus (comme Showdown).
    """
    spe = effective_speed(state)
    if tailwind:
        spe *= 2
    return spe


@dataclass
class SpeedEntry:
    species: str
    speed: int
    notes: list[str]              # ex. ["Choice Scarf", "Tailwind", "paralysé"]


def _speed_notes(state: PokemonState, tailwind: bool) -> list[str]:
    notes: list[str] = []
    if to_id(state.item or "") == "choicescarf":
        notes.append("Choice Scarf")
    if tailwind:
        notes.append("Tailwind")
    if state.status == "par":
        notes.append("paralysé")
    boost = state.boosts.get("spe", 0)
    if boost:
        notes.append(f"Vit {boost:+d}")
    return notes


def speed_tiers(states: list[PokemonState], *,
                tailwinds: list[bool] | None = None,
                trick_room: bool = False) -> list[SpeedEntry]:
    """Classe des Pokémon par vitesse effective.

    `tailwinds` : liste parallèle de drapeaux Tailwind (défaut : tous False).
    `trick_room` : si vrai, l'ordre d'ACTION s'inverse (le plus lent agit en
    premier) — on trie alors en vitesse croissante. Le champ `speed` reste la
    vraie vitesse ; seul l'ordre de la liste change.
    """
    tw = tailwinds if tailwinds is not None else [False] * len(states)
    entries = [
        SpeedEntry(species=s.species, speed=compute_speed(s, tailwind=t),
                   notes=_speed_notes(s, t))
        for s, t in zip(states, tw)
    ]
    entries.sort(key=lambda e: e.speed, reverse=not trick_room)
    return entries


# ---------------------------------------------------------------------------
# Optimiseur : Vitesse pour dépasser une cible
# ---------------------------------------------------------------------------

@dataclass
class OutspeedResult:
    feasible: bool
    sp: int | None                # SP minimal en Vitesse (None si impossible)
    my_speed: int | None          # ma vitesse au SP trouvé (ou au max testé)
    target_speed: int
    ties_only: bool = False       # au mieux on égalise (départage 50/50)

    def line(self) -> str:
        if self.feasible:
            return (f"Vitesse : {self.sp} SP suffisent "
                    f"({self.my_speed} vs {self.target_speed}).")
        if self.ties_only:
            return (f"Vitesse : impossible de dépasser ; on peut au mieux "
                    f"ÉGALISER à {self.target_speed} (départage 50/50).")
        return (f"Vitesse : hors de portée — même à {SP_CAP_PER_STAT} SP, "
                f"{self.my_speed} < {self.target_speed}.")


def _with_sp(state: PokemonState, key: str, value: int) -> PokemonState:
    return replace(state, stat_points={**state.stat_points, key: value})


def _endures(state: PokemonState) -> bool:
    """Focus Sash / Fermeté : survit à UN coup s'il part des PV pleins."""
    if state.current_hp_pct < 1.0:
        return False
    return (to_id(state.item or "") == "focussash"
            or to_id(state.ability or "") == "sturdy")


def _effective_ko_hits(raw: int | None, endures: bool) -> int | None:
    """Nb de coups pour KO garanti, en tenant compte de Focus Sash / Fermeté.

    Un coup fatal partant des PV pleins est encaissé (reste 1 PV) → il faut un
    coup de plus qu'un OHKO « brut ».
    """
    if raw is None:
        return None
    return 2 if (endures and raw == 1) else raw


def min_sp_to_outspeed(me: PokemonState, target: PokemonState,
                       *, me_tailwind: bool = False,
                       target_tailwind: bool = False,
                       strict: bool = True) -> OutspeedResult:
    """SP minimal en Vitesse pour (dé)passer `target`.

    `strict=True` : il faut être **strictement** plus rapide (départage évité).
    `strict=False` : égaliser suffit.
    """
    target_speed = compute_speed(target, tailwind=target_tailwind)
    best_speed = -1
    ties = False
    for sp in range(0, SP_CAP_PER_STAT + 1):
        s = compute_speed(_with_sp(me, "spe", sp), tailwind=me_tailwind)
        best_speed = s
        if s > target_speed or (not strict and s >= target_speed):
            return OutspeedResult(True, sp, s, target_speed,
                                  ties_only=(s == target_speed))
        if s == target_speed:
            ties = True
    return OutspeedResult(False, None, best_speed, target_speed, ties_only=ties)


# ---------------------------------------------------------------------------
# Optimiseur : survie défensive
# ---------------------------------------------------------------------------

@dataclass
class SurviveResult:
    feasible: bool
    hp_sp: int | None
    def_sp: int | None
    total_sp: int | None
    move: str
    stat: str                     # "def" ou "spd" (côté défensif sollicité)
    max_pct: float | None = None  # % PV du roll haut au spread trouvé
    by_endure: bool = False       # survie garantie par Focus Sash / Fermeté

    def line(self) -> str:
        if self.by_endure:
            return (f"Survie à {self.move} : garantie par Focus Sash / Fermeté "
                    f"(depuis PV pleins) — 0 SP requis.")
        if not self.feasible:
            return (f"Survie à {self.move} : impossible même à fond "
                    f"(PV + {self.stat}).")
        return (f"Survie à {self.move} : {self.total_sp} SP "
                f"(PV {self.hp_sp} / {self.stat} {self.def_sp}) — "
                f"le roll haut fait {self.max_pct:.0f}% max.")


def min_sp_to_survive(defender: PokemonState, attacker: PokemonState,
                      move: str, field: FieldState | None = None, *,
                      crit: bool = False) -> SurviveResult:
    """SP défensif total minimal (PV + Déf/Déf.Spé) pour survivre au roll haut.

    On énumère les répartitions par total croissant et on renvoie la première
    (donc de coût minimal) qui garantit la survie même sur le roll max. Le
    défenseur est évalué à PLEINS PV (un seuil de survie « propre »).
    """
    m = get_move(move)
    stat = "def" if m.is_physical else "spd"
    base = replace(defender, current_hp_pct=1.0)
    # Focus Sash / Fermeté : survie garantie depuis PV pleins, sans SP.
    if _endures(base):
        return SurviveResult(True, 0, 0, 0, m.name, stat, by_endure=True)
    cap = SP_CAP_PER_STAT
    for total in range(0, 2 * cap + 1):
        lo = max(0, total - cap)
        hi = min(cap, total)
        for hp_sp in range(lo, hi + 1):
            def_sp = total - hp_sp
            trial = replace(base, stat_points={
                **base.stat_points, "hp": hp_sp, stat: def_sp})
            r = calculate(attacker, trial, m, field, crit=crit)
            if r.max_damage < r.defender_max_hp:
                return SurviveResult(True, hp_sp, def_sp, total, m.name, stat,
                                     max_pct=r.max_pct)
    return SurviveResult(False, None, None, None, m.name, stat)


# ---------------------------------------------------------------------------
# Optimiseur : SP offensif pour garantir un KO
# ---------------------------------------------------------------------------

@dataclass
class KoResult:
    feasible: bool
    sp: int | None
    move: str
    stat: str                     # "atk" ou "spa"
    hits: int                     # KO recherché en N coups
    min_pct: float | None = None  # % PV du roll bas au SP trouvé
    blocked_by_endure: bool = False   # empêché par Focus Sash / Fermeté

    def line(self) -> str:
        what = "OHKO" if self.hits == 1 else f"KO en {self.hits}"
        if self.blocked_by_endure:
            return (f"{what} avec {self.move} : bloqué par Focus Sash / Fermeté "
                    f"(cible à PV pleins) — impossible en {self.hits}.")
        if not self.feasible:
            return (f"{what} avec {self.move} : hors de portée même à "
                    f"{SP_CAP_PER_STAT} SP {self.stat}.")
        return (f"{what} avec {self.move} : {self.sp} SP {self.stat} "
                f"(roll bas {self.min_pct:.0f}%).")


def min_sp_to_ko(attacker: PokemonState, defender: PokemonState,
                 move: str, field: FieldState | None = None, *,
                 hits: int = 1, crit: bool = False) -> KoResult:
    """SP offensif minimal (Atq ou Atq.Spé) pour un KO **garanti** en `hits`.

    « Garanti » = même le roll bas tue en `hits` coups. Le défenseur est pris
    dans l'état fourni (PV courants inclus), ce qui permet aussi de raisonner
    « combien pour finir un adversaire déjà entamé ».
    """
    m = get_move(move)
    stat = "atk" if m.is_physical else "spa"
    endures = _endures(defender)
    for sp in range(0, SP_CAP_PER_STAT + 1):
        trial = _with_sp(attacker, stat, sp)
        r = calculate(trial, defender, m, field, crit=crit)
        g = _effective_ko_hits(r.guaranteed_ko_hits, endures)
        if g is not None and g <= hits:
            return KoResult(True, sp, m.name, stat, hits, min_pct=r.min_pct)
    # KO en `hits` inatteignable : signaler si c'est Focus Sash / Fermeté qui
    # l'empêche (un OHKO devient un 2HKO minimum).
    blocked = endures and hits < 2
    return KoResult(False, None, m.name, stat, hits, blocked_by_endure=blocked)
