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
import random
from dataclasses import replace

from .sim import Mon, Side, simulate_turn_actions
from .usage import likely_set, sample_set, has_usage

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
    """Évaluation **d'équipe** (mon point de vue).

    On compare la santé MOYENNE de mon camp (actif + banc, un Pokémon K.O. compte
    0) à celle de l'actif adverse — perdre un membre coûte donc réellement, ce
    qui valorise un changement qui **préserve** l'actif menacé. Un actif adverse
    K.O. rapporte un bonus (on ne modélise pas son banc). Termes légers pour les
    boosts/statuts de mon actif.
    """
    slots = [me.active, *me.bench]
    my_avg = sum(x.hp_pct for x in slots) / len(slots)
    opp_hp = 0.0 if opp_active.fainted else opp_active.hp_pct
    v = my_avg - opp_hp
    if opp_active.fainted:
        v += 1.0                              # j'ai battu l'actif adverse
    a = me.active
    off = ("atk", "spa", "spe")
    v += 0.03 * sum(a.boosts.get(k, 0) for k in off)
    if not a.fainted and a.status in _STATUSES:
        v -= 0.08
    if opp_active.status in _STATUSES:
        v += 0.08
    return v


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


def _aggregate(values: list[float], model: str) -> float:
    """Agrège les issues sur les coups adverses : moyenne (nœud « chance ») ou
    minimum (adversaire qui joue au mieux contre moi — minimax)."""
    return min(values) if model == "worst" else sum(values) / len(values)


def _state_value(me: Side, opp: Side, field: FieldState | None,
                 depth: int, roll: float, opp_cands: list[str | None],
                 model: str) -> float:
    """Valeur d'un état (mon point de vue) : je maximise, l'adversaire est agrégé
    selon `model` ('expected' = moyenne, 'worst' = minimax). Feuille à
    `depth<=0`/terminal."""
    if depth <= 0 or _terminal(me, opp):
        return evaluate_side(me, opp.active)
    best = float("-inf")
    for action in _my_actions(me, allow_switch=False):
        vals = [
            _state_value(
                *_child(me, opp, action, omv, field, roll),
                field, depth - 1, roll, opp_cands, model)
            for omv in opp_cands
        ]
        best = max(best, _aggregate(vals, model))
    return GAMMA * best


def _child(me: Side, opp: Side, action: tuple, omv: str | None,
           field: FieldState | None, roll: float) -> tuple[Side, Side]:
    res = simulate_turn_actions(me, opp, action, ("move", omv), field,
                                roll=roll, copy=True)
    return res.me, res.opp


