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
| — | UI — page HTML autonome (§12) | 🟡 v1 (calc de dégâts) |
| — | UI — serveur local (tous les modules) | 🟡 v1 (Dégâts/B1/B2/B3) |
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
│   ├── dist/simupoke.html       # fichier autonome assemblé (généré)
│   └── server/                  # frontend de la version hébergée (index.html + app.js)
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
l'utilisation de l'outil. (`@pkmn/dex` ≥ 0.10.11 intègre les Méga custom de
Pokémon Champions ; régénérer le fichier les inclut automatiquement.)

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
simulateur de tour. Les **nouvelles Méga Champions** (Feraligatr-Mega à
Dragonize, Meganium-Mega à Mega Sol, Floette-Mega, Scovillain-Mega…) ont
désormais leurs **base stats réelles** : elles figurent dans `@pkmn/dex`
(≥ 0.10.11, qui intègre les données du mod Champions de Showdown) et sont donc
incluses automatiquement dans `data/pokedex.json` — aucune valeur inventée.

## B2 — Aide au tirage (Roster Ranch)

`simupoke.draft.rank_lineup` note et classe les 10 Pokémon d'un lineup (§11.3).
Le score combine des sous-scores pondérés : **stats** (BST), **typage
défensif**, **couverture offensive**, **rôle** (sweeper/mur/pivot/support),
**synergie avec mon Box** (couvre les menaces de l'équipe sans empiler de
faiblesses) et **rareté** (shiny/titre). La sortie est un classement /100 avec
justification et reco **essai 7 j vs permanent (2 500 VP)**.

> Le sous-score **usage/méta** est branché sur le modèle d'usage ci-dessous (et
> retombe à un neutre 0.5 si aucune donnée d'usage n'est disponible).

## Modèle d'adversaire — stats d'usage (§0.2, §10.3)

`simupoke.usage` transforme des stats d'usage agrégées (un JSON par régulation,
`data/usage/<reg>.json`) en :

- **priors de popularité** (`usage_prior`) → pondèrent le sous-score « méta » de
  B2 (appliqués automatiquement par le serveur / `cli draft --usage`) ;
- **set le plus probable** d'une espèce (`likely_set`) → comble les inconnues
  adverses (objet, talent, nature, capacités) tant que rien n'est observé.
  Exposé par `GET /api/likely?species=…` et le bouton « Adversaire probable »
  de l'onglet Combat.

> `data/usage/reg_m_b.json` est désormais alimenté par de **vraies stats
> d'usage Smogon** (format Champions `gen9championsvgc2026regma`, palier 1630,
> mois 2026-05), importées via `simupoke.usage_import`. Faute de stats publiées
> pour Reg M-B, on utilise Reg M-A comme **meilleur proxy disponible** ; la
> source exacte est tracée dans `_meta.source`. Le joueur peut toujours
> surcharger un prior dès qu'il observe une info réelle.

### Importer de vraies stats d'usage (partie réseau)

`simupoke.usage_import` récupère et convertit des stats d'usage au format
**Showdown « chaos » JSON** (le standard de fait). Le téléchargement utilise
`urllib` (proxy-aware) ; il s'exécute là où le réseau est ouvert (ton PC).

```bash
# depuis une URL (ex. un dump chaos Showdown/Smogon)
python -m simupoke.usage_import https://example/chaos/gen9vgc.json --reg reg_m_b
# ou, après `pip install -e .` :
simupoke-import-usage chemin/vers/chaos.json --reg reg_m_b
```

Les comptes bruts sont normalisés en probabilités conditionnelles, filtrés et
écrits dans `data/usage/<reg>.json` — directement consommé par B2 (priors) et le
modèle d'adversaire. Le parseur est testé hors-ligne (`tests/test_usage_import.py`) ;
si une source bloque l'accès réseau, télécharge le fichier puis importe-le en
local. Format détaillé en tête de `src/simupoke/usage_import.py`.

## B3 — Team builder & assistant team preview

`simupoke.team` couvre deux besoins (§11.2, §11.4), sans dépendance externe :

