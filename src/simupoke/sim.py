"""Simulateur de tour déterministe — fondation de la Phase 4 (§10.2).

Jusqu'ici l'outil raisonnait **coup par coup** (calc) ou par heuristique (B1 à
un tour). Ce module **résout un tour complet** en Singles : ordre d'action
(priorité + vitesse, paralysie/Scarf/Trick Room), dégâts (via le calc figé),
coups de statut/setup/protection/soin, puis effets de **fin de tour** (brûlure,
poison, Vestiges, tempête de sable, Orbe Vie). Il permet d'enchaîner les tours
(`rollout`) pour **rejouer une ligne** (§10.1) et servira de substrat à la
recherche simultanée (MCTS/ISMCTS, §10.2).

Périmètre v1 (assumé, extensible) :
  - **Singles**, un actif par camp ; les **changements** ne sont pas encore
    simulés (ce sera l'étape suivante) — on résout deux coups.
  - Dégâts pris à un **roll** paramétrable (défaut : médian) pour rester
    déterministe ; la pleine stochasticité (16 rolls) viendra avec le MCTS.
  - Coups de statut modélisés par leur **effet primaire** (tables B1), sans
    probabilités d'effet secondaire. Toxic à compteur croissant.

Tout réutilise le moteur figé (`damage.calculate`) et les tables de `combat` :
une seule source de vérité.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .model import PokemonState, FieldState
from .basestats import get_species, to_id
from .moves import get_move, is_known as move_known
from .damage import calculate, battle_stats
from .combat import (
    effective_speed, _add_boosts, _STATUS_MOVES, _SETUP_BOOSTS,
    _PROTECT_MOVES, _RECOVERY_MOVES, _POWDER_MOVES,
)


# ---------------------------------------------------------------------------
# Combattant (état mutable d'un tour à l'autre)
# ---------------------------------------------------------------------------

@dataclass
class Mon:
    """État vivant d'un Pokémon en combat (PV absolus, statut, boosts…)."""
    build: PokemonState
    hp: int
    max_hp: int
    status: str | None = None
    boosts: dict[str, int] = field(default_factory=dict)
    item: str | None = None
    toxic_counter: int = 0
    sleep_turns: int = 0
    protected: bool = False

    @classmethod
    def from_state(cls, st: PokemonState) -> "Mon":
        mx = battle_stats(st)["hp"]
        hp = mx if st.current_hp_pct >= 1.0 else max(1, int(mx * st.current_hp_pct))
        return cls(build=st, hp=hp, max_hp=mx, status=st.status,
                   boosts=dict(st.boosts), item=st.item)

    @property
    def fainted(self) -> bool:
        return self.hp <= 0

    @property
    def hp_pct(self) -> float:
        return self.hp / self.max_hp if self.max_hp else 0.0

    def snapshot(self) -> PokemonState:
        """PokemonState reflétant l'état courant (pour le calc)."""
        return replace(self.build, boosts=dict(self.boosts), status=self.status,
                       item=self.item, current_hp_pct=self.hp_pct)


# ---------------------------------------------------------------------------
# Ordre d'action
# ---------------------------------------------------------------------------

def _priority(move: str | None) -> int:
    return get_move(move).priority if move and move_known(move) else 0


def action_order(me: Mon, opp: Mon, my_move: str | None, opp_move: str | None,
                 field: FieldState | None) -> list[str]:
    """Ordre d'action : 'me'/'opp' résolus par priorité puis vitesse effective."""
    pr_me, pr_opp = _priority(my_move), _priority(opp_move)
    if pr_me != pr_opp:
        return ["me", "opp"] if pr_me > pr_opp else ["opp", "me"]
    sm = effective_speed(me.snapshot())
    so = effective_speed(opp.snapshot())
    trick_room = bool(field and field.trick_room)
    if sm == so:
        return ["me", "opp"]                     # départage arbitraire stable
    faster_me = (sm < so) if trick_room else (sm > so)
    return ["me", "opp"] if faster_me else ["opp", "me"]


# ---------------------------------------------------------------------------
# Application d'un coup
# ---------------------------------------------------------------------------

def _roll_index(roll: float) -> int:
    return min(15, max(0, round(roll * 15)))


_STATUS_IMMUNE_TYPE = {"brn": "Fire", "par": "Electric"}


