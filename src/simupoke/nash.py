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

Limite assumée v1 : l'adversaire est traité comme un type « moyen » sur la
croyance (une stratégie de colonne unique), pas une stratégie par monde (seat-2
par-world de PokaiTrainer) ; profondeur 1 (un tour). Ces deux axes sont la suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dfield

from .model import PokemonState, FieldState
from .moves import get_move, is_known as move_known
from .sim import Mon, Side, simulate_turn_actions
from .search import evaluate_side          # réutilise la même éval d'équipe
from .belief import opponent_belief, opponent_move_support, Particle

# Jets de dégâts représentatifs (énumération de la chance, poids uniforme).
ROLLS = (0.15, 0.5, 0.85)


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

def _payoff_matrix(me: Mon, my_bench: list[Mon], particles: list[Particle],
                   my_actions: list[tuple], opp_moves: list[str | None],
                   field: FieldState | None
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
                    vals.append(evaluate_side(res.me, res.opp.active))
                num += part.weight * (sum(vals) / len(vals))
                den += part.weight
            row.append(num / den if den > 0 else 0.0)
        matrix.append(row)
    return matrix


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
               seed: int | None = 0) -> NashResult:
    """Résout le tour courant vers Nash et renvoie ma stratégie mixte.

    Mes actions = mes coups (connus) + un changement par membre vivant du banc.
    L'adversaire = coups plausibles sur la croyance (usage §10.3, filtrée par
    l'observé). La chance (jets de dégâts) est énumérée sur `ROLLS`.
    """
    bench = my_bench or []
    particles = opponent_belief(opp.build, reg_id, n_samples=belief_samples,
                                seed=seed)
    opp_moves: list[str | None] = list(opponent_move_support(particles)) or [None]

    my_actions: list[tuple] = [("move", m) for m in me.build.moves if move_known(m)]
    my_actions += [("switch", i) for i, b in enumerate(bench) if not b.fainted]
    if not my_actions:
        my_actions = [("move", None)]
    labels = [_label(a, me, bench) for a in my_actions]

    U = _payoff_matrix(me, bench, particles, my_actions, opp_moves, field)
    rst, cst, val = solve_matrix(U, iters=iters)

    strat = sorted(zip(labels, rst), key=lambda t: t[1], reverse=True)
    opp_strat = sorted(zip(opp_moves, cst), key=lambda t: t[1], reverse=True)

    # Meilleure réponse PURE à la stratégie adverse moyenne (info « coup sûr »).
    br_idx = max(range(len(my_actions)),
                 key=lambda i: sum(cst[j] * U[i][j] for j in range(len(opp_moves))))
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
    return NashResult(strategy=strat, value=val, opp_actions=opp_moves,
                      opp_strategy=opp_strat, best_response=best_response,
                      recommendation=reco, notes=notes)


def _phrase_label(label: str) -> str:
    return f"Changer pour {label[2:]}" if label.startswith("→ ") else f"Joue {label}"
