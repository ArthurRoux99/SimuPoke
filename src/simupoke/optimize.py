"""Optimiseur de spread SP (§8.3 — « distribuer 66 points, max 32 par stat »).

`bench.py` répond aux seuils **isolés** (« combien de SP en Vitesse ? »). Ici on
**compose** ces seuils : à partir d'une liste d'objectifs (dépasser X, survivre
à Y, tuer Z), on cherche un spread SP **complet et légal** — total ≤ 66, chaque
stat ≤ 32 (§8.3) — qui les satisfait tous, au coût minimal.

Décomposition (ce qui rend le problème facile) : les objectifs se rangent par
axe de stats presque indépendants —

  - **Vitesse** : seule `spe` compte → on prend le max des seuils d'outspeed ;
  - **Offense** : `atk` (physique) ou `spa` (spécial), indépendants → max par
    stat des seuils de KO ;
  - **Défense** : `hp` est **partagé** entre Déf et Déf.Spé, c'est le seul axe
    couplé → on balaie `hp` et, pour chacun, on prend le min de Déf/Déf.Spé qui
    couvre tous les objectifs de survie, en minimisant `hp + def + spd`.

On additionne les trois axes ; si le total dépasse le budget (ou qu'un objectif
est hors de portée même à fond), le spread est renvoyé avec les objectifs non
tenus signalés — l'outil reste **explicable** (§1).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .basestats import get_base_stats, is_known
from .bench import min_sp_to_ko, min_sp_to_outspeed, min_sp_to_survive
from .damage import calculate
from .model import FieldState, PokemonState
from .moves import get_move
from .stats import SP_CAP_PER_STAT, SP_TOTAL_BUDGET, STAT_KEYS, compute_all_stats

# ---------------------------------------------------------------------------
# Objectifs
# ---------------------------------------------------------------------------

@dataclass
class Outspeed:
    """Dépasser (ou égaliser) une cible en vitesse."""
    target: PokemonState
    strict: bool = True
    me_tailwind: bool = False
    target_tailwind: bool = False
    label: str = ""


@dataclass
class Survive:
    """Encaisser (roll haut) une attaque venant de `attacker`."""
    attacker: PokemonState
    move: str
    field: FieldState | None = None
    crit: bool = False
    label: str = ""


@dataclass
class Ko:
    """Garantir un KO (roll bas) en `hits` coups sur `defender`."""
    defender: PokemonState
    move: str
    hits: int = 1
    field: FieldState | None = None
    crit: bool = False
    label: str = ""


# ---------------------------------------------------------------------------
# Résultat
# ---------------------------------------------------------------------------

@dataclass
class SpreadResult:
    feasible: bool
    sp: dict[str, int]                 # spread requis, par stat
    total: int
    budget: int
    stats: dict[str, int] | None       # stats finales (None si espèce inconnue)
    unmet: list[str] = field(default_factory=list)   # objectifs non tenus

    @property
    def leftover(self) -> int:
        return self.budget - self.total

    def lines(self) -> list[str]:
        order = [("hp", "PV"), ("atk", "Atq"), ("def", "Déf"),
                 ("spa", "A.Sp"), ("spd", "D.Sp"), ("spe", "Vit")]
        parts = [f"{lab} {self.sp[k]}" for k, lab in order if self.sp.get(k)]
        out = ["Spread proposé : " + (", ".join(parts) if parts else "aucun SP requis")]
        out.append(f"  total {self.total}/{self.budget} SP"
                   + (f" — reste {self.leftover} à placer" if self.leftover > 0
                      else "" if self.leftover == 0
                      else f" — DÉPASSEMENT de {-self.leftover}"))
        if self.stats:
            st = "  ".join(f"{lab} {self.stats[k]}" for k, lab in order)
            out.append("  stats : " + st)
        if self.unmet:
            out.append("  ⚠ objectifs non tenus :")
            out.extend(f"     · {u}" for u in self.unmet)
        elif self.feasible:
            out.append("  ✓ tous les objectifs sont tenus dans le budget.")
        return out


# ---------------------------------------------------------------------------
# Solveur
# ---------------------------------------------------------------------------

def _me(species: str, nature: str, item: str | None, ability: str | None,
        sp: dict[str, int]) -> PokemonState:
    return PokemonState(species=species, nature=nature, item=item,
                        ability=ability, stat_points=sp, current_hp_pct=1.0)


def _min_def_given_hp(me_defender: PokemonState, obj: Survive, hp_sp: int,
                      def_key: str, cap: int) -> int | None:
    """Min de SP dans `def_key` pour survivre à `obj` à `hp_sp` PV fixés."""
    for def_sp in range(cap + 1):
        trial = replace(me_defender, stat_points={
            **me_defender.stat_points, "hp": hp_sp, def_key: def_sp})
        r = calculate(obj.attacker, trial, obj.move, obj.field, crit=obj.crit)
        if r.max_damage < r.defender_max_hp:
            return def_sp
    return None


def _solve_defense(me_defender: PokemonState, survives: list[Survive],
                   cap: int) -> tuple[int, int, int]:
    """Balaie `hp` et renvoie (hp, def, spd) minimisant le coût total.

    Les objectifs sont supposés faisables individuellement (pré-filtrés en
    amont). Sans objectif de survie, renvoie (0, 0, 0).
    """
    phys = [o for o in survives if get_move(o.move).is_physical]
    spec = [o for o in survives if not get_move(o.move).is_physical]
    if not phys and not spec:
        return (0, 0, 0)
    best: tuple[int, int, int, int] | None = None   # (total, hp, def, spd)
    for hp_sp in range(cap + 1):
        def_need = max((_min_def_given_hp(me_defender, o, hp_sp, "def", cap) or 0
                        for o in phys), default=0)
        spd_need = max((_min_def_given_hp(me_defender, o, hp_sp, "spd", cap) or 0
                        for o in spec), default=0)
        total = hp_sp + def_need + spd_need
        if best is None or total < best[0]:
            best = (total, hp_sp, def_need, spd_need)
    assert best is not None
    return (best[1], best[2], best[3])


def optimize_spread(species: str, nature: str,
                    objectives: list[Outspeed | Survive | Ko], *,
                    item: str | None = None, ability: str | None = None,
                    budget: int = SP_TOTAL_BUDGET,
                    cap: int = SP_CAP_PER_STAT) -> SpreadResult:
    """Cherche un spread SP couvrant tous les `objectives`, au coût minimal.

    Chaque axe (vitesse / offense / défense) est résolu séparément puis
    additionné ; le couplage réel (PV partagé) est traité dans le solveur
    défensif. Les objectifs hors de portée (même à 32 SP) ou le dépassement de
    budget sont signalés dans `unmet` plutôt que de faire échouer le calcul.
    """
    sp = dict.fromkeys(STAT_KEYS, 0)
    unmet: list[str] = []

    outspeeds = [o for o in objectives if isinstance(o, Outspeed)]
    kos = [o for o in objectives if isinstance(o, Ko)]
    survives = [o for o in objectives if isinstance(o, Survive)]

    # --- Vitesse ---
    for o in outspeeds:
        res = min_sp_to_outspeed(_me(species, nature, item, ability, {}), o.target,
                                 me_tailwind=o.me_tailwind,
                                 target_tailwind=o.target_tailwind,
                                 strict=o.strict)
        tag = o.label or o.target.species
        if not res.feasible:
            unmet.append(f"dépasser {tag} : hors de portée (vitesse)")
        else:
            sp["spe"] = max(sp["spe"], res.sp)

    # --- Offense (KO) ---
    for o in kos:
        res = min_sp_to_ko(_me(species, nature, item, ability, {}), o.defender,
                           o.move, o.field, hits=o.hits, crit=o.crit)
        tag = o.label or f"{o.move} sur {o.defender.species}"
        if not res.feasible:
            reason = ("bloqué par Focus Sash / Fermeté"
                      if res.blocked_by_endure
                      else f"hors de portée (>{cap} SP {res.stat})")
            unmet.append(f"KO {tag} : {reason}")
        else:
            sp[res.stat] = max(sp[res.stat], res.sp)

    # --- Défense (survie), axe couplé par les PV ---
    me_def = _me(species, nature, item, ability, {})
    feasible_survives: list[Survive] = []
    for o in survives:
        chk = min_sp_to_survive(me_def, o.attacker, o.move, o.field, crit=o.crit)
        tag = o.label or f"{o.move} de {o.attacker.species}"
        if not chk.feasible:
            unmet.append(f"survivre à {tag} : hors de portée (même à fond)")
        else:
            feasible_survives.append(o)
    hp_need, def_need, spd_need = _solve_defense(me_def, feasible_survives, cap)
    sp["hp"], sp["def"], sp["spd"] = hp_need, def_need, spd_need

    total = sum(sp.values())
    if total > budget:
        unmet.append(f"budget dépassé : {total} SP requis > {budget}")

    stats = (compute_all_stats(get_base_stats(species), sp, nature)
             if is_known(species) else None)
    feasible = not unmet
    return SpreadResult(feasible=feasible, sp=sp, total=total, budget=budget,
                        stats=stats, unmet=unmet)
