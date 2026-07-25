# SimuPoke

Outil **hors-ligne** d'aide à la décision pour **Pokémon Champions**, à **saisie
manuelle**, s'appuyant sur un moteur de combat de type Pokémon Showdown.

> Outil séparé, à saisie manuelle, qui ne communique **jamais** avec le jeu
> (cf. cadre CGU, §3 du document socle). C'est un calculateur / conseiller, au
> même titre qu'un *damage calc* ou un *team builder* communautaire.

Document de conception complet : [`docs/conception_socle.md`](docs/conception_socle.md).

## État du projet

Le modèle de stats Champions est **figé et vérifié en jeu** (Tyranocif Jovial,
4/4 stats exactes le 23/06/2026). Voir §8.3 du document socle.

| Phase | Objet | Statut |
|---|---|---|
| 0 | Socle données + conversion SP→stats + damage calc (talents/items/Paradox/écrans) | ✅ |
| 1 | B2 — Aide au tirage (Roster Ranch) + priors d'usage | ✅ |
| 2 | B3 — Team builder + team preview (matchups par dégâts) | ✅ |
| 3 | B1 — Mode analyse (coups + switchs + soutien) | ✅ |
| — | Seuils & optimiseur de SP (speed tiers, outspeed/survive/ko, spread) | ✅ |
| — | UI — page HTML autonome (calc, parité JS 33/33) | ✅ |
| — | UI — serveur local (tous les modules + recherche) | ✅ |
| — | Modèle d'usage + import Showdown paste + i18n FR/EN | ✅ |
| 4 | B1 — Mode simultané : simulateur + recherche multi-tours/switchs/minimax/déterminisation | 🟡 (ISMCTS complet à venir) |
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
│   ├── sim.py                   # simulateur de tour (ordre, dégâts, statut, fin de tour) — fondation Phase 4
│   ├── search.py                # recherche à coups simultanés (§10.2) : multi-tours, switchs, minimax, déterminisation
│   ├── bench.py                 # seuils & optimiseur de SP (speed tiers, outspeed/survive/ko)
│   ├── optimize.py              # optimiseur de spread complet (objectifs combinés → SP)
│   ├── model.py                  # OwnedPokemon + état de combat (Doubles-ready)
│   ├── showdown.py              # import/export « Showdown paste » (EV ⇄ SP)
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
brûlure, météo, terrains, esquive multi-cibles, boosts.

- **Items** : Choice Band/Specs, Life Orb, Expert Belt, Assault Vest ; items
  « type-boost » (Charbon, Eau Mystique…) ×1.2 ; Muscle Band / Wise Glasses ×1.1.
- **Talents offensifs** : Huge/Pure Power, Guts, Technician, Tinted Lens,
  Neuroforce, Water Bubble, Solar Power, Sand Force, **Protosynthèse / Charge
  Quantique** (Paradox : dope la plus haute stat sous soleil / champ électrifié
  ou Énergie Booster) et type-boost (Steelworker, Dragon's Maw, Rocky Payload,
  Transistor).
- **Talents défensifs** : Multiscale, Filter & co., immunités (Lévitation,
  Torche, Absorbe-Volt/Eau…), réductions (Thick Fat, Heatproof) et **Fluffy,
  Ice Scales, Sel Purifiant, Water Bubble, Peau Sèche**.
- **Écrans** : Protection (physique), Mur Lumière (spécial), Voile Aurore (les
  deux) — ×0.5 en singles, ×0.667 en doubles, **ignorés par le critique**.

> Nouveaux modificateurs vérifiés par **ratio** contre les valeurs Showdown
> (`tests/test_damage_coverage.py`) ; les 12 scénarios de parité `@smogon/calc`
> historiques restent verts. Les écrans se pilotent par `--screen` (CLI),
> `screen` (API), le sélecteur **Écran** de l'UI et `min_sp_to_survive(screen=…)`.
> **Tera** est volontairement absent : il n'est pas dans Champions au lancement
> (§4.6 du document socle).

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
  d'envoi**, avec justification. Le matchup est **affiné par le calculateur de
  dégâts** (`use_damage=True`, défaut) : il compare les **coups pour KO** de
  chaque camp (moves connus, sinon set le plus probable §10.3) plutôt qu'une
  simple efficacité de types — avec **repli automatique sur les types** quand
  aucune capacité n'est estimable. `--no-damage` force l'ancien mode.

