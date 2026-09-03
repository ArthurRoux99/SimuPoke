"""Analyse offensive **Doubles** (Phase 5) — matrice de menaces 2v2.

Première tranche des Doubles : un « damage calc Doubles » décisionnel qui réutilise
le calc figé. Pour un plateau (mes 1–2 actifs, les 1–2 actifs adverses), il donne :

- le **meilleur coup mono-cible** de chaque attaquant sur chaque cible ;
- les **KO garantis** (coup seul) et les lignes de **focus fire** (deux attaquants
  combinant un KO sur une même cible, au roll min) ;
- les **coups de zone** (spread) et leurs dégâts sur chaque cible (×0.75).

Ne simule pas le tour complet — l'ordre d'action, Protect, la redirection
(Lightning Rod / Follow Me) et les cibles alliées viendront avec le simulateur
Doubles. Une seule source de vérité : `damage.calculate`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .basestats import get_species
from .damage import battle_stats, calculate
from .model import FieldState, PokemonState
from .moves import get_move
from .moves import is_known as move_known


def _name(species: str) -> str:
    return get_species(species).get("name", species)


def _current_hp(state: PokemonState) -> int:
    mx = battle_stats(state)["hp"]
    if state.current_hp_pct >= 1.0:
        return mx
    return max(1, int(mx * state.current_hp_pct))


def _damaging_moves(state: PokemonState) -> list[str]:
    out = []
    for m in state.moves:
        if not move_known(m):
            continue
        mv = get_move(m)
        if mv.base_power > 0 and not mv.is_status:
            out.append(m)
    return out


@dataclass
class Hit:
    attacker: str          # espèce de l'attaquant
    move: str              # nom du coup
    min_pct: float
    max_pct: float
    min_dmg: int
    max_dmg: int
    ko: bool               # KO garanti par ce seul coup (roll min ≥ PV cible)


@dataclass
class TargetReport:
    target: str            # espèce de la cible
    hp: int                # PV actuels
    hits: list[Hit]        # meilleur coup mono-cible de chaque attaquant
    focus_ko: bool         # focus fire des attaquants : KO garanti ?


@dataclass
class SpreadOption:
    attacker: str
    move: str
    per_target: list[tuple[str, float, float]]   # (cible, min%, max%)


@dataclass
class DoublesReport:
    targets: list[TargetReport]
    spreads: list[SpreadOption]

    def lines(self) -> list[str]:
        out: list[str] = ["Menaces offensives (Doubles) :"]
        for t in self.targets:
            tag = "  ⚡ FOCUS FIRE : KO garanti" if t.focus_ko else ""
            out.append(f"\n▸ Cible {t.target} ({t.hp} PV){tag}")
            if not t.hits:
                out.append("    (aucun coup offensif)")
            for h in t.hits:
                ko = "  — KO garanti" if h.ko else ""
                out.append(f"    {h.attacker} · {h.move} : "
                           f"{h.min_pct:.0f}–{h.max_pct:.0f} %{ko}")
        if self.spreads:
            out.append("\nCoups de zone (touchent les deux, ×0.75) :")
            for s in self.spreads:
                per = " / ".join(f"{tg} {mn:.0f}–{mx:.0f} %"
                                 for tg, mn, mx in s.per_target)
                out.append(f"    {s.attacker} · {s.move} : {per}")
        return out


def _best_single(attacker: PokemonState, target: PokemonState,
                 field: FieldState | None):
    """Meilleur coup mono-cible (max des dégâts max) de `attacker` sur `target`."""
    best = None
    for m in _damaging_moves(attacker):
        r = calculate(attacker, target, m, field)
        if best is None or r.max_damage > best[1].max_damage:
            best = (m, r)
    return best


def analyze_doubles(mine: list[PokemonState], opp: list[PokemonState],
                    field: FieldState | None = None) -> DoublesReport:
    """Matrice de menaces 2v2 (mon point de vue offensif)."""
    targets: list[TargetReport] = []
    for t in opp:
        hp = _current_hp(t)
        hits: list[Hit] = []
        for a in mine:
            best = _best_single(a, t, field)
            if best is None:
                continue
            m, r = best
            hits.append(Hit(
                attacker=_name(a.species),
                move=get_move(m).name,
                min_pct=r.min_pct, max_pct=r.max_pct,
                min_dmg=r.min_damage, max_dmg=r.max_damage,
                ko=r.min_damage >= hp))
        focus_ko = bool(hits) and sum(h.min_dmg for h in hits) >= hp
        targets.append(TargetReport(
            target=_name(t.species), hp=hp,
            hits=hits, focus_ko=focus_ko))

    spreads: list[SpreadOption] = []
    for a in mine:
        for m in _damaging_moves(a):
            mv = get_move(m)
            if not mv.is_spread:
                continue
            per = []
            for t in opp:
                r = calculate(a, t, m, field, apply_spread=True)
                per.append((_name(t.species), r.min_pct, r.max_pct))
            if per:
                spreads.append(SpreadOption(
                    attacker=_name(a.species),
                    move=mv.name, per_target=per))
    return DoublesReport(targets=targets, spreads=spreads)
