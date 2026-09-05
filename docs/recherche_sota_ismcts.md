# Vers l'état de l'art — recherche de décision pour Champions (§10.2)

Note de recherche (2026-09) : où en est l'IA Pokémon compétitive, ce que
SimuPoke fait désormais, et le chemin pour atteindre — voire dépasser — l'état
de l'art **dans le cadre d'un conseiller hors-ligne, sans entraînement, explicable**.

## 1. L'état de l'art (2025-2026)

| Système | Approche | Force mesurée |
|---|---|---|
| **PokéChamp** | Minimax profondeur-limitée + LLM (shortlist d'actions, modèle adverse, éval de feuille) | Elo ~1300-1500 (top 30-10 %) |
| **Metamon / ByteRL** | RL offline à grande échelle (transformers, 4M démos humaines + 18M synthétiques) | Niveau humain en Gen1-4 OU |
| **PokaiTrainer** | **Recherche en état de croyance** : belief sur les mondes adverses + **CFR linéaire** sur le jeu matriciel bayésien simultané + réseau de valeur | 59 % de sets vs humains ~1320 Elo, pic top 500 |
| **VGC-Bench** | MARL empirique (self-play, fictitious play, double oracle) | Bat un pro VGC en miroir mono-équipe |

Théorie sous-jacente (jeux à coups **simultanés** et **information imparfaite**) :
- un tour de combat est un **jeu matriciel** ; recommander une action pure est
  **exploitable** — la solution est une **stratégie mixte de Nash** ;
- **SM-MCTS** avec *regret matching* / DUCT **converge vers Nash** (Lisý, Bošanský,
  Winands) ;
- **ISMCTS** (Cowling, Powley, Whitehouse) gère l'information imparfaite par des
  **ensembles d'information** + **déterminisation** ;
- **CFR / ReBeL** résolvent des sous-jeux en **état de croyance** avec un réseau
  de valeur contrefactuel.

**Enseignement transversal** (PokaiTrainer) : *« la recherche porte l'agent »* —
même une éval de feuille faible + une bonne recherche bat la politique seule.

## 2. Ce que SimuPoke fait maintenant

`simupoke.nash.solve_turn` résout le tour courant **vers l'équilibre de Nash**,
exactement dans l'esprit PokaiTrainer (sans le réseau neuronal) :

1. **croyance** sur le set adverse (`simupoke.belief`) — nuage de particules
   échantillonnées depuis l'usage (§10.3), **filtrées bayésiennement** par
   l'observé (coups vus, objet/talent connus) et **mises à jour tour après
   tour** sur le coup adverse joué (`update_belief`, cran 3 ci-dessous) ;
2. **matrice de gains** `U[a][b]` évaluée par le simulateur figé (`sim`) +
   l'éval d'équipe, **pondérée par la croyance** et **moyennée sur les jets**
   (énumération de la chance) ;
3. **regret matching** (CFR) → **stratégie mixte** inexploitable, valeur du jeu,
   stratégie adverse, meilleure réponse pure.

Exposé partout : CLI `nash`, API `/api/nash` (donc dans la PWA, côté client via
Pyodide). Vérifié : sur des jeux à équilibre connu (pile/face, pierre-feuille-
ciseaux → uniforme), et sur des tours réels (hedge correct face à Protect au lieu
d'un KO exploitable).

C'est déjà **l'état de l'art pour un conseiller hors-ligne, sans entraînement et
explicable** : la même primitive théorique (Nash sur le jeu de croyance) que le
meilleur agent VGC connu, remplaçant seulement le réseau de valeur par une
heuristique transparente.

## 3. Le chemin vers « l'état de l'art voire plus »

Par ordre d'impact / coût croissant — chaque cran rapproche de PokaiTrainer :

1. ~~**Stratégie adverse par monde** (seat-2 par-world de PokaiTrainer)~~ **✅ fait** :
   `solve_bayesian` — une table de regret par particule ; l'adversaire connaît son
   set et joue au mieux dans chaque monde, je committe une stratégie robuste. Plus
   juste que l'adversaire « moyen » (qui sur-arme l'adversaire en lui prêtant des
   coups absents de certains mondes). *Pur algo, hors-ligne.*
2. **Profondeur** ✅ **fait, avec CFR récursif** : le fond de la matrice évalue
   l'état post-tour par un lookahead de `horizon` tours (`solve_turn(horizon=…)`,
   défaut 0). À l'intérieur d'un monde (set adverse **connu**), la continuation
   est résolue **vers Nash à chaque étage** (`_sm_nash_value`, regret matching
   récursif) — les deux camps jouent au mieux, ni adversaire moyen (expectimax)
   ni pire cas pur (minimax). Vérifié : nash ≤ expectimax, entre moyen et pire.
   **Budget d'expansion ✅ fait**, à **deux leviers complémentaires** — l'un
   réduit la largeur en restant exact, l'autre échantillonne en profondeur :

   - **Largeur bridée** (`width`, `nash._shortlist`) : les actions sont classées
     par une éval **1 ply** (moyenne sur les réponses du camp d'en face) et seules
     les `width` meilleures de chaque côté sont développées — la **shortlist
     d'actions** de PokéChamp, avec une heuristique déterministe au lieu d'un LLM.
     Le nœud reste résolu **exactement vers Nash**, sur un jeu restreint : coût
     `(width²)^horizon`, horizon jusqu'à **5**. Mesuré (4 coups par camp,
     `width=2`) : profondeur 3, 3632 → 280 développements (13×, 1,65 s → 0,07 s) ;
     profondeur 4, 12,2 s → 0,08 s (150×) — valeur identique à 1e-3 près.
   - **Arbre échantillonné** (`budget`, `ismcts.sm_mcts_value`) : à chaque nœud
     les deux camps tirent leur action selon une stratégie de **regret matching**
     — la même primitive que `solve_matrix`. C'est le **SM-MCTS-RM** de Lisý,
     Kovařík et Bošanský (NeurIPS 2013), retenu plutôt que DUCT (UCB découplé)
     parce que lui **converge vers l'équilibre de Nash** du jeu à coups
     simultanés. Le coût devient **linéaire** (`budget × profondeur`), horizon
     jusqu'à **8**. Mesuré (4 coups par camp) : profondeur 3, 0,58 s → **0,02 s**
     (écart de valeur 0,012) ; profondeur 4, 9,9 s → **0,02 s**.

   Les deux se **composent** : avec `width` *et* `budget`, la recherche
   échantillonne un arbre déjà réduit en largeur. Exposé partout :
   `solve_turn(width=…, budget=…)`, CLI `nash --width N --budget N`, API
   `/api/nash` (`width`, `budget`).
