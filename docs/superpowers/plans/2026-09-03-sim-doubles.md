# Simulateur de tour Doubles (PR A) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Doter SimuPoke d'un simulateur de tour Doubles 2v2 qui résout l'ordre
d'action des quatre combattants, le ciblage, les coups de zone et les cinq
mécaniques d'appui décisives (Protect, redirection, Wide Guard, Ally Switch,
Helping Hand), en réutilisant le moteur de dégâts figé.

**Architecture:** Un module neuf `src/simupoke/sim_doubles.py` réutilise `Mon`,
`_apply_move`, `_end_of_turn`, `_apply_hazards` et `_tick_conditions` de `sim.py`
par duck typing — son `DoublesSide` expose `.screens`, `.tailwind` et `.hazards`
comme le `Side` Singles. Deux paramètres optionnels neutres sont ajoutés au calc
(`power_mod`) et à `_apply_move` (`apply_spread`, `power_mod`) pour faire passer
les coups de zone et Helping Hand sans dupliquer la résolution.

**Tech Stack:** Python 3.13 (stdlib uniquement), pytest, ruff ; Node 24 pour les
scripts de parité (`@smogon/calc`).

## Global Constraints

- **Hors-ligne (invariant #1)** : aucun appel réseau dans le runtime. Les scripts
  `scripts/gen_*.mjs` et `calc_reference.mjs` sont hors-ligne, exécutés à la main.
- **Source de vérité Python (#2)** : toute règle vit dans `src/simupoke/` et est
  testée. Ne jamais recopier une règle déjà implémentée — l'appeler.
- **Parité JS (#3)** : toute modification de `damage.py` doit être répercutée dans
  `web/engine.js`. Les trois scripts doivent rester verts :
  `node web/verify_engine.mjs`, `node web/verify_bench.mjs`, `node web/verify_team.mjs`.
- **Données (#4, #5)** : ciblage, priorités et drapeaux de zone se lisent dans
  `data/moves.json` via `moves.get_move` — aucune table de moves en dur. Ne jamais
  éditer à la main `data/pokedex.json`, `data/moves.json`, `data/typechart.json`.
- **Conventions** : IDs internes en anglais style Showdown, commentaires et
  messages de log en français, lignes ≤ 100 caractères (ruff).
- **Commandes de vérification** (depuis la racine du dépôt, venv déjà installé) :
  - `./.venv/Scripts/python.exe -m pytest -q`
  - `./.venv/Scripts/python.exe -m ruff check .`
- **Branche** : `feat/doubles-sim`. Un commit par tâche, CI verte à chaque commit.
- **Référence** : la spec validée est
  `docs/superpowers/specs/2026-09-03-doubles-nash-design.md`.

## Structure des fichiers

| Fichier | Responsabilité | Tâches |
|---|---|---|
| `src/simupoke/damage.py` | Calc figé — reçoit `power_mod` (modificateur de puissance de base) | 1 |
| `web/engine.js` | Port JS du calc — reçoit `powerMod`, parité obligatoire | 1 |
| `scripts/calc_reference.mjs` | Vecteurs de référence `@smogon/calc` — 34ᵉ vecteur Helping Hand | 1 |
| `tests/test_damage.py` | Parité Python du calc | 1 |
| `web/verify_engine.mjs` | Parité JS du calc | 1 |
| `src/simupoke/sim.py` | Simulateur Singles — `_apply_move` relaie deux paramètres neutres | 2 |
| `src/simupoke/sim_doubles.py` | **Neuf** — état 2v2, ordre à 4 acteurs, ciblage, résolution du tour | 3–9 |
| `tests/test_sim_doubles.py` | **Neuf** — tests du simulateur Doubles | 3–9 |
| `src/simupoke/cli.py` | Sous-commande `simd` | 10 |
| `README.md`, `CLAUDE.md` | Documentation de la commande et de l'état de la Phase 5 | 10 |

---

### Task 1 : `power_mod` dans le calc, des deux côtés

**Files:**
- Modify: `src/simupoke/damage.py:252-355`
- Modify: `web/engine.js:130-206`
- Modify: `scripts/calc_reference.mjs` (fin de fichier)
- Test: `tests/test_damage.py` (liste `CASES`)
- Test: `web/verify_engine.mjs` (liste `cases`)

**Interfaces:**
- Consomme : rien (première tâche).
- Produit : `damage.calculate(..., power_mod: float = 1.0)` — multiplicateur
  appliqué à la **puissance de base**, converti en modificateur 4096ᵉ. Côté JS,
  `opts.powerMod` dans `makeEngine(...).calculate(attacker, defender, moveId, field, opts)`.

- [ ] **Step 1 : Écrire le vecteur de parité qui échoue**

Dans `tests/test_damage.py`, ajouter à la fin de la liste `CASES` :

```python
    # Helping Hand : ×1.5 sur la puissance de base (référence @smogon/calc,
    # field.attackerSide.isHelpingHand).
    ("eq_helpinghand",     CHOMP_AD(), TTAR(), "earthquake",
     {"power_mod": 1.5}, 260, 308),
```

- [ ] **Step 2 : Lancer le test et vérifier qu'il échoue**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_damage.py -q -k helpinghand`
Attendu : ÉCHEC — `TypeError: calculate() got an unexpected keyword argument 'power_mod'`.

- [ ] **Step 3 : Ajouter le paramètre au calc Python**

Dans `src/simupoke/damage.py`, signature de `calculate` (ligne ~252) :

```python
def calculate(attacker: PokemonState, defender: PokemonState,
              move: str | Move, field: FieldState | None = None, *,
              crit: bool = False, apply_spread: bool = False,
              screen: str | None = None, power_mod: float = 1.0) -> DamageResult:
```

Compléter la docstring, juste après la ligne décrivant `screen` :

```python
    `power_mod` : multiplicateur externe de **puissance de base** (Helping Hand
    ×1.5 en Doubles). Neutre à 1.0 ; converti en modificateur 4096ᵉ et chaîné
    avec les autres modificateurs de puissance.
```

Puis, dans la section « Puissance de base (modificateurs) » (ligne ~338), ajouter
**avant** le `if bp_mods:` final :

```python
    if power_mod != 1.0:
        bp_mods.append(round(power_mod * 4096))
```

- [ ] **Step 4 : Lancer le test et vérifier qu'il passe**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_damage.py -q`
Attendu : tous verts, y compris `eq_helpinghand`.

- [ ] **Step 5 : Répercuter dans le port JS**

Dans `web/engine.js`, à la ligne ~132 où les options sont lues :

```js
      const crit = !!opts.crit, applySpread = !!opts.applySpread;
      const powerMod = opts.powerMod === undefined ? 1 : opts.powerMod;
```

Puis, juste avant `if (bpMods.length)` (ligne ~206) :

```js
      if (powerMod !== 1) bpMods.push(Math.round(powerMod * 4096));
```

Et ajouter le vecteur correspondant à la liste `cases` de `web/verify_engine.mjs`,
à la suite des autres :

```js
  ['eq_helpinghand', mk('garchomp', 'adamant', { atk: 31 }), mk('tyranitar', 'jolly'), 'earthquake', { powerMod: 1.5 }, 260, 308],
```

- [ ] **Step 6 : Vérifier la parité JS**

Run : `node web/verify_engine.mjs`
Attendu : `Parité JS : 34/34 OK`.

- [ ] **Step 7 : Inscrire le vecteur dans le générateur de référence**

Dans `scripts/calc_reference.mjs`, à la suite du scénario 18 :

```js
// 19. Helping Hand (Doubles) : ×1.5 sur la puissance de base
add('eq_helpinghand', { species: 'Garchomp', nature: 'Adamant', evs: { atk: 248 } },
  { species: 'Tyranitar', nature: 'Jolly', evs: {} }, { name: 'Earthquake' },
  { attackerSide: { isHelpingHand: true } });
```

Vérifier que le générateur reproduit bien 260/308 :

```bash
cd scripts && node calc_reference.mjs | grep -A2 eq_helpinghand
```

Attendu : `"min": 260` et `"max": 308`.

- [ ] **Step 8 : Lint et suite complète**

Run : `./.venv/Scripts/python.exe -m ruff check .` puis
`./.venv/Scripts/python.exe -m pytest -q`
Attendu : `All checks passed!` et 312 tests verts (311 + le nouveau vecteur).

- [ ] **Step 9 : Commit**

```bash
git add src/simupoke/damage.py web/engine.js web/verify_engine.mjs scripts/calc_reference.mjs tests/test_damage.py
git commit -m "feat(calc): power_mod — modificateur externe de puissance de base

Prépare Helping Hand (Doubles). Neutre par défaut, vérifié contre
@smogon/calc (34e vecteur), répercuté dans le port JS.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2 : `_apply_move` relaie `apply_spread` et `power_mod`

**Files:**
- Modify: `src/simupoke/sim.py:199-203` (signature) et `:277` (appel à `calculate`)
- Test: `tests/test_sim.py`

**Interfaces:**
- Consomme : `damage.calculate(..., power_mod=…)` (Task 1).
- Produit : `sim._apply_move(attacker, defender, move, field, roll, log, *,
  atk_side=None, def_side=None, field_dur=None, apply_spread=False,
  power_mod=1.0)`. Les deux nouveaux paramètres sont **relayés tels quels** au
  calc ; aucun appelant existant ne les passe.

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à `tests/test_sim.py` :

```python
# --- Relais des paramètres de calc (substrat Doubles) -----------------------

def test_apply_move_relays_spread_and_power_mod():
    from simupoke.sim import _apply_move

    def hit(**kw):
        atk = mon("garchomp", "adamant", {"atk": 31}, moves=["earthquake"])
        dfn = mon("tyranitar", "jolly")
        before = dfn.hp
        _apply_move(atk, dfn, "earthquake", None, 0.5, [], **kw)
        return before - dfn.hp

    plein = hit()
    zone = hit(apply_spread=True)
    boost = hit(power_mod=1.5)
    assert zone < plein, "la pénalité de zone doit réduire les dégâts"
    assert boost > plein, "power_mod doit augmenter les dégâts"
```

- [ ] **Step 2 : Lancer le test et vérifier qu'il échoue**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim.py -q -k relays`
Attendu : ÉCHEC — `TypeError: _apply_move() got an unexpected keyword argument 'apply_spread'`.

- [ ] **Step 3 : Ajouter les paramètres et les relayer**

Dans `src/simupoke/sim.py`, signature de `_apply_move` :

```python
def _apply_move(attacker: Mon, defender: Mon, move: str,
                field: FieldState | None, roll: float, log: list[str], *,
                atk_side: Side | None = None, def_side: Side | None = None,
                field_dur: dict | None = None,
                apply_spread: bool = False, power_mod: float = 1.0) -> None:
```

Compléter la docstring :

```python
    `apply_spread`/`power_mod` (chemin Doubles) sont relayés au calc : pénalité
    de zone ×0.75 et modificateur de puissance externe (Helping Hand).
```

Puis l'appel au calc (ligne ~277) :

```python
        r = calculate(attacker.snapshot(), defender.snapshot(), m, field,
                      screen=scr, apply_spread=apply_spread, power_mod=power_mod)
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim.py -q`
Attendu : tous verts. Puis la suite complète : `./.venv/Scripts/python.exe -m pytest -q`
Attendu : 313 tests verts, **aucune régression** (les appelants existants ne
passent pas les nouveaux paramètres).

- [ ] **Step 5 : Commit**

```bash
git add src/simupoke/sim.py tests/test_sim.py
git commit -m "feat(sim): _apply_move relaie apply_spread et power_mod au calc

Substrat du simulateur Doubles : les coups de zone et Helping Hand
transitent par la résolution existante, sans la dupliquer.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3 : état 2v2 et ordre d'action à quatre acteurs

**Files:**
- Create: `src/simupoke/sim_doubles.py`
- Test: `tests/test_sim_doubles.py`

**Interfaces:**
- Consomme : `sim.Mon`, `combat.effective_speed`, `moves.get_move`.
- Produit :
  - `Target = tuple[str, int]` — `("foe", 0|1)`, `("ally", 0)`, `("self", 0)`.
  - `SlotAction` — `("move", move_id, Target | None)` | `("switch", index, None)` | `("pass", None, None)`.
  - `SideActions = tuple[SlotAction, SlotAction]`.
  - `Actor = tuple[str, int]` — `("me", 0)`, `("opp", 1)`…
  - `DoublesSide(active, bench=[], screens={}, tailwind=0, hazards={}, wide_guard=False)`.
  - `action_order_doubles(me, opp, my_actions, opp_actions, field) -> list[Actor]`.

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_sim_doubles.py` :

```python
"""Tests du simulateur de tour Doubles (sim_doubles.py)."""

from __future__ import annotations

from simupoke.model import FieldState, PokemonState
from simupoke.sim import Mon
from simupoke.sim_doubles import DoublesSide, action_order_doubles


def st(species, nature="serious", sp=None, item=None, ability=None,
       moves=None, hp=1.0, status=None):
    return PokemonState(species=species, nature=nature, stat_points=sp or {},
                        item=item, ability=ability, moves=moves or [],
                        current_hp_pct=hp, status=status)


def mon(*a, **k):
    return Mon.from_state(st(*a, **k))


def side(*mons, **kw):
    return DoublesSide(active=list(mons), **kw)


def mv(move_id, target=None):
    return ("move", move_id, target)


PASS = ("pass", None, None)


# --- Ordre d'action ---------------------------------------------------------

def test_order_sorts_four_actors_by_speed():
    me = side(mon("garchomp", "jolly", {"spe": 32}), mon("snorlax", "brave"))
    opp = side(mon("dragapult", "timid", {"spe": 32}), mon("torkoal", "quiet"))
    order = action_order_doubles(me, opp, (mv("earthquake"), mv("bodyslam")),
                                 (mv("dragondarts"), mv("eruption")), None)
    assert order[0] == ("opp", 0)          # Dragapult, le plus rapide
    assert order[-1] in (("me", 1), ("opp", 1))   # les deux lents ferment


def test_order_priority_beats_speed():
    me = side(mon("snorlax", "brave"), mon("snorlax", "brave"))
    opp = side(mon("dragapult", "timid", {"spe": 32}), mon("torkoal", "quiet"))
    order = action_order_doubles(me, opp, (mv("protect"), PASS),
                                 (mv("dragondarts"), PASS), None)
    assert order[0] == ("me", 0)           # Protect, priorité +4


def test_order_trick_room_reverses():
    me = side(mon("snorlax", "brave"), mon("snorlax", "brave"))
    opp = side(mon("dragapult", "timid", {"spe": 32}), mon("torkoal", "quiet"))
    field = FieldState(trick_room=True)
    order = action_order_doubles(me, opp, (mv("bodyslam"), PASS),
                                 (mv("dragondarts"), PASS), field)
    assert order[0] == ("me", 0)           # le plus lent agit en premier


def test_order_tailwind_doubles_speed():
    me = side(mon("snorlax", "brave"), mon("snorlax", "brave"), tailwind=3)
    opp = side(mon("snorlax", "brave"), mon("snorlax", "brave"))
    order = action_order_doubles(me, opp, (mv("bodyslam"), PASS),
                                 (mv("bodyslam"), PASS), None)
    assert order[0] == ("me", 0)


def test_order_is_stable_on_speed_tie():
    me = side(mon("snorlax", "brave"), mon("snorlax", "brave"))
    opp = side(mon("snorlax", "brave"), mon("snorlax", "brave"))
    order = action_order_doubles(me, opp, (mv("bodyslam"), mv("bodyslam")),
                                 (mv("bodyslam"), mv("bodyslam")), None)
    assert order == [("me", 0), ("me", 1), ("opp", 0), ("opp", 1)]
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q`
Attendu : ÉCHEC — `ModuleNotFoundError: No module named 'simupoke.sim_doubles'`.

- [ ] **Step 3 : Créer le module avec l'état et l'ordre d'action**

Créer `src/simupoke/sim_doubles.py` :

```python
"""Simulateur de tour **Doubles** (Phase 5) — résolution 2v2.

Porte en 2v2 la résolution de tour de `sim.py` : ordre d'action sur **quatre**
acteurs, ciblage, coups de zone et mécaniques d'appui (Protect, redirection,
Wide Guard, Ally Switch, Helping Hand).

Aucune règle n'est réécrite : les dégâts, les objets, les talents et la fin de
tour passent par `sim._apply_move` et `sim._end_of_turn` — une seule source de
vérité. Le ciblage et les priorités sont **lus dans les données**
(`Move.target`, `Move.priority`), jamais codés en dur.

Périmètre v1 (assumé) : pas de remplacement d'un K.O. en cours de tour (le slot
reste vide jusqu'au tour suivant), pas de Quash / Après Vous.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .combat import effective_speed
from .model import FieldState
from .moves import get_move
from .moves import is_known as move_known
from .sim import Mon

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
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q`
Attendu : 5 tests verts.

- [ ] **Step 5 : Commit**

```bash
git add src/simupoke/sim_doubles.py tests/test_sim_doubles.py
git commit -m "feat(doubles): état 2v2 et ordre d'action à quatre acteurs

DoublesSide expose screens/tailwind/hazards comme le Side Singles : _apply_move
s'y branche sans conteneur commun. Priorités lues dans la donnée.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4 : résolution du tour — ciblage mono-cible, changements, fin de tour

**Files:**
- Modify: `src/simupoke/sim_doubles.py`
- Test: `tests/test_sim_doubles.py`

**Interfaces:**
- Consomme : `action_order_doubles` (Task 3), `sim._apply_move` (Task 2),
  `sim._end_of_turn`, `sim._apply_hazards`, `sim._tick_conditions`.
- Produit :
  - `DoublesResult(me: DoublesSide, opp: DoublesSide, log: list[str])`.
  - `simulate_turn_doubles(me, opp, my_actions, opp_actions, field=None, *,
    roll=0.5, copy=True) -> DoublesResult`.
  - `resolve_targets(actor, action, me, opp, field) -> list[Mon]` — liste des
    Pokémon effectivement touchés, dans l'ordre des slots.

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `tests/test_sim_doubles.py` :

```python
from simupoke.sim_doubles import simulate_turn_doubles


# --- Résolution du tour -----------------------------------------------------

def test_single_target_hits_the_named_slot():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["earthquake"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (mv("rockslide", ("foe", 1)), PASS),
                                (PASS, PASS), None)
    assert res.opp.active[1].hp < res.opp.active[1].max_hp   # le slot 1 encaisse
    assert res.opp.active[0].hp == res.opp.active[0].max_hp  # le slot 0 est intact


def test_default_target_is_first_living_foe():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["rockslide"]),
              mon("snorlax", "brave"))
    opp = side(mon("torkoal", "quiet"), mon("tyranitar", "jolly"))
    res = simulate_turn_doubles(me, opp, (mv("dragonclaw"), PASS),
                                (PASS, PASS), None)
    assert res.opp.active[0].hp < res.opp.active[0].max_hp


def test_fainted_target_wastes_the_move():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"]),
              mon("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"]))
    opp = side(mon("torkoal", "quiet", hp=0.02), mon("tyranitar", "jolly"))
    # Les deux visent le slot 0 ; le premier le met K.O., le second perd son coup.
    res = simulate_turn_doubles(
        me, opp, (mv("dragonclaw", ("foe", 0)), mv("dragonclaw", ("foe", 0))),
        (PASS, PASS), None)
    assert res.opp.active[0].fainted
    assert res.opp.active[1].hp == res.opp.active[1].max_hp
    assert any("coup perdu" in line for line in res.log)


