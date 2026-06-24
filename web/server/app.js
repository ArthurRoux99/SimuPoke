/* SimuPoke — frontend de la version hébergée. Appelle l'API du serveur local
 * (/api/*) qui exécute le moteur Python. Aucune logique de jeu côté client. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const SP = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];
  const SP_FR = { hp: 'PV', atk: 'Atq', def: 'Déf', spa: 'A.Sp', spd: 'D.Sp', spe: 'Vit' };
  let META = { species: [], moves: [], natures: [] };
  let SAMPLES = {};
  const builders = {};

  async function api(path, body) {
    const opt = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body) } : {};
    const res = await fetch(path, opt);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || ('HTTP ' + res.status));
    return data;
  }

  const esc = (s) => String(s == null ? '' : s).replace(/"/g, '&quot;');
  const splitMoves = (s) => s.split(',').map((x) => x.trim()).filter(Boolean);
  function natureOptions(sel) { return META.natures.map((n) => `<option value="${n}"${n === sel ? ' selected' : ''}>${n}</option>`).join(''); }

  function fillBoost(s) { let h = ''; for (let i = 6; i >= -6; i--) h += `<option value="${i}"${i === 0 ? ' selected' : ''}>${i > 0 ? '+' + i : i}</option>`; s.innerHTML = h; }
  function fillSP(c, p) { c.innerHTML = SP.map((k) => `<div class="cell"><label>${SP_FR[k]}</label><input id="${p}-sp-${k}" type="number" min="0" max="32" value="0"></div>`).join(''); }
  function readSP(p) { const sp = {}; SP.forEach((k) => { sp[k] = parseInt($(`${p}-sp-${k}`).value || '0', 10); }); return sp; }

  // ---------- Composant builder (lignes éditables) ----------
  function makeBuilder(container, opts) {
    opts = Object.assign({ withRarity: false, withSP: false }, opts || {});
    const list = document.createElement('div');
    const add = document.createElement('button');
    add.type = 'button'; add.textContent = '+ Ajouter un Pokémon';
    add.addEventListener('click', () => addRow({}));
    container.innerHTML = ''; container.appendChild(list); container.appendChild(add);

    function spStr(sp) { return sp ? Object.entries(sp).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join(',') : ''; }
    function parseSP(s) { const o = {}; (s || '').split(',').forEach((p) => { const [k, v] = p.split('='); if (k && v) o[k.trim()] = parseInt(v, 10); }); return o; }

    function addRow(d) {
      const row = document.createElement('div');
      row.className = 'builder-row';
      row.innerHTML =
        `<input class="b-species" list="species-list" placeholder="espèce" value="${esc(d.species)}">` +
        `<select class="b-nature">${natureOptions(d.nature || 'serious')}</select>` +
        `<input class="b-item" placeholder="objet" value="${esc(d.item)}">` +
        `<input class="b-ability" placeholder="talent" value="${esc(d.ability)}">` +
        `<input class="b-moves" placeholder="capacités (a, b, c)" value="${esc((d.moves || []).join(', '))}">` +
        (opts.withSP ? `<input class="b-sp" placeholder="SP atk=32,spe=32" value="${esc(spStr(d.stat_points))}">` : '') +
        (opts.withRarity ? `<label class="b-rar"><input type="checkbox" class="b-shiny"${d.is_shiny ? ' checked' : ''}>✨</label>` : '') +
        `<button class="b-del" type="button" title="retirer">✕</button>`;
      row.querySelector('.b-del').addEventListener('click', () => list.removeChild(row));
      list.appendChild(row);
    }
    function getEntries() {
      return Array.from(list.querySelectorAll('.builder-row')).map((row) => {
        const e = {
          species: row.querySelector('.b-species').value.trim(),
          nature: row.querySelector('.b-nature').value,
          item: row.querySelector('.b-item').value.trim() || null,
          ability: row.querySelector('.b-ability').value.trim() || null,
          moves: splitMoves(row.querySelector('.b-moves').value),
        };
        if (opts.withSP) e.stat_points = parseSP(row.querySelector('.b-sp').value);
        if (opts.withRarity) e.is_shiny = row.querySelector('.b-shiny').checked;
        return e;
      }).filter((e) => e.species);
    }
    function setEntries(arr) { list.innerHTML = ''; (arr || []).forEach(addRow); }
    return { getEntries, setEntries, addRow, el: container };
  }

  // ---------- Onglets ----------
  function initTabs() {
    document.querySelectorAll('#tabs button').forEach((b) => {
      b.addEventListener('click', () => {
        document.querySelectorAll('#tabs button').forEach((x) => x.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach((x) => x.classList.remove('active'));
        b.classList.add('active'); $('tab-' + b.dataset.tab).classList.add('active');
      });
    });
  }

  // ---------- Dégâts ----------
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

  // ---------- Combat ----------
  async function runCombat() {
    try {
      const me = { species: $('c-me-species').value, nature: $('c-me-nature').value,
        sp: readSP('c-me'), moves: splitMoves($('c-me-moves').value),
        hpPct: parseFloat($('c-me-hp').value || '100') / 100 };
      const opp = { species: $('c-opp-species').value, nature: $('c-opp-nature').value,
        moves: splitMoves($('c-opp-moves').value), hpPct: parseFloat($('c-opp-hp').value || '100') / 100 };
      const r = await api('/api/analyze', { me, opp, opp_move: $('c-opp-move').value,
        field: { weather: $('c-weather').value, terrain: $('c-terrain').value } });
      $('combat-result').textContent = r.lines.join('\n');
    } catch (e) { $('combat-result').textContent = '⚠ ' + e.message; }
  }

  // ---------- Tirage ----------
  async function runDraft() {
    const out = $('draft-result');
    try {
      const r = await api('/api/draft', { lineup: builders.draft.getEntries() });
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

  // ---------- Équipe ----------
  async function runTeam() {
    try { const r = await api('/api/team', { team: builders.team.getEntries() });
      $('team-result').textContent = r.lines.join('\n');
    } catch (e) { $('team-result').textContent = '⚠ ' + e.message; }
  }

  // ---------- Preview ----------
  async function runPreview() {
    try {
      const r = await api('/api/preview', { my_team: builders.prevMine.getEntries(),
        opp_team: builders.prevOpp.getEntries(), format: $('prev-format').value });
      $('preview-result').textContent = r.lines.join('\n');
    } catch (e) { $('preview-result').textContent = '⚠ ' + e.message; }
  }

  // ---------- Mon Box ----------
  async function loadBox() {
    try { const r = await api('/api/roster'); builders.box.setEntries(r.roster);
      $('box-status').textContent = `${r.roster.length} Pokémon chargé(s).`;
    } catch (e) { $('box-status').textContent = '⚠ ' + e.message; }
  }
  async function saveBox() {
    try {
      const r = await api('/api/roster', { roster: builders.box.getEntries() });
      let msg = `Enregistré : ${r.count} Pokémon.`;
      if (r.unknown && r.unknown.length) msg += ` ⚠ espèces inconnues : ${r.unknown.join(', ')}`;
      $('box-status').textContent = msg;
    } catch (e) { $('box-status').textContent = '⚠ ' + e.message; }
  }

  const entriesFrom = (sample, key) => (sample && sample[key]) ? sample[key] : [];

  async function init() {
    initTabs();
    try { META = await api('/api/meta'); } catch (e) { /* listes vides */ }
    try { SAMPLES = await api('/api/samples'); } catch (e) { SAMPLES = {}; }

    document.querySelectorAll('#tab-damage select[id$="-nature"], #tab-combat select[id$="-nature"]')
      .forEach((s) => { s.innerHTML = natureOptions('serious'); });
    document.querySelectorAll('.boost').forEach(fillBoost);
    ['a', 'd', 'c-me'].forEach((p) => { const el = $(`${p}-sp`); if (el) fillSP(el, p); });
    $('a-nature').value = 'adamant'; $('d-nature').value = 'jolly';
    $('a-sp-atk').value = 31; $('a-sp-spa').value = 31;
    if ($('c-me-sp-atk')) { $('c-me-sp-atk').value = 32; $('c-me-sp-spe').value = 32; }
    $('species-list').innerHTML = META.species.map((n) => `<option value="${n}">`).join('');
    $('move-list').innerHTML = META.moves.map((n) => `<option value="${n}">`).join('');

    // Builders
    builders.draft = makeBuilder($('draft-builder'), { withRarity: true });
    builders.team = makeBuilder($('team-builder'));
    builders.prevMine = makeBuilder($('prev-mine'));
    builders.prevOpp = makeBuilder($('prev-opp'));
    builders.box = makeBuilder($('box-builder'), { withSP: true, withRarity: true });

    builders.draft.setEntries(entriesFrom(SAMPLES.lineup, 'lineup'));
    builders.team.setEntries(entriesFrom(SAMPLES.team, 'team'));
    builders.prevMine.setEntries(entriesFrom(SAMPLES.team, 'team'));
    builders.prevOpp.setEntries(entriesFrom(SAMPLES.opponent, 'team'));

    // Listeners
    $('tab-damage').querySelectorAll('input, select').forEach((el) => {
      el.addEventListener('input', computeDamage); el.addEventListener('change', computeDamage);
    });
    $('c-run').addEventListener('click', runCombat);
    $('draft-run').addEventListener('click', runDraft);
    $('draft-sample').addEventListener('click', () => builders.draft.setEntries(entriesFrom(SAMPLES.lineup, 'lineup')));
    $('team-run').addEventListener('click', runTeam);
    $('team-sample').addEventListener('click', () => builders.team.setEntries(entriesFrom(SAMPLES.team, 'team')));
    $('team-frombox').addEventListener('click', async () => {
      try { const r = await api('/api/roster'); builders.team.setEntries(r.roster); } catch (e) { /* */ }
    });
    $('prev-run').addEventListener('click', runPreview);
    $('prev-sample').addEventListener('click', () => {
      builders.prevMine.setEntries(entriesFrom(SAMPLES.team, 'team'));
      builders.prevOpp.setEntries(entriesFrom(SAMPLES.opponent, 'team'));
    });
    $('box-save').addEventListener('click', saveBox);
    $('box-reload').addEventListener('click', loadBox);

    loadBox();
    computeDamage();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
