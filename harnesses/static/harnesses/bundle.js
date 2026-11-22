/* A harness's bundle drawn: its trunk as a line (to scale along the page's width), each connector at the end of its
   branch where it breaks out of the trunk (the branches not to scale, their lengths written on them), and what is put
   along it: cable ties, sleeves and shrink (from where to where), where a shield is stripped back from its connector,
   splices and labels; under it the trunk's dimensions, where each branch leaves it. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, value, cls, anchor) {
    var t = el('text', { x: x, y: y, class: cls, 'text-anchor': anchor || 'middle' }, parent);
    t.textContent = value;
    return t;
  }
  function num(v) { var n = parseFloat(v); return isFinite(n) ? n : null; }
  function mm(v) { return String(Math.round(v * 10) / 10); }

  function mount(root, data) {
    var svg = root.querySelector('svg'), last = -1;
    function render() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      var trunk = num(data.trunk);
      var ends = data.ends.map(function (e) { return { e: e, along: num(e.along), reach: num(e.reach) || 0 }; })
        .filter(function (b) { return b.along !== null; });
      if (!trunk) trunk = Math.max.apply(null, [0].concat(ends.map(function (b) { return b.along; })));
      root.hidden = !trunk;
      if (!trunk) return;
      last = root.clientWidth;
      var W = Math.max(root.clientWidth - 24, 600), BOXW = 96, BOXH = 30;

      // each connector's way out of the trunk: at the trunk's ends straight on (others fanned), elsewhere up and down in turn
      var at = {};
      ends.forEach(function (b) { (at[mm(b.along)] = at[mm(b.along)] || []).push(b); });
      var turn = 0;
      Object.keys(at).sort(function (a, b) { return a - b; }).forEach(function (k) {
        at[k].forEach(function (b, i) {
          var start = b.along <= 0, end = b.along >= trunk, s = Math.SQRT1_2;
          if (start || end) {
            var h = end ? 1 : -1;
            b.dir = i === 0 ? [h, 0] : i % 2 ? [h * s, -s] : [h * s, s];
          } else {
            b.dir = turn++ % 2 ? [0, 1] : [0, -1];
            if (i > 0) b.dir = [b.dir[1] > 0 ? s : -s, b.dir[1] * s];   // more at one place: slanted apart
          }
        });
      });
      function long(b) { return b.reach > 0 ? Math.min(Math.max(b.reach * scale0, 46), 150) : (b.dir[0] && !b.dir[1] ? 0 : 30); }
      var side = { left: 30, right: 30, up: 30, down: 30 }, scale0 = (W - 320) / trunk;
      ends.forEach(function (b) {
        var L = long(b);
        if (b.dir[0] < 0) side.left = Math.max(side.left, -b.dir[0] * L + BOXW + 10);
        if (b.dir[0] > 0) side.right = Math.max(side.right, b.dir[0] * L + BOXW + 10);
        if (b.dir[1] < 0) side.up = Math.max(side.up, -b.dir[1] * L + BOXH + 10);
        if (b.dir[1] > 0) side.down = Math.max(side.down, b.dir[1] * L + BOXH + 10);
      });
      var X0 = side.left + 20, X1 = W - side.right - 20, scale = (X1 - X0) / trunk, yT = side.up + 60;
      var dimY = yT + side.down + 50, H = dimY + 40;
      svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
      svg.style.width = W + 'px';
      svg.style.height = H + 'px';

      var lines = el('g', {}, svg), marksG = el('g', {}, svg), labels = el('g', {}, svg);
      function base(b) { return [X0 + b.along * scale, yT]; }
      ends.forEach(function (b) {
        var p = base(b), L = long(b);
        b.base = p; b.len = L;
        b.tip = [p[0] + b.dir[0] * L, p[1] + b.dir[1] * L];
      });
      function point(on, at) {   // ``at`` mm along the trunk, or from a connector along its branch
        if (on === null || on === undefined) return [X0 + Math.min(Math.max(at, 0), trunk) * scale, yT];
        var b = ends.filter(function (o) { return o.e.id === on; })[0];
        if (!b) return null;
        var t = b.reach > 0 ? Math.min(Math.max(at / b.reach, 0), 1) : 0;
        return [b.tip[0] - b.dir[0] * b.len * t, b.tip[1] - b.dir[1] * b.len * t];
      }
      function across(on) {   // the way across the line a mark is on
        if (on === null || on === undefined) return [0, 1];
        var b = ends.filter(function (o) { return o.e.id === on; })[0];
        return b ? [-b.dir[1], b.dir[0]] : [0, 1];
      }

      // the trunk, the branches, the connectors
      el('line', { x1: X0, y1: yT, x2: X1, y2: yT, class: 'bd-line' }, lines);
      ends.forEach(function (b) {
        if (b.len) el('line', { x1: b.base[0], y1: b.base[1], x2: b.tip[0], y2: b.tip[1], class: 'bd-line bd-branch' }, lines);
        var cx = b.tip[0] + b.dir[0] * (BOXW / 2 + 2), cy = b.tip[1] + b.dir[1] * (BOXH / 2 + 2);
        var g = el('g', { class: 'bd-end', 'data-end': b.e.designator }, labels);
        el('rect', { x: cx - BOXW / 2, y: cy - BOXH / 2, width: BOXW, height: BOXH }, g);
        text(g, cx, cy - 1, b.e.designator, 'bd-name');
        if (b.e.what) text(g, cx, cy + 11, b.e.what, 'bd-what');
        if (b.reach > 0) {   // its branch's length, beside it
          var m = [(b.base[0] + b.tip[0]) / 2, (b.base[1] + b.tip[1]) / 2];
          if (b.dir[1]) text(labels, m[0] + 10, m[1] + 4, mm(b.reach), 'bd-dim-text', 'start');   // to its right
          else text(labels, m[0], m[1] - 10, mm(b.reach), 'bd-dim-text');                          // above it
        }
      });

      // along it
      var level = {};   // marks on the same line: their texts out at different distances, each side in turn
      data.marks.forEach(function (m, i) {
        var on = m.on === null ? null : m.on, a = point(on, num(m.start)), key = String(on);
        if (!a) return;
        var n = across(on), k = level[key] = (level[key] || 0) + 1, sideOf = k % 2 ? -1 : 1, out = 22 + (Math.floor((k - 1) / 2) % 3) * 14;
        var g = el('g', { class: 'bd-mark bd-' + m.kind, 'data-kind': m.kind }, marksG);
        var title = el('title', {}, g), words;
        var where = m.end !== '' && m.end !== null ? mm(num(m.start)) + '–' + mm(num(m.end)) : mm(num(m.start));
        if (m.kind === 'sleeve' || m.kind === 'shrink') {
          var b2 = point(on, num(m.end));
          el('line', { x1: a[0], y1: a[1], x2: b2[0], y2: b2[1], class: 'bd-stretch' }, g);
          words = (m.text || m.what || m.label) + ' ' + where;
          a = [(a[0] + b2[0]) / 2, (a[1] + b2[1]) / 2];
        } else if (m.kind === 'tie') {
          el('line', { x1: a[0] - n[0] * 9, y1: a[1] - n[1] * 9, x2: a[0] + n[0] * 9, y2: a[1] + n[1] * 9, class: 'bd-tick' }, g);
          words = (m.text || 'Tie') + ' ' + where;
        } else if (m.kind === 'strip') {   // from the connector to where its shield is cut back
          var c0 = point(on, 0), off = [n[0] * 12 * sideOf, n[1] * 12 * sideOf];
          el('path', { d: 'M' + (c0[0] + off[0]) + ',' + (c0[1] + off[1]) + ' L' + (a[0] + off[0]) + ',' + (a[1] + off[1]) +
                          ' M' + (a[0] - n[0] * 8) + ',' + (a[1] - n[1] * 8) + ' L' + (a[0] + n[0] * 8) + ',' + (a[1] + n[1] * 8), class: 'bd-cut' }, g);
          words = 'Strip' + (m.set ? ' ' + m.set : '') + ' ' + where;
        } else if (m.kind === 'splice') {
          var d = 8;
          el('polygon', { points: [[a[0], a[1] - d], [a[0] + d, a[1]], [a[0], a[1] + d], [a[0] - d, a[1]]].join(' '), class: 'bd-diamond' }, g);
          words = 'Splice ' + m.text + ' ' + where;
        } else {
          el('circle', { cx: a[0], cy: a[1], r: 4, class: 'bd-dot' }, g);
          words = (m.text || 'Label') + ' ' + where;
        }
        title.textContent = m.label + (m.what ? ' · ' + m.what : '') + ' · ' + where + ' mm';
        var tx = a[0] + n[0] * out * sideOf, ty = a[1] + n[1] * out * sideOf;
        el('line', { x1: a[0] + n[0] * 8 * sideOf, y1: a[1] + n[1] * 8 * sideOf, x2: tx - n[0] * 6 * sideOf, y2: ty - n[1] * 6 * sideOf, class: 'bd-leader' }, g);
        var t = text(g, tx, ty + 4, words, 'bd-mark-text', n[0] ? (n[0] * sideOf > 0 ? 'start' : 'end') : 'middle');
        var w = 0;
        try { w = t.getBBox().width; } catch (err) { w = words.length * 6.4; }
        var x0 = n[0] ? (n[0] * sideOf > 0 ? tx - 3 : tx - w - 3) : tx - w / 2 - 3;
        g.insertBefore(el('rect', { x: x0, y: ty - 8, width: w + 6, height: 16, rx: 3, class: 'bd-mark-box' }), t);
      });

      // the trunk's dimensions: where each branch leaves it, from its start
      var stops = [0, trunk].concat(ends.map(function (b) { return b.along; })).filter(function (v, i, all) {
        return all.indexOf(v) === i && v >= 0 && v <= trunk;
      }).sort(function (a, b) { return a - b; });
      el('line', { x1: X0, y1: dimY, x2: X1, y2: dimY, class: 'bd-dim' }, lines);
      stops.forEach(function (v, i) {
        var xv = X0 + v * scale;
        el('line', { x1: xv, y1: yT + 6, x2: xv, y2: dimY + 6, class: 'bd-guide' }, lines);
        text(labels, xv, dimY + 18, mm(v), 'bd-dim-text');
        if (i > 0) {   // the stretch between two stops
          var prev = stops[i - 1];
          text(labels, X0 + (prev + v) / 2 * scale, dimY - 5, mm(v - prev), 'bd-dim-text bd-span');
        }
      });
    }
    render();
    var later;
    window.addEventListener('resize', function () {
      clearTimeout(later);
      later = setTimeout(function () { if (root.clientWidth && root.clientWidth !== last) render(); }, 150);
    });
  }

  window.Bundle = { mount: mount };
})();
