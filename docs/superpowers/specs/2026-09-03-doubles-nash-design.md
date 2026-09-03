# Phase 5 — Doubles : simulateur de tour 2v2 et Nash joint

*Conception validée le 2026-09-03. Fait suite au cran 5 de
[`docs/recherche_sota_ismcts.md`](../../recherche_sota_ismcts.md) et à la Phase 5
de la feuille de route.*

## 1. Problème

Les Doubles n'existent aujourd'hui que sous forme de **lecture statique** :
`doubles.analyze_doubles` dresse une matrice de menaces 2v2 à partir du calc
(meilleur coup par attaquant et par cible, focus fire, coups de zone). Elle ne
simule aucun tour — ni ordre d'action, ni Protect, ni redirection — et ne
recommande donc aucune action.

Toute la machinerie de décision acquise en Phase 4 est **mono-cible** :
`sim.simulate_turn_actions` résout un tour à deux combattants, et
`nash.solve_turn` résout la matrice 1v1 par regret matching sur une croyance du
set adverse.

L'objectif de la Phase 5 est de porter cette machinerie en 2v2 : décider une
**paire d'actions** face à un adversaire qui en choisit une aussi, simultanément.

## 2. Décisions de conception

| Question | Décision | Raison |
|---|---|---|
| Substrat du Nash 2v2 | Un **simulateur de tour Doubles** dédié, puis Nash par-dessus | Reproduit l'enchaînement `sim → search → nash` de la Phase 4 ; le Nash ne réinvente pas les règles |
| Combinatoire des paires | **Élagage top-k par slot** avant de former les paires | `solve_matrix` reste intact et résout *exactement* le jeu réduit ; un seul paramètre de coût ; filtre explicable |
| Croyance sur deux sets | **Nuage joint échantillonné** (couples pondérés, borné) | `solve_bayesian` se réutilise tel quel : l'adversaire connaît ses deux sets et joue au mieux dans chaque monde |
| Livraison | **Deux PR** : simulateur, puis Nash + surfaces | Chaque PR est relisable et garde la CI verte, comme #12 puis #13 |

## 3. PR A — `sim_doubles.py`, le simulateur de tour 2v2

### 3.1 Réutilisation, pas de réécriture

Le module réutilise `sim.Mon`, `_apply_move`, `_end_of_turn`, `_apply_hazards`,
`_tick_conditions` et `combat.effective_speed`. **`sim.py` n'est pas modifié** :
`_apply_move` n'accède aux camps que par `.screens`, `.tailwind` et `.hazards`,
que le conteneur Doubles expose aussi. Aucune régression possible sur les tests
existants, et aucun impact sur la parité JS.

### 3.2 Structures

```python
Target      = tuple[str, int]   # ("foe", 0|1) | ("ally", 0) | ("self", slot)
SlotAction  = tuple             # ("move", move_id, Target|None) | ("switch", idx) | ("pass", None, None)
SideActions = tuple[SlotAction, SlotAction]

@dataclass
class DoublesSide:
    active: list[Mon]           # 2 slots ; un slot K.O. reste en place
    bench: list[Mon]
    screens: dict[str, int]
    tailwind: int
    hazards: dict[str, int]
    wide_guard: bool = False    # posé pour le tour courant
```

### 3.3 Résolution d'un tour

`simulate_turn_doubles(me, opp, my_actions, opp_actions, field, *, roll=0.5, copy=True)`

1. **Changements** d'abord, les deux camps, l'entrant subit les pièges.
2. **Ordre sur 4 acteurs** : tri par priorité (lue dans la donnée), puis vitesse
   effective (Tailwind ×2, Trick Room inverse le sens), départage stable
   (`me` avant `opp`, slot 0 avant slot 1). Les priorités des coups d'appui sont
   déjà dans `data/moves.json` — Ally Switch +2, Wide Guard +3, Protect +4,
   Helping Hand +5 — donc l'ordre sort **sans code spécifique**.
