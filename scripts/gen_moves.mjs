// Génère data/moves.json et data/typechart.json depuis @pkmn/dex (§12).
// Étape hors-ligne (npm) ; le runtime ne lit que les JSON produits.
//
// Usage : cd scripts && npm install && node gen_moves.mjs

import { Dex } from '@pkmn/dex';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA = join(__dirname, '..', 'data');

// --- Table des types ------------------------------------------------------
// @pkmn encode damageTaken[typeAttaquant] : 0=neutre, 1=faible(2x),
// 2=résiste(0.5x), 3=immunise(0x). On reconstruit chart[atk][def] = multiplicateur.
const CODE_TO_MULT = { 0: 1, 1: 2, 2: 0.5, 3: 0 };
const types = Dex.types.all().map((t) => t.name);
const chart = {};
for (const atk of types) chart[atk] = {};
for (const def of Dex.types.all()) {
  for (const atk of types) {
    const code = def.damageTaken[atk];
    // Certains types (ex. Stellar) n'ont pas d'entrée : neutre par défaut.
    chart[atk][def.name] = code === undefined ? 1 : CODE_TO_MULT[code];
  }
}
writeFileSync(
  join(DATA, 'typechart.json'),
  JSON.stringify(
    {
      _meta: {
        description: 'Table d\'efficacité des types. chart[type_attaquant][type_defenseur] = multiplicateur.',
        source: '@pkmn/dex',
        generated_by: 'scripts/gen_moves.mjs',
      },
      types,
      chart,
    },
    null,
    0,
  ) + '\n',
  'utf8',
);

// --- Moves ----------------------------------------------------------------
// Cibles « de zone » (touchent plusieurs Pokémon) -> pénalité spread en doubles.
const SPREAD_TARGETS = new Set(['allAdjacent', 'allAdjacentFoes']);

const moves = {};
let count = 0;
for (const m of Dex.moves.all()) {
  if (m.isNonstandard === 'CAP' || m.isNonstandard === 'Custom') continue;
  moves[m.id] = {
    name: m.name,
    type: m.type,
    category: m.category, // 'Physical' | 'Special' | 'Status'
    basePower: m.basePower,
    priority: m.priority,
    target: m.target,
    isSpread: SPREAD_TARGETS.has(m.target),
    makesContact: Boolean(m.flags && m.flags.contact),
  };
  count++;
}
writeFileSync(
  join(DATA, 'moves.json'),
  JSON.stringify(
    {
      _meta: {
        description: 'Données de moves (type, catégorie, puissance...).',
        source: '@pkmn/dex',
        generated_by: 'scripts/gen_moves.mjs',
        count,
        note: 'NE PAS éditer à la main. Régénérer via gen_moves.mjs.',
      },
      moves,
    },
    null,
    0,
  ) + '\n',
  'utf8',
);

console.log(`Écrit ${types.length} types et ${count} moves.`);
