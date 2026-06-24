/* SimuPoke — frontend de la version hébergée. Appelle l'API du serveur local
 * (/api/*) qui exécute le moteur Python. Aucune logique de jeu côté client. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const SP = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];
  const SP_FR = { hp: 'PV', atk: 'Atq', def: 'Déf', spa: 'A.Sp', spd: 'D.Sp', spe: 'Vit' };
  let META = { species: [], moves: [], natures: [] };
  let SAMPLES = {};

  async function api(path, body) {
    const opt = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) } : {};
    const res = await fetch(path, opt);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || ('HTTP ' + res.status));
    return data;
  }

  function fillNatures(sel) {
    sel.innerHTML = META.natures.map((n) => `<option value="${n}">${n}</option>`).join('');
  }
  function fillBoost(sel) {
    let h = '';
    for (let i = 6; i >= -6; i--) h += `<option value="${i}"${i === 0 ? ' selected' : ''}>${i > 0 ? '+' + i : i}</option>`;
    sel.innerHTML = h;
  }
  function fillSP(container, prefix) {
    container.innerHTML = SP.map((k) =>
      `<div class="cell"><label>${SP_FR[k]}</label><input id="${prefix}-sp-${k}" type="number" min="0" max="32" value="0"></div>`).join('');
  }
  function readSP(prefix) {
    const sp = {}; SP.forEach((k) => { sp[k] = parseInt($(`${prefix}-sp-${k}`).value || '0', 10); });
    return sp;
  }
  const splitMoves = (s) => s.split(',').map((x) => x.trim()).filter(Boolean);

  // ---------- Onglets ----------
  function initTabs() {
    document.querySelectorAll('#tabs button').forEach((b) => {
      b.addEventListener('click', () => {
        document.querySelectorAll('#tabs button').forEach((x) => x.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach((x) => x.classList.remove('active'));
        b.classList.add('active');
        $('tab-' + b.dataset.tab).classList.add('active');
      });
    });
  }

  // ---------- Onglet Dégâts ----------
  function readMon(prefix) {
    const boosts = {};
    document.querySelectorAll(`#${prefix}-boost-atk, #${prefix}-boost-spa, #${prefix}-boost-def, #${prefix}-boost-spd`)
      .forEach((el) => { boosts[el.id.split('-')[2]] = parseInt(el.value, 10); });
    return {
      species: $(`${prefix}-species`).value, nature: $(`${prefix}-nature`).value,
      sp: readSP(prefix), item: $(`${prefix}-item`).value, ability: $(`${prefix}-ability`).value,
      status: prefix === 'a' ? $('a-status').value : '',
      boosts, hpPct: prefix === 'd' ? parseFloat($('d-hp').value || '100') / 100 : 1,
    };
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
  async function computeDamage() {
    try {
      const r = await api('/api/damage', {
        attacker: readMon('a'), defender: readMon('d'), move: $('move').value,
        field: { weather: $('weather').value, terrain: $('terrain').value },
        crit: $('crit').checked, spread: $('spread').checked,
      });
      const left = Math.min(100, r.minPct), w = Math.min(100, r.maxPct) - left;
      $('dmg-result').innerHTML = `
        <div class="headline">${r.min}–${r.max} <span style="color:var(--muted);font-size:15px">(${r.minPct.toFixed(1)}–${r.maxPct.toFixed(1)} %)</span></div>
        <div class="sub">${r.move} sur ${$('d-species').value} — ${r.curHp}/${r.maxHp} PV</div>
        <div class="badges">${effBadge(r.eff)}${r.isStab ? '<span class="badge stab">STAB</span>' : ''}${r.crit ? '<span class="badge crit">critique</span>' : ''}</div>
        <div class="bar"><div class="fill" style="left:${left}%;width:${Math.max(1, w)}%"></div></div>
        <div class="ko">${koLine(r)}</div>
        <div class="rolls">rolls : ${r.rolls.join(' ')}</div>`;
    } catch (e) { $('dmg-result').innerHTML = `<div class="error">⚠ ${e.message}</div>`; }
  }

  // ---------- Onglet Combat ----------
  async function runCombat() {
    try {
      const me = { species: $('c-me-species').value, nature: $('c-me-nature').value,
        sp: readSP('c-me'), moves: splitMoves($('c-me-moves').value),
        hpPct: parseFloat($('c-me-hp').value || '100') / 100 };
      const opp = { species: $('c-opp-species').value, nature: $('c-opp-nature').value,
        moves: splitMoves($('c-opp-moves').value),
        hpPct: parseFloat($('c-opp-hp').value || '100') / 100 };
      const r = await api('/api/analyze', { me, opp, opp_move: $('c-opp-move').value,
        field: { weather: $('c-weather').value, terrain: $('c-terrain').value } });
      $('combat-result').textContent = r.lines.join('\n');
    } catch (e) { $('combat-result').textContent = '⚠ ' + e.message; }
  }

  // ---------- Onglet Tirage ----------
  async function runDraft() {
    const out = $('draft-result');
    try {
      const lineup = JSON.parse($('draft-input').value).lineup;
      const r = await api('/api/draft', { lineup });
      out.innerHTML = r.ranking.map((e, i) => `
        <div class="rank-row">
          <div class="rank">${i + 1}</div>
          <div><div class="name">${e.species}${e.shiny ? ' ✨' : ''} <span class="meta">${e.role}</span></div>
            <div class="meta">${e.reasons.join(' · ')}</div>
            <div class="meta">→ ${e.recommendation}</div></div>
          <div class="score">${e.score}</div>
        </div>`).join('');
    } catch (e) { out.innerHTML = `<div class="error">⚠ ${e.message}</div>`; }
  }

  // ---------- Onglet Équipe ----------
  async function runTeam() {
    try {
      const team = JSON.parse($('team-input').value).team;
      const r = await api('/api/team', { team });
      $('team-result').textContent = r.lines.join('\n');
    } catch (e) { $('team-result').textContent = '⚠ ' + e.message; }
  }

  // ---------- Onglet Preview ----------
  async function runPreview() {
    try {
      const my_team = JSON.parse($('prev-mine').value).team;
      const opp_team = JSON.parse($('prev-opp').value).team;
      const r = await api('/api/preview', { my_team, opp_team, format: $('prev-format').value });
      $('preview-result').textContent = r.lines.join('\n');
    } catch (e) { $('preview-result').textContent = '⚠ ' + e.message; }
  }

  async function init() {
    initTabs();
    try { META = await api('/api/meta'); } catch (e) { /* listes vides */ }
    try { SAMPLES = await api('/api/samples'); } catch (e) { SAMPLES = {}; }

    document.querySelectorAll('select[id$="-nature"], #a-nature, #d-nature').forEach(fillNatures);
    document.querySelectorAll('.boost').forEach(fillBoost);
    ['a', 'd', 'c-me', 'c-opp'].forEach((p) => { const el = $(`${p}-sp`); if (el) fillSP(el, p); });
    $('a-nature').value = 'adamant'; $('d-nature').value = 'jolly';
    $('a-sp-atk').value = 31; $('a-sp-spa').value = 31;
    if ($('c-me-sp-atk')) { $('c-me-sp-atk').value = 32; $('c-me-sp-spe').value = 32; }

    $('species-list').innerHTML = META.species.map((n) => `<option value="${n}">`).join('');
    $('move-list').innerHTML = META.moves.map((n) => `<option value="${n}">`).join('');

    // Dégâts : recalcul à chaque modif
    $('tab-damage').querySelectorAll('input, select').forEach((el) => {
      el.addEventListener('input', computeDamage); el.addEventListener('change', computeDamage);
    });
    $('c-run').addEventListener('click', runCombat);
    $('draft-run').addEventListener('click', runDraft);
    $('team-run').addEventListener('click', runTeam);
    $('prev-run').addEventListener('click', runPreview);

    // Préremplissage des exemples
    if (SAMPLES.lineup) $('draft-input').value = JSON.stringify(SAMPLES.lineup, null, 1);
    if (SAMPLES.team) { $('team-input').value = JSON.stringify(SAMPLES.team, null, 1);
      $('prev-mine').value = JSON.stringify(SAMPLES.team, null, 1); }
    if (SAMPLES.opponent) $('prev-opp').value = JSON.stringify(SAMPLES.opponent, null, 1);
    $('draft-sample').addEventListener('click', () => { if (SAMPLES.lineup) $('draft-input').value = JSON.stringify(SAMPLES.lineup, null, 1); });
    $('team-sample').addEventListener('click', () => { if (SAMPLES.team) $('team-input').value = JSON.stringify(SAMPLES.team, null, 1); });
    $('prev-sample').addEventListener('click', () => {
      if (SAMPLES.team) $('prev-mine').value = JSON.stringify(SAMPLES.team, null, 1);
      if (SAMPLES.opponent) $('prev-opp').value = JSON.stringify(SAMPLES.opponent, null, 1);
    });

    computeDamage();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
