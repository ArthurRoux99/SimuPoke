/* Vérifie la parité du moteur JS (web/engine.js) contre les mêmes vecteurs que
 * le moteur Python (tests/test_damage.py), eux-mêmes calés sur @smogon/calc.
 *   node web/verify_engine.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const require = createRequire(import.meta.url);
const SimuEngine = require(join(__dirname, 'engine.js'));

const pokedex = JSON.parse(readFileSync(join(ROOT, 'data/pokedex.json'))).species;
const moves = JSON.parse(readFileSync(join(ROOT, 'data/moves.json'))).moves;
const typechart = JSON.parse(readFileSync(join(ROOT, 'data/typechart.json'))).chart;
const ab = JSON.parse(readFileSync(join(ROOT, 'data/reg_m_b/abilities.json'))).abilities;
const ateMap = {};
for (const a of ab) { const p = a.params || {}; if (p.from_type === 'Normal' && p.to_type) ateMap[a.id] = p.to_type; }

const E = SimuEngine.makeEngine({ pokedex, moves, typechart, ateMap });
const mk = (species, nature = 'serious', sp = {}, x = {}) => ({ species, nature, sp, ...x });

const cases = [
  ['eq_stab_se', mk('garchomp', 'adamant', { atk: 31 }), mk('tyranitar', 'jolly'), 'earthquake', {}, 174, 206],
  ['crunch', mk('tyranitar', 'adamant', { atk: 31 }), mk('garchomp', 'jolly'), 'crunch', {}, 81, 96],
  ['flareblitz', mk('incineroar', 'adamant', { atk: 31 }), mk('tyranitar', 'jolly'), 'flareblitz', {}, 47, 56],
  ['fireblast', mk('garchomp', 'modest', { spa: 31 }), mk('tyranitar', 'jolly'), 'fireblast', {}, 25, 30],
  ['eq_crit', mk('garchomp', 'adamant', { atk: 31 }), mk('tyranitar', 'jolly'), 'earthquake', { crit: true }, 260, 308],
  ['eq_burned', mk('garchomp', 'adamant', { atk: 31 }, { status: 'brn' }), mk('tyranitar', 'jolly'), 'earthquake', {}, 87, 103],
  ['waterfall_rain', mk('garchomp', 'adamant', { atk: 31 }), mk('tyranitar', 'jolly'), 'waterfall', { field: { weather: 'rain' } }, 138, 164],
  ['eq_band', mk('garchomp', 'adamant', { atk: 31 }, { item: 'choiceband' }), mk('tyranitar', 'jolly'), 'earthquake', {}, 258, 306],
  ['fireblast_lo', mk('garchomp', 'modest', { spa: 31 }, { item: 'lifeorb' }), mk('tyranitar', 'jolly'), 'fireblast', {}, 32, 39],
  ['eq_plus2', mk('garchomp', 'adamant', { atk: 31 }, { boosts: { atk: 2 } }), mk('tyranitar', 'jolly'), 'earthquake', {}, 344, 408],
  ['fireblast_av', mk('garchomp', 'modest', { spa: 31 }), mk('tyranitar', 'careful', {}, { item: 'assaultvest' }), 'fireblast', {}, 15, 18],
  ['eq_spread', mk('garchomp', 'adamant', { atk: 31 }), mk('tyranitar', 'jolly'), 'earthquake', { applySpread: true }, 132, 156],
  ['thickfat_fb', mk('garchomp', 'modest', { spa: 31 }), mk('snorlax', 'careful', {}, { ability: 'thickfat' }), 'fireblast', {}, 22, 26],
  ['thickfat_ice', mk('mamoswine', 'adamant', { atk: 31 }), mk('snorlax', 'impish', {}, { ability: 'thickfat' }), 'iciclecrash', {}, 51, 61],
  ['levitate', mk('garchomp', 'adamant', { atk: 31 }), mk('rotomwash', 'serious', {}, { ability: 'levitate' }), 'earthquake', {}, 0, 0],
  ['flashfire', mk('garchomp', 'modest', { spa: 31 }), mk('heatran', 'serious', {}, { ability: 'flashfire' }), 'fireblast', {}, 0, 0],
  ['pixilate', mk('sylveon', 'modest', { spa: 31 }, { ability: 'pixilate' }), mk('garchomp', 'jolly'), 'hypervoice', {}, 206, 246],
  ['plain_hv', mk('sylveon', 'modest', { spa: 31 }, { ability: 'cutecharm' }), mk('garchomp', 'jolly'), 'hypervoice', {}, 57, 68],
  // Couverture étendue (valeurs de référence issues du moteur Python).
  ['charcoal', mk('charizard', 'modest', { spa: 31 }, { item: 'charcoal' }), mk('venusaur', 'bold'), 'flamethrower', {}, 180, 212],
  ['muscleband', mk('garchomp', 'adamant', { atk: 31 }, { item: 'muscleband' }), mk('snorlax', 'careful'), 'earthquake', {}, 145, 172],
  ['wiseglasses', mk('charizard', 'modest', { spa: 31 }, { item: 'wiseglasses' }), mk('venusaur', 'bold'), 'flamethrower', {}, 164, 194],
  ['waterbubble_off', mk('azumarill', 'modest', { spa: 31 }, { ability: 'waterbubble' }), mk('blissey', 'calm'), 'hydropump', {}, 90, 106],
  ['transistor', mk('pikachu', 'timid', { spa: 31 }, { ability: 'transistor' }), mk('snorlax', 'careful'), 'thunderbolt', {}, 48, 57],
  ['proto_sun', mk('roaringmoon', 'adamant', { atk: 31 }, { ability: 'protosynthesis' }), mk('garchomp', 'jolly'), 'crunch', { field: { weather: 'sun' } }, 108, 127],
  ['proto_booster', mk('roaringmoon', 'adamant', { atk: 31 }, { ability: 'protosynthesis', item: 'boosterenergy' }), mk('garchomp', 'jolly'), 'crunch', {}, 108, 127],
  ['sandforce', mk('excadrill', 'adamant', { atk: 31 }, { ability: 'sandforce' }), mk('tyranitar', 'jolly'), 'earthquake', { field: { weather: 'sand' } }, 230, 272],
  ['fluffy_fire', mk('charizard', 'modest', { spa: 31 }), mk('snorlax', 'careful', {}, { ability: 'fluffy' }), 'flamethrower', {}, 126, 150],
  ['fluffy_contact', mk('machamp', 'adamant', { atk: 31 }), mk('snorlax', 'careful', {}, { ability: 'fluffy' }), 'closecombat', {}, 159, 187],
  ['icescales', mk('charizard', 'modest', { spa: 31 }), mk('blissey', 'calm', {}, { ability: 'icescales' }), 'airslash', {}, 22, 27],
  ['dryskin_fire', mk('charizard', 'modest', { spa: 31 }), mk('snorlax', 'careful', {}, { ability: 'dryskin' }), 'flamethrower', {}, 79, 94],
  ['purifyingsalt', mk('gengar', 'modest', { spa: 31 }), mk('garchomp', 'careful', {}, { ability: 'purifyingsalt' }), 'shadowball', {}, 39, 46],
  ['eq_band_reflect', mk('garchomp', 'adamant', { atk: 31 }, { item: 'choiceband' }), mk('tyranitar', 'jolly'), 'earthquake', { screen: 'reflect' }, 129, 153],
  ['fireblast_lightscreen', mk('charizard', 'modest', { spa: 31 }), mk('tyranitar', 'jolly'), 'fireblast', { screen: 'lightscreen' }, 22, 27],
];

let pass = 0, fail = 0;
for (const [name, a, d, mv, opts, emin, emax] of cases) {
  const r = E.calculate(a, d, mv, opts.field, { crit: opts.crit, applySpread: opts.applySpread, screen: opts.screen });
  if (r.min === emin && r.max === emax) pass++;
  else { fail++; console.log('FAIL', name, 'got', r.min, r.max, 'exp', emin, emax); }
}
console.log(`Parité JS : ${pass}/${pass + fail} OK`);
process.exit(fail ? 1 : 0);
