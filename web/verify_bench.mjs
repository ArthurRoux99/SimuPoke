/* Vérifie la parité du port JS des Seuils (web/bench.js) contre le cœur Python
 * (src/simupoke/bench.py). Valeurs de référence générées depuis Python.
 *   node web/verify_bench.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const require = createRequire(import.meta.url);
const SimuEngine = require(join(__dirname, 'engine.js'));
const SimuBench = require(join(__dirname, 'bench.js'));

const pokedex = JSON.parse(readFileSync(join(ROOT, 'data/pokedex.json'))).species;
const moves = JSON.parse(readFileSync(join(ROOT, 'data/moves.json'))).moves;
const typechart = JSON.parse(readFileSync(join(ROOT, 'data/typechart.json'))).chart;
const ab = JSON.parse(readFileSync(join(ROOT, 'data/reg_m_b/abilities.json'))).abilities;
const ateMap = {};
for (const a of ab) { const p = a.params || {}; if (p.from_type === 'Normal' && p.to_type) ateMap[a.id] = p.to_type; }

const E = SimuEngine.makeEngine({ pokedex, moves, typechart, ateMap });
const B = SimuBench.makeBench(E);
const mk = (species, nature = 'serious', sp = {}, x = {}) => ({ species, nature, sp, ...x });

let pass = 0, fail = 0;
const check = (name, got, exp) => {
  const ok = JSON.stringify(got) === JSON.stringify(exp);
  if (ok) pass++; else { fail++; console.log('FAIL', name, 'got', JSON.stringify(got), 'exp', JSON.stringify(exp)); }
};

// outspeed : garchomp serious vs garchomp serious spe20 -> 21 SP, 143 vs 142
let r = B.minSpToOutspeed(mk('garchomp', 'serious'), mk('garchomp', 'serious', { spe: 20 }));
check('outspeed', [r.feasible, r.sp, r.mySpeed, r.targetSpeed], [true, 21, 143, 142]);

// survive : tyranitar careful vs CB adamant garchomp EQ -> infaisable
r = B.minSpToSurvive(mk('tyranitar', 'careful'), mk('garchomp', 'adamant', { atk: 32 }, { item: 'choiceband' }), 'earthquake');
check('survive_infeasible', [r.feasible, r.stat], [false, 'def']);

// ko : CB adamant garchomp EQ vs tyranitar adamant -> 0 SP atk
r = B.minSpToKo(mk('garchomp', 'adamant', {}, { item: 'choiceband' }), mk('tyranitar', 'adamant'), 'earthquake', null, { hits: 1 });
check('ko', [r.feasible, r.sp, r.stat], [true, 0, 'atk']);

// survive via Focus Sash -> 0 SP, byEndure
r = B.minSpToSurvive(mk('fluttermane', 'timid', { hp: 0 }, { item: 'focussash' }), mk('garchomp', 'adamant', { atk: 32 }, { item: 'choiceband' }), 'earthquake');
check('survive_sash', [r.feasible, r.totalSp, r.byEndure], [true, 0, true]);

// speed tiers ordering + valeurs
const tiers = B.speedTiers([mk('snorlax', 'brave'), mk('garchomp', 'jolly', { spe: 32 })]);
check('tiers', tiers.map((t) => [t.species, t.speed]), [['garchomp', 169], ['snorlax', 45]]);

// optimiseur de spread : Tyranitar OHKO Garchomp (Ice Punch) + survivre Séisme + dépasser Amoonguss
const spr = B.optimizeSpread('tyranitar', 'adamant', [
  { kind: 'ko', defender: mk('garchomp', 'jolly', { spe: 32 }), move: 'icepunch', hits: 1 },
  { kind: 'survive', attacker: mk('garchomp', 'adamant', { atk: 32 }), move: 'earthquake' },
  { kind: 'outspeed', target: mk('amoonguss', 'sassy', { spe: 0 }) },
]);
check('spread', [spr.feasible, spr.sp.hp, spr.sp.atk, spr.sp.def, spr.total],
  [true, 2, 15, 22, 39]);

console.log(`Parité Seuils JS : ${pass}/${pass + fail} OK`);
process.exit(fail ? 1 : 0);
