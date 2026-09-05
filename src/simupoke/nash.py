"""Résolution de tour vers l'équilibre de Nash (§10.2) — jeu matriciel bayésien
à coups simultanés, résolu par **regret matching** (CFR).

Le tour de combat est **simultané** : je choisis en même temps que l'adversaire.
Recommander une seule action « optimale » est donc **exploitable** ; la réponse
correcte, à l'état de l'art (PokéChamp minimax, PokaiTrainer belief-state + CFR),
est une **stratégie mixte** de Nash.

Ce module :

1. construit une **croyance** sur le set adverse ([`belief`], usage §10.3) ;
2. dresse la **matrice de gains** ``U[a][b]`` = valeur de mon état après (mon
   action `a`, coup adverse `b`), **pondérée par la croyance** (moyenne sur les
   particules qui peuvent jouer `b`) et **moyennée sur les jets de dégâts**
   (énumération de la chance, façon PokaiTrainer) ;
3. résout le jeu à somme nulle (je maximise, l'adversaire minimise) par
   **regret matching** — qui converge vers Nash sur un jeu matriciel — et renvoie
   ma **stratégie mixte**, la valeur du jeu et la stratégie adverse.

État (échelle SOTA de `docs/recherche_sota_ismcts.md`) : adversaire **par monde**
(seat-2 par-world de PokaiTrainer, `solve_bayesian`), **profondeur** par CFR
récursif (`horizon`, `_sm_nash_value`), et **mise à jour de croyance inter-tours**
sur le coup observé (`belief.update_belief`, alimentée par `opp_world_strategies`
exposé ici). Restent : budget d'expansion PUCT et évaluateur de feuille appris.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dfield

from .belief import Particle, opponent_belief, opponent_move_support
from .model import FieldState
from .moves import get_move
from .moves import is_known as move_known
from .search import GAMMA, _child, _my_actions, _state_value, _terminal, evaluate_side
from .sim import Mon, Side, simulate_turn_actions

# Jets de dégâts représentatifs (énumération de la chance, poids uniforme).
ROLLS = (0.15, 0.5, 0.85)
# Itérations de regret matching pour les nœuds internes du lookahead Nash.
_INNER_ITERS = 500


# ---------------------------------------------------------------------------
# Solveur de jeu matriciel — regret matching (converge vers Nash)
# ---------------------------------------------------------------------------

def solve_matrix(U: list[list[float]], iters: int = 2000
                 ) -> tuple[list[float], list[float], float]:
    """Résout le jeu à somme nulle `U` (ligne maximise, colonne minimise).

    Renvoie (stratégie ligne moyenne, stratégie colonne moyenne, valeur du jeu).
    Déterministe : le regret matching en self-play converge vers un équilibre.
    """
    n, m = len(U), len(U[0])
    rreg = [0.0] * n
    creg = [0.0] * m
    rsum = [0.0] * n
    csum = [0.0] * m

    def strat(reg: list[float]) -> list[float]:
        pos = [r if r > 0 else 0.0 for r in reg]
        s = sum(pos)
        return [p / s for p in pos] if s > 0 else [1.0 / len(reg)] * len(reg)

    for _ in range(iters):
        rs = strat(rreg)
        cs = strat(creg)
        for i in range(n):
            rsum[i] += rs[i]
        for j in range(m):
            csum[j] += cs[j]
        # Regrets de la ligne (elle maximise U).
        urow = [sum(cs[j] * U[i][j] for j in range(m)) for i in range(n)]
        vrow = sum(rs[i] * urow[i] for i in range(n))
        for i in range(n):
            rreg[i] += urow[i] - vrow
        # Regrets de la colonne (elle minimise U, i.e. maximise -U).
        ucol = [sum(rs[i] * (-U[i][j]) for i in range(n)) for j in range(m)]
        vcol = sum(cs[j] * ucol[j] for j in range(m))
        for j in range(m):
            creg[j] += ucol[j] - vcol

    rst = [x / sum(rsum) for x in rsum]
    cst = [x / sum(csum) for x in csum]
    val = sum(rst[i] * U[i][j] * cst[j]
              for i in range(n) for j in range(m))
    return rst, cst, val


# ---------------------------------------------------------------------------
# Construction de la matrice croyance × chance
# ---------------------------------------------------------------------------

def _leaf_value(res, field: FieldState | None, roll: float,
                opp_cands: list[str | None], horizon: int) -> float:
    """Valeur de l'état post-tour. `horizon=0` : éval immédiate. `horizon>0` :
    lookahead expectimax de `horizon` tours (réutilise `search._state_value`,
    qui retombe sur l'éval immédiate à profondeur 0)."""
    if horizon <= 0:
        return evaluate_side(res.me, res.opp.active)
    return _state_value(res.me, res.opp, field, horizon, roll, opp_cands,
                        "expected")


def _sm_nash_value(me: Side, opp: Side, field: FieldState | None,
                   depth: int, roll: float) -> float:
    """Valeur **Nash** d'un état à information parfaite, à `depth` tours.

    À l'intérieur d'un monde, le set adverse est connu : la continuation est un
    jeu simultané à information parfaite. On la résout vers Nash à **chaque
    étage** (regret matching), au lieu de l'expectimax (adversaire fixe + moi
    glouton). C'est le cran « CFR récursif » de l'échelle SOTA.
    """
    if depth <= 0 or _terminal(me, opp):
        return evaluate_side(me, opp.active)
    my_acts = _my_actions(me, allow_switch=False)
    opp_acts: list[str | None] = [m for m in opp.active.build.moves
                                  if move_known(m)] or [None]
    U = [[_sm_nash_value(*_child(me, opp, a, omv, field, roll),
                         field=field, depth=depth - 1, roll=roll)
          for omv in opp_acts]
         for a in my_acts]
    _, _, val = solve_matrix(U, iters=_INNER_ITERS)
    return GAMMA * val


def _leaf_value_world(res, field: FieldState | None, roll: float,
                      horizon: int, budget: int | None = None) -> float:
    """Feuille d'un monde (adversaire connu) : éval immédiate à `horizon=0`,
    sinon **Nash récursif** (les deux camps jouent au mieux à chaque tour).

    `budget` bascule sur la recherche **échantillonnée** (`ismcts`, SM-MCTS avec
    regret matching) : coût linéaire en `budget × horizon` au lieu
    d'exponentiel, donc un horizon bien au-delà des 3 tours du calcul exact.
    """
    if horizon <= 0:
        return evaluate_side(res.me, res.opp.active)
    if budget:
        from .ismcts import sm_mcts_value
        return sm_mcts_value(res.me, res.opp, field, depth=horizon, roll=roll,
                             budget=budget)
    return _sm_nash_value(res.me, res.opp, field, horizon, roll)


def _payoff_matrix(me: Mon, my_bench: list[Mon], particles: list[Particle],
                   my_actions: list[tuple], opp_moves: list[str | None],
                   field: FieldState | None, horizon: int = 0
                   ) -> list[list[float]]:
    """U[i][j] = valeur attendue de mon état après (mon action i, coup adverse j),
    pondérée par les particules qui peuvent jouer j et moyennée sur les jets."""
    matrix: list[list[float]] = []
    for action in my_actions:
        row: list[float] = []
        for omv in opp_moves:
            num = 0.0
            den = 0.0
            for part in particles:
                feasible = omv is None or omv in part.build.moves
                if not feasible:
                    continue
                opp_mon = Mon.from_state(part.build)
                vals = []
                for roll in ROLLS:
                    res = simulate_turn_actions(
                        Side(active=me, bench=my_bench), Side(active=opp_mon),
                        action, ("move", omv), field, roll=roll, copy=True)
                    vals.append(_leaf_value(res, field, roll, opp_moves, horizon))
                num += part.weight * (sum(vals) / len(vals))
                den += part.weight
            row.append(num / den if den > 0 else 0.0)
        matrix.append(row)
    return matrix


# ---------------------------------------------------------------------------
# Jeu bayésien : l'adversaire connaît son set (info privée) et joue PAR MONDE
# ---------------------------------------------------------------------------
# Un cran vers l'état de l'art (PokaiTrainer : une table de regret par monde pour
# le seat 2). L'adversaire n'est plus un « type moyen » : dans chaque monde
# (particule de croyance) il joue au mieux contre moi, et je dois committer une
# stratégie unique **avant** de savoir quel monde est réel. Résultat : robuste à
# un adversaire qui exploite ce qu'il sait.

def _world_payoff(me: Mon, my_bench: list[Mon], particle: Particle,
                  my_actions: list[tuple], opp_actions_w: list[str | None],
                  field: FieldState | None, horizon: int = 0,
                  budget: int | None = None) -> list[list[float]]:
    """Matrice de gains DANS un monde : U[a][b] moyennée sur les jets."""
    opp_mon = Mon.from_state(particle.build)
    matrix: list[list[float]] = []
    for action in my_actions:
        row: list[float] = []
        for omv in opp_actions_w:
            vals = []
            for roll in ROLLS:
                res = simulate_turn_actions(
                    Side(active=me, bench=my_bench), Side(active=opp_mon),
                    action, ("move", omv), field, roll=roll, copy=True)
                vals.append(_leaf_value_world(res, field, roll, horizon,
                                              budget))
            row.append(sum(vals) / len(vals))
        matrix.append(row)
    return matrix


def solve_bayesian(my_n: int, worlds: list[tuple[float, list[list[float]],
                   list[str | None]]], iters: int = 2000
                   ) -> tuple[list[float], float, list[tuple[str | None, float]],
                              int, list[list[float]]]:
    """Résout le jeu bayésien : je maximise une stratégie **unique** (`my_n`
    actions) ; dans chaque monde `w` (poids, matrice `U_w`, libellés adverses)
    l'adversaire minimise avec sa **propre** stratégie. Regret matching :
    une table pour moi, une par monde pour l'adversaire (converge vers l'équilibre
    bayésien ex-ante).

    Renvoie (ma stratégie moyenne, valeur, stratégie adverse **marginale**
    (label → proba), indice de ma meilleure réponse pure, **stratégie adverse
    par monde** (une distribution sur les colonnes de chaque `U_w`)).
    """
    r1 = [0.0] * my_n
    s1 = [0.0] * my_n
    r2 = [[0.0] * len(U[0]) for _, U, _ in worlds]
    s2 = [[0.0] * len(U[0]) for _, U, _ in worlds]

    def strat(reg: list[float]) -> list[float]:
        pos = [r if r > 0 else 0.0 for r in reg]
        tot = sum(pos)
        return [p / tot for p in pos] if tot > 0 else [1.0 / len(reg)] * len(reg)

    for _ in range(iters):
        sig1 = strat(r1)
        sig2 = [strat(r2[w]) for w in range(len(worlds))]
        for a in range(my_n):
            s1[a] += sig1[a]
        for w in range(len(worlds)):
            for b in range(len(sig2[w])):
                s2[w][b] += sig2[w][b]
        # Utilités de MES actions : moyenne pondérée sur les mondes et la
        # stratégie adverse propre à chaque monde.
        u1 = [0.0] * my_n
        for a in range(my_n):
            for w, (pw, U, _) in enumerate(worlds):
                u1[a] += pw * sum(sig2[w][b] * U[a][b] for b in range(len(U[a])))
        v1 = sum(sig1[a] * u1[a] for a in range(my_n))
        for a in range(my_n):
            r1[a] += u1[a] - v1
        # Utilités adverses PAR MONDE (il minimise U_w, i.e. maximise -U_w).
        for w, (_, U, _) in enumerate(worlds):
            ucol = [-sum(sig1[a] * U[a][b] for a in range(my_n))
                    for b in range(len(U[0]))]
            vcol = sum(sig2[w][b] * ucol[b] for b in range(len(ucol)))
            for b in range(len(ucol)):
                r2[w][b] += ucol[b] - vcol

    my_strat = [x / sum(s1) for x in s1]
    world_strat = [[x / sum(s2[w]) for x in s2[w]] for w in range(len(worlds))]

    value = 0.0
    for w, (pw, U, _) in enumerate(worlds):
        value += pw * sum(my_strat[a] * U[a][b] * world_strat[w][b]
                          for a in range(my_n) for b in range(len(U[0])))

    # Stratégie adverse marginale (pour l'affichage), sur l'union des libellés.
    marg: dict[str | None, float] = {}
    for w, (pw, _, labels) in enumerate(worlds):
        for b, lbl in enumerate(labels):
            marg[lbl] = marg.get(lbl, 0.0) + pw * world_strat[w][b]
    opp_marginal = sorted(marg.items(), key=lambda t: t[1], reverse=True)

    br = max(range(my_n),
             key=lambda a: sum(pw * sum(world_strat[w][b] * U[a][b]
                                        for b in range(len(U[0])))
                               for w, (pw, U, _) in enumerate(worlds)))
    return my_strat, value, opp_marginal, br, world_strat


# ---------------------------------------------------------------------------
# Résultat + résolution de tour
# ---------------------------------------------------------------------------

@dataclass
class NashResult:
    strategy: list[tuple[str, float]]        # (libellé action, probabilité) desc
    value: float                             # valeur du jeu (mon point de vue)
    opp_actions: list[str | None]
    opp_strategy: list[tuple[str, float]]
    best_response: str                       # meilleure action PURE vs strat adverse
    recommendation: str
    notes: list[str] = dfield(default_factory=list)
    belief: list[Particle] = dfield(default_factory=list)  # croyance sur le set adverse
    # Stratégie adverse par monde (alignée sur `belief`) : {coup: proba}. Sert à
    # la mise à jour bayésienne inter-tours (`belief.update_belief`).
    opp_world_strategies: list[dict] = dfield(default_factory=list)

    def lines(self) -> list[str]:
        out = ["Stratégie mixte de Nash (jeu simultané, croyance sur l'adversaire) :"]
        for label, p in self.strategy:
            if p >= 0.005:
                out.append(f"  {label:<18} {p*100:5.1f} %")
        out.append("")
        opp = ", ".join(f"{(m or 'inactif')} {p*100:.0f}%"
                        for m, p in self.opp_strategy if p >= 0.02)
        out.append(f"Adversaire (modèle Nash) : {opp}")
        out.append(f"Valeur du jeu : {self.value:+.2f}")
        if len(self.belief) > 1:
            out.append("")
            out.append("Croyance sur le set adverse (usage §10.3) :")
            for part in self.belief:
                b = part.build
                item = f" @ {b.item}" if b.item else ""
                out.append(f"  {part.weight*100:4.0f} %{item}  ·  "
                           f"{', '.join(b.moves)}")
        out.append("")
        out.append(f"➤ {self.recommendation}")
        return out


def _label(action: tuple, me: Mon, my_bench: list[Mon]) -> str:
    kind, x = action
    if kind == "switch":
        return f"→ {my_bench[x].build.species}"
    if x is None:
        return "(inactif)"
    return get_move(x).name


def solve_turn(me: Mon, opp: Mon, field: FieldState | None = None, *,
               my_bench: list[Mon] | None = None, reg_id: str = "reg_m_b",
               iters: int = 2000, belief_samples: int = 80,
               per_world: bool = True, horizon: int = 0,
               belief: list[Particle] | None = None,
               budget: int | None = None,
               seed: int | None = 0) -> NashResult:
    """Résout le tour courant vers Nash et renvoie ma stratégie mixte.

    Mes actions = mes coups (connus) + un changement par membre vivant du banc.
    L'adversaire = coups plausibles sur la croyance (usage §10.3, filtrée par
    l'observé). La chance (jets de dégâts) est énumérée sur `ROLLS`.

    `per_world=True` (défaut) : jeu **bayésien** — l'adversaire connaît son set
    (info privée) et joue au mieux **dans chaque monde** de la croyance ; je
    committe une stratégie unique (robuste). `per_world=False` : adversaire
    « moyen » (une stratégie de colonne unique sur la croyance).

    `belief` : croyance **déjà maintenue** (particules pondérées) à résoudre
    telle quelle, au lieu de la reconstruire depuis `opp`. Sert à chaîner la
    mise à jour bayésienne inter-tours (`belief.update_belief`).

    `budget` : nombre d'itérations de la recherche **échantillonnée**
    (`ismcts`). Sans lui, le lookahead développe tout l'arbre et `horizon` est
    bridé à 3 tours (coût exponentiel) ; avec lui, le coût devient linéaire et
    l'horizon monte jusqu'à 8.
    """
    bench = my_bench or []
    particles = (belief if belief is not None
                 else opponent_belief(opp.build, reg_id,
                                      n_samples=belief_samples, seed=seed))
    opp_moves: list[str | None] = list(opponent_move_support(particles)) or [None]

    my_actions: list[tuple] = [("move", m) for m in me.build.moves if move_known(m)]
    my_actions += [("switch", i) for i, b in enumerate(bench) if not b.fainted]
    if not my_actions:
        my_actions = [("move", None)]
    labels = [_label(a, me, bench) for a in my_actions]

    # Sans budget, le lookahead est exhaustif : coût exponentiel par ply, donc
    # horizon bridé à 3. Avec budget, il est échantillonné : coût linéaire.
    horizon = max(0, min(8 if budget else 3, horizon))
    world_strategies: list[dict] = []
    if per_world and len(particles) > 1:
        worlds = []
        for part in particles:
            opp_w: list[str | None] = [m for m in part.build.moves
                                       if move_known(m)] or [None]
            U_w = _world_payoff(me, bench, part, my_actions, opp_w, field,
                                horizon, budget)
            worlds.append((part.weight, U_w, opp_w))
        rst, val, opp_strat, br_idx, world_strat = solve_bayesian(
            len(my_actions), worlds, iters=iters)
        world_strategies = [dict(zip(worlds[w][2], world_strat[w]))
                            for w in range(len(worlds))]
    else:
        U = _payoff_matrix(me, bench, particles, my_actions, opp_moves, field,
                           horizon)
        rst, cst, val = solve_matrix(U, iters=iters)
        opp_strat = sorted(zip(opp_moves, cst), key=lambda t: t[1], reverse=True)
        br_idx = max(range(len(my_actions)),
                     key=lambda i: sum(cst[j] * U[i][j]
                                       for j in range(len(opp_moves))))
        # Un seul monde : la stratégie de colonne s'applique à chaque particule.
        world_strategies = [dict(zip(opp_moves, cst)) for _ in particles]

    strat = sorted(zip(labels, rst), key=lambda t: t[1], reverse=True)
    best_response = labels[br_idx]

    top_label, top_p = strat[0]
    if top_p >= 0.9:
        reco = f"{_phrase_label(top_label)} — action quasi pure ({top_p*100:.0f} %)."
    else:
        mix = ", ".join(f"{lbl} {p*100:.0f}%" for lbl, p in strat[:3] if p >= 0.05)
        reco = (f"Stratégie mixte optimale : {mix} — mélange pour ne pas être "
                f"exploité au jeu simultané.")
    notes = []
    if len(particles) > 1:
        notes.append(f"croyance : {len(particles)} builds adverses pondérés")
    if budget and horizon:
        notes.append(f"lookahead sous budget : {budget} itérations SM-MCTS "
                     f"sur {horizon} tours")
    return NashResult(strategy=strat, value=val, opp_actions=opp_moves,
                      opp_strategy=opp_strat, best_response=best_response,
                      recommendation=reco, notes=notes, belief=particles,
                      opp_world_strategies=world_strategies)


def _phrase_label(label: str) -> str:
    return f"Changer pour {label[2:]}" if label.startswith("→ ") else f"Joue {label}"