def rank_actions(me: Mon, opp: Mon, field: FieldState | None = None, *,
                 my_moves: list[str] | None = None,
                 my_bench: list[Mon] | None = None,
                 use_usage: bool = True, roll: float = 0.5,
                 depth: int = 1, opp_model: str = "expected") -> SearchResult:
    """Classe mes actions (coups **et** changements) par valeur.

    `depth=1` : évaluation immédiate après le tour (rapide). `depth≥2` : recherche
    multi-tours sur le simulateur.
    `opp_model` : « expected » (adversaire moyen — nœuds chance) ou « worst »
    (minimax — l'adversaire répond au mieux contre moi, à chaque tour ; mode
    prudent). Dans les deux cas on remonte `expected` et `worst` pour info, mais
    le **classement** suit le modèle choisi. Si `my_bench` est fourni, chaque
    changement vers un Pokémon vivant est évalué au même titre qu'un coup.
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
                                             roll, opp_cands, opp_model))
            if res.opp_fainted:
                ko_chance = True
            if res.me_fainted:
                survives_worst = False
        actions.append(ActionValue(
            move=label, expected=sum(outcomes) / len(outcomes),
            worst=min(outcomes), ko_chance=ko_chance,
            survives_worst=survives_worst, kind=kind))

    key = ((lambda a: (a.worst, a.expected)) if opp_model == "worst"
           else (lambda a: (a.expected, a.worst)))
    actions.sort(key=key, reverse=True)
    return SearchResult(actions=actions, opp_moves=opp_cands,
                        recommendation=_recommend(actions, opp_model))


def _phrase(a: ActionValue) -> str:
    if a.kind == "switch":
        return f"Changer pour {a.move[2:]}"      # retire le préfixe « → »
    return a.move


def _sampled_opp(opp: Mon, ls, reg_id: str) -> Mon:
    """Applique un build échantillonné à l'adversaire, en respectant l'info déjà
    observée (§10.3 : ce qui est renseigné n'est pas ré-échantillonné)."""
    st = opp.build
    moves = st.moves or (ls.moves or [])
    nature = st.nature if st.nature not in (None, "serious") else (ls.nature or "serious")
    return Mon.from_state(replace(
        st, moves=list(moves), item=st.item or ls.item,
        ability=st.ability or ls.ability, nature=nature))


def rank_actions_sampled(me: Mon, opp: Mon, field: FieldState | None = None, *,
                         my_bench: list[Mon] | None = None, depth: int = 1,
                         opp_model: str = "expected", roll: float = 0.5,
                         n_samples: int = 8, reg_id: str = "reg_m_b",
                         seed: int | None = 0) -> SearchResult:
    """Recherche **déterminisée** (ISMCTS-lite, §0.1) : quand le build adverse est
    inconnu, échantillonne `n_samples` builds plausibles depuis l'usage, lance la
    recherche pour chacun et **agrège** les valeurs par action.

    Si l'adversaire a déjà des coups renseignés, ou s'il n'y a pas de données
    d'usage, on retombe sur `rank_actions` (une seule évaluation).
    """
    if opp.build.moves or not has_usage(reg_id):
        return rank_actions(me, opp, field, my_bench=my_bench, depth=depth,
                            opp_model=opp_model, roll=roll)
    rng = random.Random(seed)
    agg: dict[str, dict] = {}
    order: list[str] = []
    n_ok = 0
    for _ in range(max(1, n_samples)):
        ls = sample_set(opp.build.species, reg_id, rng=rng)
        if not ls.moves:
            break                            # espèce absente de l'usage
        sopp = _sampled_opp(opp, ls, reg_id)
        res = rank_actions(me, sopp, field, my_bench=my_bench, depth=depth,
                          opp_model=opp_model, roll=roll, use_usage=False)
        n_ok += 1
        for a in res.actions:
            if a.move not in agg:
                agg[a.move] = {"e": 0.0, "w": 0.0, "ko": False, "sv": True,
                               "kind": a.kind}
                order.append(a.move)
            d = agg[a.move]
            d["e"] += a.expected
            d["w"] += a.worst
            d["ko"] = d["ko"] or a.ko_chance
            d["sv"] = d["sv"] and a.survives_worst
    if n_ok == 0:
        return rank_actions(me, opp, field, my_bench=my_bench, depth=depth,
                            opp_model=opp_model, roll=roll)
    actions = [ActionValue(move=label, expected=agg[label]["e"] / n_ok,
                           worst=agg[label]["w"] / n_ok, ko_chance=agg[label]["ko"],
                           survives_worst=agg[label]["sv"], kind=agg[label]["kind"])
               for label in order]
    key = ((lambda a: (a.worst, a.expected)) if opp_model == "worst"
           else (lambda a: (a.expected, a.worst)))
    actions.sort(key=key, reverse=True)
    return SearchResult(actions=actions,
                        opp_moves=[f"échantillonné ({n_ok} builds d'usage)"],
                        recommendation=_recommend(actions, opp_model))


def _recommend(actions: list[ActionValue], opp_model: str = "expected") -> str:
    if not actions:
        return "aucune action évaluable."
    best = actions[0]
    if opp_model == "worst":
        # Le classement est déjà minimax : `best` est l'action la plus sûre.
        ko = " — peut mettre KO" if best.ko_chance else ""
        risk = "" if best.survives_worst else " (aucune option ne garantit la survie)"
        return f"{_phrase(best)} — meilleure garantie au pire cas{ko}{risk}."
    # Préfère une option sûre si elle est proche de la meilleure espérance.
    safe = [a for a in actions if a.survives_worst]
    if safe and safe[0] is not best and safe[0].expected >= best.expected - 0.15:
        s = safe[0]
        return (f"{_phrase(s)} — meilleur compromis sûr "
                f"(attendu {s.expected:+.2f}, ne se fait pas KO).")
    risk = "" if best.survives_worst else " (mais risque de KO au pire cas)"
    ko = " — peut mettre KO" if best.ko_chance else ""
    return f"{_phrase(best)} — meilleure valeur attendue{ko}{risk}."