> Le profil défensif tient compte des **immunités de talent** (Lévitation,
> Torche, Absorbe-Volt/Eau…) : un Motisma-Lavage à Lévitation n'est plus compté
> faible au Sol. Le mode dégâts prend en compte objets/talents/SP réels (Choice
> Band, Life Orb…), donc l'ordre d'amenée reflète la vraie pression, pas juste
> les types.

## UI — page HTML autonome (thème sombre)

Une interface graphique **hors-ligne, en un seul fichier** (§12), pour le
calculateur de dégâts. Le moteur JS (`web/engine.js`) est un **port fidèle** de
`src/simupoke/damage.py` — socle **et** modificateurs avancés (items type-boost,
Muscle Band/Wise Glasses, Water Bubble, Solar Power, Sand Force, Protosynthèse /
Charge Quantique, type-boost, Fluffy/Ice Scales/Sel Purifiant/Peau Sèche) —
vérifié par **parité** (`node web/verify_engine.mjs` → **33/33**) : 18 vecteurs
`@smogon/calc` historiques + 15 vecteurs de référence issus du moteur Python
(modificateurs avancés + écrans).

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
(B1), Tirage (B2), Équipe (B3), Team preview, Seuils** et **Mon Box**. Le frontend
(`web/server/`) appelle l'API JSON `/api/*` ; toute la logique de jeu reste côté
Python. Les onglets Tirage/Équipe/Preview utilisent un **éditeur de Pokémon**
(lignes ajoutables : espèce, nature, objet, talent, capacités), préremplis avec
les exemples de `data/`. L'onglet **Mon Box** charge, édite et **enregistre**
`data/my_roster.json` directement. Rien ne sort de ta machine (§3).

> API : `GET /api/meta|samples|roster`,
> `POST /api/damage|analyze|decide|draft|team|preview|stats|roster|speed|outspeed|survive|ko|spread|paste|export`.

### Accès mobile / 2ᵉ écran (proximité, sans rien exposer, §15 Q4)

Pas besoin d'hébergement cloud : le serveur tourne sur ton PC et peut être ouvert
depuis ton **mobile ou un 2ᵉ écran** sur le **même wifi**. Tout reste local (le
cadre §3 est préservé — ni le jeu ni un serveur tiers ne voient tes données).

```bash
python -m simupoke.server --host 0.0.0.0
#   Accès mobile / 2e écran (même wifi) : http://192.168.x.x:8000
```

Le démarrage affiche directement l'URL LAN à ouvrir sur le téléphone. Pour un
accès **partout** (hors wifi) sans serveur, la **page autonome** (calc) est déjà
publiée sur GitHub Pages ; les autres modules pourront y être ajoutés en JS.

## B1 — Assistant de combat (mode analyse)

`simupoke.combat.analyze_turn` réalise une **analyse à 1 tour** (§10.1, palier
« rapide et indicatif » §15 Q3) : elle classe mes coups par valeur attendue à
partir du calculateur de dégâts, en tenant compte du **KO**, de l'**ordre
d'action** (priorité + vitesse, paralysie, Choice Scarf, Trick Room) et du
**risque** (dégâts subis). L'action adverse peut être **fournie** (info quasi
parfaite), **déduite** des coups déjà observés, ou — si rien n'est connu —
**estimée via le set le plus probable de l'espèce** (modèle d'usage §10.3,
signalée « estimé via l'usage »).

Les **changements** (switch) sont évalués si un banc est fourni : `analyze_turn`
note chaque Pokémon du banc sur sa **sûreté à l'entrée** (coup encaissé) et sa
**menace au tour suivant** (offense escomptée), et **recommande un pivot** quand
l'actif serait mis KO sans tuer d'abord et qu'un remplaçant encaisse. Exposé en
CLI (`analyze --bench …`), par l'API (`bench` dans `POST /api/analyze`, champ
`switches` en sortie) et le champ **Mon banc** de l'onglet Combat.

