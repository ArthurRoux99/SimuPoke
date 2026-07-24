"""Recherche à coups simultanés (§10.2) — expectimax sur le simulateur.

Au lieu de l'heuristique à un tour de B1, on **simule** chaque combinaison (mon
coup × coup adverse) via le simulateur, on **évalue l'état résultant**, et on
classe mes actions par valeur **attendue** sur la distribution des coups adverses
— en signalant le **pire cas** (l'adversaire choisit en même temps que moi,
information imparfaite).

Avec `depth≥2`, on cherche en **profondeur** : après mon action et la réponse
(stochastique, nœud « chance ») de l'adversaire, je continue à jouer au mieux
(nœud « max ») sur `depth-1` tours de plus, avec un escompte `GAMMA` par tour
(les gains proches priment). Ce n'est pas encore de l'ISMCTS, mais un expectimax
déterminisé, borné et explicable — même fonction d'évaluation, même simulateur.

Bornage de l'arbre : dans la descente, seuls les **coups** sont explorés côté
« moi » (plus un changement FORCÉ si l'actif tombe K.O.) ; les changements
volontaires ne sont évalués qu'au **niveau racine**. L'adversaire est un nœud
stochastique **uniforme** sur ses coups probables (observés, sinon usage §10.3) ;
son banc n'est pas modélisé (un actif adverse K.O. = feuille favorable).
"""

from __future__ import annotations

from dataclasses import dataclass, field as dfield

from .model import PokemonState, FieldState
from .basestats import is_known
from .moves import get_move, is_known as move_known
from .sim import Mon, Side, simulate_turn_actions
from .usage import likely_set

_STATUSES = ("brn", "par", "tox", "slp", "frz", "psn")

# Escompte par tour de recherche : une victoire (ou une bonne position) plus
# proche vaut mieux qu'une lointaine, et départage les valeurs saturées à ±2.
GAMMA = 0.9


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


# ---------------------------------------------------------------------------
# Recherche en profondeur (expectimax à coups simultanés)
# ---------------------------------------------------------------------------

def _terminal(me: Side, opp: Side) -> bool:
    """État feuille : l'adversaire est K.O. (on ne modélise pas son banc), ou je
    n'ai plus rien à envoyer."""
    if opp.active.fainted:
        return True
    if me.active.fainted and not any(not b.fainted for b in me.bench):
        return True
    return False


def _my_actions(me: Side, allow_switch: bool) -> list[tuple]:
    """Actions légales pour moi. Les changements « volontaires » ne sont permis
    qu'au niveau demandé (`allow_switch`) — dans la descente, seuls les coups (ou
    un changement FORCÉ si l'actif est K.O.) sont explorés, ce qui borne l'arbre.
    """
    if me.active.fainted:
        return [("switch", i) for i, b in enumerate(me.bench) if not b.fainted]
    acts: list[tuple] = [("move", m) for m in me.active.build.moves if move_known(m)]
    if allow_switch:
        acts += [("switch", i) for i, b in enumerate(me.bench) if not b.fainted]
    return acts or [("move", None)]


def _state_value(me: Side, opp: Side, field: FieldState | None,
                 depth: int, roll: float, opp_cands: list[str | None]) -> float:
    """Valeur d'un état (mon point de vue) : je maximise, l'adversaire est un
    nœud stochastique (uniforme) sur `opp_cands`. Feuille à `depth<=0`/terminal."""
    if depth <= 0 or _terminal(me, opp):
        return evaluate_side(me, opp.active)
    best = float("-inf")
    for action in _my_actions(me, allow_switch=False):
        acc = 0.0
        for omv in opp_cands:
            child = simulate_turn_actions(me, opp, action, ("move", omv),
                                          field, roll=roll, copy=True)
            acc += _state_value(child.me, child.opp, field, depth - 1, roll,
                                opp_cands)
        best = max(best, acc / len(opp_cands))
    return GAMMA * best


def rank_actions(me: Mon, opp: Mon, field: FieldState | None = None, *,
                 my_moves: list[str] | None = None,
                 my_bench: list[Mon] | None = None,
                 use_usage: bool = True, roll: float = 0.5,
                 depth: int = 1) -> SearchResult:
    """Classe mes actions (coups **et** changements) par valeur attendue.

    `depth=1` : évaluation immédiate après le tour (rapide). `depth≥2` : recherche
    expectimax multi-tours — après mon action et la réponse (stochastique) de
    l'adversaire, je continue à jouer au mieux sur `depth-1` tours de plus. Si
    `my_bench` est fourni, chaque changement vers un Pokémon vivant est évalué au
    même titre qu'un coup (l'adversaire frappe l'entrant).
    """
    depth = max(1, min(5, depth))            # borne de sécurité (coût ~ ×10/ply)
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
            if depth <= 1:
                outcomes.append(evaluate_side(res.me, res.opp.active))
            else:
                outcomes.append(_state_value(res.me, res.opp, field, depth - 1,
                                             roll, opp_cands))
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
