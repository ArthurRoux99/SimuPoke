/* SimuPoke — amorçage Pyodide pour l'application complète.
 *
 * Fait tourner le moteur Python (calc + delta, B1/B2/B3, seuils, recherche)
 * DANS le navigateur via Pyodide, et détourne `window.fetch` : tout appel
 * `/api/*` est routé vers le dispatcher Python `simupoke.server.dispatch_json`.
 * Le frontend hébergé (`app.js`) fonctionne ainsi à l'identique, sans serveur.
 *
 * `app.js` s'exécute sans attendre : son premier `fetch('/api/meta')` est mis en
 * file par le shim, qui patiente jusqu'à ce que Pyodide soit prêt.
 */
(function () {
  'use strict';
  var PYODIDE_INDEX = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
  var origFetch = window.fetch.bind(window);

  // PWA : installe le service worker (hors-ligne + installable). Sans effet en
  // contexte non sécurisé (file://) ; échoue en silence.
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('./sw.js').catch(function () {});
    });
  }

  // --- Voile de chargement -------------------------------------------------
  var veil = document.createElement('div');
  veil.setAttribute('id', 'sp-veil');
  veil.style.cssText =
    'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;' +
    'justify-content:center;flex-direction:column;gap:14px;text-align:center;' +
    'background:#0E141B;color:#E6EDF3;font:15px/1.5 system-ui,sans-serif;padding:24px';
  veil.innerHTML =
    '<div style="width:22px;height:22px;border:3px solid #2A3947;border-top-color:#F0B429;' +
    'border-radius:50%;animation:spspin .7s linear infinite"></div>' +
    '<div id="sp-veil-msg" style="max-width:34ch;color:#93A4B4">Démarrage du moteur Python…</div>' +
    '<style>@keyframes spspin{to{transform:rotate(360deg)}}' +
    '@media(prefers-reduced-motion:reduce){#sp-veil div{animation:none}}</style>';
  var setMsg = function (m) { var e = document.getElementById('sp-veil-msg'); if (e) e.textContent = m; };
  (document.body || document.documentElement).appendChild(veil);

  // --- Chargement du moteur (une seule fois) -------------------------------
  var ready = (async function () {
    setMsg('Chargement de Pyodide (WebAssembly)…');
    var pyodide = await loadPyodide({ indexURL: PYODIDE_INDEX });

    setMsg('Montage des données de jeu…');
    var manifest = await (await origFetch('./manifest.json')).json();
    for (var i = 0; i < manifest.data.length; i++) {
      var rel = manifest.data[i];
      var slash = rel.lastIndexOf('/');
      pyodide.FS.mkdirTree(slash >= 0 ? '/data/' + rel.slice(0, slash) : '/data');
      var text = await (await origFetch('./data/' + rel)).text();
      pyodide.FS.writeFile('/data/' + rel, text);
    }
    // Pointer le moteur vers /data AVANT tout import de simupoke.
    pyodide.runPython("import os; os.environ['SIMUPOKE_DATA_DIR']='/data'");

    setMsg('Installation du paquet simupoke…');
    await pyodide.loadPackage('micropip');
    var micropip = pyodide.pyimport('micropip');
    await micropip.install(new URL('./' + manifest.wheel, location.href).href);

    // Handle direct vers le dispatcher chaîne (JS ↔ Python).
    var dispatch = pyodide.runPython(
      'from simupoke.server import dispatch_json as _d; _d');
    setMsg('Prêt.');
    return dispatch;
  })();

  ready.then(function () {
    var v = document.getElementById('sp-veil');
    if (v) v.remove();
  }).catch(function (err) {
    setMsg('Erreur de démarrage : ' + (err && err.message ? err.message : err));
    console.error(err);
  });

  // --- Shim fetch : /api/* -> Python --------------------------------------
  window.fetch = async function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var path = url;
    try { path = new URL(url, location.href).pathname; } catch (e) { /* url relative */ }

    if (path.indexOf('/api/') !== 0 &&
        !(typeof url === 'string' && url.indexOf('/api/') === 0)) {
      return origFetch(input, init);   // fichiers statiques, etc.
    }

    var route = (typeof url === 'string' ? url : path).split('?')[0];
    if (route.indexOf('/api/') !== 0) route = path.split('?')[0];
    var query = '';
    var qi = url.indexOf('?');
    if (qi >= 0) query = url.slice(qi + 1);

    var method = (init && init.method) || 'GET';
    var body = (init && init.body) || '';

    var dispatch = await ready;
    var raw = dispatch(method.toUpperCase(), route, body, query);
    var parsed = JSON.parse(raw);
    return new Response(JSON.stringify(parsed.body), {
      status: parsed.status,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  };
})();
