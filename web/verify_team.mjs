/* Parité du port JS de l'analyse d'équipe (web/team.js) contre src/simupoke/team.py
 * sur data/sample_team.json.  node web/verify_team.mjs */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const require = createRequire(import.meta.url);
const SimuEngine = require(join(__dirname, 'engine.js'));
const SimuTeam = require(join(__dirname, 'team.js'));

const pokedex = JSON.parse(readFileSync(join(ROOT, 'data/pokedex.json'))).species;
const moves = JSON.parse(readFileSync(join(ROOT, 'data/moves.json'))).moves;
const typechart = JSON.parse(readFileSync(join(ROOT, 'data/typechart.json'))).chart;

const E = SimuEngine.makeEngine({ pokedex, moves, typechart, ateMap: {} });
const T = SimuTeam.makeTeam(E);

const team = JSON.parse(readFileSync(join(ROOT, 'data/sample_team.json'))).team;
const r = T.analyzeTeam(team);

let pass = 0, fail = 0;
const check = (name, got, exp) => {
  const ok = JSON.stringify(got) === JSON.stringify(exp);
  if (ok) pass++; else { fail++; console.log('FAIL', name, 'got', JSON.stringify(got), 'exp', JSON.stringify(exp)); }
};

check('shared', r.sharedWeaknesses, { Ground: 3 });
check('gaps', r.offensiveGaps.slice().sort(), ['Fairy']);
check('roles', r.roles, { sweeper: 2, wall: 2, support: 2 });
check('clauses', r.clauseViolations, []);

console.log(`Parité Équipe JS : ${pass}/${pass + fail} OK`);
process.exit(fail ? 1 : 0);