3. Chaque acteur agit s'il est vivant et n'a pas été mis K.O. entre-temps.
4. **Ciblage piloté par la donnée** (`Move.target`) :
   - `normal` / `adjacentFoe` / `any` → cible explicite (défaut : premier adverse vivant) ;
   - `allAdjacentFoes` → les deux adversaires vivants ;
   - `allAdjacent` → les deux adversaires **et l'allié** — le *friendly fire* de
     Séisme et Surf, décisif en Doubles, sort gratuitement de la donnée ;
   - `self` / `allySide` → l'utilisateur ou son camp ;
   - `adjacentAlly` → l'allié (Helping Hand).
5. **Pénalité de zone ×0.75 seulement si ≥ 2 cibles sont effectivement touchées**
   (règle réelle : un spread sur une cible unique frappe à pleine puissance).
6. **Fin de tour** sur les 4 combattants, puis décompte des conditions de camp.

### 3.4 Mécaniques d'appui couvertes

**Protect** — déjà porté par `Mon.protected` et le blocage dans `_apply_move` ;
gratuit en 2v2, y compris contre les coups de zone.

**Redirection** — résolue *au moment où l'acteur agit*, jamais à la déclaration :

- **Follow Me / Rage Powder** (priorité +2) : tout coup **mono-cible** visant le
  camp du redirecteur est détourné vers lui, s'il est vivant et a agi plus tôt
  dans le tour. Les coups de zone, les coups sur soi et sur l'allié sont exclus.
- **Rage Powder** est inopérant sur les types Plante, les porteurs de Masque de
  Sécurité et le talent Peau Duvetée : `combat._POWDER_MOVES` couvre déjà
  l'immunité Plante, `ragepowder` y est ajouté.
- **Talents Paratonnerre / Lisse-Flot** : redirigent les coups Électrik / Eau du
  camp adverse vers le porteur, qui est **immunisé** et gagne +1 en Attaque
  Spéciale. Actif sans action, donc résolu avant la redirection par coup.
- Priorité entre les deux : un redirecteur **actif** (Follow Me) l'emporte sur un
  talent de redirection.

**Wide Guard** (priorité +3) — pose `wide_guard` sur le camp pour le tour ; tout
coup de zone visant ce camp est annulé, journalisé. Retombe à `False` à la fin du
tour, comme `protected`.

**Ally Switch** (priorité +2) — échange les deux slots du camp. Les cibles déjà
déclarées visent une **position**, pas un Pokémon : un coup ciblant le slot 0
frappe donc l'occupant du slot 0 *après* l'échange. C'est exactement le bluff que
le coup existe pour produire.

**Helping Hand** (priorité +5) — multiplie par 1,5 la puissance du prochain coup
offensif de l'allié **ce tour**. Seul élément qui touche le moteur figé :

- `damage.calculate` reçoit un paramètre optionnel **`power_mod: float = 1.0`**,
  appliqué à la puissance de base avec les autres modificateurs. Neutre par
  défaut : les 33 vecteurs de parité restent inchangés.
- Le même paramètre est ajouté à `web/engine.js` pour tenir l'invariant #3 (les
  deux moteurs ne divergent pas), même si la page autonome ne l'utilise pas
  encore.
- Un **34ᵉ vecteur de parité** avec Helping Hand est ajouté à
  `scripts/calc_reference.mjs` si `@smogon/calc` expose le drapeau
  (`field.attackerSide.isHelpingHand`) ; sinon le paramètre reste couvert par les
  seuls tests Python, et le fait est noté dans le module.
- Côté simulateur, l'effet est porté par un drapeau `helping_hand` sur le `Mon`
  bénéficiaire, consommé par son premier coup offensif du tour.

### 3.5 Hors périmètre, assumé et journalisé

Remplacement d'un K.O. en cours de tour (le slot reste vide jusqu'au tour
suivant), Quash / Après Vous, coups à cibles multiples au-delà des cas ci-dessus,
et la durée exacte des conditions de champ entre déterminisations — mêmes limites
que le simulateur Singles.

