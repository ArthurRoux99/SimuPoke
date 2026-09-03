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
  let spObjs = null;   // conteneur des lignes d'objectifs de l'optimiseur

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
        crit: $('crit').checked, spread: $('spread').checked, screen: $('screen').value,
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
  async function fillLikelyOpponent() {
    const sp = $('c-opp-species').value.trim();
    if (!sp) return;
    try {
      const r = await api('/api/likely?species=' + encodeURIComponent(sp));
      if (!r.known) { $('c-likely-status').textContent = 'aucune donnée d\'usage pour ' + sp; return; }
      if (r.moves && r.moves.length) $('c-opp-moves').value = r.moves.join(', ');
      if (r.nature) $('c-opp-nature').value = r.nature;
      const bits = [];
      if (r.item) bits.push('objet ' + r.item);
      if (r.ability) bits.push('talent ' + r.ability);
      $('c-likely-status').textContent = 'rempli depuis l\'usage' + (bits.length ? ' (' + bits.join(', ') + ')' : '');
    } catch (e) { $('c-likely-status').textContent = '⚠ ' + e.message; }
  }
  function parseBench(spec) {
    return (spec || '').split(';').map((chunk) => {
      const parts = chunk.split(',').map((x) => x.trim());
      if (!parts[0]) return null;
      return { species: parts[0], nature: parts[1] || 'serious',
        moves: (parts[2] || '').split('|').map((x) => x.trim()).filter(Boolean) };
    }).filter(Boolean);
  }
  async function runCombat() {
    try {
      const me = { species: $('c-me-species').value, nature: $('c-me-nature').value,
        sp: readSP('c-me'), moves: splitMoves($('c-me-moves').value),
        hpPct: parseFloat($('c-me-hp').value || '100') / 100 };
      const opp = { species: $('c-opp-species').value, nature: $('c-opp-nature').value,
        moves: splitMoves($('c-opp-moves').value), hpPct: parseFloat($('c-opp-hp').value || '100') / 100 };
      const r = await api('/api/analyze', { me, opp, opp_move: $('c-opp-move').value,
        bench: parseBench($('c-bench').value),
        field: { weather: $('c-weather').value, terrain: $('c-terrain').value } });
      $('combat-result').textContent = r.lines.join('\n');
    } catch (e) { $('combat-result').textContent = '⚠ ' + e.message; }
  }

  async function runDecide() {
    try {
      const me = { species: $('c-me-species').value, nature: $('c-me-nature').value,
        sp: readSP('c-me'), moves: splitMoves($('c-me-moves').value),
        hpPct: parseFloat($('c-me-hp').value || '100') / 100 };
      const opp = { species: $('c-opp-species').value, nature: $('c-opp-nature').value,
        moves: splitMoves($('c-opp-moves').value), hpPct: parseFloat($('c-opp-hp').value || '100') / 100 };
      const r = await api('/api/decide', { me, opp, bench: parseBench($('c-bench').value),
        depth: parseInt($('c-depth').value || '1', 10),
        opp_model: $('c-cautious').checked ? 'worst' : 'expected',
        field: { weather: $('c-weather').value, terrain: $('c-terrain').value } });
      $('combat-result').textContent = r.lines.join('\n');
    } catch (e) { $('combat-result').textContent = '⚠ ' + e.message; }
  }

  async function runNash() {
    const out = $('nash-result');
    out.innerHTML = '<div class="muted">Résolution du jeu simultané…</div>';
    try {
      const me = { species: $('c-me-species').value, nature: $('c-me-nature').value,
        sp: readSP('c-me'), moves: splitMoves($('c-me-moves').value),
        hpPct: parseFloat($('c-me-hp').value || '100') / 100 };
      const opp = { species: $('c-opp-species').value, nature: $('c-opp-nature').value,
        moves: splitMoves($('c-opp-moves').value), hpPct: parseFloat($('c-opp-hp').value || '100') / 100 };
      const r = await api('/api/nash', { me, opp, bench: parseBench($('c-bench').value),
        field: { weather: $('c-weather').value, terrain: $('c-terrain').value } });
      const bars = r.strategy.filter((s) => s.prob >= 0.005).map((s) => {
        const pct = (s.prob * 100).toFixed(0);
        return `<div class="nash-row"><span class="nash-lbl">${esc(s.action)}</span>`
          + `<span class="nash-bar"><i style="width:${Math.max(2, s.prob * 100)}%"></i></span>`
          + `<span class="nash-pct">${pct}%</span></div>`;
      }).join('');
      const opp3 = r.oppStrategy.filter((o) => o.prob >= 0.02)
        .map((o) => `${o.move == null ? 'inactif' : esc(o.move)} ${(o.prob * 100).toFixed(0)}%`)
        .join(' · ');
      let beliefHtml = '';
      if (r.belief && r.belief.length > 1) {
        const rows = r.belief.map((p) => {
          const item = p.item ? ` @ ${esc(p.item)}` : '';
          return `<div class="nash-belief-row"><span class="nash-belief-w">${(p.weight * 100).toFixed(0)}%</span>`
            + `<span class="nash-belief-set"><b>${item ? esc(p.item) : '—'}</b> · ${esc((p.moves || []).join(', '))}</span></div>`;
        }).join('');
        beliefHtml = `<div class="nash-belief"><div class="nash-belief-head">Croyance sur le set adverse (usage)</div>${rows}</div>`;
      }
      out.innerHTML =
        `<div class="nash-head">Stratégie mixte de Nash — jeu simultané, croyance sur l'adversaire</div>`
        + `<div class="nash-strat">${bars}</div>`
        + `<div class="nash-meta">Adversaire (modèle Nash) : ${opp3 || '—'}`
        + ` &nbsp;·&nbsp; Valeur du jeu : <b>${r.value >= 0 ? '+' : ''}${r.value.toFixed(2)}</b></div>`
        + beliefHtml
        + `<div class="nash-reco">➤ ${esc(r.recommendation)}</div>`;
    } catch (e) { out.innerHTML = `<div class="error">⚠ ${e.message}</div>`; }
  }

  // ---------- Doubles ----------
  function dblSample() {
    builders.dblMine.setEntries(entriesFrom(SAMPLES.team, 'team').slice(0, 2));
    builders.dblOpp.setEntries(entriesFrom(SAMPLES.opponent, 'team').slice(0, 2));
  }
  async function runDoubles() {
    const out = $('dbl-result');
    out.innerHTML = '<div class="muted">Calcul des menaces…</div>';
    try {
      const r = await api('/api/doubles', {
        mine: builders.dblMine.getEntries(),
        opp: builders.dblOpp.getEntries(),
        field: { weather: $('dbl-weather').value, terrain: $('dbl-terrain').value },
      });
      const tgts = r.targets.map((t) => {
        const badge = t.focusKo ? '<span class="dbl-focus">⚡ FOCUS FIRE — KO garanti</span>' : '';
        const hits = t.hits.map((h) => {
          const ko = h.ko ? ' <span class="dbl-ko">KO</span>' : '';
          return `<div class="dbl-hit"><span class="dbl-atk">${esc(h.attacker)}</span> · ${esc(h.move)} `
            + `<b>${h.minPct.toFixed(0)}–${h.maxPct.toFixed(0)} %</b>${ko}</div>`;
        }).join('') || '<div class="muted">aucun coup offensif</div>';
        return `<div class="dbl-target"><div class="dbl-thead">▸ ${esc(t.target)} `
          + `<span class="muted">(${t.hp} PV)</span> ${badge}</div>${hits}</div>`;
      }).join('');
      let spreads = '';
      if (r.spreads.length) {
        spreads = '<div class="dbl-spread-head">Coups de zone (×0.75)</div>'
          + r.spreads.map((s) => `<div class="dbl-hit">${esc(s.attacker)} · ${esc(s.move)} : `
            + s.perTarget.map((p) => `${esc(p.target)} ${p.minPct.toFixed(0)}–${p.maxPct.toFixed(0)} %`).join(' / ')
            + '</div>').join('');
      }
      out.innerHTML = tgts + spreads || '<div class="muted">Renseigne des Pokémon des deux côtés.</div>';
    } catch (e) { out.innerHTML = `<div class="error">⚠ ${e.message}</div>`; }
  }

  // ---------- Tirage ----------
  async function runDraft() {
    const out = $('draft-result');
    try {
      const r = await api('/api/draft', { lineup: builders.draft.getEntries() });
      $('draft-status').textContent = 'Synergie : Mon Box · Méta : '
        + (r.usageApplied ? 'prior d\'usage appliqué' : 'aucune donnée d\'usage');
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

  async function importPaste() {
    const status = $('team-paste-status');
    try {
      const r = await api('/api/paste', { paste: $('team-paste').value });
      if (!r.count) { status.textContent = 'aucun Pokémon reconnu'; return; }
      builders.team.setEntries(r.team);
      let msg = `${r.count} Pokémon importé(s).`;
      if (r.unknown && r.unknown.length) msg += ` ⚠ inconnus : ${r.unknown.join(', ')}`;
      status.textContent = msg;
    } catch (e) { status.textContent = '⚠ ' + e.message; }
  }

  // ---------- Preview ----------
  async function runPreview() {
    try {
      const r = await api('/api/preview', { my_team: builders.prevMine.getEntries(),
        opp_team: builders.prevOpp.getEntries(), format: $('prev-format').value,
        use_damage: $('prev-damage').checked });
      $('preview-result').textContent = r.lines.join('\n');
    } catch (e) { $('preview-result').textContent = '⚠ ' + e.message; }
  }

  // ---------- Seuils (benchmarks) ----------
  function benchClass(ok) { return ok ? 'headline' : 'headline error'; }
  async function runOutspeed() {
    const out = $('os-result');
    try {
      const r = await api('/api/outspeed', {
        me: { species: $('os-me-species').value, nature: $('os-me-nature').value },
        target: { species: $('os-tg-species').value, nature: $('os-tg-nature').value,
          sp: { spe: parseInt($('os-tg-spe').value || '0', 10) } },
        me_tailwind: $('os-me-tw').checked, target_tailwind: $('os-tg-tw').checked,
        strict: !$('os-tie').checked,
      });
      out.innerHTML = `<div class="${benchClass(r.feasible)}">${esc(r.line)}</div>`;
    } catch (e) { out.innerHTML = `<div class="error">⚠ ${e.message}</div>`; }
  }
  async function runSurvive() {
    const out = $('sv-result');
    try {
      const off = parseInt($('sv-atk-off').value || '0', 10);
      const r = await api('/api/survive', {
        defender: { species: $('sv-def-species').value, nature: $('sv-def-nature').value },
        attacker: { species: $('sv-atk-species').value, nature: $('sv-atk-nature').value,
          item: $('sv-atk-item').value, sp: { atk: off, spa: off } },
        move: $('sv-move').value,
      });
      out.innerHTML = `<div class="${benchClass(r.feasible)}">${esc(r.line)}</div>`;
    } catch (e) { out.innerHTML = `<div class="error">⚠ ${e.message}</div>`; }
  }
  async function runKo() {
    const out = $('ko-result');
    try {
      const r = await api('/api/ko', {
        attacker: { species: $('ko-atk-species').value, nature: $('ko-atk-nature').value,
          item: $('ko-atk-item').value },
        defender: { species: $('ko-def-species').value, nature: $('ko-def-nature').value,
          hpPct: parseFloat($('ko-def-hp').value || '100') / 100 },
        move: $('ko-move').value, hits: parseInt($('ko-hits').value || '1', 10),
      });
      out.innerHTML = `<div class="${benchClass(r.feasible)}">${esc(r.line)}</div>`;
    } catch (e) { out.innerHTML = `<div class="error">⚠ ${e.message}</div>`; }
  }

  // ---------- Optimiseur de spread ----------
  function addObjRow(d) {
    d = d || {};
    const row = document.createElement('div');
    row.className = 'builder-row';
    row.innerHTML =
      `<select class="o-kind">
         <option value="outspeed">dépasser</option>
         <option value="survive">survivre</option>
         <option value="ko">tuer</option></select>` +
      `<input class="o-species" list="species-list" placeholder="espèce cible" value="${esc(d.species)}">` +
      `<select class="o-nature">${natureOptions(d.nature || 'serious')}</select>` +
      `<input class="o-move" list="move-list" placeholder="capacité (survivre/tuer)" value="${esc(d.move)}">` +
      `<input class="o-num" type="number" placeholder="SP / coups" style="max-width:88px" value="${d.num != null ? d.num : ''}">` +
      `<input class="o-item" placeholder="objet cible" value="${esc(d.item)}">` +
      `<button class="b-del" type="button" title="retirer">✕</button>`;
    row.querySelector('.o-kind').value = d.kind || 'outspeed';
    row.querySelector('.b-del').addEventListener('click', () => spObjs.removeChild(row));
    spObjs.appendChild(row);
  }
  function collectObjectives() {
    return Array.from(spObjs.querySelectorAll('.builder-row')).map((row) => {
      const kind = row.querySelector('.o-kind').value;
      const species = row.querySelector('.o-species').value.trim();
      const nature = row.querySelector('.o-nature').value;
      const move = row.querySelector('.o-move').value.trim();
      const num = parseInt(row.querySelector('.o-num').value || '0', 10);
      const item = row.querySelector('.o-item').value.trim() || null;
      if (!species) return null;
      if (kind === 'outspeed') return { kind, target: { species, nature, sp: { spe: num || 0 }, item } };
      if (kind === 'survive') return { kind, attacker: { species, nature, sp: { atk: num || 0, spa: num || 0 }, item }, move };
      return { kind: 'ko', defender: { species, nature, item }, move, hits: num || 1 };
    }).filter(Boolean);
  }
  async function runSpread() {
    const out = $('sp-result');
    try {
      const r = await api('/api/spread', {
        species: $('sp-species').value, nature: $('sp-nature').value,
        item: $('sp-item').value || null,
        budget: parseInt($('sp-budget').value || '66', 10),
        objectives: collectObjectives(),
      });
      out.innerHTML = `<div class="${r.feasible ? 'headline' : 'headline error'}">`
        + (r.feasible ? '✓ spread trouvé' : '⚠ objectifs non tous tenus') + '</div>'
        + `<pre class="report" style="margin-top:8px">${esc(r.lines.join('\n'))}</pre>`;
    } catch (e) { out.innerHTML = `<div class="error">⚠ ${e.message}</div>`; }
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

    document.querySelectorAll('#tab-damage select[id$="-nature"], #tab-combat select[id$="-nature"], #tab-bench select[id$="-nature"]')
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
    builders.dblMine = makeBuilder($('dbl-mine'), { withSP: true });
    builders.dblOpp = makeBuilder($('dbl-opp'), { withSP: true });

    builders.draft.setEntries(entriesFrom(SAMPLES.lineup, 'lineup'));
    builders.team.setEntries(entriesFrom(SAMPLES.team, 'team'));
    builders.prevMine.setEntries(entriesFrom(SAMPLES.team, 'team'));
    builders.prevOpp.setEntries(entriesFrom(SAMPLES.opponent, 'team'));
    dblSample();

    // Listeners
    $('tab-damage').querySelectorAll('input, select').forEach((el) => {
      el.addEventListener('input', computeDamage); el.addEventListener('change', computeDamage);
    });
    $('c-run').addEventListener('click', runCombat);
    $('c-decide').addEventListener('click', runDecide);
    $('c-nash').addEventListener('click', runNash);
    $('c-opp-likely').addEventListener('click', fillLikelyOpponent);
    $('draft-run').addEventListener('click', runDraft);
    $('draft-sample').addEventListener('click', () => builders.draft.setEntries(entriesFrom(SAMPLES.lineup, 'lineup')));
    $('team-run').addEventListener('click', runTeam);
    $('team-sample').addEventListener('click', () => builders.team.setEntries(entriesFrom(SAMPLES.team, 'team')));
    $('team-frombox').addEventListener('click', async () => {
      try { const r = await api('/api/roster'); builders.team.setEntries(r.roster); } catch (e) { /* */ }
    });
    $('team-import').addEventListener('click', importPaste);
    $('prev-run').addEventListener('click', runPreview);
    $('prev-sample').addEventListener('click', () => {
      builders.prevMine.setEntries(entriesFrom(SAMPLES.team, 'team'));
      builders.prevOpp.setEntries(entriesFrom(SAMPLES.opponent, 'team'));
    });
    $('dbl-run').addEventListener('click', runDoubles);
    $('dbl-sample').addEventListener('click', dblSample);
    $('os-run').addEventListener('click', runOutspeed);
    $('sv-run').addEventListener('click', runSurvive);
    $('ko-run').addEventListener('click', runKo);
    // Optimiseur de spread : conteneur d'objectifs + exemples de départ.
    spObjs = $('sp-objs');
    if (spObjs) {
      $('sp-nature').value = 'adamant';
      addObjRow({ kind: 'ko', species: 'Garchomp', nature: 'jolly', move: 'icepunch', num: 1 });
      addObjRow({ kind: 'survive', species: 'Garchomp', nature: 'adamant', move: 'earthquake', num: 32 });
      addObjRow({ kind: 'outspeed', species: 'Amoonguss', nature: 'sassy', num: 0 });
      $('sp-add').addEventListener('click', () => addObjRow({}));
      $('sp-run').addEventListener('click', runSpread);
    }
    // Natures par défaut plus parlantes pour les seuils.
    if ($('os-me-nature')) { $('os-me-nature').value = 'jolly'; $('sv-def-nature').value = 'careful'; }
    if ($('sv-atk-nature')) { $('sv-atk-nature').value = 'adamant'; $('ko-atk-nature').value = 'adamant'; }
    if ($('ko-def-nature')) $('ko-def-nature').value = 'jolly';
    $('box-save').addEventListener('click', saveBox);
    $('box-reload').addEventListener('click', loadBox);

    loadBox();
    computeDamage();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