def _apply_status(target: Mon, status: str, move_id: str, log: list[str]) -> None:
    if target.status:
        log.append(f"  {target.build.species} est déjà {target.status}")
        return
    types = get_species(target.build.species).get("types") or []
    immune = _STATUS_IMMUNE_TYPE.get(status)
    if immune and immune in types:
        log.append(f"  sans effet ({immune} insensible)")
        return
    if status == "par" and move_id == "thunderwave" and "Ground" in types:
        log.append("  sans effet (Sol insensible à Cage-Éclair)")
        return
    if move_id in _POWDER_MOVES and "Grass" in types:
        log.append("  sans effet (poudre inefficace sur Plante)")
        return
    target.status = status
    if status == "slp":
        target.sleep_turns = 2               # déterministe (Showdown : 1–3)
    log.append(f"  {target.build.species} est maintenant {status}")


def _can_act(mon: Mon, log: list[str]) -> bool:
    """Sommeil / gel empêchent d'agir (déterministe ; para/gel probabilistes non
    modélisés au-delà de la baisse de vitesse)."""
    if mon.status == "frz":
        log.append(f"  {mon.build.species} est gelé et ne peut agir")
        return False
    if mon.status == "slp":
        if mon.sleep_turns > 0:
            mon.sleep_turns -= 1
            log.append(f"  {mon.build.species} dort")
            return False
        mon.status = None
        log.append(f"  {mon.build.species} se réveille")
    return True


