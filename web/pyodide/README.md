# PoC Pyodide — le moteur Python dans le navigateur

Preuve de concept de l'**étape 1 du chantier « moteur unique »** : faire tourner
le paquet Python `simupoke` (déjà testé) **côté client** via
[Pyodide](https://pyodide.org) (CPython compilé en WebAssembly), sans le port
JavaScript `web/engine.js`.

## Lancer

```bash
python scripts/build_pyodide.py            # assemble web/pyodide/dist/
python -m http.server -d web/pyodide/dist 8123
# puis ouvrir http://127.0.0.1:8123
```

La page charge Pyodide (jsDelivr), monte les données de jeu dans le FS virtuel,
installe la wheel `simupoke`, exécute le calculateur de dégâts sur des scénarios
de référence et **vérifie la parité** avec les valeurs produites côté dépôt
(4/4 attendu).

## Comment ça marche

- `scripts/build_pyodide.py` construit la wheel pure-Python (`pip wheel`), copie
  les données requises sous `dist/data/`, la page sous `dist/`, et écrit
  `dist/manifest.json` (wheel + liste des fichiers data).
- La page pointe `SIMUPOKE_DATA_DIR` vers `/data` **avant** d'importer
  `simupoke` — mécanisme fourni par [`simupoke.paths`](../../src/simupoke/paths.py),
  qui rend le dossier de données surchargeable (indispensable hors dépôt).
- `dist/` et `*.whl` sont **gitignorés** : seuls cette page, le script de build
  et le README sont versionnés.

## Ce que ça prouve / la suite

Le moteur testé (source de vérité unique) s'exécute à l'identique dans le
navigateur → **le port `engine.js` pourra être retiré**. Prochaines étapes du
chantier : exposer B1/B2/B3 + la recherche via le même pont, puis frontend
React/TypeScript et empaquetage **PWA** (installable, hors-ligne après mise en
cache de Pyodide + wheel + données).