```bash
python -m simupoke.cli analyze gengar timid shadowball garchomp jolly \
    --me-hp 0.3 --opp-move earthquake \
    --bench "skarmory,impish,bravebird ; rotomwash,bold,hydropump"
#   -> ➤ Changer pour skarmory — l'actif serait mis KO ; ce switch encaisse.
```

Les **coups de soutien** sont désormais notés (palier indicatif) : les **setups**
(Danse-Lames, Machination, Danse Draco…) sont chiffrés par l'**offense qu'ils
débloquent** au tour suivant (recalcul avec les boosts) ; **statut**
(Feu Follet/Cage-Éclair/Spore, avec immunités de type), **protection** et **soin**
par des heuristiques transparentes. Un setup **sûr** peut primer la reco ; sous
menace de OHKO il est déprécié.

> Limitations restantes (assumées) : un seul tour ; coups de soutien notés par
> **heuristique** (pas de simulation multi-tours) ; pas encore de recherche
> d'arbre — ce sera la **Phase 4** (MCTS/ISMCTS, §10.2). Build adverse inconnu
> ⇒ nature neutre / 0 SP (le modèle d'usage §10.3 affine).

## Seuils & optimiseur de SP (§11.1 — « seuils de survie / de KO »)

`simupoke.bench` répond aux questions **inverses** du damage calc — celles que
se pose un joueur VGC en réglant son spread. Le modèle de SP Champions (entiers
dans [0, 32], §8.3) rend l'espace de recherche trivial : on énumère.

- **Speed tiers** (`speed_tiers`) : classe des Pokémon par vitesse effective,
  Choice Scarf / Tailwind / paralysie / boosts inclus, avec inversion sous
  **Trick Room**.
- **Vitesse** (`min_sp_to_outspeed`) : SP minimal en Vitesse pour (dé)passer une
  cible (option « égaliser suffit », Tailwind des deux côtés).
- **Survie** (`min_sp_to_survive`) : SP défensif total minimal (PV + Déf/Déf.Spé)
  pour encaisser le **roll haut** d'une attaque, avec la répartition de coût
  minimal.
- **KO** (`min_sp_to_ko`) : SP offensif minimal (Atq/Atq.Spé) pour un KO
  **garanti** (roll bas) en N coups — tient compte des PV courants de la cible
  (finir un adversaire entamé).

> **Focus Sash / Fermeté** sont pris en compte : une cible à PV pleins encaisse
> un coup fatal (reste 1 PV) — la survie est garantie sans SP et un OHKO devient
> un 2HKO minimum (signalé dans les seuils et l'optimiseur de spread).

> Ces optimiseurs raisonnent **stat par stat** (le minimum requis là où ça
> compte) ; la contrainte de budget global (66 SP au total) reste au joueur qui
> assemble le spread complet. Exposés en CLI (`speed`/`outspeed`/`survive`/`ko`)
> et par l'API (`POST /api/speed|outspeed|survive|ko`) + l'onglet **Seuils**.

### Optimiseur de spread complet (§8.3)

`simupoke.optimize.optimize_spread` **compose** ces seuils : à partir d'une liste
d'**objectifs** (dépasser X, survivre à Y, tuer Z), il résout un spread SP
**complet et légal** — total ≤ 66, ≤ 32 par stat — au coût minimal. La
décomposition rend le problème facile : Vitesse (`spe`) et Offense (`atk`/`spa`)
sont des axes indépendants (max des seuils), seule la **défense** est couplée
(les PV sont partagés entre Déf et Déf.Spé) — on balaie alors les PV en
minimisant `hp + def + spd`. Les objectifs hors de portée ou le dépassement de
budget sont **signalés** (l'outil reste explicable) plutôt que de faire échouer
le calcul.

```bash
# Tyranitar Rigide : OHKO Garchomp (Ice Punch), survivre au Séisme d'un Garchomp
# max Atq, dépasser Amoonguss → spread SP complet
python -m simupoke.cli spread tyranitar adamant \
    --ko garchomp,jolly,icepunch \
    --survive garchomp,adamant,earthquake,off=32 \
    --outspeed amoonguss,sassy,spe=0
#   -> Spread proposé : PV 2, Atq 15, Déf 22 (39/66) — tous objectifs tenus
#   (ajoute item=choiceband au Séisme et l'objectif de survie passe hors de portée)
```

> Exposé aussi par l'API (`POST /api/spread`) et le panneau **Optimiseur de
> spread** de l'onglet Seuils (éditeur d'objectifs dépasser/survivre/tuer).

```bash
# Combien de SP en Vitesse pour dépasser un Flutter Mane vitesse max ?
python -m simupoke.cli outspeed garchomp jolly fluttermane timid --target-sp spe=32

# Quel investissement défensif pour survivre à un Séisme Choice Band ?
python -m simupoke.cli survive tyranitar careful garchomp adamant earthquake \
    --atk-sp atk=32 --atk-item choiceband

# Combien d'Attaque pour OHKO garanti ?
python -m simupoke.cli ko garchomp adamant earthquake tyranitar adamant --atk-item choiceband

# Speed tiers d'une équipe (fichier), inversion possible sous Trick Room
python -m simupoke.cli speed data/sample_team.json --trick-room
```

## Simulateur de tour (fondation Phase 4, §10.2)

`simupoke.sim` **résout un tour complet** en Singles — au-delà du calcul mono-coup :
ordre d'action (priorité + vitesse effective, paralysie/Scarf/Trick Room), dégâts
(via le calc figé, à un roll paramétrable), coups de **statut/setup/protection/soin**,
sommeil/gel, puis effets de **fin de tour** (brûlure, poison/toxik à compteur,
Vestiges, tempête de sable, Orbe Vie). `rollout` enchaîne les tours pour **rejouer
une ligne** (revue de partie, §10.1) et servira de substrat à la recherche
simultanée (MCTS/ISMCTS).

```bash
# Rejoue une ligne tour par tour (séquences de coups séparées par des virgules)
python -m simupoke.cli sim garchomp jolly swordsdance,earthquake amoonguss sassy spore,sludgebomb \
    --me-sp atk=32,spe=32 --opp-sp hp=32,spd=32
#   -> déroulé commenté (setup, sommeil, KO) + verdict de la ligne
```

Les **changements** sont gérés via `simulate_turn_actions(Side, Side, action, …)`
où une action est `("move", nom)` ou `("switch", indice)` : les switchs se
résolvent avant les coups (le coup adverse touche l'entrant), boosts du sortant
remis à zéro. Ce chemin gère aussi les **conditions de camp/champ** : écrans
(Protection/Mur Lumière/Voile Aurore), **Tailwind** (vitesse ×2), **pièges
d'entrée** (Piège de Roc selon l'efficacité Roche, Picots pour les non-Vol/
Lévitation), et les coups posant **météo/terrain/Trick Room**. Recul, drain et
les **objets/talents à déclenchement** (Focus Sash / Fermeté, Baie Sitrus, baies
de résistance de type, Ceinture Force, Ballon, Casque Brut / Peau Dure / Épines
de Fer au contact, Orbe Vie) et le soin de fin de tour du **Champ Herbu** sont
appliqués partout (y compris `rollout`/`sim`).

> Périmètre v1 (assumé, extensible) : Singles ; dégâts déterministes à un roll ;
> effets secondaires probabilistes non modélisés (para 25 %, flinch, gel/dégel…).
> C'est la brique qui débloque la **Phase 4** (recherche multi-tours).

## Recherche à coups simultanés (Phase 4, §10.2)

`simupoke.search.rank_actions` fait le **premier vrai pas** au-delà de
l'heuristique à un tour : elle **simule** chaque combinaison (mon coup × coup
adverse) via le simulateur, **évalue l'état résultant** (`evaluate_state` : K.O.
dominants, différentiel de PV, boosts, statut) et classe mes actions par valeur
**attendue** sur la distribution des coups adverses — en signalant le **pire cas**
(coups simultanés = information imparfaite). La distribution adverse vient des
coups observés, sinon du **set le plus probable** (usage §10.3), sinon adversaire
inactif.

