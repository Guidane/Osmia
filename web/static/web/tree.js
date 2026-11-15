/* The trees on the left (.browser-tree) fold: a node with nodes under it (a deeper --depth right after it) gets a ▸ / ▾
   in front that shows or hides them, without following the node's link. A long tree starts folded but for the way down
   to the node picked (.on, .open); a short one starts open. What was opened or closed stays so in this browser. */
(function () {
  'use strict';
  var LONG = 15;   // nodes: more than this, and it starts folded
  function depth(a) { return parseInt(a.style.getPropertyValue('--depth'), 10) || 0; }

  document.querySelectorAll('.browser-tree').forEach(function (nav) {
    var nodes = Array.prototype.slice.call(nav.querySelectorAll(':scope > a'));
    if (!nodes.some(function (a, i) { return nodes[i + 1] && depth(nodes[i + 1]) > depth(a); })) return;   // flat: nothing to fold
    var key = 'osmia-tree:' + location.pathname + ':' + (nav.getAttribute('aria-label') || ''), saved = {};
    try { saved = JSON.parse(localStorage.getItem(key) || '{}'); } catch (e) { saved = {}; }
    var folded = nodes.length > LONG, open = new Map();

    nodes.forEach(function (a, i) {
      var label = a.querySelector('span');
      var twist = document.createElement('span');
      twist.className = 'tree-twist';
      if (nodes[i + 1] && depth(nodes[i + 1]) > depth(a)) {
        var id = a.getAttribute('href');
        open.set(a, id in saved ? saved[id] : !folded || a.classList.contains('on') || a.classList.contains('open'));
        twist.setAttribute('role', 'button');
        twist.setAttribute('tabindex', '0');
        twist.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); toggle(a); });
        twist.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); toggle(a); }
        });
      }
      if (label) label.insertBefore(twist, label.firstChild);
    });

    function show() {   // a node shows when every node above it is open
      var shut = [];    // the depths of the closed nodes above, as the tree goes down
      nodes.forEach(function (a) {
        var d = depth(a);
        while (shut.length && shut[shut.length - 1] >= d) shut.pop();
        a.hidden = shut.length > 0;
        if (open.has(a)) {
          var twist = a.querySelector('.tree-twist');
          twist.textContent = open.get(a) ? '▾' : '▸';
          twist.setAttribute('aria-expanded', open.get(a) ? 'true' : 'false');
          twist.title = open.get(a) ? 'Fold' : 'Unfold';
          if (!open.get(a)) shut.push(d);
        }
      });
    }
    function toggle(a) {
      open.set(a, !open.get(a));
      saved[a.getAttribute('href')] = open.get(a);
      try { localStorage.setItem(key, JSON.stringify(saved)); } catch (e) { /* not kept: fine */ }
      show();
    }
    show();
  });
})();
