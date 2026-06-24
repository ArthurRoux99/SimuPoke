# SimuPoke

Outil **hors-ligne** d'aide à la décision pour **Pokémon Champions**, à **saisie
manuelle**, s'appuyant sur un moteur de combat de type Pokémon Showdown.

> Outil séparé, à saisie manuelle, qui ne communique **jamais** avec le jeu
> (cf. cadre CGU, §3 du document socle). C'est un calculateur / conseiller, au
> même titre qu'un *damage calc* ou un *team builder* communautaire.

Document de conception complet : [`docs/conception_socle.md`](docs/conception_socle.md).

## État du projet

**Phase 0 — Socle données & stats** (en cours).

Le modèle de stats Champions est **figé et vérifié en jeu** (Tyranocif Jovial,
4/4 stats exactes le 23/06/2026). Voir §8.3 du document socle.

| Phase | Objet | Statut |
|---|---|---|
| 0 | Socle données + conversion SP→stats + damage calc | ✅ |
| 1 | B2 — Aide au tirage (Roster Ranch) | 🟡 v1 (sans priors d'usage) |
| 2 | B3 — Team builder + team preview | 🟡 v1 (matchups par types) |
| 3 | B1 — Mode analyse (Singles) | 🟡 v1 (analyse 1 tour) |
| — | UI v2 — page HTML autonome (§12) | 🟡 v1 (calc de dégâts) |
| 4 | B1 — Mode simultané (MCTS/ISMCTS) | ⏳ |
| 5 | Doubles | ⏳ |
| 6 | (optionnel) Apprentissage | ⏳ |

## Décisions actées (§0 du document socle)

- **Singles d'abord**, mais **architecture pensée Doubles** dès le départ
  (`SideState.active` est une liste).
- **Python** comme langage cœur ; UI v1 = **CLI**, UI v2 = page HTML autonome.
- **IDs internes en anglais** (style Showdown) ; **affichage FR par défaut**,
  bascule EN prévue (couche i18n).
- L'outil **connaît mon Box** (Pokémon possédés) pour personnaliser les conseils.
- Données **versionnées par régulation** en JSON, modifiables sans toucher au code.

## Structure

```
SimuPoke/
├── docs/conception_socle.md      # document socle de conception (v0.4)
├── data/
│   ├── pokedex.json              # base stats + méta (généré depuis @pkmn/dex)
│   ├── moves.json               # données de moves (généré depuis @pkmn/dex)
│   ├── typechart.json           # efficacité des types (généré depuis @pkmn/dex)
│   ├── my_roster.json            # « mon Box » (Pokémon possédés)
│   └── reg_m_b/                  # données de la régulation courante (M-B)
│       ├── roster.json           # espèces légales + flags (peut méga ?)
│       ├── abilities.json        # talents custom (delta Champions, §7.2)
│       ├── items.json
│       ├── moves_overrides.json  # exceptions de moves vs VGC classique
│       └── clauses.json          # Species/Item Clause, formats
├── web/                          # UI v2 — page HTML autonome (thème sombre)
│   ├── index.html · style.css · app.js   # source de l'interface
│   ├── engine.js                # moteur de dégâts JS (port de damage.py)
│   ├── verify_engine.mjs        # parité JS vs vecteurs @smogon/calc
│   └── dist/simupoke.html       # fichier autonome assemblé (généré)
├── scripts/
│   ├── gen_pokedex.mjs           # génère data/pokedex.json (hors-ligne, via npm)
│   ├── gen_moves.mjs            # génère data/moves.json + typechart.json
│   ├── calc_reference.mjs       # scénarios de référence @smogon/calc (tests)
│   ├── build_web.py             # assemble web/dist/simupoke.html (stdlib)
│   └── package.json
├── data/sample_lineup.json      # exemple de tirage (démo/fixture B2)
├── data/sample_team.json        # exemple d'équipe (démo/fixture B3)
├── data/sample_opponent.json    # exemple d'équipe adverse (team preview)
├── src/simupoke/
│   ├── stats.py                  # modèle de stats figé (conversion SP→stats)
│   ├── basestats.py              # base stats + méta (lit data/pokedex.json)
│   ├── moves.py                 # données de moves
│   ├── typechart.py             # efficacité des types
│   ├── damage.py                # calculateur de dégâts (Gen 5+, parité @smogon/calc)
│   ├── delta.py                 # delta Champions : talents custom (§7.2) au calc
│   ├── analysis.py              # typage défensif/offensif + inférence de rôle
│   ├── draft.py                 # B2 — scoring/classement du tirage
│   ├── team.py                  # B3 — analyse d'équipe + assistant team preview
│   ├── combat.py                # B1 — assistant de combat (mode analyse, 1 tour)
│   ├── model.py                  # OwnedPokemon + état de combat (Doubles-ready)
│   ├── i18n.py                   # couche d'affichage FR/EN
│   ├── loaders.py                # chargement roster + régulation + lineup + équipe
│   └── cli.py                    # CLI de validation du pipeline
└── tests/                        # tests pytest
```

## Données de base (base stats)

Les base stats proviennent de **`@pkmn/dex`** (source nommée au §12), alignées
sur les IDs Showdown utilisés en interne. Elles sont **figées dans un fichier
versionné** `data/pokedex.json` (1300+ espèces, formes Méga incluses), de sorte
que le runtime reste **100 % hors-ligne** (§3) — aucune requête réseau pendant
l'utilisation de l'outil.

> Les base stats sont identiques à celles du jeu principal : Champions ne change
> que le système IV/SP, pas les stats de base (§4.3).

Les **moves** et la **table des types** suivent le même principe
(`data/moves.json`, `data/typechart.json`).

Pour **régénérer** les fichiers (mise à jour `@pkmn/dex`, nouvelle régulation) :

```bash
cd scripts
npm install
node gen_pokedex.mjs   # réécrit ../data/pokedex.json
node gen_moves.mjs     # réécrit ../data/moves.json + typechart.json
# ou : npm run gen:all
```

## Calculateur de dégâts

`simupoke.damage.calculate` implémente la formule de dégâts **Génération 5+**
(modificateurs chaînés en base 4096, `pokeRound`, 16 rolls 85–100 %), avec
**parité vérifiée contre `@smogon/calc`** (12 scénarios, `tests/test_damage.py`).

Couvert : STAB (×1.5 / ×2 Adaptability), efficacité des types, coup critique,
brûlure, météo, terrains, esquive multi-cibles, boosts ; items Choice
Band/Specs, Life Orb, Expert Belt, Assault Vest ; talents Huge/Pure Power,
Guts, Technician, Tinted Lens, Neuroforce, Multiscale, Filter & co. ; **talents
défensifs** : immunités (Lévitation, Torche, Absorbe-Volt/Eau, etc.) et
réductions (Thick Fat, Heatproof).

### Delta Champions (§7.2)

`simupoke.delta` branche les **talents custom de Champions** sur le calc, en
combinant des templates intégrés et les données de régulation
(`data/<reg>/abilities.json`) — ajouter un clone de template est ainsi une
opération **de données**, sans toucher au moteur :

- **Famille -ate** (Pixilate/Aerilate/Refrigerate/Galvanize) + le custom
  **Dragonize** (M. Feraligatr, « Normal → Dragon, +20 % ») : chargé depuis les
  données. Le chemin générique -ate est validé à l'identique contre `@smogon/calc`.
- **Mega Sol** (M. Meganium) : soleil « personnel » (boost ×1.5 des moves Feu).

Les talents purement « moteur » (Piercing Drill = passe Protect, Spicy Spray =
brûlure au contact) ne sont pas des modificateurs de dégâts et relèveront du
simulateur de tour. Les **nouvelles Méga** absentes de `@pkmn/dex` (Feraligatr,
Meganium…) ont leur *mécanique* en place ; il reste à saisir leurs **base stats
réelles** dans les données de régulation (pas de valeurs inventées).

## B2 — Aide au tirage (Roster Ranch)

`simupoke.draft.rank_lineup` note et classe les 10 Pokémon d'un lineup (§11.3).
Le score combine des sous-scores pondérés : **stats** (BST), **typage
défensif**, **couverture offensive**, **rôle** (sweeper/mur/pivot/support),
**synergie avec mon Box** (couvre les menaces de l'équipe sans empiler de
faiblesses) et **rareté** (shiny/titre). La sortie est un classement /100 avec
justification et reco **essai 7 j vs permanent (2 500 VP)**.

> Le sous-score **usage/méta** est un *hook* neutre (0.5) tant que l'importeur
> de stats d'usage (limitless / pokedata, §0.2) n'est pas branché : il suffira
> de passer `usage_prior={espèce: 0..1}` à `rank_lineup` — rien d'autre ne change.

## B3 — Team builder & assistant team preview

`simupoke.team` couvre deux besoins (§11.2, §11.4), sans dépendance externe :

- **Analyse d'équipe** (`analyze_team`) : vérification des **clauses** (Species,
  Item), **trous défensifs** (faiblesses partagées par ≥ la moitié de l'équipe),
  **couverture offensive manquante**, distribution des **rôles**.
- **Assistant team preview** (`select_team_preview`) : à partir de mes 6 et des
  6 adverses, choisit les **3 (singles) / 4 (doubles)** à amener et l'**ordre
  d'envoi**, selon un score de matchup de types + vitesse, avec justification.

> Limitations v1 (documentées) : le profil défensif est **purement typé** — les
> immunités de talent (Levitate, Lévitation, etc.) ne sont pas encore prises en
> compte ; le matchup preview est une **heuristique de types** (le calculateur
> de dégâts pourra l'affiner ensuite).

## UI — page HTML autonome (thème sombre)

Une interface graphique **hors-ligne, en un seul fichier** (§12), pour le
calculateur de dégâts. Le moteur JS (`web/engine.js`) est un **port fidèle** de
`src/simupoke/damage.py`, vérifié contre les **mêmes vecteurs de parité
`@smogon/calc`** (`node web/verify_engine.mjs` → 18/18).

```bash
# Construire le fichier autonome (stdlib Python, aucune dépendance)
python scripts/build_web.py        # -> web/dist/simupoke.html (~285 Ko)
```

Ouvrir ensuite `web/dist/simupoke.html` dans un navigateur : tout est embarqué
(données + moteur), aucun serveur requis. La page propose attaquant/défenseur
(espèce, nature, SP, objet, talent, boosts, statut, PV %), météo/terrain,
critique et attaque de zone, avec dégâts min–max, %, KO en N coups et le delta
Champions (ex. talent `dragonize`).

> Source dans `web/` (`index.html` + `style.css` + `engine.js` + `app.js`),
> assemblée par `scripts/build_web.py`. Les autres modules (B2/B3/B1) restent en
> CLI pour l'instant ; ils rejoindront l'UI ensuite.

## B1 — Assistant de combat (mode analyse)

`simupoke.combat.analyze_turn` réalise une **analyse à 1 tour** (§10.1, palier
« rapide et indicatif » §15 Q3) : elle classe mes coups par valeur attendue à
partir du calculateur de dégâts, en tenant compte du **KO**, de l'**ordre
d'action** (priorité + vitesse, paralysie, Choice Scarf, Trick Room) et du
**risque** (dégâts subis). L'action adverse peut être **fournie** (info quasi
parfaite) ou **estimée** depuis ses coups connus.

> Limitations v1 (assumées) : un seul tour, centré sur les coups offensifs (les
> coups de statut sont listés mais non évalués) ; pas de changement ni de
> recherche d'arbre — ce sera la **Phase 4** (MCTS/ISMCTS, §10.2). Build adverse
> inconnu ⇒ nature neutre / 0 SP (le modèle d'usage §10.3 affinera).

## Démarrage rapide

```bash
# Optionnel : environnement virtuel
python -m venv .venv && source .venv/bin/activate

# Installation (mode développement) avec les dépendances de test
pip install -e ".[dev]"

# Lancer les tests
pytest

# Afficher mon Box avec stats finales calculées
python -m simupoke.cli roster

# Calculer les stats d'un build ad hoc
#   stats <species> <nature> <hp> <atk> <def> <spa> <spd> <spe>
python -m simupoke.cli stats tyranitar jolly 2 32 0 0 0 32

# Calculer des dégâts
#   damage <atk_species> <atk_nature> <move> <def_species> <def_nature> [options]
python -m simupoke.cli damage garchomp adamant earthquake tyranitar jolly \
    --atk-sp atk=31 --item-atk choiceband
#   -> Earthquake : 258–306 (147.4–174.9 %) — super efficace (×2) — STAB
#      KO garanti en 1 coup(s)

# B2 — Aide au tirage : classer les 10 Pokémon du jour
python -m simupoke.cli draft data/sample_lineup.json
#   -> classement /100 + rôle + reco essai/permanent + justification

# B3 — Analyse d'équipe (clauses, trous défensifs, couverture, rôles)
python -m simupoke.cli team data/sample_team.json

# B3 — Assistant team preview : quoi amener face à l'adversaire
python -m simupoke.cli preview data/sample_team.json data/sample_opponent.json --format doubles

# B1 — Assistant de combat (mode analyse) : classer mes coups ce tour
python -m simupoke.cli analyze garchomp jolly earthquake,dragonclaw,stoneedge \
    tyranitar adamant --me-sp atk=32,spe=32 --opp-move crunch
#   -> menace adverse + options classées (dégâts, KO, ordre, risque) + reco
```

> Sans installation, on peut aussi lancer depuis la racine du dépôt avec
> `PYTHONPATH=src python -m simupoke.cli ...` et `PYTHONPATH=src pytest`.

## Modèle de stats (rappel, §8.3)

Niveau 50, IV 31 partout, SP ∈ [0, 32] par stat, budget total **66 SP**.

```
I       = 2·Base + 31 + 2·SP
PV      = ⌊I / 2⌋ + 60
Autres  = ⌊ (⌊I / 2⌋ + 5) · Nature ⌋     (Nature ∈ {0.9, 1.0, 1.1})
```

## Prochaines étapes (Phase 0 → Phase 1)

- [x] Brancher une vraie source de base stats (`@pkmn/dex`) → `data/pokedex.json`.
- [x] Calculateur de dégâts (formule Gen 5+, parité `@smogon/calc`).
- [x] B2 — Aide au tirage v1 (scoring, classement, justification, reco).
- [x] B3 — Team builder + assistant team preview v1 (clauses, trous, matchups).
- [x] Talents défensifs dans le calc (immunités + Thick Fat/Heatproof).
- [x] B1 — Assistant de combat, mode analyse v1 (analyse 1 tour, §10.1).
- [x] Delta Champions au calc : talents -ate (dont Dragonize, piloté par données) + Mega Sol.
- [x] UI v2 — page HTML autonome v1 (calculateur de dégâts, moteur JS à parité).
- [ ] Étendre l'UI aux modules B2/B3/B1.
- [ ] Saisir les base stats des nouvelles Méga Champions dans les données de régulation.
- [ ] Importeur de stats d'usage (limitless / pokedata) → priors B2 + adversaire (§0.2).
- [ ] B1 — Mode décision simultané (MCTS/ISMCTS, §10.2) — Phase 4.
- [ ] UI v2 — page HTML autonome (thème sombre, §12).
