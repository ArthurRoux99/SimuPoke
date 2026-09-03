"""B1 — Assistant de combat, mode analyse (§10.1).

Premier palier « rapide et indicatif » (§15 Q3) : une analyse **à 1 tour** qui
classe mes coups par valeur attendue à l'aide du calculateur de dégâts, en
tenant compte du KO, de l'ordre d'action (priorité + vitesse, Trick Room) et du
risque encouru (dégâts subis). L'action adverse peut être **fournie** (info
quasi parfaite, §10.1) ou **estimée** à partir des coups adverses connus.

Les **changements** (switch) sont évalués si un banc est fourni : sûreté à
l'entrée (coup encaissé) + menace offensive au tour suivant (escomptée), et
peuvent primer la recommandation quand l'actif serait mis KO sans tuer d'abord.

Les **coups de soutien** sont notés (§10.1, palier indicatif) : les setups sont
chiffrés par l'offense qu'ils débloquent au tour suivant (via le calc), les
statuts/protection/soin par des heuristiques transparentes ; un setup sûr peut
primer la recommandation.

Limites restantes (assumées) :
  - analyse d'un seul tour ; les coups de soutien sont notés par heuristique
    (pas de simulation multi-tours) ; pas encore de recherche d'arbre
    (ce sera §10.2, MCTS) ;
  - build adverse inconnu => nature neutre / 0 SP par défaut (le modèle d'usage
    §10.3 affinera plus tard).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from dataclasses import field as dfield

from .basestats import get_species, is_known, to_id
from .damage import battle_stats, calculate
from .model import FieldState, PokemonState
from .moves import get_move
from .moves import is_known as move_known
from .usage import likely_set

# Poids de la fonction de valeur (ajustables).
W_OFFENSE = 1.0
W_KO = 0.5
W_RISK = 0.8
W_SPEED = 0.1

# Changements (switch) : l'offense n'arrive qu'au tour SUIVANT -> on l'escompte,
# et on pénalise le coup encaissé à l'entrée.
W_SWITCH_OFF = 0.5
W_SWITCH_RISK = 0.9

# --- Coups de soutien (§10.1, palier indicatif) ---------------------------
# Setups : capacité -> boosts accordés (le gain est ensuite chiffré via le calc).
_SETUP_BOOSTS: dict[str, dict[str, int]] = {
    "swordsdance": {"atk": 2}, "howl": {"atk": 1}, "bulkup": {"atk": 1, "def": 1},
    "nastyplot": {"spa": 2}, "calmmind": {"spa": 1, "spd": 1},
    "dragondance": {"atk": 1, "spe": 1}, "quiverdance": {"spa": 1, "spd": 1, "spe": 1},
    "agility": {"spe": 2}, "rockpolish": {"spe": 2}, "shellsmash": {"atk": 2, "spa": 2, "spe": 2},
    "workup": {"atk": 1, "spa": 1}, "victorydance": {"atk": 1, "def": 1, "spe": 1},
}
# Coups infligeant un statut à l'adversaire.
_STATUS_MOVES: dict[str, str] = {
    "willowisp": "brn", "thunderwave": "par", "spore": "slp", "sleeppowder": "slp",
    "hypnosis": "slp", "toxic": "tox", "glare": "par", "stunspore": "par",
    "nuzzle": "par", "lovelykiss": "slp", "darkvoid": "slp",
}
_POWDER_MOVES = {"spore", "sleeppowder", "stunspore"}   # sans effet sur Plante
_PROTECT_MOVES = {"protect", "detect", "kingsshield", "spikyshield", "banefulbunker"}
_RECOVERY_MOVES = {"recover", "roost", "synthesis", "moonlight", "morningsun",
                   "slackoff", "softboiled", "milkdrink", "rest", "shoreup"}


def _boost_mult(stage: int) -> float:
    return (2 + stage) / 2 if stage >= 0 else 2 / (2 - stage)


def effective_speed(state: PokemonState) -> int:
    """Vitesse effective : base + boosts + Choice Scarf + paralysie."""
    spe = battle_stats(state)["spe"]
    spe = int(spe * _boost_mult(state.boosts.get("spe", 0)))
    if to_id(state.item or "") == "choicescarf":
        spe = int(spe * 1.5)
    if state.status == "par":
        spe = int(spe * 0.5)
    return spe


def _priority(move: str | None) -> int:
    return get_move(move).priority if move and move_known(move) else 0


def moves_first(me: PokemonState, opp: PokemonState, my_move: str | None,
                opp_move: str | None, field: FieldState | None) -> bool | None:
    """True si j'agis avant l'adversaire ; None si égalité de vitesse."""
    pr_me, pr_opp = _priority(my_move), _priority(opp_move)
    if pr_me != pr_opp:
        return pr_me > pr_opp
    sm, so = effective_speed(me), effective_speed(opp)
    if sm == so:
        return None
    trick_room = bool(field and field.trick_room)
    return (sm < so) if trick_room else (sm > so)


# ---------------------------------------------------------------------------
# Menace adverse (dégâts entrants)
# ---------------------------------------------------------------------------

@dataclass
class Incoming:
    move: str | None
    max_pct: float            # % de mes PV max (roll haut)
    ohko: bool                # me met KO d'un coup ?
    known: bool = True
    estimated: bool = False   # menace estimée via l'usage (coups non saisis)


def _incoming(me: PokemonState, opp: PokemonState, field: FieldState | None,
              opp_move: str | None, use_usage: bool = True) -> Incoming:
    """Dégâts que l'adversaire m'inflige (action fournie, ou pire coup connu).

    Si aucun coup adverse n'est connu, on estime via le set le plus probable de
    l'espèce (usage, §10.3) — le résultat est marqué `estimated`.
    """
    estimated = False
    if opp_move:
        candidates = [opp_move]
    elif opp.moves:
        candidates = list(opp.moves)
    elif use_usage and is_known(opp.species):
        candidates = likely_set(opp.species).moves
        estimated = bool(candidates)
    else:
        candidates = []

    best: Incoming | None = None
    for mv in candidates:
        if not mv or not move_known(mv) or get_move(mv).is_status:
            continue
        try:
            r = calculate(opp, me, mv, field)
        except (ValueError, KeyError):
            continue
        cur = r.defender_current_hp
        cand = Incoming(move=mv, max_pct=r.max_pct, ohko=(r.max_damage >= cur),
                        estimated=estimated)
        if best is None or cand.max_pct > best.max_pct:
            best = cand
    if best is None:
        return Incoming(move=opp_move, max_pct=0.0, ohko=False, known=False)
    return best


# ---------------------------------------------------------------------------
# Évaluation d'un coup
# ---------------------------------------------------------------------------

@dataclass
class MoveEval:
    move: str
    kind: str                          # 'damage' | 'status'
    value: float
    min_pct: float | None = None
    max_pct: float | None = None
    ko: str | None = None
    first: bool | None = None
    notes: list[str] = dfield(default_factory=list)


@dataclass
class SwitchEval:
    species: str
    incoming_pct: float               # % PV encaissés à l'entrée (roll haut)
    survives: bool                    # survit au coup d'entrée ?
    best_move: str | None             # meilleur coup offensif au tour suivant
    best_move_pct: float              # % moyen infligé par ce coup
    value: float
    notes: list[str] = dfield(default_factory=list)


def _best_offense(mon: PokemonState, opp: PokemonState,
                  field: FieldState | None) -> tuple[str | None, float, bool]:
    """Meilleur coup offensif de `mon` sur `opp` : (nom, % moyen, KO possible)."""
    best_name: str | None = None
    best_avg = 0.0
    best_ko = False
    for mv in mon.moves:
        if not move_known(mv) or get_move(mv).is_status:
            continue
        try:
            r = calculate(mon, opp, mv, field)
        except (ValueError, KeyError):
            continue
        avg = (r.min_pct + r.max_pct) / 2
        if avg > best_avg:
            best_avg, best_name = avg, get_move(mv).name
            best_ko = r.max_damage >= r.defender_current_hp
    return best_name, best_avg, best_ko


def _add_boosts(current: dict[str, int], delta: dict[str, int]) -> dict[str, int]:
    """Combine des boosts (plafonnés à ±6)."""
    out = dict(current)
    for k, v in delta.items():
        out[k] = max(-6, min(6, out.get(k, 0) + v))
    return out


def _evaluate_support(move_name: str, me: PokemonState, opp: PokemonState,
                      field: FieldState | None, incoming: Incoming
                      ) -> tuple[float, list[str]]:
    """Note un coup de soutien (setup / statut / protection / soin).

    Palier indicatif (§10.1) : le setup est chiffré par l'**offense qu'il
    débloque** au tour suivant (via le calc) ; le reste par des heuristiques
    transparentes. Un coup encaissé mortel (OHKO subi) déprécie le setup/soin.
    """
    mid = to_id(move_name)
    inc_ohko = incoming.known and incoming.ohko
    inc_frac = min(1.0, incoming.max_pct / 100.0) if incoming.known else 0.0
    notes: list[str] = []

    if mid in _PROTECT_MOVES:
        if inc_ohko:
            return 0.5, ["bloque un coup fatal ce tour (répit / scout)"]
        return 0.25, ["protection / scout"]

    if mid in _SETUP_BOOSTS:
        if inc_ohko:
            return -0.3, ["risqué : mis KO pendant le setup"]
        boosted = replace(me, boosts=_add_boosts(me.boosts, _SETUP_BOOSTS[mid]))
        _, off_now, _ = _best_offense(me, opp, field)
        _, off_after, ko_after = _best_offense(boosted, opp, field)
        gain = max(0.0, (off_after - off_now) / 100.0)
        value = 1.2 * gain - W_RISK * inc_frac
        notes.append(f"offense ~{off_now:.0f}%→{off_after:.0f}% au tour suivant")
        if ko_after and off_now < 100:
            notes.append("débloque un KO")
        return value, notes

    if mid in _STATUS_MOVES:
        if opp.status:
            return 0.05, [f"adversaire déjà {opp.status}"]
        st = _STATUS_MOVES[mid]
        opp_types = get_species(opp.species).get("types") or []
        if st == "brn" and "Fire" in opp_types:
            return 0.0, ["sans effet (Feu insensible à la brûlure)"]
        if st == "par" and ("Electric" in opp_types
                            or (mid == "thunderwave" and "Ground" in opp_types)):
            return 0.0, ["sans effet (immunité à la paralysie)"]
        if mid in _POWDER_MOVES and "Grass" in opp_types:
            return 0.0, ["sans effet (poudre inefficace sur Plante)"]
        value = 0.55 if st == "slp" else (0.45 if st in ("par", "brn") else 0.4)
        notes.append(f"inflige {st} à l'adversaire")
        return value, notes

    if mid in _RECOVERY_MOVES:
        if inc_ohko:
            return -0.1, ["soin inutile si mis KO"]
        return max(0.0, 0.5 - inc_frac), ["soin (~50% PV)"]

    return 0.1, ["coup de soutien — non modélisé"]


def evaluate_switches(bench: list[PokemonState], opp: PokemonState,
                      field: FieldState | None, opp_move: str | None,
                      use_usage: bool = True) -> list[SwitchEval]:
    """Note chaque changement possible : sûreté à l'entrée + menace au tour +1.

    Palier « indicatif » (§15 Q3) : on suppose que l'adversaire attaque le
    Pokémon qui entre (le coup fourni/estimé le touche), puis on estime la
    valeur offensive du nouvel actif au tour suivant (escomptée).
    """
    evals: list[SwitchEval] = []
    for mon in bench:
        inc = _incoming(mon, opp, field, opp_move, use_usage=use_usage)
        inc_frac = min(1.0, inc.max_pct / 100.0) if inc.known else 0.0
        off_name, off_avg, off_ko = _best_offense(mon, opp, field)
        value = W_SWITCH_OFF * (off_avg / 100.0) - W_SWITCH_RISK * inc_frac
        notes: list[str] = []
        survives = not inc.ohko if inc.known else True
        if inc.known and inc.ohko:
            notes.append("mis KO à l'entrée")
            value -= 0.5
        if off_ko:
            notes.append("menace un KO au tour suivant")
        evals.append(SwitchEval(
            species=mon.species, incoming_pct=inc.max_pct if inc.known else 0.0,
            survives=survives, best_move=off_name, best_move_pct=off_avg,
            value=value, notes=notes))
    evals.sort(key=lambda e: e.value, reverse=True)
    return evals


@dataclass
class TurnAnalysis:
    options: list[MoveEval]            # coups offensifs, classés
    other: list[MoveEval]             # coups de statut/soutien (non notés)
    incoming: Incoming
    recommendation: str
    switches: list[SwitchEval] = dfield(default_factory=list)

    def lines(self) -> list[str]:
        out: list[str] = []
        inc = self.incoming
        if not inc.known:
            out.append("Menace adverse : inconnue (aucun coup renseigné).")
        else:
            mv = inc.move or "?"
            tag = " — OHKO sur moi !" if inc.ohko else ""
            src = " [estimé via l'usage]" if inc.estimated else ""
            out.append(f"Menace adverse : {mv} ~{inc.max_pct:.0f}% max{tag}{src}")
        out.append("")
        out.append("Mes options (classées) :")
        for i, e in enumerate(self.options, 1):
            order = ("agit avant" if e.first else
                     "plus lent" if e.first is False else "vitesse égale")
            ko = f" — {e.ko}" if e.ko else ""
            out.append(f"  {i}. {e.move:<16} {e.min_pct:.0f}-{e.max_pct:.0f}% "
                       f"[{order}]{ko}  (valeur {e.value:+.2f})")
            for n in e.notes:
                out.append(f"       · {n}")
        if self.other:
            out.append("")
            out.append("Coups de soutien (classés) :")
            for e in self.other:
                note = f"  — {e.notes[0]}" if e.notes else ""
                out.append(f"  · {e.move:<16} (valeur {e.value:+.2f}){note}")
        if self.switches:
            out.append("")
            out.append("Changements possibles (classés) :")
            for s in self.switches:
                surv = "encaisse" if s.survives else "KO à l'entrée"
                mv = f" puis {s.best_move} {s.best_move_pct:.0f}%" if s.best_move else ""
                extra = f" — {', '.join(s.notes)}" if s.notes else ""
                out.append(f"  ~ {s.species:<14} entrée {s.incoming_pct:.0f}% "
                           f"[{surv}]{mv}  (valeur {s.value:+.2f}){extra}")
        out.append("")
        out.append(f"➤ Recommandation : {self.recommendation}")
        return out


def analyze_turn(me: PokemonState, opp: PokemonState,
                 field: FieldState | None = None, *,
                 opp_move: str | None = None,
                 my_moves: list[str] | None = None,
                 bench: list[PokemonState] | None = None,
                 use_usage: bool = True) -> TurnAnalysis:
    """Classe mes coups pour le tour courant (mode analyse).

    Si l'adversaire est connu mais ses coups non renseignés, la menace est
    estimée à partir de son set le plus probable (usage, §10.3). Si un banc
    (`bench`) est fourni, les changements possibles sont aussi évalués et
    peuvent primer la recommandation quand la situation de l'actif est mauvaise.
    """
    my_moves = my_moves if my_moves is not None else list(me.moves)
    incoming = _incoming(me, opp, field, opp_move, use_usage=use_usage)
    my_max_hp = battle_stats(me)["hp"]
    my_cur_hp = max(1, int(my_max_hp * max(0.0, min(1.0, me.current_hp_pct))) or my_max_hp)
    inc_frac = min(1.0, (incoming.max_pct / 100.0) * (my_max_hp / my_cur_hp)) \
        if incoming.known else 0.0

    options: list[MoveEval] = []
    other: list[MoveEval] = []

    for mv in my_moves:
        if not move_known(mv):
            other.append(MoveEval(move=mv, kind="status", value=0.0,
                                  notes=["coup inconnu (hors données)"]))
            continue
        m = get_move(mv)
        if m.is_status:
            val, notes = _evaluate_support(m.name, me, opp, field, incoming)
            other.append(MoveEval(move=m.name, kind="status", value=val,
                                  notes=notes))
            continue
        try:
            res = calculate(me, opp, mv, field)
        except (ValueError, KeyError):
            # Coup à puissance variable / non géré par le calc : listé, non noté.
            other.append(MoveEval(move=m.name, kind="status", value=0.0,
                                  notes=["puissance variable — non évalué"]))
            continue
        cur = res.defender_current_hp
        guaranteed = res.min_damage >= cur
        possible = res.max_damage >= cur
        ko_flag = 1.0 if guaranteed else (0.5 if possible else 0.0)
        ko_txt = ("KO garanti" if guaranteed else
                  "KO possible" if possible else None)
        first = moves_first(me, opp, mv, opp_move, field)

        off = min(1.0, (res.min_damage + res.max_damage) / 2 / cur)
        # Si j'agis en premier ET je tue à coup sûr, l'adversaire ne riposte pas.
        safe = (first is True and guaranteed)
        eff_incoming = 0.0 if safe else inc_frac
        value = (W_OFFENSE * off + W_KO * ko_flag - W_RISK * eff_incoming
                 + (W_SPEED if first else 0.0))

        notes: list[str] = []
        if safe:
            notes.append("tue avant que l'adversaire agisse")
        elif incoming.ohko and first is not True:
            notes.append("risque : OHKO subi avant d'agir")
        if res.type_effectiveness == 0:
            notes.append("sans effet (immunité)")

        options.append(MoveEval(
            move=m.name, kind="damage", value=value,
            min_pct=res.min_pct, max_pct=res.max_pct, ko=ko_txt,
            first=first, notes=notes,
        ))

    options.sort(key=lambda e: e.value, reverse=True)
    other.sort(key=lambda e: e.value, reverse=True)
    switches = (evaluate_switches(bench, opp, field, opp_move, use_usage)
                if bench else [])
    recommendation = _recommend(options, incoming, switches, other)
    return TurnAnalysis(options=options, other=other, incoming=incoming,
                        recommendation=recommendation, switches=switches)


def _recommend(options: list[MoveEval], incoming: Incoming,
               switches: list[SwitchEval] | None = None,
               support: list[MoveEval] | None = None) -> str:
    switches = switches or []
    support = support or []
    best = options[0] if options else None

    # Situation mauvaise pour l'actif : mis KO avant d'agir sans tuer en premier.
    active_bad = (incoming.ohko and (best is None or not (best.first and best.ko)))
    best_switch = switches[0] if switches else None
    if active_bad and best_switch and best_switch.survives \
            and best_switch.value > 0:
        pivot = (f" (menace {best_switch.best_move})"
                 if best_switch.best_move else "")
        return (f"Changer pour {best_switch.species} — l'actif serait mis KO ; "
                f"ce switch encaisse{pivot}.")

    # Un coup de soutien peut primer si l'actif ne tue pas déjà à coup sûr.
    best_support = support[0] if support else None
    if best_support and best_support.value > 0.3 \
            and (best is None or (best.ko != "KO garanti"
                                  and best_support.value > best.value)):
        why = f" — {best_support.notes[0]}" if best_support.notes else ""
        return f"{best_support.move}{why}."

    if best is None:
        if best_switch and best_switch.survives:
            return f"Changer pour {best_switch.species} (aucun coup offensif utile)."
        return "aucun coup offensif disponible (voir coups de statut)."
    if best.ko == "KO garanti" and best.first:
        return f"{best.move} — KO garanti en agissant en premier."
    if best.ko == "KO garanti":
        risk = " (mais tu peux être mis KO avant)" if incoming.ohko else ""
        return f"{best.move} — KO garanti{risk}."
    if best.ko == "KO possible":
        return f"{best.move} — meilleure pression (KO possible)."
    return f"{best.move} — meilleur compromis dégâts/risque."
