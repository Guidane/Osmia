/* A thing's page as a tree, a table and details (.browser[data-sections]): the tree's links (a[data-section])
   show the middle panel of that name ([data-panel]), kept in the address (#name), else the first. The right pane
   ([data-detail]) shows the thing itself; a row of a panel with its details (tr[data-brief-url]) picked by a click,
   Enter or the arrow keys shows those instead, until another section (or the thing, at the top of the tree) is
   picked. A panel marked data-wide takes the right pane's room too (a drawing). A "brief" event on the document tells
   when details were put there; a resize when a panel shows (a drawing in it fits itself). */
(function () {
  'use strict';
  var root = document.querySelector('.browser[data-sections]');
  if (!root) return;
  var links = Array.prototype.slice.call(root.querySelectorAll('a[data-section]'));
  var panels = Array.prototype.slice.call(root.querySelectorAll('[data-panel]'));
  var detail = root.querySelector('[data-detail]'), home = null, picked = null, asked = 0;
  if (detail) {   // the thing's own details stay as they are (their cards work), hidden while a row's are shown
    home = document.createElement('div');
    home.dataset.home = '';
    while (detail.firstChild) home.appendChild(detail.firstChild);
    picked = document.createElement('div');
    picked.dataset.picked = '';
    picked.hidden = true;
    detail.appendChild(home);
    detail.appendChild(picked);
  }

  function told() { document.dispatchEvent(new CustomEvent('brief', { detail: detail })); }
  function back() {   // the thing itself on the right again
    if (!detail) return;
    asked += 1;
    root.querySelectorAll('tr[data-brief-url].on').forEach(function (r) { r.classList.remove('on'); });
    if (!picked.hidden) { picked.hidden = true; picked.innerHTML = ''; home.hidden = false; told(); }
  }
  function show(name) {
    var named = function (n) { return panels.find(function (p) { return p.dataset.panel === n; }); };
    var panel = named(name) || (links[0] && named(links[0].dataset.section)) || panels[0];   // else the tree's first
    if (!panel) return;
    links.forEach(function (a) { a.classList.toggle('on', a.dataset.section === panel.dataset.panel); });
    panels.forEach(function (p) { p.hidden = p !== panel; });
    root.classList.toggle('wide', panel.hasAttribute('data-wide'));
    back();
    window.dispatchEvent(new Event('resize'));
  }
  function pick(row) {
    root.querySelectorAll('tr[data-brief-url]').forEach(function (r) { r.classList.toggle('on', r === row); });
    var mine = ++asked;
    fetch(row.dataset.briefUrl, { headers: { 'X-Requested-With': 'fetch' } }).then(function (r) { return r.text(); }).then(function (html) {
      if (mine !== asked) return;
      picked.innerHTML = html;
      picked.hidden = false;
      home.hidden = true;
      told();
    });
  }

  links.forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      history.replaceState(null, '', '#' + a.dataset.section);
      show(a.dataset.section);
    });
  });
  root.addEventListener('click', function (e) {
    var row = e.target.closest('tr[data-brief-url]');
    if (!row || !detail || e.target.closest('a, input, button, select, form, textarea, label')) return;
    pick(row);
  });
  root.addEventListener('keydown', function (e) {
    var row = e.target.closest && e.target.closest('tr[data-brief-url]');
    if (!row || e.target !== row) return;
    var rows = Array.prototype.slice.call(row.closest('[data-panel]').querySelectorAll('tr[data-brief-url]')), i = rows.indexOf(row);
    var to = e.key === 'ArrowDown' ? rows[i + 1] : e.key === 'ArrowUp' ? rows[i - 1] : e.key === 'Enter' ? row : null;
    if (!to) return;
    e.preventDefault();
    to.focus();
    pick(to);
  });
  root.querySelectorAll('tr[data-brief-url]').forEach(function (r) { if (!r.hasAttribute('tabindex')) r.tabIndex = 0; });
  show(location.hash.slice(1));
  told();
})();