def test_switch_resolves_before_moves():
    me = side(mon("garchomp", "jolly", {"spe": 32}, moves=["dragonclaw"]),
              mon("snorlax", "brave"),
              bench=[mon("tyranitar", "jolly", moves=["crunch"])])
    opp = side(mon("torkoal", "quiet", moves=["eruption"]), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (("switch", 0, None), PASS),
                                (PASS, PASS), None)
    assert res.me.active[0].build.species == "tyranitar"


def test_end_of_turn_applies_to_all_four():
    me = side(mon("garchomp", "jolly", item="leftovers", hp=0.5),
              mon("snorlax", "brave", item="leftovers", hp=0.5))
    opp = side(mon("tyranitar", "jolly", item="leftovers", hp=0.5),
               mon("torkoal", "quiet", item="leftovers", hp=0.5))
    res = simulate_turn_doubles(me, opp, (PASS, PASS), (PASS, PASS), None)
    for camp in (res.me, res.opp):
        for m in camp.active:
            assert m.hp > m.max_hp // 2      # Vestiges ont soigné les quatre
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q -k "target or switch or end_of_turn"`
Attendu : ÉCHEC — `ImportError: cannot import name 'simulate_turn_doubles'`.

- [ ] **Step 3 : Implémenter le ciblage et la résolution**

Ajouter à `src/simupoke/sim_doubles.py` (imports à compléter en tête de fichier :
`from .sim import Mon, _apply_hazards, _apply_move, _end_of_turn, _tick_conditions`) :

```python
# Cibles « toutes les cibles adjacentes » : la donnée distingue les alliés.
_FOE_SPREAD = "allAdjacentFoes"
_ALL_SPREAD = "allAdjacent"


