"""Recherche à coups simultanés (§10.2) — 1-ply expectimax sur le simulateur.

Premier vrai pas vers la Phase 4 : au lieu de l'heuristique à un tour de B1, on
**simule** chaque combinaison (mon coup × coup adverse) via `sim.simulate_turn`,
on **évalue l'état résultant**, et on classe mes actions par valeur **attendue**
sur la distribution des coups adverses — tout en signalant le **pire cas** (l'
adversaire choisit en même temps que moi, information imparfaite).

La distribution adverse vient des coups observés, sinon du set le plus probable
(usage §10.3) ; à défaut, on suppose l'adversaire inactif. Profondeur 1 pour
rester rapide et explicable ; l'extension MCTS/ISMCTS multi-tours réutilisera la
même fonction d'évaluation et le même simulateur.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dfield

from .model import PokemonState, FieldState
from .basestats import is_known
from .moves import get_move, is_known as move_known
from .sim import Mon, Side, simulate_turn_actions
from .usage import likely_set

_STATUSES = ("brn", "par", "tox", "slp", "frz", "psn")


# ---------------------------------------------------------------------------
# Fonction d'évaluation (du point de vue « moi »)
# ---------------------------------------------------------------------------

def evaluate_state(me: Mon, opp: Mon) -> float:
    """Score d'un état, positif = favorable à `me`.

    Les K.O. dominent (±2) ; sinon différentiel de PV (∈ [-1,1]) plus des termes
    légers pour boosts offensifs et statut.
    """
    if opp.fainted and not me.fainted:
        return 2.0
    if me.fainted and not opp.fainted:
        return -2.0
    if me.fainted and opp.fainted:
        return 0.0
    v = me.hp_pct - opp.hp_pct
    off = ("atk", "spa", "spe")
    v += 0.05 * (sum(me.boosts.get(k, 0) for k in off)
                 - sum(opp.boosts.get(k, 0) for k in off))
    if opp.status in _STATUSES:
        v += 0.12
    if me.status in _STATUSES:
        v -= 0.12
    return v


def evaluate_side(me: Side, opp_active: Mon) -> float:
    """Évaluation consciente du banc : l'actif domine, le banc compte un peu.

    Un actif K.O. mais avec un banc vivant n'est pas une défaite totale.
    """
    base = evaluate_state(me.active, opp_active)
    if me.active.fainted and any(not b.fainted for b in me.bench):
        base = max(base, -0.8)                # on peut renvoyer un autre Pokémon
    if me.bench:
        base += 0.1 * sum(b.hp_pct for b in me.bench) / len(me.bench)
    return base


# ---------------------------------------------------------------------------
# Candidats adverses
# ---------------------------------------------------------------------------

def opponent_moves(opp: Mon, use_usage: bool = True) -> list[str | None]:
    """Coups plausibles de l'adversaire (observés, sinon usage, sinon inactif)."""
    if opp.build.moves:
        cands = list(opp.build.moves)
    elif use_usage and is_known(opp.build.species):
        cands = list(likely_set(opp.build.species).moves)
    else:
        cands = []
    cands = [m for m in cands if move_known(m)]
    return cands or [None]                    # [None] = adversaire inactif


# ---------------------------------------------------------------------------
# Classement des actions
# ---------------------------------------------------------------------------

@dataclass
class ActionValue:
    move: str                      # nom du coup, ou « → Espèce » pour un switch
    expected: float                # valeur moyenne sur les coups adverses
    worst: float                   # pire cas (adversaire optimal contre moi)
    ko_chance: bool                # met l'adversaire K.O. dans ≥ un scénario ?
    survives_worst: bool           # je survis au pire cas ?
    kind: str = "move"             # "move" | "switch"
    notes: list[str] = dfield(default_factory=list)


@dataclass
class SearchResult:
    actions: list[ActionValue]
    opp_moves: list[str | None]
    recommendation: str

    def lines(self) -> list[str]:
        opp = ", ".join(m or "inactif" for m in self.opp_moves)
        out = [f"Adversaire modélisé : {opp}", "",
               "Mes actions (valeur attendue / pire cas) :"]
        for i, a in enumerate(self.actions, 1):
            flags = []
            if a.ko_chance:
                flags.append("peut KO")
            if not a.survives_worst:
                flags.append("KO subi au pire")
            tag = f"  [{', '.join(flags)}]" if flags else ""
            out.append(f"  {i}. {a.move:<16} attendu {a.expected:+.2f} / "
                       f"pire {a.worst:+.2f}{tag}")
        out.append("")
        out.append(f"➤ Recommandation : {self.recommendation}")
        return out


def rank_actions(me: Mon, opp: Mon, field: FieldState | None = None, *,
                 my_moves: list[str] | None = None,
                 my_bench: list[Mon] | None = None,
                 use_usage: bool = True, roll: float = 0.5) -> SearchResult:
    """Classe mes actions (coups **et** changements) par valeur attendue à 1 tour.

    Si `my_bench` est fourni, chaque changement vers un Pokémon vivant est
    évalué au même titre qu'un coup : l'adversaire (qui joue en même temps)
    frappe l'entrant, et l'état résultant est noté avec `evaluate_side`.
    """
    bench = my_bench or []
    my_cands = my_moves if my_moves is not None else list(me.build.moves)
    opp_cands = opponent_moves(opp, use_usage)

    # (kind, action, label)
    specs: list[tuple[str, tuple, str]] = [
        ("move", ("move", mv), get_move(mv).name)
        for mv in my_cands if move_known(mv)
    ]
    for i, b in enumerate(bench):
        if not b.fainted:
            specs.append(("switch", ("switch", i), f"→ {b.build.species}"))

    actions: list[ActionValue] = []
    for kind, action, label in specs:
        outcomes: list[float] = []
        ko_chance = False
        survives_worst = True
        for omv in opp_cands:
            res = simulate_turn_actions(
                Side(active=me, bench=bench), Side(active=opp),
                action, ("move", omv), field, roll=roll, copy=True)
            outcomes.append(evaluate_side(res.me, res.opp.active))
            if res.opp_fainted:
                ko_chance = True
            if res.me_fainted:
                survives_worst = False
        actions.append(ActionValue(
            move=label, expected=sum(outcomes) / len(outcomes),
            worst=min(outcomes), ko_chance=ko_chance,
            survives_worst=survives_worst, kind=kind))

    actions.sort(key=lambda a: (a.expected, a.worst), reverse=True)
    return SearchResult(actions=actions, opp_moves=opp_cands,
                        recommendation=_recommend(actions))


def _phrase(a: ActionValue) -> str:
    if a.kind == "switch":
        return f"Changer pour {a.move[2:]}"      # retire le préfixe « → »
    return a.move


def _recommend(actions: list[ActionValue]) -> str:
    if not actions:
        return "aucune action évaluable."
    best = actions[0]
    # Préfère une option sûre si elle est proche de la meilleure espérance.
    safe = [a for a in actions if a.survives_worst]
    if safe and safe[0] is not best and safe[0].expected >= best.expected - 0.15:
        s = safe[0]
        return (f"{_phrase(s)} — meilleur compromis sûr "
                f"(attendu {s.expected:+.2f}, ne se fait pas KO).")
    risk = "" if best.survives_worst else " (mais risque de KO au pire cas)"
    ko = " — peut mettre KO" if best.ko_chance else ""
    return f"{_phrase(best)} — meilleure valeur attendue{ko}{risk}."
