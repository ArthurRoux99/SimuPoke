/* SimuPoke — moteur de dégâts (port JS fidèle de src/simupoke/damage.py).
 *
 * Formule Génération 5+ : modificateurs chaînés en base 4096, pokeRound,
 * 16 rolls (85..100 %). Delta Champions : famille -ate + Mega Sol.
 * Couvre aussi les items type-boost, Muscle Band/Wise Glasses, Water Bubble,
 * Solar Power, Sand Force, Protosynthèse/Charge Quantique, type-boost (Steelworker
 * & co.) et les talents défensifs (Fluffy, Ice Scales, Sel Purifiant, Peau Sèche).
 *
 * Données attendues dans `data` : { pokedex, moves, typechart, ateMap }.
 * Utilisable côté navigateur (window.SimuEngine) et côté Node (module.exports),
 * pour permettre la vérification de parité contre @smogon/calc.
 */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = mod;
  else root.SimuEngine = mod;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const LEVEL = 50, IV = 31;
  const STAT_KEYS = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];

  // (stat+, stat-) ; null = neutre.
  const NATURES = {
    hardy: [null, null], docile: [null, null], bashful: [null, null],
    quirky: [null, null], serious: [null, null],
    lonely: ['atk', 'def'], brave: ['atk', 'spe'], adamant: ['atk', 'spa'], naughty: ['atk', 'spd'],
    bold: ['def', 'atk'], relaxed: ['def', 'spe'], impish: ['def', 'spa'], lax: ['def', 'spd'],
    modest: ['spa', 'atk'], mild: ['spa', 'def'], quiet: ['spa', 'spe'], rash: ['spa', 'spd'],
    calm: ['spd', 'atk'], gentle: ['spd', 'def'], sassy: ['spd', 'spe'], careful: ['spd', 'spa'],
    timid: ['spe', 'atk'], hasty: ['spe', 'def'], jolly: ['spe', 'spa'], naive: ['spe', 'spd'],
  };

  const ABILITY_IMMUNITY = {
    levitate: 'Ground', eartheater: 'Ground', flashfire: 'Fire',
    voltabsorb: 'Electric', lightningrod: 'Electric', motordrive: 'Electric',
    waterabsorb: 'Water', stormdrain: 'Water', dryskin: 'Water', sapsipper: 'Grass',
  };
  const PERSONAL_WEATHER = { megasol: 'sun' };
  const ATE_POWER_MOD = 4915;

  // Items « type-boost » (×1.2 sur la puissance des moves de ce type).
  const TYPE_ITEM = {
    charcoal: 'Fire', mysticwater: 'Water', magnet: 'Electric', miracleseed: 'Grass',
    nevermeltice: 'Ice', blackbelt: 'Fighting', poisonbarb: 'Poison', softsand: 'Ground',
    sharpbeak: 'Flying', twistedspoon: 'Psychic', silverpowder: 'Bug', hardstone: 'Rock',
    spelltag: 'Ghost', dragonfang: 'Dragon', blackglasses: 'Dark', metalcoat: 'Steel',
    silkscarf: 'Normal', fairyfeather: 'Fairy',
  };
  // Talents « type-boost » offensifs (modifient la stat d'attaque, base 4096).
  const TYPE_BOOST_ABILITY = {
    steelworker: ['Steel', 6144], steelyspirit: ['Steel', 6144],
    dragonsmaw: ['Dragon', 6144], rockypayload: ['Rock', 6144],
    transistor: ['Electric', 5325],
  };

  const WEATHER_ALIASES = {
    sun: 'sun', sunnyday: 'sun', harshsunlight: 'sun', desolateland: 'sun',
    rain: 'rain', raindance: 'rain', primordialsea: 'rain',
    sand: 'sand', sandstorm: 'sand', snow: 'snow', hail: 'snow',
  };
  const TERRAIN_ALIASES = {
    electric: 'electric', electricterrain: 'electric', grassy: 'grassy', grassyterrain: 'grassy',
    psychic: 'psychic', psychicterrain: 'psychic', misty: 'misty', mistyterrain: 'misty',
  };

  function toId(s) { return (s || '').toLowerCase().replace(/[^a-z0-9]/g, ''); }
  function pokeRound(x) { const fl = Math.floor(x); return fl + (x - fl > 0.5 ? 1 : 0); }
  function chainMods(mods) {
    let m = 4096;
    for (const mod of mods) if (mod !== 4096) m = (m * mod + 2048) >> 12;
    return m;
  }
  function applyMod(v, mod) { return pokeRound((v * mod) / 4096); }

  function boostMult(stage, ignoreNeg, ignorePos) {
    if (stage > 0 && ignorePos) stage = 0;
    if (stage < 0 && ignoreNeg) stage = 0;
    return stage >= 0 ? (2 + stage) / 2 : 2 / (2 - stage);
  }

  function makeEngine(data) {
    const { pokedex, moves, typechart, ateMap } = data;
    const ATE = Object.assign({
      pixilate: 'Fairy', aerilate: 'Flying', refrigerate: 'Ice', galvanize: 'Electric',
    }, ateMap || {});

    function species(id) {
      const rec = pokedex[toId(id)];
      if (!rec) throw new Error('Espèce inconnue : ' + id);
      return rec;
    }
    function move(id) {
      const m = moves[toId(id)];
      if (!m) throw new Error('Move inconnu : ' + id);
      return m;
    }
    function natureMult(nature) {
      const n = NATURES[toId(nature)] || [null, null];
      const mult = { hp: 1, atk: 1, def: 1, spa: 1, spd: 1, spe: 1 };
      if (n[0]) mult[n[0]] = 1.1;
      if (n[1]) mult[n[1]] = 0.9;
      return mult;
    }
    function computeStat(base, sp, isHp, nm) {
      const inter = 2 * base + IV + 2 * (sp || 0);
      const core = Math.floor((inter * LEVEL) / 100);
      return isHp ? core + LEVEL + 10 : Math.floor((core + 5) * nm);
    }
    function battleStats(mon) {
      const base = species(mon.species).baseStats;
      const nm = natureMult(mon.nature);
      const out = {};
      for (const k of STAT_KEYS) out[k] = computeStat(base[k], (mon.sp || {})[k], k === 'hp', nm[k]);
      return out;
    }
    function effectiveness(atkType, defTypes) {
      if (!atkType) return 1;
      const row = typechart[atkType];
      if (!row) return 1;
      let m = 1;
      for (const d of defTypes) m *= (row[d] === undefined ? 1 : row[d]);
      return m;
    }
    function grounded(mon) {
      const t = species(mon.species).types || [];
      return t.indexOf('Flying') < 0 && toId(mon.ability) !== 'levitate';
    }

    function calculate(attacker, defender, moveId, field, opts) {
      opts = opts || {};
      const crit = !!opts.crit, applySpread = !!opts.applySpread;
      field = field || {};
      const mv = move(moveId);
      if (mv.category === 'Status' || mv.basePower <= 0)
        throw new Error(mv.name + " n'inflige pas de dégâts directs.");

      const atkAb = toId(attacker.ability), defAb = toId(defender.ability);
      const atkItem = toId(attacker.item), defItem = toId(defender.item);
      const aStats = battleStats(attacker), dStats = battleStats(defender);
      const defTypes = species(defender.species).types || [];
      const atkTypes = species(attacker.species).types || [];
      const weather = WEATHER_ALIASES[toId(field.weather)] || null;
      const terrain = TERRAIN_ALIASES[toId(field.terrain)] || null;

      // Protosynthèse / Charge Quantique : stat dopée (plus haute hors PV).
      function paradoxStat(mon, ab) {
        let active;
        if (ab === 'protosynthesis') active = weather === 'sun' || toId(mon.item) === 'boosterenergy';
        else if (ab === 'quarkdrive') active = terrain === 'electric' || toId(mon.item) === 'boosterenergy';
        else return null;
        if (!active) return null;
        const s = battleStats(mon);
        const order = ['atk', 'def', 'spa', 'spd', 'spe'];
        let best = order[0];
        for (const k of order) if (s[k] > s[best]) best = k;
        return best;
      }

      // Delta : type effectif (-ate)
      let moveType = mv.type;
      const ate = atkAb ? ATE[atkAb] : null;
      const typeChanged = !!(ate && mv.type === 'Normal');
      if (typeChanged) moveType = ate;

      const physical = mv.category === 'Physical';
      const atkKey = physical ? 'atk' : 'spa', defKey = physical ? 'def' : 'spd';

      // Stat offensive
      let attack = Math.floor(aStats[atkKey] * boostMult((attacker.boosts || {})[atkKey] || 0, crit, false));
      const atMods = [];
      if (physical && atkItem === 'choiceband') atMods.push(6144);
      if (!physical && atkItem === 'choicespecs') atMods.push(6144);
      if (physical && (atkAb === 'hugepower' || atkAb === 'purepower')) atMods.push(8192);
      if (atkAb === 'guts' && attacker.status) atMods.push(6144);
      if (atkAb === 'waterbubble' && moveType === 'Water') atMods.push(8192);
      if (atkAb === 'solarpower' && !physical && weather === 'sun') atMods.push(6144);
      const tb = TYPE_BOOST_ABILITY[atkAb];
      if (tb && tb[0] === moveType) atMods.push(tb[1]);
      if (paradoxStat(attacker, atkAb) === atkKey) atMods.push(5325);
      if (defAb === 'thickfat' && (moveType === 'Fire' || moveType === 'Ice')) atMods.push(2048);
      if (defAb === 'heatproof' && moveType === 'Fire') atMods.push(2048);
      if (atMods.length) attack = applyMod(attack, chainMods(atMods));
      attack = Math.max(1, attack);

      // Stat défensive
      let defense = Math.floor(dStats[defKey] * boostMult((defender.boosts || {})[defKey] || 0, false, crit));
      const dfMods = [];
      if (!physical && defItem === 'assaultvest') dfMods.push(6144);
      if (!physical && weather === 'sand' && defTypes.indexOf('Rock') >= 0) dfMods.push(6144);
      if (physical && weather === 'snow' && defTypes.indexOf('Ice') >= 0) dfMods.push(6144);
      if (paradoxStat(defender, defAb) === defKey) dfMods.push(5325);
      if (dfMods.length) defense = applyMod(defense, chainMods(dfMods));
      defense = Math.max(1, defense);

      // Puissance
      let bp = mv.basePower;
      const bpMods = [];
      if (atkAb === 'technician' && bp <= 60) bpMods.push(6144);
      if (typeChanged) bpMods.push(ATE_POWER_MOD);
      if (TYPE_ITEM[atkItem] === moveType) bpMods.push(4915);
      if (atkItem === 'muscleband' && physical) bpMods.push(4506);
      if (atkItem === 'wiseglasses' && !physical) bpMods.push(4506);
      if (atkAb === 'sandforce' && weather === 'sand'
          && (moveType === 'Ground' || moveType === 'Rock' || moveType === 'Steel')) bpMods.push(5325);
      if (bpMods.length) bp = Math.max(1, applyMod(bp, chainMods(bpMods)));

      // Dégâts de base
      let baseDamage = Math.floor(Math.floor((Math.floor((2 * LEVEL) / 5 + 2) * bp * attack) / defense) / 50) + 2;
      if (applySpread) baseDamage = applyMod(baseDamage, 3072);

      const offWeather = (atkAb && PERSONAL_WEATHER[atkAb]) || weather;
      if (offWeather === 'sun') {
        if (moveType === 'Fire') baseDamage = applyMod(baseDamage, 6144);
        else if (moveType === 'Water') baseDamage = applyMod(baseDamage, 2048);
      } else if (offWeather === 'rain') {
        if (moveType === 'Water') baseDamage = applyMod(baseDamage, 6144);
        else if (moveType === 'Fire') baseDamage = applyMod(baseDamage, 2048);
      }

      if (terrain && grounded(attacker)) {
        if (terrain === 'electric' && moveType === 'Electric') baseDamage = applyMod(baseDamage, 5325);
        else if (terrain === 'grassy' && moveType === 'Grass') baseDamage = applyMod(baseDamage, 5325);
        else if (terrain === 'psychic' && moveType === 'Psychic') baseDamage = applyMod(baseDamage, 5325);
      }
      if (terrain === 'misty' && moveType === 'Dragon' && grounded(defender)) baseDamage = applyMod(baseDamage, 2048);

      if (crit) baseDamage = Math.floor(baseDamage * 1.5);

      const isStab = atkTypes.indexOf(moveType) >= 0;
      const stabMod = isStab ? (atkAb === 'adaptability' ? 8192 : 6144) : 4096;
      let eff = effectiveness(moveType, defTypes);
      if (ABILITY_IMMUNITY[defAb] === moveType) eff = 0;
      const burned = physical && attacker.status === 'brn' && atkAb !== 'guts';

      const finalMods = [];
      if (atkItem === 'lifeorb') finalMods.push(5324);
      if (atkItem === 'expertbelt' && eff > 1) finalMods.push(4915);
      if (atkAb === 'tintedlens' && eff > 0 && eff < 1) finalMods.push(8192);
      if (atkAb === 'neuroforce' && eff > 1) finalMods.push(5120);
      const dHpPct = defender.hpPct === undefined ? 1 : defender.hpPct;
      if ((defAb === 'multiscale' || defAb === 'shadowshield') && dHpPct >= 1) finalMods.push(2048);
      if ((defAb === 'filter' || defAb === 'solidrock' || defAb === 'prismarmor') && eff > 1) finalMods.push(3072);
      // Talents défensifs modulant les dégâts finaux.
      if (defAb === 'fluffy') {
        if (moveType === 'Fire') finalMods.push(8192);
        if (mv.makesContact) finalMods.push(2048);
      }
      if (defAb === 'icescales' && !physical) finalMods.push(2048);
      if (defAb === 'purifyingsalt' && moveType === 'Ghost') finalMods.push(2048);
      if (defAb === 'waterbubble' && moveType === 'Fire') finalMods.push(2048);
      if (defAb === 'dryskin' && moveType === 'Fire') finalMods.push(5120);
      const finalMod = chainMods(finalMods);

      const rolls = [];
      for (let i = 0; i < 16; i++) {
        let d = Math.floor((baseDamage * (85 + i)) / 100);
        if (stabMod !== 4096) d = pokeRound((d * stabMod) / 4096);
        d = Math.floor(d * eff);
        if (burned) d = Math.floor(d / 2);
        if (finalMod !== 4096) d = pokeRound(Math.max(1, (d * finalMod) / 4096));
        if (eff > 0) d = Math.max(1, d);
        rolls.push(d);
      }
      rolls.sort((a, b) => a - b);

      const maxHp = dStats.hp;
      let curHp = Math.max(0, Math.floor(maxHp * Math.max(0, Math.min(1, dHpPct))));
      if (dHpPct >= 1) curHp = maxHp;

      return {
        move: mv.name, moveType, rolls, maxHp, curHp,
        eff, isStab, crit,
        min: rolls[0], max: rolls[15],
        minPct: (100 * rolls[0]) / maxHp, maxPct: (100 * rolls[15]) / maxHp,
        koGuaranteed: rolls[0] >= curHp ? 1 : Math.ceil(curHp / Math.max(1, rolls[0])),
        koPossible: rolls[15] >= curHp ? 1 : Math.ceil(curHp / Math.max(1, rolls[15])),
      };
    }

    return { calculate, battleStats, effectiveness, species, move, toId, NATURES, STAT_KEYS };
  }

  return { makeEngine, toId, pokeRound, chainMods };
});