### 3.6 Tests — `tests/test_sim_doubles.py`

Ordre à 4 acteurs (priorité, vitesse, Tailwind, Trick Room) · spread ×0.75 sur
deux cibles **et pleine puissance sur une seule** · Séisme touche l'allié ·
Protect bloque, y compris un spread · Wide Guard bloque un spread mais pas un
mono-cible · Follow Me détourne un mono-cible, pas un spread · Rage Powder sans
effet sur un Plante · Paratonnerre redirige, immunise et booste · Ally Switch
fait frapper le mauvais slot · Helping Hand donne bien ×1,5 · cible K.O. avant
l'action = coup perdu · focus fire tuant en deux coups · fin de tour appliquée
aux 4.

### 3.7 CLI

```
python -m simupoke.cli simd <board.json> --me "rockslide,protect" --opp "earthquake,followme"
```

`board.json` = `{"mine": [...], "opp": [...], "field": {...}}`, format déjà
accepté par la commande `doubles`. Ciblage optionnel par suffixe : `move@0`,
`move@1`. La commande imprime le log du tour — le pendant Doubles du rejeu de
ligne existant.

## 4. PR B — `nash_doubles.py`, la décision 2v2

### 4.1 Élagage top-k par slot

Pour chaque slot, les actions candidates (coups × cibles légales, plus un
changement par membre vivant du banc) sont scorées par une passe rapide — dégâts
attendus, K.O. atteint, valeur d'appui — et seules les **k meilleures** sont
retenues (défaut `k = 3`, paramétrable). Les actions de camp sont le produit des
survivantes : une matrice de l'ordre de 9×9.

`nash.solve_matrix` est réutilisé **inchangé** et résout *exactement* le jeu
réduit. Le filtre est reporté à l'utilisateur (« options considérées par slot »),
donc la recommandation reste explicable.

### 4.2 Croyance jointe

Un monde est un **couple** (set du slot adverse gauche, set du droit), tiré par
échantillonnage pondéré du produit de deux `belief.opponent_belief`, borné à `N`
mondes (défaut 12). `nash.solve_bayesian` se réutilise tel quel : l'adversaire
connaît ses deux sets et joue au mieux dans chaque monde, je committe une paire
mixte robuste.

### 4.3 Budget

`9 × 9 × 12 mondes × 1 roll ≈ 1 000` simulations de tour par résolution, avec
`rolls` et `horizon` en paramètres pour monter en qualité. Les défauts sont
**calibrés par un chronométrage** avant d'être figés : cible ≤ 2 s pour une
résolution interactive.

### 4.4 Surfaces

- CLI `nash2 <board.json>` — stratégie mixte de paires, valeur du jeu, croyance ;
- endpoint `POST /api/doubles_nash` ;
- onglet **Doubles** de l'app : la matrice de menaces devient le volet *lecture*,
  la stratégie mixte le volet *décision*.

### 4.5 Tests

Somme des probabilités à 1 · une paire dominée reste sous le seuil d'affichage ·
un K.O. garanti par focus fire domine la stratégie · Protect monte en probabilité
face à une menace de K.O. · déterminisme à graine fixée · l'élagage ne supprime
jamais l'action de meilleure réponse pure.

## 5. Suite hors périmètre

Le triptyque de croyance inter-tours (coup / vitesse / dégâts, mergé en #14) se
branche ensuite sur le nuage joint : ce sera une tranche C.

## 6. Invariants respectés

Hors-ligne (#1) : aucun appel réseau. Source de vérité Python (#2) : le
simulateur Doubles est en Python et testé. Parité JS (#3) : seul `power_mod`
touche `damage.py`, répercuté dans `engine.js`, les scripts de parité restent
verts. Données (#4, #5) : ciblage, priorités et flags de zone sont **lus dans
`data/moves.json`**, aucune table en dur, aucune donnée générée éditée à la main.