def _apply_move(attacker: Mon, defender: Mon, move: str,
                field: FieldState | None, roll: float, log: list[str]) -> None:
    """Résout un coup de `attacker` sur `defender` (mutation en place)."""
    if attacker.fainted:
        return
    if not _can_act(attacker, log):
        return
    if not move_known(move):
        log.append(f"{attacker.build.species} utilise {move} (inconnu, ignoré)")
        return
    m = get_move(move)
    mid = m.id
    log.append(f"{attacker.build.species} utilise {m.name}")

    # Coups non offensifs.
    if m.is_status:
        if mid in _PROTECT_MOVES:
            attacker.protected = True
            log.append("  se protège")
        elif mid in _SETUP_BOOSTS:
            attacker.boosts = _add_boosts(attacker.boosts, _SETUP_BOOSTS[mid])
            log.append(f"  boosts -> {attacker.boosts}")
        elif mid in _RECOVERY_MOVES:
            healed = min(attacker.max_hp - attacker.hp, attacker.max_hp // 2)
            attacker.hp += healed
            log.append(f"  récupère {healed} PV ({attacker.hp}/{attacker.max_hp})")
        elif mid in _STATUS_MOVES:
            _apply_status(defender, _STATUS_MOVES[mid], mid, log)
        else:
            log.append("  (effet non modélisé)")
        return

    # Coup offensif.
    if defender.protected:
        log.append(f"  {defender.build.species} est protégé — bloqué")
        return
    r = calculate(attacker.snapshot(), defender.snapshot(), m, field)
    dmg = r.rolls[_roll_index(roll)]
    if r.type_effectiveness == 0:
        log.append("  sans effet (immunité)")
        return
    defender.hp = max(0, defender.hp - dmg)
    log.append(f"  {dmg} dégâts -> {defender.build.species} "
               f"{defender.hp}/{defender.max_hp} ({100*defender.hp//defender.max_hp}%)")
    if defender.fainted:
        log.append(f"  {defender.build.species} est K.O. !")
    # Orbe Vie : recul de 1/10 des PV max après un coup qui touche.
    if to_id(attacker.item or "") == "lifeorb" and dmg > 0:
        recoil = max(1, attacker.max_hp // 10)
        attacker.hp = max(0, attacker.hp - recoil)
        log.append(f"  {attacker.build.species} subit {recoil} (Orbe Vie)")


# ---------------------------------------------------------------------------
# Fin de tour
# ---------------------------------------------------------------------------

def _end_of_turn(mon: Mon, field: FieldState | None, log: list[str]) -> None:
    if mon.fainted:
        return
    item = to_id(mon.item or "")
    # Vestiges.
    if item == "leftovers" and mon.hp < mon.max_hp:
        heal = max(1, mon.max_hp // 16)
        mon.hp = min(mon.max_hp, mon.hp + heal)
        log.append(f"  {mon.build.species} récupère {heal} (Vestiges)")
    # Statut persistant.
    if mon.status == "brn":
        dmg = max(1, mon.max_hp // 16)
        mon.hp = max(0, mon.hp - dmg)
        log.append(f"  {mon.build.species} souffre de sa brûlure ({dmg})")
    elif mon.status == "psn":
        dmg = max(1, mon.max_hp // 8)
        mon.hp = max(0, mon.hp - dmg)
        log.append(f"  {mon.build.species} souffre du poison ({dmg})")
    elif mon.status == "tox":
        mon.toxic_counter += 1
        dmg = max(1, (mon.max_hp // 16) * mon.toxic_counter)
        mon.hp = max(0, mon.hp - dmg)
        log.append(f"  {mon.build.species} souffre du poison grave ({dmg})")
    # Tempête de sable (chip sur non Sol/Roche/Acier).
    weather = to_id(field.weather or "") if field else ""
    if weather in ("sand", "sandstorm"):
        types = get_species(mon.build.species).get("types") or []
        if not ({"Rock", "Ground", "Steel"} & set(types)) and not mon.fainted:
            dmg = max(1, mon.max_hp // 16)
            mon.hp = max(0, mon.hp - dmg)
            log.append(f"  {mon.build.species} est malmené par le sable ({dmg})")
    if mon.fainted:
        log.append(f"  {mon.build.species} est K.O. (fin de tour) !")


# ---------------------------------------------------------------------------
# Résolution d'un tour
# ---------------------------------------------------------------------------

@dataclass
class TurnResult:
    me: Mon
    opp: Mon
    log: list[str]
    me_fainted: bool
    opp_fainted: bool
    me_hp: int = 0            # PV (instantané en fin de tour)
    opp_hp: int = 0
    me_max: int = 0
    opp_max: int = 0


def simulate_turn(me: Mon, opp: Mon, my_move: str | None, opp_move: str | None,
                  field: FieldState | None = None, *, roll: float = 0.5,
                  copy: bool = True) -> TurnResult:
    """Résout un tour (deux coups) et renvoie l'état résultant.

    `roll` ∈ [0,1] choisit le jet de dégâts (0 = min, 1 = max, défaut médian).
    `copy=True` laisse les `Mon` d'entrée intacts (utile pour explorer des lignes).
    """
    if copy:
        me = replace(me, boosts=dict(me.boosts))
        opp = replace(opp, boosts=dict(opp.boosts))
    me.protected = opp.protected = False
    log: list[str] = []
    sides = {"me": me, "opp": opp}
    moves = {"me": my_move, "opp": opp_move}

    for who in action_order(me, opp, my_move, opp_move, field):
        actor, target = sides[who], sides["opp" if who == "me" else "me"]
        if actor.fainted or target.fainted:
            continue
        if moves[who]:
            _apply_move(actor, target, moves[who], field, roll, log)

    for who in action_order(me, opp, my_move, opp_move, field):
        _end_of_turn(sides[who], field, log)

    return TurnResult(me=me, opp=opp, log=log,
                      me_fainted=me.fainted, opp_fainted=opp.fainted,
                      me_hp=me.hp, opp_hp=opp.hp,
                      me_max=me.max_hp, opp_max=opp.max_hp)


def rollout(me: Mon, opp: Mon, my_moves: list[str], opp_moves: list[str],
            field: FieldState | None = None, *, roll: float = 0.5,
            max_turns: int = 20) -> list[TurnResult]:
    """Enchaîne des tours selon deux séquences de coups (rejeu d'une ligne).

    Si une séquence est plus courte, son dernier coup est répété. S'arrête dès
    qu'un camp est K.O. ou après `max_turns`.
    """
    results: list[TurnResult] = []
    cur_me = replace(me, boosts=dict(me.boosts))
    cur_opp = replace(opp, boosts=dict(opp.boosts))
    for t in range(max_turns):
        mv_me = my_moves[min(t, len(my_moves) - 1)] if my_moves else None
        mv_opp = opp_moves[min(t, len(opp_moves) - 1)] if opp_moves else None
        res = simulate_turn(cur_me, cur_opp, mv_me, mv_opp, field, roll=roll,
                            copy=False)
        results.append(res)
        if res.me_fainted or res.opp_fainted:
            break
        cur_me, cur_opp = res.me, res.opp
    return results
