// Génère des scénarios de référence avec @smogon/calc pour valider le calc Python.
// EVs choisis multiples de 8 et <= 248 => SP = EV/8 donne des stats identiques.
import { calculate, Generations, Pokemon, Move, Field } from '@smogon/calc';
const gen = Generations.get(9);

const L = 50;
const scen = [];
function add(name, atk, def, mv, fieldOpts) {
  const a = new Pokemon(gen, atk.species, { level: L, nature: atk.nature || 'Serious',
    evs: atk.evs || {}, boosts: atk.boosts || {}, item: atk.item, ability: atk.ability,
    status: atk.status });
  const d = new Pokemon(gen, def.species, { level: L, nature: def.nature || 'Serious',
    evs: def.evs || {}, boosts: def.boosts || {}, item: def.item, ability: def.ability,
    curHP: def.curHP });
  const m = new Move(gen, mv.name, { isCrit: !!mv.crit });
  const f = new Field(fieldOpts || {});
  const r = calculate(gen, a, d, m, f);
  const dmg = Array.isArray(r.damage) ? r.damage : [r.damage];
  scen.push({
    name, move: mv.name, crit: !!mv.crit,
    attacker: { ...atk }, defender: { ...def },
    field: fieldOpts || {},
    a_stats: { atk: a.stats.atk, spa: a.stats.spa },
    d_stats: { def: d.stats.def, spd: d.stats.spd, hp: d.maxHP() },
    min: Math.min(...dmg), max: Math.max(...dmg), rolls: dmg,
  });
}

// 1. STAB + super efficace, physique
add('eq_stab_se', { species: 'Garchomp', nature: 'Adamant', evs: { atk: 248 } },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Earthquake' });
// 2. STAB neutre, physique
add('crunch_stab_neutral', { species: 'Tyranitar', nature: 'Adamant', evs: { atk: 248 } },
  { species: 'Garchomp', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Crunch' });
// 3. STAB peu efficace, physique
add('flareblitz_resisted', { species: 'Incineroar', nature: 'Adamant', evs: { atk: 248 } },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Flare Blitz' });
// 4. Spécial non-STAB, peu efficace
add('fireblast_special', { species: 'Garchomp', nature: 'Modest', evs: { spa: 248 } },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Fire Blast' });
// 5. Coup critique
add('eq_crit', { species: 'Garchomp', nature: 'Adamant', evs: { atk: 248 } },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Earthquake', crit: true });
// 6. Brûlure (attaquant brûlé, physique)
add('eq_burned', { species: 'Garchomp', nature: 'Adamant', evs: { atk: 248 }, status: 'brn' },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Earthquake' });
// 7. Pluie + move Eau (STAB)
add('waterfall_rain', { species: 'Garchomp', nature: 'Adamant', evs: { atk: 248 } },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Waterfall' }, { weather: 'Rain' });
// 8. Choice Band
add('eq_band', { species: 'Garchomp', nature: 'Adamant', evs: { atk: 248 }, item: 'Choice Band' },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Earthquake' });
// 9. Life Orb (spécial)
add('fireblast_lo', { species: 'Garchomp', nature: 'Modest', evs: { spa: 248 }, item: 'Life Orb' },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Fire Blast' }, {});
// 10. Boost +2 attaque
add('eq_plus2', { species: 'Garchomp', nature: 'Adamant', evs: { atk: 248 }, boosts: { atk: 2 } },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Earthquake' });
// 11. Assault Vest (défenseur), spécial
add('fireblast_av', { species: 'Garchomp', nature: 'Modest', evs: { spa: 248 } },
  { species: 'Tyranitar', nature: 'Careful', evs: { hp: 0 }, item: 'Assault Vest' },
  { name: 'Fire Blast' });
// 12. Spread en doubles
add('eq_spread', { species: 'Garchomp', nature: 'Adamant', evs: { atk: 248 } },
  { species: 'Tyranitar', nature: 'Jolly', evs: { hp: 0 } }, { name: 'Earthquake' },
  { gameType: 'Doubles' });
// 13. Thick Fat (défenseur), spécial Feu
add('thickfat_fireblast', { species: 'Garchomp', nature: 'Modest', evs: { spa: 248 } },
  { species: 'Snorlax', nature: 'Careful', evs: { hp: 0 }, ability: 'Thick Fat' },
  { name: 'Fire Blast' });
// 14. Thick Fat, physique Glace
add('thickfat_ice', { species: 'Mamoswine', nature: 'Adamant', evs: { atk: 248 } },
  { species: 'Snorlax', nature: 'Impish', evs: { hp: 0 }, ability: 'Thick Fat' },
  { name: 'Icicle Crash' });
// 15. Immunité de talent : Lévitation
add('levitate_eq', { species: 'Garchomp', nature: 'Adamant', evs: { atk: 248 } },
  { species: 'Rotom-Wash', ability: 'Levitate' }, { name: 'Earthquake' });
// 16. Immunité de talent : Torche (Flash Fire)
add('flashfire', { species: 'Garchomp', nature: 'Modest', evs: { spa: 248 } },
  { species: 'Heatran', ability: 'Flash Fire' }, { name: 'Fire Blast' });

console.log(JSON.stringify(scen, null, 1));
