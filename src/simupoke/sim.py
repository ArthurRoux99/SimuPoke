"""Simulateur de tour déterministe — fondation de la Phase 4 (§10.2).

Jusqu'ici l'outil raisonnait **coup par coup** (calc) ou par heuristique (B1 à
un tour). Ce module **résout un tour complet** en Singles : ordre d'action
(priorité + vitesse, paralysie/Scarf/Trick Room), dégâts (via le calc figé),
coups de statut/setup/protection/soin, puis effets de **fin de tour** (brûlure,
poison, Vestiges, tempête de sable, Orbe Vie). Il permet d'enchaîner les tours
(`rollout`) pour **rejouer une ligne** (§10.1) et servira de substrat à la
recherche simultanée (MCTS/ISMCTS, §10.2).

Mécaniques couvertes (Singles) : ordre d'action (priorité + vitesse effective,
Tailwind, Trick Room), dégâts, recul (recoil) et drain, coups de statut/setup/
protection/soin, sommeil/gel, **écrans** (Protection/Mur Lumière/Voile Aurore),
**Tailwind**, **pièges d'entrée** (Piège de Roc, Picots), coups posant
**météo/terrain/Trick Room**, objets/talents à déclenchement (**Focus Sash /
Fermeté**, **Baie Sitrus**, **baies de résistance de type**, **Ceinture Force**,
**Ballon**, **Casque Brut / Peau Dure / Épines de Fer** au contact, **Orbe Vie**),
et les effets de fin de tour (brûlure, poison, toxik à compteur, Vestiges, sable,
**Champ Herbu**).

Périmètre v1 (assumé, extensible) :
  - Dégâts pris à un **roll** paramétrable (défaut : médian) pour rester
    déterministe ; la pleine stochasticité (16 rolls) viendra avec le MCTS.
  - Coups de statut modélisés par leur **effet primaire** (tables B1), sans
    probabilités d'effet secondaire. Toxic à compteur croissant. Météo/terrain
    posés persistent le temps de la résolution (durée non répercutée entre
    déterminisations de la recherche) ; les conditions de camp (écrans/Tailwind/
    pièges) persistent, elles, via les `Side`.

Tout réutilise le moteur figé (`damage.calculate`) et les tables de `combat` :
une seule source de vérité.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .basestats import get_species, to_id
from .combat import (
    _POWDER_MOVES,
    _PROTECT_MOVES,
    _RECOVERY_MOVES,
    _SETUP_BOOSTS,
    _STATUS_MOVES,
    _add_boosts,
    effective_speed,
)
from .damage import battle_stats, calculate
from .model import FieldState, PokemonState
from .moves import get_move
from .moves import is_known as move_known

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
    def from_state(cls, st: PokemonState) -> Mon:
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
                 field: FieldState | None, *, me_tailwind: bool = False,
                 opp_tailwind: bool = False) -> list[str]:
    """Ordre d'action : 'me'/'opp' résolus par priorité puis vitesse effective
    (Tailwind double la vitesse du camp concerné)."""
    pr_me, pr_opp = _priority(my_move), _priority(opp_move)
    if pr_me != pr_opp:
        return ["me", "opp"] if pr_me > pr_opp else ["opp", "me"]
    sm = effective_speed(me.snapshot()) * (2 if me_tailwind else 1)
    so = effective_speed(opp.snapshot()) * (2 if opp_tailwind else 1)
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

# Recul : fraction des DÉGÂTS infligés reprise par l'attaquant.
_RECOIL: dict[str, float] = {
    "flareblitz": 1 / 3, "bravebird": 1 / 3, "doubleedge": 1 / 3,
    "woodhammer": 1 / 3, "volttackle": 1 / 3, "headcharge": 1 / 4,
    "wildcharge": 1 / 4, "takedown": 1 / 4, "submission": 1 / 4,
    "headsmash": 1 / 2, "lightofruin": 1 / 2,
}
# Drain : fraction des dégâts infligés récupérée en PV.
_DRAIN: dict[str, float] = {
    "drainpunch": 0.5, "gigadrain": 0.5, "leechlife": 0.5, "hornleech": 0.5,
    "paraboliccharge": 0.5, "dreameater": 0.5, "absorb": 0.5, "megadrain": 0.5,
    "bitterblade": 0.5, "drainingkiss": 0.75, "oblivionwing": 0.75,
    "bouncybubble": 0.75,
}

# Coups posant des conditions de terrain / de camp.
_SCREEN_MOVES = {"reflect", "lightscreen", "auroraveil"}
_WEATHER_MOVES = {"sunnyday": "sun", "raindance": "rain", "sandstorm": "sand",
                  "snowscape": "snow", "hail": "snow", "chillyreception": "snow"}
_TERRAIN_MOVES = {"electricterrain": "electric", "grassyterrain": "grassy",
                  "psychicterrain": "psychic", "mistyterrain": "misty"}
_HAZARD_MOVES = {"stealthrock", "spikes"}
_SPIKE_FRACTION = {1: 8, 2: 6, 3: 4}   # couches -> dénominateur (1/8, 1/6, 1/4)

# Baies de résistance : divisent par deux UN coup super efficace de ce type
# (Baie Rass", etc. — Chilan couvre le Normal même non super efficace).
_RESIST_BERRY: dict[str, str] = {
    "occaberry": "Fire", "passhoberry": "Water", "wacanberry": "Electric",
    "rindoberry": "Grass", "yacheberry": "Ice", "chopleberry": "Fighting",
    "kebiaberry": "Poison", "shucaberry": "Ground", "cobaberry": "Flying",
    "payapaberry": "Psychic", "tangaberry": "Bug", "chartiberry": "Rock",
    "kasibberry": "Ghost", "habanberry": "Dragon", "colburberry": "Dark",
    "babiriberry": "Steel", "roseliberry": "Fairy", "chilanberry": "Normal",
}


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
                field: FieldState | None, roll: float, log: list[str], *,
                atk_side: Side | None = None, def_side: Side | None = None,
                field_dur: dict | None = None,
                apply_spread: bool = False, power_mod: float = 1.0) -> None:
    """Résout un coup de `attacker` sur `defender` (mutation en place).

    `atk_side`/`def_side`/`field_dur` (facultatifs, chemin « actions ») activent
    les conditions de camp/champ : écrans, Tailwind, météo/terrain/Trick Room,
    pièges d'entrée.

    `apply_spread`/`power_mod` (chemin Doubles) sont relayés au calc : pénalité
    de zone ×0.75 et modificateur de puissance externe (Helping Hand).
    """
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
        elif atk_side is not None and mid in _SCREEN_MOVES:
            dur = 8 if to_id(attacker.item or "") == "lightclay" else 5
            atk_side.screens[mid] = dur
            log.append(f"  écran posé ({mid}, {dur} tours)")
        elif atk_side is not None and mid == "tailwind":
            atk_side.tailwind = 4
            log.append("  Tailwind posé (4 tours)")
        elif field is not None and field_dur is not None and mid in _WEATHER_MOVES:
            field.weather = _WEATHER_MOVES[mid]
            field_dur["weather"] = 5
            log.append(f"  météo -> {field.weather}")
        elif field is not None and field_dur is not None and mid in _TERRAIN_MOVES:
            field.terrain = _TERRAIN_MOVES[mid]
            field_dur["terrain"] = 5
            log.append(f"  terrain -> {field.terrain}")
        elif field is not None and field_dur is not None and mid == "trickroom":
            field.trick_room = not field.trick_room
            field_dur["trickroom"] = 0 if not field.trick_room else 5
            log.append(f"  Trick Room {'activé' if field.trick_room else 'annulé'}")
        elif def_side is not None and mid in _HAZARD_MOVES:
            if mid == "spikes":
                def_side.hazards["spikes"] = min(3, def_side.hazards.get("spikes", 0) + 1)
                log.append(f"  Picots posés (couche {def_side.hazards['spikes']})")
            else:
                def_side.hazards["stealthrock"] = 1
                log.append("  Piège de Roc posé")
        else:
            log.append("  (effet non modélisé)")
        return

    # Coup offensif.
    if defender.protected:
        log.append(f"  {defender.build.species} est protégé — bloqué")
        return
    scr = None
    if def_side is not None and def_side.screens:
        s = def_side.screens
        if m.is_physical and ("reflect" in s or "auroraveil" in s):
            scr = "auroraveil" if "auroraveil" in s else "reflect"
        elif not m.is_physical and ("lightscreen" in s or "auroraveil" in s):
            scr = "auroraveil" if "auroraveil" in s else "lightscreen"
    try:
        r = calculate(attacker.snapshot(), defender.snapshot(), m, field,
                      screen=scr, apply_spread=apply_spread, power_mod=power_mod)
    except (ValueError, KeyError):
        # Coup à puissance variable / non modélisé par le calc (ex. Balayage) :
        # on l'ignore plutôt que de planter la simulation.
        log.append(f"  {m.name} : effet non simulé")
        return
    dmg = r.rolls[_roll_index(roll)]
    if r.type_effectiveness == 0:
        log.append("  sans effet (immunité)")
        return
    def_item = to_id(defender.item or "")
    def_ability = to_id(defender.build.ability or "")
    # Ballon : immunité au Sol tant qu'il n'a pas été percé (par un coup non-Sol).
    if def_item == "airballoon":
        if r.move_type == "Ground":
            log.append(f"  {defender.build.species} flotte (Ballon) — sans effet")
            return
        defender.item = None
        def_item = ""
        log.append(f"  le Ballon de {defender.build.species} éclate")
    # Baie de résistance : divise par deux un coup super efficace du bon type.
    berry_type = _RESIST_BERRY.get(def_item)
    if berry_type and r.move_type == berry_type \
            and (r.type_effectiveness > 1 or def_item == "chilanberry"):
        dmg = dmg // 2
        defender.item = None
        log.append(f"  {defender.build.species} mange sa baie (dégâts ÷2)")
    # Focus Sash / Fermeté : survit à 1 PV depuis des PV pleins.
    if dmg >= defender.hp and defender.hp >= defender.max_hp \
            and (def_item == "focussash" or def_ability == "sturdy"):
        dmg = defender.hp - 1
        if def_item == "focussash":
            defender.item = None
        log.append(f"  {defender.build.species} tient bon ("
                   + ("Focus Sash" if def_item == "focussash" else "Fermeté") + ")")
    hp_before = defender.hp
    defender.hp = max(0, defender.hp - dmg)
    dealt = hp_before - defender.hp        # dégâts réellement infligés (plafonnés)
    log.append(f"  {dmg} dégâts -> {defender.build.species} "
               f"{defender.hp}/{defender.max_hp} ({100*defender.hp//defender.max_hp}%)")
    if defender.fainted:
        log.append(f"  {defender.build.species} est K.O. !")
    if dealt <= 0:
        return
    atk_ability = to_id(attacker.build.ability or "")
    # --- Réactions du défenseur survivant ---
    if not defender.fainted:
        # Casque Brut / Peau Dure / Épines de Fer : chip au contact.
        if m.makes_contact:
            if def_item == "rockyhelmet":
                chip = max(1, attacker.max_hp // 6)
                attacker.hp = max(0, attacker.hp - chip)
                log.append(f"  {attacker.build.species} subit {chip} (Casque Brut)")
            elif def_ability in ("roughskin", "ironbarbs"):
                chip = max(1, attacker.max_hp // 8)
                attacker.hp = max(0, attacker.hp - chip)
                log.append(f"  {attacker.build.species} subit {chip} (Peau Dure)")
        # Ceinture Force (Weakness Policy) : +2 Atq/Atq.Spé sur coup super efficace.
        if def_item == "weaknesspolicy" and r.type_effectiveness > 1:
            defender.boosts = _add_boosts(defender.boosts, {"atk": 2, "spa": 2})
            defender.item = None
            log.append(f"  {defender.build.species} : Ceinture Force (+2 Atq/A.Sp)")
        # Baie Sitrus : soin de 25 % dès que les PV tombent à ≤ 50 %.
        if def_item == "sitrusberry" and defender.hp <= defender.max_hp // 2:
            heal = max(1, defender.max_hp // 4)
            defender.hp = min(defender.max_hp, defender.hp + heal)
            defender.item = None
            log.append(f"  {defender.build.species} mange sa Baie Sitrus (+{heal})")
    # Drain : soin d'une fraction des dégâts infligés.
    if mid in _DRAIN and attacker.hp > 0:
        healed = min(attacker.max_hp - attacker.hp,
                     max(1, int(dealt * _DRAIN[mid])))
        if healed > 0:
            attacker.hp += healed
            log.append(f"  {attacker.build.species} draine {healed} PV")
    # Recul (sauf Tête de Roche / Garde Magik).
    if mid in _RECOIL and atk_ability not in ("rockhead", "magicguard"):
        recoil = max(1, int(dealt * _RECOIL[mid]))
        attacker.hp = max(0, attacker.hp - recoil)
        log.append(f"  {attacker.build.species} subit {recoil} (recul)")
        if attacker.fainted:
            log.append(f"  {attacker.build.species} est K.O. (recul) !")
    # Orbe Vie : recul de 1/10 des PV max après un coup qui touche.
    if to_id(attacker.item or "") == "lifeorb":
        lo = max(1, attacker.max_hp // 10)
        attacker.hp = max(0, attacker.hp - lo)
        log.append(f"  {attacker.build.species} subit {lo} (Orbe Vie)")


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
    # Champ Herbu : soin des Pokémon au sol.
    terr = to_id(field.terrain or "") if field and field.terrain else ""
    if terr in ("grassy", "grassyterrain") and _grounded(mon) \
            and mon.hp < mon.max_hp:
        heal = max(1, mon.max_hp // 16)
        mon.hp = min(mon.max_hp, mon.hp + heal)
        log.append(f"  {mon.build.species} récupère {heal} (Champ Herbu)")
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


# ---------------------------------------------------------------------------
# Actions complètes (coup OU changement) — camps avec banc
# ---------------------------------------------------------------------------

@dataclass
class Side:
    """Un camp : Pokémon actif + banc, plus ses conditions de camp."""
    active: Mon
    bench: list[Mon] = field(default_factory=list)
    screens: dict[str, int] = field(default_factory=dict)   # nom -> tours restants
    tailwind: int = 0                                        # tours restants
    hazards: dict[str, int] = field(default_factory=dict)   # pièges SUR ce camp


def _copy_mon(m: Mon) -> Mon:
    return replace(m, boosts=dict(m.boosts))


def _copy_side(s: Side) -> Side:
    return Side(active=_copy_mon(s.active), bench=[_copy_mon(b) for b in s.bench],
                screens=dict(s.screens), tailwind=s.tailwind,
                hazards=dict(s.hazards))


def _grounded(mon: Mon) -> bool:
    types = get_species(mon.build.species).get("types") or []
    return "Flying" not in types and to_id(mon.build.ability or "") != "levitate"


def _apply_hazards(side: Side, mon: Mon, log: list[str]) -> None:
    """Dégâts d'entrée des pièges présents sur `side` (Piège de Roc, Picots)."""
    from .typechart import effectiveness
    if "stealthrock" in side.hazards and not mon.fainted:
        types = get_species(mon.build.species).get("types") or []
        eff = effectiveness("Rock", types)
        dmg = max(1, int(mon.max_hp * eff / 8))
        mon.hp = max(0, mon.hp - dmg)
        log.append(f"  {mon.build.species} souffre du Piège de Roc ({dmg})")
    layers = side.hazards.get("spikes", 0)
    if layers and _grounded(mon) and not mon.fainted:
        dmg = max(1, mon.max_hp // _SPIKE_FRACTION[min(3, layers)])
        mon.hp = max(0, mon.hp - dmg)
        log.append(f"  {mon.build.species} souffre des Picots ({dmg})")
    if mon.fainted:
        log.append(f"  {mon.build.species} est K.O. à l'entrée !")


def _do_switch(side: Side, index: int, log: list[str]) -> None:
    """Rappelle l'actif et envoie `bench[index]` (boosts du sortant remis à zéro,
    statut conservé) ; l'entrant subit les pièges présents sur son camp."""
    if not (0 <= index < len(side.bench)):
        log.append("  changement invalide (indice hors banc)")
        return
    old = side.active
    old.boosts = {}
    old.protected = False
    new = side.bench[index]
    side.bench[index] = old
    side.active = new
    log.append(f"{old.build.species} est rappelé ; {new.build.species} entre")
    _apply_hazards(side, new, log)


@dataclass
class ActionResult:
    me: Side
    opp: Side
    log: list[str]
    me_fainted: bool
    opp_fainted: bool


def simulate_turn_actions(me: Side, opp: Side, my_action: tuple, opp_action: tuple,
                          field: FieldState | None = None, *, roll: float = 0.5,
                          copy: bool = True) -> ActionResult:
    """Résout un tour d'**actions** : chaque camp joue ('move', nom) ou
    ('switch', indice). Les changements sont résolus **avant** les coups (le coup
    adverse touche donc l'entrant), puis les coups par ordre de vitesse, puis la
    fin de tour.
    """
    if copy:
        me, opp = _copy_side(me), _copy_side(opp)
    # Copie de travail du champ (on ne mute pas celui de l'appelant).
    src = field or FieldState()
    field = FieldState(weather=src.weather, terrain=src.terrain,
                       trick_room=src.trick_room, turn=src.turn)
    field_dur: dict = {}
    me.active.protected = opp.active.protected = False
    log: list[str] = []
    # Conditions présentes AVANT ce tour (celles posées ce tour gardent leur durée).
    pre = {"me": (set(me.screens), me.tailwind > 0),
           "opp": (set(opp.screens), opp.tailwind > 0)}

    # 1) Changements d'abord (l'entrant subit les pièges).
    for side, action in ((me, my_action), (opp, opp_action)):
        if action and action[0] == "switch":
            _do_switch(side, action[1], log)

    # 2) Coups, dans l'ordre de vitesse (Tailwind inclus).
    mv_me = my_action[1] if my_action and my_action[0] == "move" else None
    mv_opp = opp_action[1] if opp_action and opp_action[0] == "move" else None
    side_of = {"me": me, "opp": opp}
    moves = {"me": mv_me, "opp": mv_opp}
    order = action_order(me.active, opp.active, mv_me, mv_opp, field,
                         me_tailwind=me.tailwind > 0, opp_tailwind=opp.tailwind > 0)
    for who in order:
        atk_side = side_of[who]
        def_side = side_of["opp" if who == "me" else "me"]
        if atk_side.active.fainted or def_side.active.fainted or not moves[who]:
            continue
        _apply_move(atk_side.active, def_side.active, moves[who], field, roll, log,
                    atk_side=atk_side, def_side=def_side, field_dur=field_dur)

    _end_of_turn(me.active, field, log)
    _end_of_turn(opp.active, field, log)
    _tick_conditions(me, opp, pre, log)
    return ActionResult(me=me, opp=opp, log=log,
                        me_fainted=me.active.fainted, opp_fainted=opp.active.fainted)


def _tick_conditions(me: Side, opp: Side, pre: dict, log: list[str]) -> None:
    """Décrémente écrans / Tailwind — seulement ceux présents AVANT ce tour (les
    conditions posées ce tour-ci gardent leur durée), et les retire à expiration."""
    for key, side in (("me", me), ("opp", opp)):
        pre_screens, pre_tw = pre[key]
        for name in list(side.screens):
            if name not in pre_screens:
                continue
            side.screens[name] -= 1
            if side.screens[name] <= 0:
                del side.screens[name]
                log.append(f"  écran dissipé ({name})")
        if pre_tw and side.tailwind > 0:
            side.tailwind -= 1
            if side.tailwind == 0:
                log.append("  Tailwind dissipé")


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
