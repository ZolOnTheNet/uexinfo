// ═══════════════════════════════════════════════════════════════════════════════
// Réglages en formulaire : tiroir qui arrive de la droite (⚙ de la barre d'état, /config edit)
// Inséré dans index.html par overlay/__init__.py:_load_html, avant le script principal.
//
// Onglets et champs viennent du serveur (uexinfo/overlay/settings_form.py, message
// « settings_schema ») ; les valeurs et la flotte arrivent par « settings », à la connexion
// puis après chaque commande /config, /ship, /auto. Un changement envoie « settings_set »
// (clé, valeur) ou « settings_ship » (action sur un vaisseau) : le serveur en fait la
// commande /config ou /ship existante, visible dans la sortie. La page ne construit
// aucune commande et ne calcule aucune valeur.
//
// Vaisseaux : clic = fiche du vaisseau (second tiroir), double-clic = vaisseau actif.
// ═══════════════════════════════════════════════════════════════════════════════

window.SettingsPanel = (() => {
  const elDrawer = document.getElementById('settings-drawer');
  const elTabs   = elDrawer.querySelector('.st-tabs');
  const elBody   = elDrawer.querySelector('.st-body');
  const elFoot   = elDrawer.querySelector('.st-foot');
  const elShip   = document.getElementById('ship-drawer');

  let tabs = [], sizes = [], vehicles = [];
  let values = {}, ships = [];
  let tabId = 'ships';
  let shipName = null;      // fiche ouverte
  let ddOpen = null;        // liste déroulante ouverte (clé du champ)
  let removeArmed = false;  // « Retirer » demande un second clic
  const queue = [];         // messages en attente pendant une commande

  function _h(t) { return String(t ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
  function _busy() { return document.body.classList.contains('busy'); }

  function _post(msg) {
    if (_busy()) queue.push(msg); else send(msg);
  }
  /** Fin d'une commande : envoie le message suivant (le serveur n'en garde qu'un en attente). */
  function flush() { if (queue.length && !_busy()) send(queue.shift()); }

  function setValue(key, v) { _post({type: 'settings_set', key, value: String(v)}); }
  function shipAction(action, name, extra = {}) { _post({type: 'settings_ship', action, name, ...extra}); }

  // ── Messages du serveur ────────────────────────────────────────────────────
  function schema(msg) {
    tabs = msg.tabs || []; sizes = msg.sizes || []; vehicles = msg.vehicles || [];
    if (!tabs.some(t => t.id === tabId) && tabs.length) tabId = tabs[0].id;
    render();
  }
  function update(msg) {
    values = msg.values || {}; ships = msg.ships || [];
    if (shipName && !ships.some(s => s.name === shipName)) shipName = null;   // retiré
    render();
  }

  function isOpen() { return elDrawer.classList.contains('open'); }
  function open(tab) {
    if (tab && tabs.some(t => t.id === tab)) tabId = tab;
    elDrawer.classList.add('open');
    render();
  }
  function close() { closeShip(); elDrawer.classList.remove('open'); ddOpen = null; }
  function toggle() { isOpen() ? close() : open(); }
  function openShip(name) { shipName = name; removeArmed = false; renderShip(); elShip.classList.add('open'); }
  function closeShip() { shipName = null; elShip.classList.remove('open'); }

  // ── Rendu ──────────────────────────────────────────────────────────────────
  function render() {
    // Saisie en cours : retrouver le champ et son texte après le rendu
    const act = document.activeElement;
    const keep = act && elBody.contains(act) && act.dataset.key
      ? {key: act.dataset.key, val: act.value, pos: act.selectionStart} : null;

    elTabs.innerHTML = '';
    tabs.forEach(t => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'st-tab' + (t.id === tabId ? ' active' : '');
      b.innerHTML = `<span class="st-ic">${_h(t.icon)}</span><span class="st-long">${_h(t.label)}</span>`
                  + `<span class="st-short">${_h(t.short || t.label)}</span>`;
      b.title = t.label;
      b.addEventListener('click', () => { tabId = t.id; ddOpen = null; render(); });
      elTabs.appendChild(b);
    });

    elBody.innerHTML = '';
    const tab = tabs.find(t => t.id === tabId);
    if (tab) {
      if (tab.id === 'ships') renderFleet();
      tab.fields.forEach(f => elBody.appendChild(_field(f)));
    }
    if (keep) {
      const inp = elBody.querySelector(`[data-key="${CSS.escape(keep.key)}"]`);
      if (inp) { inp.value = keep.val; inp.focus(); try { inp.setSelectionRange(keep.pos, keep.pos); } catch (_) {} }
    }
    elFoot.textContent = 'Chaque changement passe par la commande /config ou /ship, affichée dans la sortie.';
    if (shipName) renderShip();
  }

  function _field(f) {
    if (f.kind === 'section') {
      return Object.assign(document.createElement('div'), {className: 'st-sec', textContent: f.label});
    }
    const row = document.createElement('div');
    row.className = 'st-row';
    row.appendChild(Object.assign(document.createElement('div'), {className: 'st-label', textContent: f.label}));
    const cur = values[f.key] ?? '';

    if (f.kind === 'choice') row.appendChild(_dropdown(f, cur));
    else if (f.kind === 'flags') row.appendChild(_flags(f, cur));
    else {
      const wrap = document.createElement('div');
      wrap.className = 'st-input';
      const inp = document.createElement('input');
      inp.dataset.key = f.key;
      inp.value = cur;
      if (f.kind === 'number') {
        Object.assign(inp, {type: 'number', min: f.min, max: f.max, step: f.step});
      } else {
        inp.type = 'text';
        inp.spellcheck = false;
        if (f.placeholder) inp.placeholder = f.placeholder;
      }
      inp.addEventListener('change', () => {
        if (f.kind === 'number' && !inp.checkValidity()) { inp.classList.add('bad'); return; }
        inp.classList.remove('bad');
        if (inp.value.trim() !== String(cur)) setValue(f.key, inp.value.trim());
      });
      inp.addEventListener('keydown', e => { if (e.key === 'Enter') inp.blur(); });
      wrap.appendChild(inp);
      if (f.unit) wrap.appendChild(Object.assign(document.createElement('span'), {className: 'st-unit', textContent: f.unit}));
      if (f.kind === 'number') wrap.appendChild(Object.assign(document.createElement('span'),
        {className: 'st-unit', textContent: `${f.min} – ${f.max}`}));
      row.appendChild(wrap);
    }
    if (f.help) row.appendChild(Object.assign(document.createElement('div'), {className: 'st-help', textContent: f.help}));
    return row;
  }

  /** Liste déroulante : mot-clé, puis son explication. */
  function _dropdown(f, cur) {
    const dd = document.createElement('div');
    dd.className = 'st-dd' + (ddOpen === f.key ? ' open' : '');
    const c = f.choices.find(x => x.v === cur);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'st-dd-cur';
    btn.innerHTML = `<b>${_h(cur || '—')}</b><span>${_h(c ? c.t : 'valeur hors liste')}</span><i>▾</i>`;
    btn.addEventListener('click', () => { ddOpen = ddOpen === f.key ? null : f.key; render(); });
    dd.appendChild(btn);
    if (ddOpen === f.key) {
      const list = document.createElement('div');
      list.className = 'st-dd-list';
      f.choices.forEach(x => {
        const o = document.createElement('div');
        o.className = 'st-dd-opt' + (x.v === cur ? ' sel' : '');
        o.innerHTML = `<b>${_h(x.v)}</b><span>${_h(x.t)}</span>`;
        o.addEventListener('click', () => { ddOpen = null; if (x.v !== cur) setValue(f.key, x.v); render(); });
        list.appendChild(o);
      });
      dd.appendChild(list);
    }
    return dd;
  }

  /** Mots-clés à cocher (options par défaut). */
  function _flags(f, cur) {
    const on = new Set(String(cur).split(/\s+/).filter(Boolean));
    const box = document.createElement('div');
    box.className = 'st-flags';
    f.choices.forEach(x => {
      const lab = document.createElement('label');
      lab.className = 'st-flag';
      lab.innerHTML = `<input type="checkbox"${on.has(x.v) ? ' checked' : ''}><b>${_h(x.v)}</b><span>${_h(x.t)}</span>`;
      lab.querySelector('input').addEventListener('change', e => {
        e.target.checked ? on.add(x.v) : on.delete(x.v);
        setValue(f.key, f.choices.map(y => y.v).filter(v => on.has(v)).join(' '));
      });
      box.appendChild(lab);
    });
    return box;
  }

  // ── Flotte ─────────────────────────────────────────────────────────────────
  function renderFleet() {
    const sec = Object.assign(document.createElement('div'), {className: 'st-sec', textContent: 'Ma flotte'});
    elBody.appendChild(sec);
    elBody.appendChild(Object.assign(document.createElement('div'), {className: 'st-help',
      textContent: 'Clic : caractéristiques du vaisseau · double-clic : vaisseau actif'}));
    const list = document.createElement('div');
    list.className = 'st-fleet';
    if (!ships.length) list.appendChild(Object.assign(document.createElement('div'),
      {className: 'st-help', textContent: 'Aucun vaisseau — ajoute le tien ci-dessous.'}));
    ships.forEach(s => {
      const it = document.createElement('div');
      it.className = 'st-ship' + (s.active ? ' active' : '') + (s.name === shipName ? ' sel' : '');
      it.innerHTML = `<span class="st-ship-name">${s.active ? '&gt;&gt;&gt; ' + _h(s.name) + ' &lt;&lt;&lt;' : _h(s.name)}</span>`
                   + `<span class="st-ship-scu">${s.scu ? s.scu + ' SCU' : '? SCU'}</span>`;
      let t = null;   // le clic attend : un double-clic ne doit pas ouvrir la fiche
      it.addEventListener('click', () => { clearTimeout(t); t = setTimeout(() => openShip(s.name), 250); });
      it.addEventListener('dblclick', () => { clearTimeout(t); if (!s.active) shipAction('set', s.name); });
      list.appendChild(it);
    });
    elBody.appendChild(list);

    const add = document.createElement('div');
    add.className = 'st-add';
    add.innerHTML = `<input type="text" list="st-vehicles" placeholder="Ajouter un vaisseau (nom UEX)" spellcheck="false">`
                  + `<button type="button">＋ Ajouter</button><datalist id="st-vehicles">`
                  + vehicles.map(v => `<option value="${_h(v)}">`).join('') + `</datalist>`;
    const inp = add.querySelector('input');
    const go = () => { if (inp.value.trim()) { shipAction('add', inp.value.trim()); inp.value = ''; } };
    add.querySelector('button').addEventListener('click', go);
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
    elBody.appendChild(add);
  }

  /** Fiche d'un vaisseau : capacité et conteneurs, enregistrés par /ship cargo. */
  function renderShip() {
    const s = ships.find(x => x.name === shipName);
    if (!s) { closeShip(); return; }
    const m = s.model;
    const grid = Object.assign({}, s.cargo);
    elShip.innerHTML = `
      <div class="st-head"><span class="st-title">✈ ${_h(s.name)}</span><button type="button" class="st-close" title="Fermer (Échap)">✕</button></div>
      <div class="st-body">
        ${s.active ? '<div class="st-active">Vaisseau actif</div>' : ''}
        ${m ? `<div class="st-help">Modèle UEX : ${_h(m.maker)} · ${m.scu || '?'} SCU${m.pad ? ' · pad ' + _h(m.pad) : ''}</div>` : '<div class="st-help">Vaisseau inconnu de UEX : capacité à saisir.</div>'}
        <div class="st-sec">Conteneurs (nombre par taille)</div>
        <div class="st-grid">${sizes.map(z => `<label><span>${z} SCU</span><input type="number" min="0" max="999" data-size="${z}" value="${grid[z] || 0}"></label>`).join('')}</div>
        <div class="st-help st-total"></div>
        <div class="st-row"><div class="st-label">Capacité</div>
          <div class="st-input"><input type="number" min="0" max="99999" class="st-scu" value="${s.scu || 0}"><span class="st-unit">SCU</span></div>
          <div class="st-help">Suit le total des conteneurs, sauf si tu la changes.</div></div>
        <div class="st-actions">
          ${m && Object.keys(m.grid || {}).length ? '<button type="button" data-a="model">Grille du modèle</button>' : ''}
          <button type="button" data-a="save" class="primary">Enregistrer</button>
          ${s.active ? '' : '<button type="button" data-a="set">Vaisseau actif</button>'}
          <button type="button" data-a="remove" class="danger">Retirer</button>
        </div>
      </div>`;
    const inputs = [...elShip.querySelectorAll('[data-size]')];
    const scu = elShip.querySelector('.st-scu');
    const total = () => inputs.reduce((n, i) => n + (+i.dataset.size) * (parseInt(i.value) || 0), 0);
    let scuEdited = (s.scu || 0) !== total() && total() > 0;
    const showTotal = () => {
      elShip.querySelector('.st-total').textContent = `Total des conteneurs : ${total()} SCU`;
      if (!scuEdited) scu.value = total();
    };
    inputs.forEach(i => i.addEventListener('input', showTotal));
    scu.addEventListener('input', () => { scuEdited = true; });
    showTotal();
    if (!total()) scu.value = s.scu || 0;

    elShip.querySelector('.st-close').addEventListener('click', closeShip);
    elShip.querySelectorAll('[data-a]').forEach(b => b.addEventListener('click', () => {
      const a = b.dataset.a;
      if (a === 'model') {
        inputs.forEach(i => { i.value = (m.grid || {})[i.dataset.size] || 0; });
        scuEdited = false; showTotal();
      } else if (a === 'save') {
        const cargo = {};
        inputs.forEach(i => { const n = parseInt(i.value) || 0; if (n > 0) cargo[i.dataset.size] = n; });
        shipAction('cargo', s.name, {cargo, scu: parseInt(scu.value) || 0});
      } else if (a === 'set') {
        shipAction('set', s.name);
      } else if (a === 'remove') {
        if (!removeArmed) { removeArmed = true; b.textContent = 'Retirer ? (confirmer)'; return; }
        shipAction('remove', s.name); closeShip();
      }
    }));
  }

  // ── Évènements ─────────────────────────────────────────────────────────────
  elDrawer.querySelector('.st-head .st-close').addEventListener('click', close);
  document.addEventListener('click', e => {
    if (ddOpen && !e.target.closest('.st-dd')) { ddOpen = null; render(); }
  });
  // Échap ferme la fiche, puis le tiroir (avant les autres usages d'Échap)
  window.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || !isOpen()) return;
    if (document.querySelector('#select-overlay.open, #scan-overlay.open')) return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (ddOpen) { ddOpen = null; render(); }
    else if (shipName) closeShip();
    else close();
  }, true);

  return {schema, update, open, close, toggle, flush};
})();
