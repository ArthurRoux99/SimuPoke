# SimuPoke dans le navigateur (Pyodide)

Le moteur Python **testé** de SimuPoke tourne **côté client** via
[Pyodide](https://pyodide.org) (CPython → WebAssembly) — sans serveur et sans le
port JavaScript `web/engine.js`. Chantier « moteur unique », étapes 1 et 2.

Deux pages (assemblées dans `dist/`) :

| Page | Rôle |
|---|---|
| `index.html` | **Application complète** : le frontend hébergé (`web/server/`) dont les appels `/api/*` sont routés vers le dispatcher Python. Dégâts, Combat (B1), Tirage (B2), Équipe (B3), Team preview, Seuils, Mon Box. |
| `parity.html` | Preuve de parité du moteur de dégâts (navigateur vs valeurs de référence). |

## Lancer

```bash
python scripts/build_pyodide.py                    # assemble web/pyodide/dist/
python -m http.server -d web/pyodide/dist 8123     # http://127.0.0.1:8123
```

## Comment ça marche

- **Une seule source de vérité de routage** : `simupoke.server.dispatch_api`
  route `/api/*` vers les fonctions du moteur — partagé par le serveur HTTP local
  **et** le navigateur. `dispatch_json` en est le pont « tout-chaîne ».
- **`bootstrap.js`** charge Pyodide, monte les données de jeu dans le FS virtuel,
  installe la wheel `simupoke`, puis **détourne `window.fetch`** : chaque `/api/*`
  est exécuté par Python. Le frontend `app.js` fonctionne à l'identique, inchangé.
- **`SIMUPOKE_DATA_DIR`** (voir [`simupoke.paths`](../../src/simupoke/paths.py))
  pointe le moteur vers `/data` avant tout import.
- **`scripts/build_pyodide.py`** construit la wheel, copie les données, la feuille
  de style et `app.js` sous `dist/static/`, compose `dist/index.html` et écrit
  `dist/manifest.json`. `dist/` et `*.whl` sont **gitignorés**.

> **Mon Box** n'est pas embarqué : `my_roster.json` est personnel (§3) et reste
> sur ta machine. Côté navigateur, la box démarre vide ; l'édition tient le temps
> de la session (FS virtuel). La persistance par navigateur (IndexedDB) viendra
> avec l'empaquetage **PWA**.

## Vérifié

Chargé en navigateur : Pyodide (Python 3.12), **1416 espèces** via `/api/meta`,
calc de dégâts, recherche B1 (`/api/decide`), tirage B2, équipe et team preview
B3 — tous `200`, côté client. Parité 4/4 sur `parity.html`.

## Suite

Frontend React/TypeScript + empaquetage **PWA** (installable iOS, hors-ligne
après mise en cache de Pyodide + wheel + données), puis retrait de `engine.js`.
