"""Simulateur de tour **Doubles** (Phase 5) — résolution 2v2.

Porte en 2v2 la résolution de tour de `sim.py` : ordre d'action sur **quatre**
acteurs, ciblage, coups de zone et mécaniques d'appui (Protect, redirection,
Wide Guard, Ally Switch, Helping Hand).

Aucune règle n'est réécrite : les dégâts, les objets, les talents et la fin de
tour passent par `sim._apply_move` et `sim._end_of_turn` — une seule source de
vérité. Le ciblage et les priorités sont **lus dans les données**
(`Move.target`, `Move.priority`), jamais codés en dur.

Périmètre v1 (assumé) : pas de remplacement d'un K.O. en cours de tour (le slot
reste vide jusqu'au tour suivant), pas de Quash / Après Vous. Les écrans
consultés lors d'un coup de zone sont ceux du camp adverse, y compris pour
l'allié touché par un `allAdjacent` : le cas est rare et l'écart est borné à un
facteur d'écran sur le seul friendly fire.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .combat import effective_speed
from .model import FieldState
from .moves import get_move
from .moves import is_known as move_known
from .sim import Mon, _apply_hazards, _apply_move, _end_of_turn, _tick_conditions

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


# ---------------------------------------------------------------------------
# Ciblage — piloté par la donnée (`Move.target`)
# ---------------------------------------------------------------------------

_FOE_SPREAD = "allAdjacentFoes"       # les deux adversaires
_ALL_SPREAD = "allAdjacent"           # les deux adversaires ET l'allié


def _living(mons: list[Mon]) -> list[Mon]:
    return [m for m in mons if not m.fainted]


def resolve_targets(actor: Actor, action: SlotAction, own: DoublesSide,
                    foes: DoublesSide) -> list[Mon]:
    """Pokémon effectivement touchés par `action`, d'après `Move.target`.

    Le ciblage vient de la **donnée** : `allAdjacentFoes` frappe les deux
    adversaires, `allAdjacent` y ajoute l'allié (Séisme, Surf), `self` et
    `allySide` restent sur le lanceur, `adjacentAlly` vise l'allié.
    """
    mid = _move_of(action)
    if not mid or not move_known(mid):
        return []
    _, slot = actor
    mv = get_move(mid)
    tgt = mv.target
    ally = [m for i, m in enumerate(own.active) if i != slot and not m.fainted]

    if tgt in ("self", "allySide"):
        return [own.active[slot]]
    if tgt == "adjacentAlly":
        return ally
    if tgt == _ALL_SPREAD:
        return _living(foes.active) + ally
    if tgt == _FOE_SPREAD:
        return _living(foes.active)
    # Mono-cible : cible explicite, sinon le premier adversaire vivant.
    named = action[2]
    if named and named[0] == "foe" and named[1] < len(foes.active):
        chosen = foes.active[named[1]]
        return [] if chosen.fainted else [chosen]
    if named and named[0] == "ally":
        return ally
    living = _living(foes.active)
    return [living[0]] if living else []


# ---------------------------------------------------------------------------
# Résolution d'un tour
# ---------------------------------------------------------------------------

@dataclass
class DoublesResult:
    me: DoublesSide
    opp: DoublesSide
    log: list[str]


def _do_switch_slot(side: DoublesSide, slot: int, index: int,
                    log: list[str]) -> None:
    """Rappelle l'occupant de `slot` et envoie `bench[index]` à sa place."""
    if not (0 <= index < len(side.bench)):
        log.append("  changement invalide (indice hors banc)")
        return
    old = side.active[slot]
    old.boosts = {}
    old.protected = False
    new = side.bench[index]
    side.bench[index] = old
    side.active[slot] = new
    log.append(f"{old.build.species} est rappelé ; {new.build.species} entre")
    _apply_hazards(side, new, log)


def simulate_turn_doubles(me: DoublesSide, opp: DoublesSide,
                          my_actions: SideActions, opp_actions: SideActions,
                          field: FieldState | None = None, *,
                          roll: float = 0.5, copy: bool = True) -> DoublesResult:
    """Résout un tour complet en Doubles (mutation d'une copie par défaut)."""
    if copy:
        me, opp = _copy_side(me), _copy_side(opp)
    src = field or FieldState()
    field = FieldState(weather=src.weather, terrain=src.terrain,
                       trick_room=src.trick_room, turn=src.turn)
    field_dur: dict = {}
    log: list[str] = []
    for camp in (me, opp):
        camp.wide_guard = False
        for m in camp.active:
            m.protected = False
    pre = {"me": (set(me.screens), me.tailwind > 0),
           "opp": (set(opp.screens), opp.tailwind > 0)}

    # 1) Changements d'abord : l'entrant subit les pièges.
    for camp, actions in ((me, my_actions), (opp, opp_actions)):
        for slot, action in enumerate(actions):
            if action and action[0] == "switch":
                _do_switch_slot(camp, slot, action[1], log)

    # 2) Coups, dans l'ordre d'action.
    order = action_order_doubles(me, opp, my_actions, opp_actions, field)
    actions_of = {"me": my_actions, "opp": opp_actions}
    side_of = {"me": me, "opp": opp}
    for actor in order:
        key, slot = actor
        own = side_of[key]
        foes = side_of["opp" if key == "me" else "me"]
        action = actions_of[key][slot]
        attacker = own.active[slot]
        mid = _move_of(action)
        if attacker.fainted or mid is None:
            continue
        targets = resolve_targets(actor, action, own, foes)
        if not targets:
            log.append(f"{attacker.build.species} : cible K.O. — coup perdu")
            continue
        # Pénalité de zone : seulement à partir de deux cibles touchées.
        spread = len(targets) >= 2
        for target in targets:
            _apply_move(attacker, target, mid, field, roll, log,
                        atk_side=own, def_side=foes, field_dur=field_dur,
                        apply_spread=spread)

    # 3) Fin de tour sur les quatre, puis conditions de camp.
    for camp in (me, opp):
        for m in camp.active:
            _end_of_turn(m, field, log)
    _tick_conditions(me, opp, pre, log)
    return DoublesResult(me=me, opp=opp, log=log)
