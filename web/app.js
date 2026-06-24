/* SimuPoke — UI du calculateur de dégâts (DOM). Utilise window.SimuEngine et
 * window.SIMUPOKE_DATA (injectés par le build). */
(function () {
  'use strict';
  const DATA = window.SIMUPOKE_DATA;
  const E = window.SimuEngine.makeEngine(DATA);
  const $ = (id) => document.getElementById(id);
  const SP = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];
  const SP_FR = { hp: 'PV', atk: 'Atq', def: 'Déf', spa: 'A.Sp', spd: 'D.Sp', spe: 'Vit' };
  const STAT_FR = { atk: 'Atq', spa: 'A.Spé', def: 'Déf', spd: 'D.Spé', spe: 'Vit' };

  // --- Remplissage des listes ---
  function fillNatures(sel) {
    const ids = Object.keys(E.NATURES).sort();
    sel.innerHTML = ids.map((id) => {
      const [p, m] = E.NATURES[id];
      const hint = p ? ` (+${STAT_FR[p]} -${STAT_FR[m]})` : ' (neutre)';
      return `<option value="${id}">${id}${hint}</option>`;
    }).join('');
  }
  function fillBoost(sel) {
    let html = '';
    for (let i = 6; i >= -6; i--) html += `<option value="${i}"${i === 0 ? ' selected' : ''}>${i > 0 ? '+' + i : i}</option>`;
    sel.innerHTML = html;
  }
  function fillSP(container, prefix) {
    container.innerHTML = SP.map((k) =>
      `<div class="cell"><label>${SP_FR[k]}</label><input id="${prefix}-sp-${k}" type="number" min="0" max="32" value="0"></div>`
    ).join('');
  }

  function init() {
    fillNatures($('a-nature')); fillNatures($('d-nature'));
    $('a-nature').value = 'adamant'; $('d-nature').value = 'jolly';
    document.querySelectorAll('.boost').forEach(fillBoost);
    fillSP($('a-sp'), 'a'); fillSP($('d-sp'), 'd');
    $('a-sp-atk').value = 31; $('a-sp-spa').value = 31;

    // datalists
    const speciesNames = Object.values(DATA.pokedex).map((s) => s.name).sort();
    $('species-list').innerHTML = speciesNames.map((n) => `<option value="${n}">`).join('');
    const moveNames = Object.values(DATA.moves)
      .filter((m) => m.category !== 'Status' && m.basePower > 0)
      .map((m) => m.name).sort();
    $('move-list').innerHTML = moveNames.map((n) => `<option value="${n}">`).join('');

    document.querySelectorAll('input, select').forEach((el) => {
      el.addEventListener('input', compute);
      el.addEventListener('change', compute);
    });
    document.querySelectorAll('[data-preset]').forEach((b) =>
      b.addEventListener('click', () => applyPreset(b.dataset.preset)));
    compute();
  }

  function readMon(prefix) {
    const sp = {};
    SP.forEach((k) => { sp[k] = parseInt($(`${prefix}-sp-${k}`).value || '0', 10); });
    const boosts = {};
    document.querySelectorAll(`#${prefix}-boost-atk, #${prefix}-boost-spa, #${prefix}-boost-def, #${prefix}-boost-spd`)
      .forEach((el) => { const stat = el.id.split('-')[2]; boosts[stat] = parseInt(el.value, 10); });
    return {
      species: $(`${prefix}-species`).value,
      nature: $(`${prefix}-nature`).value,
      sp, boosts,
      item: $(`${prefix}-item`).value,
      ability: $(`${prefix}-ability`).value,
      status: prefix === 'a' ? $('a-status').value : '',
      hpPct: prefix === 'd' ? (parseFloat($('d-hp').value || '100') / 100) : 1,
    };
  }

  function compute() {
    const out = $('result');
    let r;
    try {
      const a = readMon('a'), d = readMon('d');
      const field = { weather: $('weather').value, terrain: $('terrain').value };
      r = E.calculate(a, d, $('move').value, field,
        { crit: $('crit').checked, applySpread: $('spread').checked });
    } catch (err) {
      out.innerHTML = `<div class="error">⚠ ${err.message}</div>`;
      return;
    }
    out.innerHTML = render(r);
  }

  function effBadge(eff) {
    if (eff === 0) return '<span class="badge immune">aucun effet</span>';
    if (eff > 1) return `<span class="badge se">super efficace ×${eff}</span>`;
    if (eff < 1) return `<span class="badge nve">peu efficace ×${eff}</span>`;
    return '';
  }

  function koLine(r) {
    if (r.max === 0) return 'Aucun dégât.';
    if (r.koPossible === r.koGuaranteed) return `KO garanti en ${r.koGuaranteed} coup(s)`;
    return `KO possible en ${r.koPossible}, garanti en ${r.koGuaranteed} coup(s)`;
  }

  function render(r) {
    const badges = [
      effBadge(r.eff),
      r.isStab ? '<span class="badge stab">STAB</span>' : '',
      r.crit ? '<span class="badge crit">critique</span>' : '',
      r.moveType ? `<span class="badge">${r.moveType}</span>` : '',
    ].join('');
    const fillLeft = Math.min(100, r.minPct), fillW = Math.min(100, r.maxPct) - fillLeft;
    return `
      <div class="headline">${r.min}–${r.max} <span style="color:var(--muted);font-size:15px">(${r.minPct.toFixed(1)}–${r.maxPct.toFixed(1)} %)</span></div>
      <div class="sub">${r.move} sur ${$('d-species').value} — ${r.curHp}/${r.maxHp} PV</div>
      <div class="badges">${badges}</div>
      <div class="bar"><div class="fill" style="left:${fillLeft}%;width:${Math.max(1, fillW)}%"></div></div>
      <div class="ko">${koLine(r)}</div>
      <div class="rolls">rolls : ${r.rolls.join(' ')}</div>
    `;
  }

  const PRESETS = {
    band: { a: { species: 'Garchomp', nature: 'adamant', sp: { atk: 31 }, item: 'choiceband' },
      d: { species: 'Tyranitar', nature: 'jolly' }, move: 'Earthquake' },
    dragonize: { a: { species: 'Feraligatr', nature: 'adamant', sp: { atk: 31 }, ability: 'dragonize' },
      d: { species: 'Garchomp', nature: 'jolly' }, move: 'Double-Edge' },
    pixilate: { a: { species: 'Sylveon', nature: 'modest', sp: { spa: 31 }, ability: 'pixilate' },
      d: { species: 'Garchomp', nature: 'jolly' }, move: 'Hyper Voice' },
  };

  function applyPreset(name) {
    const p = PRESETS[name]; if (!p) return;
    const setSide = (prefix, m) => {
      $(`${prefix}-species`).value = m.species;
      $(`${prefix}-nature`).value = m.nature || 'serious';
      $(`${prefix}-item`).value = m.item || '';
      $(`${prefix}-ability`).value = m.ability || '';
      SP.forEach((k) => { $(`${prefix}-sp-${k}`).value = (m.sp && m.sp[k]) || 0; });
    };
    setSide('a', p.a); setSide('d', p.d);
    $('a-status').value = ''; $('d-hp').value = 100;
    document.querySelectorAll('.boost').forEach((el) => { el.value = '0'; });
    $('move').value = p.move;
    $('weather').value = ''; $('terrain').value = '';
    $('crit').checked = false; $('spread').checked = false;
    compute();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