Les **changements** sont des actions à part entière : si un banc est fourni,
chaque switch vers un Pokémon vivant est évalué comme un coup (l'adversaire, qui
joue en même temps, frappe l'entrant) via une évaluation **consciente du banc**
(`evaluate_side`). B1 peut donc recommander un pivot défensif chiffré.

```bash
# Gengar entamé perdant vs Garchomp Choice Band ; le banc a Skarmory (immunisé Sol)
python -m simupoke.cli decide gengar timid shadowball,sludgebomb garchomp jolly \
    --me-hp 0.35 --opp-item choiceband --opp-moves earthquake,stoneedge \
    --bench "skarmory,impish,bravebird ; rotomwash,bold,hydropump"
#   -> 1. → skarmory (attendu -0.16)  ➤ Changer pour skarmory
```

Avec **`--depth ≥2`**, la recherche va **plus loin** : après mon action et la
réponse (stochastique) de l'adversaire, je continue à jouer au mieux sur les
tours suivants (expectimax déterminisé, escompte `GAMMA` par tour pour préférer
les gains proches). Le setup qui ne paie qu'au tour d'après, ou le switch qui
mène à une position gagnante, remontent alors dans le classement.

```bash
python -m simupoke.cli decide garchomp jolly earthquake,swordsdance \
    tyranitar adamant --me-sp atk=32,spe=32 --opp-moves crunch,rockslide --depth 2
```

**Modèle d'adversaire** (`opp_model`, CLI `--cautious`) : `expected` (défaut) traite
les coups adverses comme un **nœud chance** (moyenne) ; `worst` fait de
l'adversaire un joueur qui **répond au mieux contre moi à chaque tour**
(**minimax** / mode prudent). Le classement suit le modèle choisi ; `expected` et
`worst` restent affichés pour chaque action.

```bash
# Mode prudent : face à un Dragapult plus rapide, quelle action limite la casse ?
python -m simupoke.cli decide garchomp jolly earthquake,dragonclaw,swordsdance \
    dragapult timid --opp-moves dracometeor,shadowball --depth 2 --cautious
```

> Bornage : dans la descente, seuls les **coups** sont explorés côté « moi »
> (plus un changement forcé si l'actif tombe K.O.) ; les changements volontaires
> ne sont notés qu'au niveau racine. L'adversaire est agrégé sur ses coups
> probables (son banc n'est pas modélisé). Coût ~ ×10 par tour de profondeur
> (depth 3 ≈ 300 ms) ; `depth` borné à [1, 5]. Exposé aussi par
> `POST /api/decide` (champs `bench`, `depth`, `opp_model`). Ce n'est pas encore
> de l'ISMCTS complet, mais une recherche multi-tours réelle et explicable.

Dans l'**UI hébergée**, l'onglet Combat expose cette recherche : bouton
« Décider (recherche §10.2) », sélecteur de **profondeur** et case **prudent
(pire cas)**, sur les mêmes champs (moi / adverse / banc / terrain).

### Déterminisation du build adverse (ISMCTS-lite, §0.1)

En vrai combat on connaît l'**espèce** adverse, rarement son build. `--samples N`
(ou `rank_actions_sampled`) **échantillonne** N builds adverses plausibles depuis
l'usage — objet, talent, nature et capacités tirés selon leurs distributions
(`usage.sample_set`) — lance la recherche pour chacun et **agrège** les valeurs
par action. La décision devient robuste à l'incertitude sur l'adversaire, au lieu
de parier sur un seul set. Reproductible (graine), respecte l'info déjà observée
(§10.3 : ce qui est renseigné n'est pas ré-échantillonné) et **retombe** sur la
recherche simple si les coups adverses sont connus ou l'usage indisponible.

```bash
# Adversaire dont on ne connaît que l'espèce : moyenne sur 8 builds d'usage
python -m simupoke.cli decide garchomp jolly earthquake,dragonclaw,stoneedge \
    incineroar careful --me-sp atk=32,spe=32 --samples 8
#   -> Adversaire modélisé : échantillonné (8 builds d'usage) ; Earthquake en tête
```

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

### Langue d'affichage (FR/EN, §0.5)

Le français est la langue par défaut ; `--lang en` (n'importe où sur la ligne)
ou `SIMUPOKE_LANG=en` bascule l'affichage en anglais. La bascule est **effective**
(le mode EN affiche « Garchomp », pas « Carchacrok ») : à défaut de traduction,
le libellé est dérivé des données (nom anglais du Pokédex) plutôt que de fuir
vers l'autre langue. Les IDs internes et le moteur ne changent jamais.

```bash
python -m simupoke.cli --lang en stats garchomp jolly 0 32 0 0 0 32
#   -> Garchomp (Jolly) ; HP/Attack/Sp. Atk/…
```

## Import / export « Showdown paste »

`simupoke.showdown` importe une équipe au **format Showdown** (le standard de
partage) et la regénère, en faisant le pont avec Champions : les **EV** du paste
sont convertis en **SP** (§8.3, `SP = round(EV/8)`, plafond 32 ; l'export refait
l'inverse, borné à 252 EV). IV/niveau sont ignorés (31/50 figés) ; le Tera Type
est toléré mais informatif (§4.6).

```bash
# Importer un paste et analyser l'équipe (EV -> SP), ou le sortir en JSON
python -m simupoke.cli paste mon_equipe.txt
python -m simupoke.cli paste mon_equipe.txt --json > data/mon_equipe.json
```

> Exposé par `POST /api/paste` (texte → entrées) et `POST /api/export`
> (entrées → texte) ; l'onglet **Équipe** de l'UI a un champ « Importer un paste
> Showdown » qui remplit l'éditeur.

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
- [x] Seuils & optimiseur de SP : speed tiers + `outspeed`/`survive`/`ko` (CLI + API + onglet).
- [x] Optimiseur de spread complet : objectifs combinés → spread SP légal (`spread`, API, UI).
- [x] Couverture calc étendue : items type-boost, Paradox (Protosynthèse/Charge Quantique), Fluffy/Ice Scales/Water Bubble & co.
- [x] Focus Sash / Fermeté dans les seuils de survie/KO et l'optimiseur de spread.
- [x] B1 — évaluation des changements (switch) : sûreté à l'entrée + menace, reco de pivot.
- [x] B3 — team preview affiné par le vrai calc de dégâts (coups pour KO) + repli types.
- [x] Port `engine.js` : modificateurs avancés dans la page autonome (parité 31/31).
- [x] B1 — coups de soutien évalués : setup (offense débloquée) + statut/protection/soin.
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
- [x] Simulateur de tour (ordre, dégâts, statut/setup/protection, fin de tour) + `rollout`/CLI `sim` — fondation Phase 4.
- [x] Recherche 1-ply à coups simultanés (`rank_actions`/CLI `decide`/API) : valeur attendue + pire cas.
- [x] Changements (switch) dans le simulateur (`simulate_turn_actions`/`Side`) et la recherche (reco de pivot chiffrée).
- [x] B1 — recherche multi-tours (expectimax déterminisé `depth≥2` + escompte) par-dessus le simulateur.
- [x] Déterminisation du build adverse (ISMCTS-lite) : `sample_set` + `rank_actions_sampled` (CLI `--samples`, API).
- [x] Import/export « Showdown paste » (EV ⇄ SP) : `showdown.py`, CLI `paste`, API, import UI.
- [x] Bascule d'affichage FR/EN effective (§0.5) : `i18n.set_language`, CLI `--lang`/`SIMUPOKE_LANG`.
- [ ] Effets secondaires probabilistes (para 25 %, flinch, gel/dégel) dans le simulateur.
- [ ] Déterminisations profondes (ré-échantillonnage par nœud) + budget temps — vers l'ISMCTS complet.
- [ ] Doubles (Phase 5) ; apprentissage optionnel (Phase 6).