3. ~~**Mise à jour de croyance inter-tours**~~ **✅ fait** : `belief.update_belief`
   reconditionne le nuage de particules sur le coup adverse observé —
   `w'_i ∝ w_i · P(coup | monde_i)`. La vraisemblance par monde est la
   **stratégie de Nash par monde** (`solve_turn` l'expose via
   `opp_world_strategies`) : un monde est **remonté** en proportion de la
   probabilité qu'il jouait ce coup, **écrasé au plancher** s'il ne le possède
   pas (preuve dure), et le cas **contradiction** (coup dans aucun monde) est
   traité par **synthèse de spreads** — on l'injecte plutôt que d'effondrer la
   croyance. Trois observables sont reconditionnés — le **triptyque** du scouting
   compétitif :
   - le **coup joué** (ci-dessus) ;
   - l'**ordre d'action** (`update_belief_speed`) — *scouting de vitesse* :
     « l'adversaire m'a dépassé » écrase les mondes trop lents et remonte Choice
     Scarf / nature +Vit (Trick Room, Tailwind, paralysie pris en compte) ;
   - les **dégâts observés** (`update_belief_damage`) — le % infligé/subi révèle
     le bulk et l'objet défensif (Assault Vest…) ou l'investissement offensif
     (Choice Band, Life Orb…) ; on garde les mondes dont l'intervalle de dégâts
     contient l'observé, à une marge de lecture près.

   Exposé partout : CLI `nash --opp-observed <coup>` / `--opp-faster|--opp-slower`
   / `--me-damage %` / `--opp-damage % --my-move <coup>` (glissement de croyance
   affiché), API `/api/nash` (`oppObserved`, `oppFaster`, `meDamagePct`,
   `oppDamagePct`, renvoie `beliefPrior`), et l'onglet Combat de l'app.
   *Pur algo, hors-ligne, explicable.*
4. **Réseau de valeur appris (ONNX)** — *le levier « au-delà »* : remplacer
   l'éval heuristique de feuille par un petit réseau valeur/politique entraîné en
   self-play sur `sim`, exporté en ONNX et chargé **dans le navigateur**
   (onnxruntime-web) → reste hors-ligne (§3). C'est ce qui a fait la force de
   PokaiTrainer ; c'est aussi la Phase 6 de la feuille de route.
5. **Doubles** (Phase 5) : le jeu matriciel devient 2v2 (paires d'actions,
   ciblage) ; la même machinerie Nash s'applique, matrice plus large.

> Note d'honnêteté : les approches purement RL (Metamon, VGC-Bench MARL)
> demandent GPU + entraînement massif et ne conviennent pas à un outil offline
> sans entraînement — et PokéChamp montre qu'une **recherche minimax + modèle**
> reste au sommet **et interprétable**. La cible réaliste de SimuPoke est donc
> une **recherche de croyance Nash forte et explicable**, dont le plafond se
> relève via (4) l'évaluateur appris.

## Sources
- PokéChamp — *An Expert-level Minimax Language Agent*, arXiv 2503.04094.
- Metamon / ByteRL — *Human-Level Competitive Pokémon via Scalable Offline RL
  with Transformers*, arXiv 2504.04395.
- PokaiTrainer — *Scaling Belief-State Search to Competitive Pokémon VGC*,
  arXiv 2608.29197.
- VGC-Bench — arXiv 2506.10326.
- *MCTS in Simultaneous Move Games* (Lisý et al., NeurIPS 2013) ; *ISMCTS*
  (Cowling, Powley, Whitehouse, 2012).
