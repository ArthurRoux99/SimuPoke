// Génère data/pokedex.json à partir de @pkmn/dex (source nommée au §12 du
// document socle). Étape de génération qui nécessite le réseau (npm) ; le
// runtime du projet reste 100 % hors-ligne et lit le JSON produit.
//
// Usage :
//   cd scripts && npm install && node gen_pokedex.mjs
//
// Les IDs de sortie sont les IDs Showdown (minuscule, alphanumérique), alignés
// sur les conventions internes du projet (§0.5). Les formes Méga sont incluses
// sous leur propre ID (ex. "tyranitarmega"), avec leurs base stats propres.

import { Dex } from '@pkmn/dex';
import { writeFileSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..');
const OUT_PATH = join(REPO_ROOT, 'data', 'pokedex.json');

// On exclut les espèces non canoniques (fakemons CAP / Custom). On garde le
// reste — y compris isNonstandard "Past", car les Méga y figurent et sont
// jouables dans Champions (régulations M-A / M-B, §4.6).
const EXCLUDE_NONSTANDARD = new Set(['CAP', 'Custom']);

function dexVersion() {
  try {
    const pkg = JSON.parse(
      readFileSync(join(__dirname, 'node_modules', '@pkmn', 'dex', 'package.json'), 'utf8'),
    );
    return pkg.version;
  } catch {
    return 'unknown';
  }
}

const species = {};
let count = 0;
for (const s of Dex.species.all()) {
  if (s.isNonstandard && EXCLUDE_NONSTANDARD.has(s.isNonstandard)) continue;
  if (!s.baseStats) continue;
  species[s.id] = {
    num: s.num,
    name: s.name,
    types: s.types,
    baseStats: {
      hp: s.baseStats.hp,
      atk: s.baseStats.atk,
      def: s.baseStats.def,
      spa: s.baseStats.spa,
      spd: s.baseStats.spd,
      spe: s.baseStats.spe,
    },
    abilities: Object.values(s.abilities ?? {}),
    baseSpecies: s.baseSpecies,
    forme: s.forme || null,
    isNonstandard: s.isNonstandard ?? null,
  };
  count++;
}

const out = {
  _meta: {
    description: 'Base stats + métadonnées d\'espèces, généré depuis @pkmn/dex.',
    source: '@pkmn/dex',
    dex_version: dexVersion(),
    generated_by: 'scripts/gen_pokedex.mjs',
    count,
    note: 'NE PAS éditer à la main. Régénérer via `cd scripts && npm install && node gen_pokedex.mjs`.',
  },
  species,
};

writeFileSync(OUT_PATH, JSON.stringify(out, null, 0) + '\n', 'utf8');
console.log(`Écrit ${count} espèces dans ${OUT_PATH}`);
