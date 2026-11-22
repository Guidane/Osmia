/* The family popup (inventory.picker): the branches of families as a tree on the left, the families of the one picked
   (and of those under it) with their face (the pin side; a socket gender's mirrored), found by name.
   FamilyPicker.open(current, onPick): opened on the branch of ``current``; picking a family (any gender) or one of its
   genders calls onPick with its name ("D-sub 9", "D-sub 9 / socket").
   On a form, a hidden [data-family-value] with its [data-family-open] button and [data-family-clear] is filled in.
   The tree folds: it opens on the way down to the family picked. */
(function () {
  'use strict';
  if (window.FamilyPicker) return;
  var dialog = document.querySelector('.family-finder');
  if (!dialog) return;
  var cards = dialog.querySelector('[data-family-cards]'), search = dialog.querySelector('[data-family-q]');
  var treeNav = dialog.querySelector('[data-family-tree]');
  var data = JSON.parse(document.getElementById('family-data').textContent);
  if (Array.isArray(data)) data = { families: data, tree: [] };   // as a server not yet restarted after an update sends it
  data.tree = data.tree || [];
  var families = data.families || [], branch = null, current = '', picked = null;

  function mirrored(face) {
    return Object.assign({}, face, {
      contacts: face.contacts.map(function (c) { return [c[0], face.w - c[1], c[2]]; }),
      outline: (face.outline || []).map(function (p) { return [face.w - p[0], p[1]]; })
    });
  }
  function mine(f) { return current === f.name || current.indexOf(f.name + ' / ') === 0; }
  function button(parent, label, value) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn small' + (current === value ? ' primary' : '');
    b.textContent = label;
    b.addEventListener('click', function () { dialog.close(); if (picked) picked(value); });
    parent.appendChild(b);
    return b;
  }
  function show() {
    var q = search.value.trim().toLowerCase();
    cards.innerHTML = '';
    families.filter(function (f) {
      return (!q || f.name.toLowerCase().indexOf(q) !== -1) && (!branch || branch.below.indexOf(f.branch) !== -1);
    }).forEach(function (f) {
      var card = document.createElement('section');
      card.className = 'family-card' + (mine(f) ? ' on' : '');
      var title = document.createElement('h4');
      title.textContent = f.name;
      card.appendChild(title);
      var svg = null, all = f.face ? f.face.contacts.map(function (c) { return [c[0], '']; }) : [];
      if (f.face) {
        svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'pinout-drawing');
        card.appendChild(svg);
        Pinout.face(svg, { face: f.face, pins: all });
      }
      var picks = document.createElement('div');
      picks.className = 'family-genders';
      f.genders.forEach(function (g) {
        var b = button(picks, g.name, g.value);
        if (svg) b.addEventListener('mouseenter', function () { Pinout.face(svg, { face: g.socket ? mirrored(f.face) : f.face, pins: all }); });
      });
      button(picks, 'Any', f.name);
      card.appendChild(picks);
      cards.appendChild(card);
    });
    if (!cards.children.length) cards.innerHTML = '<p class="muted small pad">No families here.</p>';
    treeNav.querySelectorAll('button').forEach(function (b, i) { b.classList.toggle('on', i === 0 ? !branch : data.tree[i - 1] === branch); });
  }
  // the tree folds: a branch with branches under it has a ▸ / ▾; it opens on the way down to the family picked
  var opened = {}, buttons = [];
  function above(node) {   // the branches it is under
    return data.tree.filter(function (n) { return n !== node && n.below.indexOf(node.id) !== -1; });
  }
  function fold() {
    buttons.forEach(function (b) {
      if (!b.node) return;
      b.hidden = above(b.node).some(function (n) { return !opened[n.id]; });
      if (b.twist) b.twist.textContent = opened[b.node.id] ? '▾' : '▸';
    });
  }
  function treeButton(label, node, depth, parent) {   // a branch on the left: its families (and those of the branches under it)
    var b = document.createElement('button');
    b.type = 'button';
    b.node = node;
    b.style.paddingLeft = (0.5 + depth) + 'em';
    if (node && parent) {
      b.twist = document.createElement('span');
      b.twist.className = 'tree-twist';
      b.twist.setAttribute('role', 'button');
      b.twist.addEventListener('click', function (e) { e.stopPropagation(); opened[node.id] = !opened[node.id]; fold(); });
      b.appendChild(b.twist);
    } else if (node) {
      b.appendChild(document.createElement('span')).className = 'tree-twist';
    }
    b.appendChild(document.createTextNode(label));
    b.addEventListener('click', function () {
      branch = node;
      if (node && parent) opened[node.id] = true;   // picked: what is under it shows too
      fold();
      show();
    });
    treeNav.appendChild(b);
    buttons.push(b);
  }
  treeButton('All families', null, 0);
  data.tree.forEach(function (node, i) {
    var next = data.tree[i + 1];
    treeButton(node.name, node, node.depth + 1, !!(next && next.depth > node.depth));
  });
  fold();
  treeNav.hidden = !data.tree.length;
  search.addEventListener('input', show);
  dialog.querySelector('[data-family-close]').addEventListener('click', function () { dialog.close(); });

  window.FamilyPicker = {
    open: function (now, onPick) {
      current = now || '';
      picked = onPick;
      var f = families.filter(mine)[0];
      branch = f && f.branch ? data.tree.filter(function (n) { return n.id === f.branch; })[0] || null : null;
      opened = {};
      if (branch) above(branch).concat([branch]).forEach(function (n) { opened[n.id] = true; });
      fold();
      search.value = '';
      show();
      dialog.showModal();
      search.focus();
    }
  };

  // a form's field
  var input = document.querySelector('[data-family-value]');
  if (!input) return;
  var open = document.querySelector('[data-family-open]'), clear = document.querySelector('[data-family-clear]');
  function set(value) {
    input.value = value;
    input.dataset.current = value;
    open.textContent = value || 'Choose…';
    clear.hidden = !value;
  }
  open.addEventListener('click', function () { FamilyPicker.open(input.dataset.current || input.value, set); });
  clear.addEventListener('click', function () { set(''); });
})();
