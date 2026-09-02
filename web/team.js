/* SimuPoke — Analyse de types/rôles + B3 analyse d'équipe (port JS de
 * src/simupoke/analysis.py + team.py, volet analyze_team). Au-dessus du moteur
 * (engine.js). Utilisable navigateur (window.SimuTeam) et Node (parité). */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = mod;
  else root.SimuTeam = mod;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const STANDARD_TYPES = ['Bug', 'Dark', 'Dragon', 'Electric', 'Fairy', 'Fighting',
    'Fire', 'Flying', 'Ghost', 'Grass', 'Ground', 'Ice', 'Normal', 'Poison',
    'Psychic', 'Rock', 'Steel', 'Water'];
  const ABILITY_IMMUNITY = {
    levitate: 'Ground', eartheater: 'Ground', flashfire: 'Fire',
    voltabsorb: 'Electric', lightningrod: 'Electric', motordrive: 'Electric',
    waterabsorb: 'Water', stormdrain: 'Water', dryskin: 'Water', sapsipper: 'Grass',
  };
  const toId = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const ROLE_FR = { sweeper: 'Sweeper', wall: 'Mur', pivot: 'Pivot', support: 'Support' };
  const clamp = (x) => Math.max(0, Math.min(1, x));

  function makeTeam(engine) {
    const types = (sp) => (engine.species(sp).types || []);
    const bs = (sp) => engine.species(sp).baseStats;

    function defensiveWeaknesses(species, ability) {
      const t = types(species);
      const immune = ability ? ABILITY_IMMUNITY[toId(ability)] : null;
      const weak = {};
      for (const atk of STANDARD_TYPES) {
        if (atk === immune) continue;
        const m = engine.effectiveness(atk, t);
        if (m > 1) weak[atk] = m;
      }
      return weak;
    }
    function offensiveTypes(species, moves) {
      const out = [];
      for (const mid of (moves || [])) {
        let m; try { m = engine.move(mid); } catch (e) { continue; }
        if (m.category !== 'Status' && m.basePower > 0 && out.indexOf(m.type) < 0) out.push(m.type);
      }
      return out.length ? out : types(species).slice();
    }
    function statusRatio(moves) {
      const known = [];
      for (const mid of (moves || [])) { try { known.push(engine.move(mid)); } catch (e) { /* */ } }
      if (!known.length) return 0;
      return known.filter((m) => m.category === 'Status').length / known.length;
    }
    function inferRole(species, moves) {
      const b = bs(species);
      const nOff = clamp((Math.max(b.atk, b.spa) - 60) / 70);
      const nSpe = clamp((b.spe - 50) / 70);
      const nHp = clamp((b.hp - 50) / 60);
      const nDef = clamp(((b.def + b.spd) / 2 - 60) / 70);
      const nSup = statusRatio(moves);
      const scores = {
        sweeper: nOff * nSpe,
        wall: nHp * nDef * (1 - nSpe),
        pivot: nHp * nDef * nOff,
        support: nSup * (0.5 + 0.5 * nDef),
      };
      let role = 'sweeper';
      for (const k of Object.keys(scores)) if (scores[k] > scores[role]) role = k;
      return { role, labelFr: ROLE_FR[role] };
    }

    function teamSharedWeaknesses(team) {
      const known = team.filter((m) => m.species);
      if (!known.length) return {};
      const threshold = Math.ceil(known.length / 2);
      const counts = {};
      for (const atk of STANDARD_TYPES) {
        let n = 0;
        for (const m of known) if (defensiveWeaknesses(m.species, m.ability)[atk]) n++;
        if (n >= threshold) counts[atk] = n;
      }
      return counts;
    }
    function teamOffensiveGaps(team) {
      const atkTypes = new Set();
      for (const m of team) for (const t of offensiveTypes(m.species, m.moves)) atkTypes.add(t);
      const gaps = [];
      for (const d of STANDARD_TYPES) {
        let hit = false;
        for (const a of atkTypes) if (engine.effectiveness(a, [d]) > 1) { hit = true; break; }
        if (!hit) gaps.push(d);
      }
      return gaps;
    }
    function roleDistribution(team) {
      const dist = {};
      for (const m of team) { const r = inferRole(m.species, m.moves).role; dist[r] = (dist[r] || 0) + 1; }
      return dist;
    }
    function checkClauses(team) {
      const v = [];
      const seenNum = {};
      for (const m of team) {
        const num = engine.species(m.species).num;
        if (num in seenNum && seenNum[num] !== m.species) v.push(`Species Clause : ${seenNum[num]} et ${m.species} (même n° ${num})`);
        else if (num in seenNum) v.push(`Species Clause : ${m.species} en double`);
        else seenNum[num] = m.species;
      }
      const seenItem = new Set();
      for (const m of team) {
        const it = m.item ? toId(m.item) : null;
        if (it) { if (seenItem.has(it)) v.push(`Item Clause : ${it} tenu plusieurs fois`); seenItem.add(it); }
      }
      return v;
    }
    function analyzeTeam(team) {
      const t = team.filter((m) => m.species);
      return {
        size: t.length,
        sharedWeaknesses: teamSharedWeaknesses(t),
        offensiveGaps: teamOffensiveGaps(t),
        roles: roleDistribution(t),
        clauseViolations: checkClauses(t),
      };
    }

    return { defensiveWeaknesses, offensiveTypes, inferRole, teamSharedWeaknesses,
      teamOffensiveGaps, roleDistribution, checkClauses, analyzeTeam, ROLE_FR };
  }

  return { makeTeam };
});
