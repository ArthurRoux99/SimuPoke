"""B1 — Assistant de combat, mode analyse (§10.1).

Premier palier « rapide et indicatif » (§15 Q3) : une analyse **à 1 tour** qui
classe mes coups par valeur attendue à l'aide du calculateur de dégâts, en
tenant compte du KO, de l'ordre d'action (priorité + vitesse, Trick Room) et du
risque encouru (dégâts subis). L'action adverse peut être **fournie** (info
quasi parfaite, §10.1) ou **estimée** à partir des coups adverses connus.

Limites v1 (assumées) :
  - analyse d'un seul tour, centrée sur les coups offensifs ; les coups de
    statut/soutien sont listés mais non évalués (il faudrait du multi-tours) ;
  - pas de changement (switch) ni de recherche d'arbre (ce sera §10.2, MCTS).
  - build adverse inconnu => nature neutre / 0 SP par défaut (le modèle d'usage
    §10.3 affinera plus tard).
"""

from __future__ import annotations

from dataclasses import dataclass, field as dfield

from .model import PokemonState, FieldState
from .basestats import is_known, to_id
from .moves import get_move, is_known as move_known
from .damage import calculate, battle_stats
from .usage import likely_set

# Poids de la fonction de valeur (ajustables).
W_OFFENSE = 1.0
W_KO = 0.5
W_RISK = 0.8
W_SPEED = 0.1


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
class TurnAnalysis:
    options: list[MoveEval]            # coups offensifs, classés
    other: list[MoveEval]             # coups de statut/soutien (non notés)
    incoming: Incoming
    recommendation: str

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
            out.append("  Autres (non évalués en v1) : "
                       + ", ".join(e.move for e in self.other))
        out.append("")
        out.append(f"➤ Recommandation : {self.recommendation}")
        return out


def analyze_turn(me: PokemonState, opp: PokemonState,
                 field: FieldState | None = None, *,
                 opp_move: str | None = None,
                 my_moves: list[str] | None = None,
                 use_usage: bool = True) -> TurnAnalysis:
    """Classe mes coups pour le tour courant (mode analyse).

    Si l'adversaire est connu mais ses coups non renseignés, la menace est
    estimée à partir de son set le plus probable (usage, §10.3).
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
            other.append(MoveEval(move=m.name, kind="status", value=0.15,
                                  notes=["coup de statut — non évalué en v1"]))
            continue
        res = calculate(me, opp, mv, field)
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
    recommendation = _recommend(options, incoming)
    return TurnAnalysis(options=options, other=other, incoming=incoming,
                        recommendation=recommendation)


def _recommend(options: list[MoveEval], incoming: Incoming) -> str:
    if not options:
        return "aucun coup offensif disponible (voir coups de statut)."
    best = options[0]
    if best.ko == "KO garanti" and best.first:
        return f"{best.move} — KO garanti en agissant en premier."
    if best.ko == "KO garanti":
        risk = " (mais tu peux être mis KO avant)" if incoming.ohko else ""
        return f"{best.move} — KO garanti{risk}."
    if best.ko == "KO possible":
        return f"{best.move} — meilleure pression (KO possible)."
    return f"{best.move} — meilleur compromis dégâts/risque."
