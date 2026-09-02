# SimuPoke — instructions projet

Outil **hors-ligne** d'aide à la décision pour **Pokémon Champions**, à saisie
manuelle. C'est un calculateur / conseiller (comme un *damage calc* ou un *team
builder* communautaire) qui ne communique **jamais** avec le jeu. Document de
conception : [`docs/conception_socle.md`](docs/conception_socle.md).

## Invariants — à ne jamais casser

1. **Hors-ligne (§3).** Le runtime ne fait **aucune requête réseau**. Les
   données de jeu sont figées dans des JSON versionnés (`data/`). N'ajoute
   jamais d'appel réseau dans le chemin d'exécution de l'outil. Seuls les
   scripts *hors-ligne* (`scripts/gen_*.mjs`, `simupoke.usage_import`) touchent
   au réseau, et uniquement pour régénérer des données, jamais au runtime.

2. **Source de vérité unique = Python.** Toute la logique de jeu vit dans
   `src/simupoke/` et est testée (`tests/`). Le calc est vérifié en **parité
   contre `@smogon/calc`**.

3. **Le port JS doit rester à parité.** `web/engine.js` (+ `web/team.js`,
   la logique de seuils) est un **port manuel** de Python. Toute modif de
   `damage.py` / `team.py` / `bench.py` doit être répercutée côté JS **et** les
   scripts de parité doivent rester verts :
   ```bash
   node web/verify_engine.mjs   # calc de dégâts
   node web/verify_bench.mjs    # seuils
   node web/verify_team.mjs     # analyse d'équipe
   ```
   > Cette double-maintenance est une dette **destinée à disparaître** (bascule
   > Pyodide au programme, cf. feuille de route). En attendant, ne laisse pas
   > diverger les deux moteurs.

4. **Les deltas Champions sont pilotés par les données.** Les talents custom
   (familles -ate, Dragonize, Mega Sol…) se branchent via
   `data/<reg>/abilities.json`, pas en dur dans le moteur. Ajouter un talent =
   opération de **données** quand c'est possible.

5. **Les données de base sont générées, pas éditées à la main.**
   `data/pokedex.json`, `data/moves.json`, `data/typechart.json` proviennent de
   `@pkmn/dex` via `scripts/gen_*.mjs`. Ne les édite pas manuellement ;
   régénère.

6. **`data/my_roster.json` est personnel.** Il n'est **jamais** embarqué dans la
   page publiée (`scripts/build_web.py` l'exclut déjà) et le dépôt est public —
   ne l'inline nulle part dans un livrable distribuable.

7. **Conventions.** IDs internes en **anglais** (style Showdown), affichage
   **FR par défaut** (couche `i18n`), bascule EN. Architecture pensée **Doubles**
   dès le départ (`SideState.active` est une liste).

## Commandes

```bash
# Installation (mode dev) + tests. pyproject fixe pythonpath=src, donc `pytest` suffit.
pip install -e ".[dev]"
pytest                       # 116+ tests (le vrai gate ; la CI le rejoue sur chaque PR)

# Sans installer : PYTHONPATH=src python -m simupoke.cli ...  /  PYTHONPATH=src pytest

# CLI (sous-commandes) :
python -m simupoke.cli roster|stats|damage|draft|team|preview|analyze
python -m simupoke.cli speed|outspeed|survive|ko|spread     # seuils & optimiseur de SP
python -m simupoke.cli sim|decide                           # simulateur + recherche (Phase 4)
python -m simupoke.cli paste                                # import/export Showdown paste

# UI — page HTML autonome (hors-ligne, un seul fichier) :
python scripts/build_web.py            # -> web/dist/simupoke.html (gitignoré ; la CI Pages le régénère)

# UI — serveur local (tous les modules via API Python) :
python -m simupoke.server              # http://127.0.0.1:8000

# Régénérer les données (hors-ligne, via npm) :
cd scripts && npm install && npm run gen:all
```

## Dépôt & CI

- Branche par défaut **`main`** ; dépôt **public** (`ArthurRoux99/SimuPoke`).
- **La CI `tests` (pytest) doit être verte** avant toute fusion. Un push sur
  `main` republie automatiquement la page autonome sur **GitHub Pages**
  (`.github/workflows/pages.yml`).
- Travail depuis l'app iOS / cloud : **via branches + PR** vers `main`, jamais
  de commit qui casse la CI.

## Feuille de route

Phases 0–3 ✅, Phase 4 🟡 (simulateur + recherche multi-tours ; **ISMCTS
complet** à venir), Phase 5 Doubles ⏳, Phase 6 apprentissage ⏳. Cap technique :
**moteur unique via Pyodide** (retire le port JS), **frontend PWA** (React/TS),
profondeur IA (ISMCTS, Doubles). Le tableau d'état détaillé est en tête du
[README](README.md).