- **Analyse d'équipe** (`analyze_team`) : vérification des **clauses** (Species,
  Item), **trous défensifs** (faiblesses partagées par ≥ la moitié de l'équipe),
  **couverture offensive manquante**, distribution des **rôles**.
- **Assistant team preview** (`select_team_preview`) : à partir de mes 6 et des
  6 adverses, choisit les **3 (singles) / 4 (doubles)** à amener et l'**ordre
  d'envoi**, selon un score de matchup de types + vitesse, avec justification.

> Le profil défensif tient compte des **immunités de talent** (Lévitation,
> Torche, Absorbe-Volt/Eau…) : un Motisma-Lavage à Lévitation n'est plus compté
> faible au Sol. Limitation restante : le matchup *preview* est une **heuristique
> de types** (le calculateur de dégâts pourra l'affiner ensuite).

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
> assemblée par `scripts/build_web.py`. Cette version autonome ne couvre que le
> calcul de dégâts.

### Publication sur GitHub Pages

La page autonome est publiée automatiquement à chaque push sur `main`
(`.github/workflows/pages.yml`) : la CI lance `build_web.py` et déploie le
fichier produit comme racine du site. Le build reste **hors du dépôt**
(`dist/` est dans `.gitignore`) — la page publiée ne peut donc jamais être
périmée par rapport aux données.

Le cadre hors-ligne (§3) est préservé : la page embarque tout (données +
moteur) et ne fait **aucune requête réseau** une fois chargée. Elle n'embarque
que `pokedex`/`moves`/`typechart` et la carte -ate de la régulation —
**jamais `data/my_roster.json`** : rien de personnel n'est publié. Les modules
B1/B2/B3, qui ont besoin du moteur Python, restent locaux (serveur ci-dessous).

### Version hébergée sur le PC (tous les modules)

Pour **tous** les modules (Dégâts, Combat B1, Tirage B2, Équipe B3, Team
preview) dans une seule interface, on lance un **serveur local** qui réutilise
directement le moteur Python — une seule source de vérité, déjà testée. Stdlib
seule, aucune dépendance.

```bash
python -m simupoke.server            # http://127.0.0.1:8000
# ou, après `pip install -e .` :  simupoke-server --port 9000
```

Puis ouvrir <http://127.0.0.1:8000> : une UI sombre à onglets **Dégâts, Combat
(B1), Tirage (B2), Équipe (B3), Team preview** et **Mon Box**. Le frontend
(`web/server/`) appelle l'API JSON `/api/*` ; toute la logique de jeu reste côté
Python. Les onglets Tirage/Équipe/Preview utilisent un **éditeur de Pokémon**
(lignes ajoutables : espèce, nature, objet, talent, capacités), préremplis avec
les exemples de `data/`. L'onglet **Mon Box** charge, édite et **enregistre**
`data/my_roster.json` directement. Rien ne sort de ta machine (§3).

> API : `GET /api/meta|samples|roster`,
> `POST /api/damage|analyze|draft|team|preview|stats|roster`.

## B1 — Assistant de combat (mode analyse)

`simupoke.combat.analyze_turn` réalise une **analyse à 1 tour** (§10.1, palier
« rapide et indicatif » §15 Q3) : elle classe mes coups par valeur attendue à
partir du calculateur de dégâts, en tenant compte du **KO**, de l'**ordre
d'action** (priorité + vitesse, paralysie, Choice Scarf, Trick Room) et du
**risque** (dégâts subis). L'action adverse peut être **fournie** (info quasi
parfaite), **déduite** des coups déjà observés, ou — si rien n'est connu —
**estimée via le set le plus probable de l'espèce** (modèle d'usage §10.3,
signalée « estimé via l'usage »).

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
- [x] UI — page HTML autonome v1 (calculateur de dégâts, moteur JS à parité).
- [x] UI — serveur local v1 : tous les modules (Dégâts/B1/B2/B3) via API Python.
- [x] UI hébergée : éditeurs de Pokémon (sans JSON brut) + onglet « Mon Box » éditable.
- [x] Modèle d'usage (§0.2) : importeur/format local + priors B2 + set probable adverse.
- [x] B3 : immunités de talent (Lévitation…) dans le profil défensif.
- [x] B1 : menace adverse estimée via l'usage quand les coups ne sont pas saisis.
- [x] Importeur réseau de stats d'usage (Showdown chaos) → `usage_import` / `simupoke-import-usage`.
- [x] Lancer l'import sur une vraie source (Smogon chaos, Champions Reg M-A 1630, 2026-05) → remplace l'échantillon.
- [x] Base stats des nouvelles Méga Champions : `@pkmn/dex` ≥ 0.10.11 + régénération de `data/pokedex.json` (24 Méga ajoutées, p. ex. Feraligatr/Meganium/Floette-Mega).
- [ ] Ré-importer l'usage sur Reg M-B dès que Smogon le publie (`simupoke-import-usage`).
- [ ] B1 — Mode décision simultané (MCTS/ISMCTS, §10.2) — Phase 4.
- [ ] Doubles (Phase 5) ; apprentissage optionnel (Phase 6).