def _living(mons: list[Mon]) -> list[Mon]:
    return [m for m in mons if not m.fainted]


def resolve_targets(actor: Actor, action: SlotAction, me: DoublesSide,
                    opp: DoublesSide) -> list[Mon]:
    """Pokémon effectivement touchés par `action`, d'après `Move.target`.

    Le ciblage vient de la **donnée** : `allAdjacentFoes` frappe les deux
    adversaires, `allAdjacent` y ajoute l'allié (Séisme, Surf), `self` et
    `allySide` restent sur le lanceur, `adjacentAlly` vise l'allié.
    """
    mid = _move_of(action)
    if not mid or not move_known(mid):
        return []
    key, slot = actor
    own, foes = (me, opp) if key == "me" else (opp, me)
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


@dataclass
class DoublesResult:
    me: DoublesSide
    opp: DoublesSide
    log: list[str]


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
        if attacker.fainted or _move_of(action) is None:
            continue
        targets = resolve_targets(actor, action, own, foes)
        if not targets:
            log.append(f"{attacker.build.species} : cible K.O. — coup perdu")
            continue
        for target in targets:
            _apply_move(attacker, target, _move_of(action), field, roll, log,
                        atk_side=own, def_side=foes, field_dur=field_dur)

    # 3) Fin de tour sur les quatre, puis conditions de camp.
    for camp in (me, opp):
        for m in camp.active:
            _end_of_turn(m, field, log)
    _tick_conditions(me, opp, pre, log)
    return DoublesResult(me=me, opp=opp, log=log)


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
```

> Note pour l'implémenteur : `_apply_move` sur un coup de statut visant
> `own.active[slot]` (cas `self`) reçoit le lanceur en `defender` — c'est le
> comportement voulu pour Protect et le setup, identique au chemin Singles.

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q`
Attendu : 10 tests verts.

