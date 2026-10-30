// ═══════════════════════════════════════════════════════════════════════════════
// Mode souris : panneau de boutons (docs/PROPOSITION_MENUS_SOURIS.html)
// Inséré dans index.html par overlay/__init__.py:_load_html, avant le script principal.
//
// Trois modes, choisis par le bouton à côté de ⚙ (ou /config mode) :
//   console : la ligne de commande seule ;
//   mixte   : la colonne des thèmes à droite de la sortie, la ligne de commande gardée ;
//             un thème ouvre son groupe, un second clic dessus (ou Échap) le referme ;
//   souris  : un groupe toujours ouvert, sans ligne de commande.
// Le panneau est une colonne à droite, en haut : la sortie garde toute sa hauteur.
// Chaque bouton envoie une commande existante, tirée du catalogue reçu du serveur
// (uexinfo/overlay/menus.py, message « menus ») : boutons et saisie passent par le
// même dispatch. Les fonctions du script principal (sendCmd, send, esc…) ne sont
// appelées qu'au clic, une fois ce script chargé.
// ═══════════════════════════════════════════════════════════════════════════════

window.MousePanel = (() => {
  const MODES = ['console', 'mixte', 'souris'];
  const MODE_INFO = {
    console: {icon: '⌨',   label: 'Console'},
    mixte:   {icon: '⌨🖱', label: 'Mixte'},
    souris:  {icon: '🖱',   label: 'Souris'},
  };
  const elPanel  = document.getElementById('mouse-panel');
  const elThemes = document.getElementById('mp-themes');
  const elPath   = document.getElementById('mp-path');
  const elGroup  = document.getElementById('mp-group');
  const elPrev   = document.getElementById('mp-preview');
  const elBtn    = document.getElementById('sb-mode');

  let mode = 'console';
  let themes = [];
  let themeIdx = -1;     // thème ouvert, -1 : aucun
  let path = [];         // indices des groupes ouverts sous le thème

  function _html(t) { return String(t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

  /** Applique le mode `m` ; `save` l'enregistre côté serveur (choix du joueur). */
  function setMode(m, save = false) {
    if (!MODES.includes(m)) m = 'console';
    const out = document.getElementById('output');
    const atBottom = out && out.scrollHeight - out.scrollTop - out.clientHeight < 8;
    mode = m;
    MODES.forEach(x => document.body.classList.toggle('mode-' + x, x === m));
    const next = MODES[(MODES.indexOf(m) + 1) % MODES.length];
    elBtn.textContent = MODE_INFO[m].icon;
    elBtn.title = `Mode ${MODE_INFO[m].label} — clic : mode ${MODE_INFO[next].label}`;
    if (m === 'souris' && themeIdx < 0 && themes.length) themeIdx = 0;   // un groupe toujours ouvert
    render();
    if (out && atBottom) out.scrollTop = out.scrollHeight;
    if (save) send({type: 'ui_mode', value: m});
  }

  /** Reçoit le catalogue des thèmes (connexion au serveur). */
  function load(list) {
    themes = Array.isArray(list) ? list : [];
    if (themeIdx >= themes.length) { themeIdx = -1; path = []; }
    if (mode === 'souris' && themeIdx < 0 && themes.length) themeIdx = 0;
    render();
  }

  function openTheme(i) { themeIdx = i; path = []; render(); }

  function closeGroup() {
    if (mode === 'souris') return;
    themeIdx = -1; path = []; render();
  }

  function isOpen() { return themeIdx >= 0 && themeIdx < themes.length; }

  function _button(cls, html, title, onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = cls;
    b.innerHTML = html;
    if (title) b.title = title;
    b.addEventListener('click', onClick);
    return b;
  }

  function _preview(cmd) { elPrev.textContent = cmd ? '› ' + cmd : ''; }

  function render() {
    // Colonne des thèmes
    elThemes.innerHTML = '';
    themes.forEach((th, i) => {
      const b = _button('mp-theme' + (i === themeIdx ? ' active' : ''),
        `<span class="mp-ic">${_html(th.icon || '')}</span>` +
        `<span class="mp-long">${_html(th.label)}</span>` +
        `<span class="mp-short">${_html(th.short || th.label)}</span>`,
        th.label,
        () => (i === themeIdx && mode !== 'souris') ? closeGroup() : openTheme(i));
      elThemes.appendChild(b);
    });

    elPanel.classList.toggle('open', isOpen());
    elPath.innerHTML = '';
    elGroup.innerHTML = '';
    _preview('');
    if (!isOpen()) return;

    // Chemin cliquable : remonte au thème ou à un groupe
    let node = themes[themeIdx];
    const segs = [[node.label, []]];
    path.forEach((idx, depth) => {
      node = node.kids[idx];
      segs.push([node.label, path.slice(0, depth + 1)]);
    });
    segs.forEach(([label, p], i) => {
      if (i) elPath.appendChild(Object.assign(document.createElement('span'), {className: 'mp-sep', textContent: '▸'}));
      const last = i === segs.length - 1;
      const s = Object.assign(document.createElement('span'), {
        className: 'mp-seg' + (last ? ' cur' : ''), textContent: label,
      });
      if (!last) s.addEventListener('click', () => { path = p; render(); });
      elPath.appendChild(s);
    });

    // Boutons du groupe ouvert
    node.kids.forEach((k, i) => {
      const grp = Array.isArray(k.kids);
      const b = _button('mp-btn ' + (grp ? 'mp-grp' : 'mp-run'),
        _html(k.label) + (grp ? ' <span class="mp-arrow">▸</span>' : ''),
        grp ? 'Ouvrir le groupe' : k.cmd + (k.note ? ' — ' + k.note : ''),
        () => {
          if (grp) { path = path.concat(i); render(); return; }
          if (document.body.classList.contains('busy')) return;   // une commande à la fois
          sendCmd(k.cmd, true);
        });
      if (!grp) {
        b.addEventListener('mouseenter', () => _preview(k.cmd));
        b.addEventListener('mouseleave', () => _preview(''));
      }
      elGroup.appendChild(b);
    });
  }

  elBtn.addEventListener('click', () => setMode(MODES[(MODES.indexOf(mode) + 1) % MODES.length], true));

  document.getElementById('mp-stop').addEventListener('click', () => {
    send({type: 'cancel'});
    appendSystem('⏳ Annulation…', 'var(--yellow)');
  });

  // Échap referme le groupe en mode mixte, quand rien d'autre ne l'attend
  // (complétion ouverte, commande en cours, sélecteur ou formulaire de scan).
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || mode !== 'mixte' || !isOpen()) return;
    if (document.body.classList.contains('busy')) return;
    const comp = document.getElementById('completion-list');
    if (comp && comp.style.display !== 'none') return;
    if (document.querySelector('#select-overlay.open, #scan-overlay.open')) return;
    closeGroup();
  }, true);

  return {setMode, load};
})();
