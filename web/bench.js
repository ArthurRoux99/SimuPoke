/* SimuPoke — Seuils & optimiseur de SP (port JS de src/simupoke/bench.py).
 *
 * Construit au-dessus du moteur (engine.js) : mêmes réponses que le cœur Python
 * (vérifié par parité). Utilisable navigateur (window.SimuBench) et Node.
 */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = mod;
  else root.SimuBench = mod;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const CAP = 32;
  const toId = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const boostMult = (st) => (st >= 0 ? (2 + st) / 2 : 2 / (2 - st));

  function makeBench(engine) {
    // --- Vitesse effective (base + boosts + Scarf + paralysie), Tailwind en option
    function effectiveSpeed(state) {
      let spe = engine.battleStats(state).spe;
      spe = Math.floor(spe * boostMult((state.boosts && state.boosts.spe) || 0));
      if (toId(state.item) === 'choicescarf') spe = Math.floor(spe * 1.5);
      if (state.status === 'par') spe = Math.floor(spe * 0.5);
      return spe;
    }
    function computeSpeed(state, tailwind) {
      const s = effectiveSpeed(state);
      return tailwind ? s * 2 : s;
    }
    const withSp = (state, key, v) =>
      Object.assign({}, state, { sp: Object.assign({}, state.sp, { [key]: v }) });

    function speedNotes(state, tailwind) {
      const n = [];
      if (toId(state.item) === 'choicescarf') n.push('Choice Scarf');
      if (tailwind) n.push('Tailwind');
      if (state.status === 'par') n.push('paralysé');
      const b = (state.boosts && state.boosts.spe) || 0;
      if (b) n.push('Vit ' + (b > 0 ? '+' : '') + b);
      return n;
    }
    function speedTiers(states, opts) {
      opts = opts || {};
      const tw = opts.tailwinds || states.map(() => false);
      const trickRoom = !!opts.trickRoom;
      const rows = states.map((s, i) => ({
        species: s.species, speed: computeSpeed(s, tw[i]), notes: speedNotes(s, tw[i]),
      }));
      rows.sort((a, b) => (trickRoom ? a.speed - b.speed : b.speed - a.speed));
      return rows;
    }

    function minSpToOutspeed(me, target, opts) {
      opts = opts || {};
      const strict = opts.strict !== false;
      const targetSpeed = computeSpeed(target, opts.targetTailwind);
      let best = -1, ties = false;
      for (let sp = 0; sp <= CAP; sp++) {
        const s = computeSpeed(withSp(me, 'spe', sp), opts.meTailwind);
        best = s;
        if (s > targetSpeed || (!strict && s >= targetSpeed)) {
          return { feasible: true, sp, mySpeed: s, targetSpeed, tiesOnly: s === targetSpeed };
        }
        if (s === targetSpeed) ties = true;
      }
      return { feasible: false, sp: null, mySpeed: best, targetSpeed, tiesOnly: ties };
    }

    function endures(state) {
      const full = (state.hpPct === undefined ? 1 : state.hpPct) >= 1;
      return full && (toId(state.item) === 'focussash' || toId(state.ability) === 'sturdy');
    }

    function minSpToSurvive(defender, attacker, move, field, opts) {
      opts = opts || {};
      const m = engine.move(move);
      const stat = m.category === 'Physical' ? 'def' : 'spd';
      const base = Object.assign({}, defender, { hpPct: 1 });
      if (endures(base)) return { feasible: true, hpSp: 0, defSp: 0, totalSp: 0, stat, byEndure: true, move: m.name };
      for (let total = 0; total <= 2 * CAP; total++) {
        const lo = Math.max(0, total - CAP), hi = Math.min(CAP, total);
        for (let hp = lo; hp <= hi; hp++) {
          const dsp = total - hp;
          const trial = Object.assign({}, base, { sp: Object.assign({}, base.sp, { hp, [stat]: dsp }) });
          const r = engine.calculate(attacker, trial, move, field, { crit: !!opts.crit, screen: opts.screen });
          if (r.max < r.maxHp) return { feasible: true, hpSp: hp, defSp: dsp, totalSp: total, stat, maxPct: r.maxPct, move: m.name };
        }
      }
      return { feasible: false, stat, move: m.name };
    }

    function effectiveKoHits(raw, end) {
      if (raw == null) return null;
      return (end && raw === 1) ? 2 : raw;
    }
    function minSpToKo(attacker, defender, move, field, opts) {
      opts = opts || {};
      const hits = opts.hits || 1;
      const m = engine.move(move);
      const stat = m.category === 'Physical' ? 'atk' : 'spa';
      const end = endures(defender);
      for (let sp = 0; sp <= CAP; sp++) {
        const trial = withSp(attacker, stat, sp);
        const r = engine.calculate(trial, defender, move, field, { crit: !!opts.crit });
        const g = effectiveKoHits(r.koGuaranteed, end);
        if (g != null && g <= hits) return { feasible: true, sp, stat, hits, minPct: r.minPct, move: m.name };
      }
      return { feasible: false, sp: null, stat, hits, blockedByEndure: end && hits < 2, move: m.name };
    }

    // --- Optimiseur de spread (port de optimize.py) ---
    function minDefGivenHp(meDef, obj, hp, defKey) {
      for (let dsp = 0; dsp <= CAP; dsp++) {
        const trial = Object.assign({}, meDef, { hpPct: 1, sp: Object.assign({}, meDef.sp, { hp, [defKey]: dsp }) });
        const r = engine.calculate(obj.attacker, trial, obj.move, obj.field || {}, { crit: !!obj.crit });
        if (r.max < r.maxHp) return dsp;
      }
      return null;
    }
    function solveDefense(meDef, survives) {
      const phys = survives.filter((o) => engine.move(o.move).category === 'Physical');
      const spec = survives.filter((o) => engine.move(o.move).category !== 'Physical');
      if (!phys.length && !spec.length) return { hp: 0, def: 0, spd: 0 };
      let best = null;
      for (let hp = 0; hp <= CAP; hp++) {
        let defNeed = 0, spdNeed = 0;
        for (const o of phys) defNeed = Math.max(defNeed, minDefGivenHp(meDef, o, hp, 'def') || 0);
        for (const o of spec) spdNeed = Math.max(spdNeed, minDefGivenHp(meDef, o, hp, 'spd') || 0);
        const total = hp + defNeed + spdNeed;
        if (best === null || total < best.total) best = { total, hp, def: defNeed, spd: spdNeed };
      }
      return best;
    }
    function optimizeSpread(species, nature, objectives, opts) {
      opts = opts || {};
      const budget = opts.budget || 66;
      const item = opts.item || null, ability = opts.ability || null;
      const me = (extra) => Object.assign({ species, nature, item, ability, sp: {} }, extra || {});
      const sp = { hp: 0, atk: 0, def: 0, spa: 0, spd: 0, spe: 0 };
      const unmet = [];
      const outs = objectives.filter((o) => o.kind === 'outspeed');
      const kos = objectives.filter((o) => o.kind === 'ko');
      const survives = objectives.filter((o) => o.kind === 'survive');

      for (const o of outs) {
        const r = minSpToOutspeed(me(), o.target, { strict: o.strict !== false, meTailwind: o.meTailwind, targetTailwind: o.targetTailwind });
        if (!r.feasible) unmet.push('dépasser ' + (o.label || o.target.species) + ' : hors de portée (vitesse)');
        else sp.spe = Math.max(sp.spe, r.sp);
      }
      for (const o of kos) {
        const r = minSpToKo(me(), o.defender, o.move, o.field || {}, { hits: o.hits || 1, crit: o.crit });
        const tag = o.label || (o.move + ' sur ' + o.defender.species);
        if (!r.feasible) unmet.push('KO ' + tag + ' : ' + (r.blockedByEndure ? 'bloqué par Focus Sash / Fermeté' : 'hors de portée (>' + CAP + ' SP ' + r.stat + ')'));
        else sp[r.stat] = Math.max(sp[r.stat], r.sp);
      }
      const meDef = me();
      const okSurv = [];
      for (const o of survives) {
        const chk = minSpToSurvive(meDef, o.attacker, o.move, o.field || {}, { crit: o.crit });
        if (!chk.feasible) unmet.push('survivre à ' + (o.label || (o.move + ' de ' + o.attacker.species)) + ' : hors de portée (même à fond)');
        else okSurv.push(o);
      }
      const d = solveDefense(meDef, okSurv);
      sp.hp = d.hp; sp.def = d.def; sp.spd = d.spd;

      const total = sp.hp + sp.atk + sp.def + sp.spa + sp.spd + sp.spe;
      if (total > budget) unmet.push('budget dépassé : ' + total + ' SP requis > ' + budget);
      let stats = null;
      try { stats = engine.battleStats({ species, nature, sp }); } catch (e) { stats = null; }
      return { feasible: unmet.length === 0, sp, total, budget, leftover: budget - total, stats, unmet };
    }

    return { effectiveSpeed, computeSpeed, speedTiers, minSpToOutspeed, minSpToSurvive, minSpToKo, optimizeSpread };
  }

  return { makeBench, toId };
});