- [ ] **Step 5 : Commit**

```bash
git add src/simupoke/sim_doubles.py tests/test_sim_doubles.py
git commit -m "feat(doubles): résolution du tour 2v2 — ciblage, changements, fin de tour

Ciblage piloté par Move.target ; cible K.O. = coup perdu ; fin de tour
appliquée aux quatre combattants.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5 : coups de zone — friendly fire et pénalité conditionnelle

**Files:**
- Modify: `src/simupoke/sim_doubles.py` (boucle de résolution)
- Test: `tests/test_sim_doubles.py`

**Interfaces:**
- Consomme : `resolve_targets` (Task 4), `_apply_move(apply_spread=…)` (Task 2).
- Produit : la pénalité de zone est appliquée **si et seulement si** au moins
  deux cibles sont effectivement touchées.

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# --- Coups de zone ----------------------------------------------------------

def test_spread_penalty_only_with_two_targets():
    def damage_to_slot0(second_foe_hp):
        me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["rockslide"]),
                  mon("snorlax", "brave"))
        opp = side(mon("tyranitar", "jolly"),
                   mon("torkoal", "quiet", hp=second_foe_hp))
        if second_foe_hp == 0.0:
            opp.active[1].hp = 0
        res = simulate_turn_doubles(me, opp, (mv("rockslide"), PASS),
                                    (PASS, PASS), None)
        return res.opp.active[0].max_hp - res.opp.active[0].hp

    deux_cibles = damage_to_slot0(1.0)
    une_cible = damage_to_slot0(0.0)
    assert une_cible > deux_cibles, "pas de pénalité ×0.75 sur une cible unique"


def test_all_adjacent_move_hits_the_ally():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["earthquake"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (mv("earthquake"), PASS),
                                (PASS, PASS), None)
    assert res.me.active[1].hp < res.me.active[1].max_hp, "Séisme touche l'allié"


def test_foe_spread_move_spares_the_ally():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["rockslide"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (mv("rockslide"), PASS),
                                (PASS, PASS), None)
    assert res.me.active[1].hp == res.me.active[1].max_hp
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q -k "spread or adjacent"`
Attendu : ÉCHEC sur `test_spread_penalty_only_with_two_targets` (dégâts identiques :
la pénalité n'est jamais appliquée) et sur `test_all_adjacent_move_hits_the_ally`
si le friendly fire n'est pas déjà couvert par `resolve_targets`.

- [ ] **Step 3 : Appliquer la pénalité de zone**

Dans `simulate_turn_doubles`, remplacer la boucle d'application par :

```python
        spread = len(targets) >= 2
        for target in targets:
            _apply_move(attacker, target, _move_of(action), field, roll, log,
                        atk_side=own, def_side=foes, field_dur=field_dur,
                        apply_spread=spread)
```

> `def_side=foes` reste correct pour un allié touché par Séisme : seuls les
> écrans du camp défenseur sont lus, et un allié n'en bénéficie pas côté
> adverse. Ce raccourci est documenté dans la docstring du module.

Compléter la docstring du module (section périmètre) :

```python
    Les écrans consultés lors d'un coup de zone sont ceux du camp adverse, y
    compris pour l'allié touché par un `allAdjacent` : le cas est rare et
    l'écart est borné à un facteur d'écran sur le friendly fire.
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q`
Attendu : 13 tests verts.

- [ ] **Step 5 : Commit**

```bash
git add src/simupoke/sim_doubles.py tests/test_sim_doubles.py
git commit -m "feat(doubles): coups de zone — friendly fire et pénalité conditionnelle

La pénalité ×0.75 ne s'applique qu'à partir de deux cibles touchées ;
allAdjacent (Séisme, Surf) frappe aussi l'allié.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6 : Protect et Wide Guard

**Files:**
- Modify: `src/simupoke/sim_doubles.py`
- Test: `tests/test_sim_doubles.py`

**Interfaces:**
- Consomme : `Mon.protected` (déjà posé par `sim._apply_move` sur les
  `_PROTECT_MOVES`), `DoublesSide.wide_guard` (Task 3).
- Produit : un coup de zone visant un camp dont `wide_guard` est vrai est annulé
  avant application ; le drapeau est posé quand le coup `wideguard` est joué.

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# --- Protect / Wide Guard ---------------------------------------------------

def test_protect_blocks_a_single_target_move():
    me = side(mon("garchomp", "jolly", {"spe": 32}, moves=["dragonclaw"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly", moves=["protect"]), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (mv("dragonclaw", ("foe", 0)), PASS),
                                (mv("protect"), PASS), None)
    assert res.opp.active[0].hp == res.opp.active[0].max_hp


def test_wide_guard_blocks_spread_but_not_single_target():
    def run(attack):
        me = side(mon("garchomp", "adamant", {"atk": 31}, moves=[attack]),
                  mon("snorlax", "brave"))
        opp = side(mon("tyranitar", "jolly", moves=["wideguard"]),
                   mon("torkoal", "quiet"))
        return simulate_turn_doubles(me, opp, (mv(attack), PASS),
                                     (mv("wideguard"), PASS), None)

    zone = run("rockslide")
    assert zone.opp.active[1].hp == zone.opp.active[1].max_hp, "zone bloquée"
    mono = run("dragonclaw")
    assert mono.opp.active[0].hp < mono.opp.active[0].max_hp, "mono-cible passe"


def test_wide_guard_expires_at_end_of_turn():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["rockslide"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly", moves=["wideguard"]), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (PASS, PASS), (mv("wideguard"), PASS), None)
    assert res.opp.wide_guard is False
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q -k "protect or wide_guard"`
Attendu : `test_protect_blocks_a_single_target_move` passe déjà (Protect est hérité
de `_apply_move`) ; les deux tests Wide Guard ÉCHOUENT.

- [ ] **Step 3 : Implémenter Wide Guard**

Ajouter la constante en tête de module :

```python
_WIDE_GUARD = "wideguard"
```

Dans `simulate_turn_doubles`, à l'intérieur de la boucle d'acteurs, **avant** de
résoudre les cibles :

```python
        mid = _move_of(action)
        if mid == _WIDE_GUARD:
            own.wide_guard = True
            log.append(f"{attacker.build.species} pose Wide Guard")
            continue
```

Puis, après le calcul de `targets` et de `spread` :

```python
        if spread and foes.wide_guard:
            log.append(f"  Wide Guard protège le camp — {get_move(mid).name} bloqué")
            continue
```

`wide_guard` est déjà remis à `False` en début de tour (Task 4), donc il expire
naturellement — le troisième test le vérifie.

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q`
Attendu : 16 tests verts.

- [ ] **Step 5 : Commit**

```bash
git add src/simupoke/sim_doubles.py tests/test_sim_doubles.py
git commit -m "feat(doubles): Wide Guard bloque les coups de zone

Protect est hérité de la résolution Singles ; Wide Guard est un drapeau de
camp, posé par le coup et expirant en fin de tour.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7 : redirection — Follow Me, Rage Powder, Paratonnerre, Lisse-Flot

**Files:**
- Modify: `src/simupoke/sim_doubles.py`
- Test: `tests/test_sim_doubles.py`

**Interfaces:**
- Consomme : `resolve_targets` (Task 4).
- Produit : `redirect_target(attacker, targets, action, foes, redirectors) -> list[Mon]`,
  appliquée aux seuls coups **mono-cible visant le camp adverse**.
  `redirectors: set[int]` = slots adverses ayant déjà joué Follow Me / Rage Powder
  ce tour.

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# --- Redirection ------------------------------------------------------------

def test_follow_me_redirects_a_single_target_move():
    me = side(mon("garchomp", "jolly", {"spe": 32}, moves=["dragonclaw"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"),
               mon("clefairy", "bold", moves=["followme"]))
    res = simulate_turn_doubles(me, opp, (mv("dragonclaw", ("foe", 0)), PASS),
                                (PASS, mv("followme")), None)
    assert res.opp.active[1].hp < res.opp.active[1].max_hp, "le redirecteur encaisse"
    assert res.opp.active[0].hp == res.opp.active[0].max_hp


def test_follow_me_does_not_redirect_a_spread_move():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["rockslide"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"),
               mon("clefairy", "bold", moves=["followme"]))
    res = simulate_turn_doubles(me, opp, (mv("rockslide"), PASS),
                                (PASS, mv("followme")), None)
    assert res.opp.active[0].hp < res.opp.active[0].max_hp, "les deux sont touchés"


def test_rage_powder_has_no_effect_on_grass_type():
    me = side(mon("venusaur", "modest", {"spa": 31}, moves=["sludgebomb"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"),
               mon("amoonguss", "bold", moves=["ragepowder"]))
    res = simulate_turn_doubles(me, opp, (mv("sludgebomb", ("foe", 0)), PASS),
                                (PASS, mv("ragepowder")), None)
    assert res.opp.active[0].hp < res.opp.active[0].max_hp, "le Plante ignore la poudre"


def test_lightning_rod_redirects_and_boosts():
    me = side(mon("raichu", "modest", {"spa": 31}, moves=["thunderbolt"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly"),
               mon("rotomwash", "bold", ability="lightningrod"))
    res = simulate_turn_doubles(me, opp, (mv("thunderbolt", ("foe", 0)), PASS),
                                (PASS, PASS), None)
    assert res.opp.active[0].hp == res.opp.active[0].max_hp
    assert res.opp.active[1].hp == res.opp.active[1].max_hp, "immunisé"
    assert res.opp.active[1].boosts.get("spa") == 1
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q -k "follow_me or rage_powder or lightning"`
Attendu : ÉCHEC des quatre — la redirection n'existe pas encore
(`test_follow_me_does_not_redirect_a_spread_move` et
`test_rage_powder_has_no_effect_on_grass_type` peuvent passer par accident : ils
gardent leur valeur de non-régression une fois la redirection en place).

- [ ] **Step 3 : Implémenter la redirection**

Ajouter en tête de module :

```python
from .basestats import get_species, to_id

_REDIRECT_MOVES = {"followme", "ragepowder"}
# Talent -> type de coup redirigé (immunité + boost d'Attaque Spéciale).
_REDIRECT_ABILITIES = {"lightningrod": "Electric", "stormdrain": "Water"}
_SINGLE_TARGETS = ("normal", "adjacentFoe", "any")


def _powder_immune(mon: Mon) -> bool:
    """Insensible aux poudres : type Plante, Masque de Sécurité, Peau Duvetée."""
    types = get_species(mon.build.species).get("types") or []
    return ("Grass" in types
            or to_id(mon.item or "") == "safetygoggles"
            or to_id(mon.build.ability or "") == "overcoat")


def redirect_target(attacker: Mon, targets: list[Mon], action: SlotAction,
                    foes: DoublesSide, redirectors: dict[int, str],
                    log: list[str]) -> list[Mon]:
    """Détourne un coup **mono-cible** visant le camp adverse, si un redirecteur
    est actif.

    `redirectors` associe un slot adverse au coup de redirection qu'il a joué
    plus tôt dans le tour (`{1: "followme"}`). Un redirecteur *par action*
    l'emporte sur un talent de redirection.
    """
    mid = _move_of(action)
    mv = get_move(mid)
    if mv.target not in _SINGLE_TARGETS or mv.is_status or len(targets) != 1:
        return targets
    if targets[0] not in foes.active:          # coup sur soi ou sur l'allié
        return targets
    # 1) Redirecteur actif (Follow Me / Rage Powder).
    for slot, red_move in sorted(redirectors.items()):
        cand = foes.active[slot]
        if cand.fainted or cand is targets[0]:
            continue
        if red_move == "ragepowder" and _powder_immune(attacker):
            continue                             # l'attaquant ignore la poudre
        log.append(f"  coup détourné vers {cand.build.species}")
        return [cand]
    # 2) Talent de redirection (Paratonnerre / Lisse-Flot) : immunité + boost.
    for cand in foes.active:
        if cand.fainted or cand is targets[0]:
            continue
        ab = to_id(cand.build.ability or "")
        if _REDIRECT_ABILITIES.get(ab) == mv.type:
            cand.boosts["spa"] = min(6, cand.boosts.get("spa", 0) + 1)
            log.append(f"  {cand.build.species} absorbe le coup "
                       f"({ab}) et gagne +1 A.Spé")
            return []                            # immunisé : aucun dégât
    return targets
```

Dans `simulate_turn_doubles`, tenir le registre et l'appliquer :

```python
    redirectors: dict[str, dict[int, str]] = {"me": {}, "opp": {}}
```

puis, dans la boucle d'acteurs, avant la résolution des cibles :

```python
        if mid in _REDIRECT_MOVES:
            redirectors[key][slot] = mid
            log.append(f"{attacker.build.species} attire les coups ({get_move(mid).name})")
            continue
```

et juste après `targets = resolve_targets(...)` :

```python
        foe_key = "opp" if key == "me" else "me"
        targets = redirect_target(attacker, targets, action, foes,
                                  redirectors[foe_key], log)
        if not targets:
            continue
```

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q`
Attendu : 20 tests verts.

- [ ] **Step 5 : Commit**

```bash
git add src/simupoke/sim_doubles.py tests/test_sim_doubles.py
git commit -m "feat(doubles): redirection — Follow Me, Rage Powder, Paratonnerre

Seuls les coups mono-cible visant le camp adverse sont détournés. Rage Powder
est sans effet sur Plante / Masque de Sécurité / Peau Duvetée ; les talents
de redirection immunisent et donnent +1 A.Spé.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8 : Ally Switch

**Files:**
- Modify: `src/simupoke/sim_doubles.py`
- Test: `tests/test_sim_doubles.py`

**Interfaces:**
- Consomme : la boucle d'acteurs de Task 4.
- Produit : le coup `allyswitch` (priorité +2, lue dans la donnée) échange
  `active[0]` et `active[1]` du camp lanceur. Les cibles déjà déclarées visent
  une **position**, donc l'occupant après échange.

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# --- Ally Switch ------------------------------------------------------------

def test_ally_switch_makes_the_attack_hit_the_other_slot():
    me = side(mon("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"]),
              mon("snorlax", "brave"))
    opp = side(mon("tyranitar", "jolly", moves=["allyswitch"]),
               mon("torkoal", "quiet"))
    res = simulate_turn_doubles(me, opp, (mv("dragonclaw", ("foe", 0)), PASS),
                                (mv("allyswitch"), PASS), None)
    # Après l'échange, le slot 0 est occupé par Torkoal, qui encaisse.
    assert res.opp.active[0].build.species == "torkoal"
    assert res.opp.active[0].hp < res.opp.active[0].max_hp
    assert res.opp.active[1].build.species == "tyranitar"
    assert res.opp.active[1].hp == res.opp.active[1].max_hp
```

- [ ] **Step 2 : Lancer le test et vérifier qu'il échoue**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q -k ally_switch`
Attendu : ÉCHEC — les slots ne sont pas échangés (`res.opp.active[0]` est encore
Tyranitar).

- [ ] **Step 3 : Implémenter l'échange**

Ajouter la constante :

```python
_ALLY_SWITCH = "allyswitch"
```

Dans la boucle d'acteurs, avec les autres coups traités avant résolution :

```python
        if mid == _ALLY_SWITCH:
            if len(own.active) == 2:
                own.active[0], own.active[1] = own.active[1], own.active[0]
                log.append(f"{attacker.build.species} échange sa place avec son allié")
            continue
```

> L'ordre d'action est calculé **avant** l'échange : un acteur déjà trié garde sa
> place dans la file, mais `own.active[slot]` est relu à chaque itération, donc
> le Pokémon qui agit après l'échange est bien celui qui occupe la position.
> C'est le comportement du jeu.

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q`
Attendu : 21 tests verts.

- [ ] **Step 5 : Commit**

```bash
git add src/simupoke/sim_doubles.py tests/test_sim_doubles.py
git commit -m "feat(doubles): Ally Switch — les cibles visent une position

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9 : Helping Hand

**Files:**
- Modify: `src/simupoke/sim_doubles.py`
- Test: `tests/test_sim_doubles.py`

**Interfaces:**
- Consomme : `_apply_move(power_mod=…)` (Task 2).
- Produit : un registre `helping: dict[str, set[int]]` — slots dont le prochain
  coup offensif du tour bénéficie de ×1.5. Consommé au premier coup offensif.

- [ ] **Step 1 : Écrire les tests qui échouent**

```python
# --- Helping Hand -----------------------------------------------------------

def test_helping_hand_boosts_the_ally_damage():
    def run(support):
        me = side(mon("clefairy", "bold", moves=["helpinghand"]),
                  mon("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"]))
        opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
        first = mv("helpinghand", ("ally", 0)) if support else PASS
        res = simulate_turn_doubles(me, opp, (first, mv("dragonclaw", ("foe", 0))),
                                    (PASS, PASS), None)
        return res.opp.active[0].max_hp - res.opp.active[0].hp

    assert run(True) > run(False), "Helping Hand doit augmenter les dégâts"


def test_helping_hand_is_consumed_by_a_single_move():
    me = side(mon("clefairy", "bold", moves=["helpinghand"]),
              mon("garchomp", "adamant", {"atk": 31}, moves=["dragonclaw"]))
    opp = side(mon("tyranitar", "jolly"), mon("torkoal", "quiet"))
    res = simulate_turn_doubles(
        me, opp, (mv("helpinghand", ("ally", 0)), mv("dragonclaw", ("foe", 0))),
        (PASS, PASS), None)
    assert res.me.active[1] is not None
    # Le registre est local au tour : rien ne persiste dans l'état renvoyé.
    assert not hasattr(res.me, "helping_hand")
```

- [ ] **Step 2 : Lancer les tests et vérifier qu'ils échouent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q -k helping_hand`
Attendu : ÉCHEC de `test_helping_hand_boosts_the_ally_damage` (dégâts identiques,
Helping Hand tombe dans la branche « effet non modélisé » de `_apply_move`).

- [ ] **Step 3 : Implémenter le registre**

Ajouter la constante :

```python
_HELPING_HAND = "helpinghand"
```

Dans `simulate_turn_doubles`, initialiser le registre à côté de `redirectors` :

```python
    helping: dict[str, set[int]] = {"me": set(), "opp": set()}
```

Dans la boucle d'acteurs, avant la résolution des cibles :

```python
        if mid == _HELPING_HAND:
            other = 1 - slot
            if len(own.active) == 2 and not own.active[other].fainted:
                helping[key].add(other)
                log.append(f"{attacker.build.species} soutient son allié "
                           f"({get_move(mid).name})")
            continue
```

Puis, au moment de l'application, consommer le bonus :

```python
        power_mod = 1.5 if slot in helping[key] else 1.0
        if power_mod != 1.0:
            helping[key].discard(slot)
        spread = len(targets) >= 2
        for target in targets:
            _apply_move(attacker, target, mid, field, roll, log,
                        atk_side=own, def_side=foes, field_dur=field_dur,
                        apply_spread=spread, power_mod=power_mod)
```

> Le registre est une variable locale au tour : rien n'est stocké sur
> `DoublesSide`, donc l'état renvoyé reste propre pour le tour suivant.

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_sim_doubles.py -q`
Attendu : 23 tests verts. Puis la suite complète et le lint :
`./.venv/Scripts/python.exe -m pytest -q` et
`./.venv/Scripts/python.exe -m ruff check .`

- [ ] **Step 5 : Commit**

```bash
git add src/simupoke/sim_doubles.py tests/test_sim_doubles.py
git commit -m "feat(doubles): Helping Hand — x1.5 sur le prochain coup de l'allié

Registre local au tour, consommé par le premier coup offensif ; le
multiplicateur passe par power_mod, vérifié en parité contre @smogon/calc.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10 : commande CLI `simd` et documentation

**Files:**
- Modify: `src/simupoke/cli.py` (près de `cmd_doubles`, ligne ~783, et du
  routage, ligne ~909)
- Modify: `README.md` (section Structure / commandes), `CLAUDE.md` (feuille de route)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consomme : `simulate_turn_doubles`, `DoublesSide` (Tasks 3–9).
- Produit : `python -m simupoke.cli simd <board.json> --me "<a>,<b>" --opp "<a>,<b>"`,
  qui imprime le log du tour. Suffixe de ciblage : `move@0`, `move@1`.

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à `tests/test_cli.py`, en suivant le style des tests existants du fichier
(lire d'abord comment ils invoquent la CLI et capturent la sortie) :

```python
def test_simd_prints_a_turn_log(tmp_path, capsys):
    board = tmp_path / "board.json"
    board.write_text(json.dumps({
        "mine": [
            {"species": "garchomp", "nature": "adamant",
             "stat_points": {"atk": 31}, "moves": ["dragonclaw"]},
            {"species": "snorlax", "nature": "brave", "moves": ["bodyslam"]},
        ],
        "opp": [
            {"species": "tyranitar", "nature": "jolly", "moves": ["crunch"]},
            {"species": "torkoal", "nature": "quiet", "moves": ["eruption"]},
        ],
    }), encoding="utf-8")
    rc = main(["simd", str(board), "--me", "dragonclaw@0,bodyslam",
               "--opp", "crunch,eruption"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dragonchomp" not in out          # garde-fou : pas de nom inventé
    assert "utilise" in out                  # le log du tour est imprimé
```

> Adapter l'import de `main` et la façon d'appeler la CLI au style déjà utilisé
> dans `tests/test_cli.py` — ne pas introduire un second style d'invocation.

- [ ] **Step 2 : Lancer le test et vérifier qu'il échoue**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -q -k simd`
Attendu : ÉCHEC — commande inconnue, code de retour non nul.

- [ ] **Step 3 : Implémenter la sous-commande**

Dans `src/simupoke/cli.py`, ajouter après `cmd_doubles` :

```python
def _parse_slot_actions(spec: str) -> tuple:
    """« rockslide@1,protect » -> (("move","rockslide",("foe",1)),
    ("move","protect",None)). Un champ vide donne une action passive."""
    from .sim_doubles import PASS
    out = []
    for raw in (spec or "").split(","):
        raw = raw.strip()
        if not raw:
            out.append(PASS)
            continue
        if "@" in raw:
            mid, _, slot = raw.partition("@")
            out.append(("move", to_id(mid), ("foe", int(slot))))
        else:
            out.append(("move", to_id(raw), None))
    while len(out) < 2:
        out.append(PASS)
    return tuple(out[:2])


def cmd_simd(args: list[str]) -> int:
    """Rejoue un tour Doubles et imprime le log."""
    from .sim import Mon
    from .sim_doubles import DoublesSide, simulate_turn_doubles

    if not args:
        print("Usage : simd <board.json> --me \"<a>,<b>\" --opp \"<a>,<b>\"",
              file=sys.stderr)
        return 2
    path, rest = args[0], args[1:]
    me_spec = _flag_value(rest, "--me") or ""
    opp_spec = _flag_value(rest, "--opp") or ""
    board = json.loads(Path(path).read_text(encoding="utf-8"))
    field = _field_from(board.get("field")) if board.get("field") else None
    me = DoublesSide(active=[Mon.from_state(_state_from(d))
                             for d in board["mine"][:2]])
    opp = DoublesSide(active=[Mon.from_state(_state_from(d))
                              for d in board["opp"][:2]])
    res = simulate_turn_doubles(me, opp, _parse_slot_actions(me_spec),
                                _parse_slot_actions(opp_spec), field)
    for line in res.log:
        print(line)
    return 0
```

> `_flag_value`, `_state_from` et `_field_from` : réutiliser les helpers déjà
> présents dans `cli.py` (les repérer dans `cmd_doubles`, qui construit déjà des
> `PokemonState` et un `FieldState` depuis le même format de board). Ne pas en
> écrire de nouveaux si un équivalent existe — adapter les noms à ceux du fichier.

Puis le routage, à côté de `if cmd == "doubles":` :

```python
    if cmd == "simd":
        return cmd_simd(rest)
```

Et l'ajouter à l'aide en tête de fichier (ligne ~11), dans le même style que les
autres commandes.

- [ ] **Step 4 : Lancer les tests et vérifier qu'ils passent**

Run : `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -q` puis la suite
complète `./.venv/Scripts/python.exe -m pytest -q`
Attendu : 24 tests Doubles + toute la suite verte.

- [ ] **Step 5 : Mettre à jour la documentation**

Dans `README.md`, ajouter `sim_doubles.py` à l'arborescence `src/simupoke/` avec
la légende « simulateur de tour Doubles (2v2) », et `simd` à la liste des
sous-commandes. Passer la ligne Phase 5 du tableau d'état de `⏳` à `🟡` avec la
mention « simulateur 2v2 ✅, Nash joint à venir ».

Dans `CLAUDE.md`, section « Feuille de route », remplacer « Phase 5 Doubles ⏳ »
par « Phase 5 🟡 (simulateur 2v2 fait ; Nash joint à venir) ». Ajouter `simd` à
la liste des sous-commandes de la section « Commandes ».

- [ ] **Step 6 : Vérification finale complète**

```bash
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m pytest -q
node web/verify_engine.mjs
node web/verify_bench.mjs
node web/verify_team.mjs
./.venv/Scripts/python.exe scripts/build_web.py
```

Attendu : lint vert, suite verte, parité `34/34`, `6/6`, `4/4`, page autonome
régénérée sans erreur.

- [ ] **Step 7 : Commit et PR**

```bash
git add src/simupoke/cli.py tests/test_cli.py README.md CLAUDE.md
git commit -m "feat(cli): sous-commande simd — rejeu d'un tour Doubles

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin feat/doubles-sim
gh pr create --title "Phase 5 — simulateur de tour Doubles 2v2" --body-file pr-body.md
```

Rédiger `pr-body.md` (fichier temporaire, à supprimer après création de la PR)
avec quatre sections : **Objet** — le simulateur 2v2 comme substrat du Nash
Doubles ; **Mécanique** — ordre à 4 acteurs, ciblage piloté par `Move.target`,
pénalité de zone conditionnelle, Protect, redirection, Wide Guard, Ally Switch,
Helping Hand ; **Périmètre assumé** — pas de remplacement d'un K.O. en cours de
tour, pas de Quash / Après Vous ; **Gates** — lint, suite pytest, parité
`34/34 · 6/6 · 4/4`. Terminer le corps par :

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## Auto-revue du plan

**Couverture de la spec** — §3.1 réutilisation → Tasks 2–4 ; §3.2 structures →
Task 3 ; §3.3 résolution (ordre, ciblage, zone conditionnelle, fin de tour) →
Tasks 3–5 ; §3.4 Protect / redirection / Wide Guard / Ally Switch / Helping Hand
→ Tasks 6–9, avec le `power_mod` et sa parité en Task 1 ; §3.5 hors périmètre →
documenté dans la docstring du module (Task 3) et le corps de PR (Task 10) ;
§3.6 tests → répartis en Tasks 3–9 ; §3.7 CLI → Task 10. La PR B (`nash_doubles`)
est hors de ce plan, comme prévu.

**Cohérence des types** — `SlotAction` est un triplet partout, y compris pour
`switch` (`("switch", idx, None)`) et `PASS`. `resolve_targets` prend
`(actor, action, own, foes)` et rend `list[Mon]` en Tasks 4, 5, 7.
`redirect_target` prend `redirectors: dict[int, str]` (slot → coup de redirection
joué), et la boucle de Task 7 lui passe `redirectors[foe_key]`, du même type.
`DoublesSide.wide_guard` est le seul drapeau porté par l'état ; les registres
`redirectors` et `helping` sont locaux au tour, donc rien ne fuit vers le tour
suivant.

**Point de vigilance pour l'implémenteur** — Task 4 introduit une seule boucle
d'acteurs, que les Tasks 5 à 9 enrichissent successivement. Les blocs de code
donnés pour ces tâches sont des *ajouts* dans cette boucle, pas des réécritures :
l'ordre final des vérifications y est Wide Guard → Ally Switch → redirection →
Helping Hand → application, chacune posée par sa tâche.
