"""Simulateur de tour **Doubles** (Phase 5) — résolution 2v2.

Porte en 2v2 la résolution de tour de `sim.py` : ordre d'action sur **quatre**
acteurs, ciblage, coups de zone et mécaniques d'appui (Protect, redirection,
Wide Guard, Ally Switch, Helping Hand).

Aucune règle n'est réécrite : les dégâts, les objets, les talents et la fin de
tour passent par `sim._apply_move` et `sim._end_of_turn` — une seule source de
vérité. Le ciblage et les priorités sont **lus dans les données**
(`Move.target`, `Move.priority`), jamais codés en dur.

Périmètre v1 (assumé) : pas de remplacement d'un K.O. en cours de tour (le slot
reste vide jusqu'au tour suivant), pas de Quash / Après Vous.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .combat import effective_speed
from .model import FieldState
from .moves import get_move
from .moves import is_known as move_known
from .sim import Mon

# Une cible : ("foe", 0|1) | ("ally", 0) | ("self", 0)
Target = tuple[str, int]
# Une action de slot : ("move", move_id, Target|None) | ("switch", idx, None)
#                    | ("pass", None, None)
SlotAction = tuple
SideActions = tuple[SlotAction, SlotAction]
# Un acteur : ("me"|"opp", slot)
Actor = tuple[str, int]

PASS: SlotAction = ("pass", None, None)


@dataclass
class DoublesSide:
    """Un camp en Doubles : deux slots actifs, banc et conditions de camp.

    Expose `screens`, `tailwind` et `hazards` comme `sim.Side` : `_apply_move`
    les consomme sans savoir s'il travaille en Singles ou en Doubles.
    """
    active: list[Mon]
    bench: list[Mon] = field(default_factory=list)
    screens: dict[str, int] = field(default_factory=dict)
    tailwind: int = 0
    hazards: dict[str, int] = field(default_factory=dict)
    wide_guard: bool = False            # posé pour le tour courant


def _copy_mon(m: Mon) -> Mon:
    return replace(m, boosts=dict(m.boosts))


def _copy_side(s: DoublesSide) -> DoublesSide:
    return DoublesSide(active=[_copy_mon(m) for m in s.active],
                       bench=[_copy_mon(b) for b in s.bench],
                       screens=dict(s.screens), tailwind=s.tailwind,
                       hazards=dict(s.hazards), wide_guard=s.wide_guard)


def _move_of(action: SlotAction) -> str | None:
    return action[1] if action and action[0] == "move" else None


def _priority(action: SlotAction) -> int:
    mid = _move_of(action)
    return get_move(mid).priority if mid and move_known(mid) else 0


def _speed_key(mon: Mon, side: DoublesSide, field: FieldState | None) -> int:
    """Vitesse effective de tri : Tailwind ×2, Trick Room inverse le sens."""
    spd = effective_speed(mon.snapshot()) * (2 if side.tailwind > 0 else 1)
    return -spd if (field and field.trick_room) else spd


def action_order_doubles(me: DoublesSide, opp: DoublesSide,
                         my_actions: SideActions, opp_actions: SideActions,
                         field: FieldState | None) -> list[Actor]:
    """Ordre d'action des quatre acteurs : priorité, puis vitesse effective.

    Départage stable : `me` avant `opp`, slot 0 avant slot 1 — comme le
    départage arbitraire de `sim.action_order` en Singles.
    """
    entries: list[tuple[Actor, int, int]] = []
    for key, camp, actions in (("me", me, my_actions), ("opp", opp, opp_actions)):
        for slot, mon in enumerate(camp.active):
            action = actions[slot] if slot < len(actions) else PASS
            entries.append(((key, slot), _priority(action),
                            _speed_key(mon, camp, field)))
    entries.sort(key=lambda e: (-e[1], -e[2]))     # tri stable
    return [actor for actor, _, _ in entries]
