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

    return { effectiveSpeed, computeSpeed, speedTiers, minSpToOutspeed, minSpToSurvive, minSpToKo };
  }

  return { makeBench, toId };
});
