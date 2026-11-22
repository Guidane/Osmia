/* A harness's Bundle tab. On top its bundle as lines: each pair of connectors (a name tag each) one line, as long as the
   way between them along the bundle (down one's branch, along the trunk, up the other's), with what is put along it
   there: cable ties, sleeves and shrink (from where to where), where a shield is stripped back, splices and labels.
   Edit mode: clicking a line puts one there (its place in mm from the left-hand connector); clicking one changes or
   removes it; clicking a connector's tag gives where its branch leaves the trunk and how long it is. Under it the trunk drawn to
   scale along the page's width, each connector at the end of its branch, with the trunk's dimensions. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] !== null && attrs[k] !== undefined) e.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(e);
    return e;
  }
  function html(tag, attrs, parent) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
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
  function width(t, fallback) { try { return t.getComputedTextLength() || fallback; } catch (err) { return fallback; } }

  function mount(root, data, opts) {
    var bar = root.querySelector('.set-chips'), svg = root.querySelector('svg.bundle-lines');
    var sketchRoot = root.querySelector('.bundle-draw'), sketchSvg = sketchRoot.querySelector('svg');
    var state = { data: data, said: '', editing: false };

    function send(fields, said) {   // answered with the drawing as it is now (else what is wrong, in ``said``)
      var body = new FormData();
      Object.keys(fields).forEach(function (k) { body.append(k, fields[k]); });
      return fetch(opts.url, { method: 'POST', body: body, credentials: 'same-origin', headers: { 'X-CSRFToken': opts.csrf } })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok) { said.textContent = res.j.error || 'That can\'t be.'; return false; }
          state.data = res.j;
          state.said = res.j.said || '';
          render();
          if (opts.onData) opts.onData(res.j);
          return true;
        });
    }

    function popup(ev) {   // a small form by where it was clicked
      var old = root.querySelector('.pd-mark-pop');
      if (old) old.remove();
      var pop = html('form', { class: 'pd-mark-pop card' }, root), box = root.getBoundingClientRect();
      pop.style.left = Math.max(4, Math.min(ev.clientX - box.left - 20, box.width - 300)) + 'px';
      pop.style.top = (ev.clientY - box.top + 14) + 'px';
      return pop;
    }
    function row(pop, label, field) {
      var r = html('label', { class: 'pd-pop-row' }, pop), sp = html('span', {}, r);
      sp.textContent = label;
      r.appendChild(field);
      return r;
    }
    function input(name, value) {
      var i = html('input', { type: 'text', name: name, inputmode: 'decimal', class: 'qty' });
      i.value = value === null || value === undefined ? '' : value;
      return i;
    }
    function actions(pop, label) {
      var said = html('p', { class: 'pd-pop-error' }, pop), acts = html('div', { class: 'pd-pop-actions' }, pop);
      var ok = html('button', { type: 'submit', class: 'btn small primary' }, acts);
      ok.textContent = label;
      var shut = html('button', { type: 'button', class: 'btn small ghost', title: 'Close' }, acts);
      shut.textContent = '✕';
      shut.addEventListener('click', function () { pop.remove(); });
      return { said: said, acts: acts, ok: ok, shut: shut };
    }

    function placePop(e, ev) {   // where a connector's branch leaves the trunk, and how long it is
      var pop = popup(ev), head = html('b', {}, pop);
      head.textContent = e.designator + (e.what ? ' · ' + e.what : '');
      var along = input('along', e.along), reach = input('reach', e.reach);
      row(pop, 'Breaks out at (mm)', along);
      row(pop, 'Branch (mm)', reach);
      var a = actions(pop, 'Save');
      pop.addEventListener('submit', function (x) {
        x.preventDefault();
        send({ action: 'end_place', end: e.id, along: along.value, reach: reach.value }, a.said);
      });
      along.focus();
    }

    function markPop(m, line, d, ev, d1) {   // something put on a line, or changed
      var B = state.data.bundle, pop = popup(ev);
      var kind = html('select', { name: 'kind', 'aria-label': 'What' });
      B.kinds.forEach(function (k) { var o = html('option', { value: k[0] }, kind); o.textContent = k[1]; });
      kind.value = m ? m.kind : 'tie';
      row(pop, 'What', kind);
      var from = input('from', d === '' || d === null || d === undefined ? '' : Math.round(d * 10) / 10);
      row(pop, 'mm from ' + line.a.designator, from);
      var to = input('to', d1 !== null && d1 !== undefined ? Math.round(d1 * 10) / 10 : '');
      var toRow = row(pop, 'to (mm)', to);
      var words = html('input', { type: 'text', name: 'text', maxlength: 100 });
      words.value = m && m.kind !== 'splice' ? m.text : '';
      var textRow = row(pop, 'Text', words);
      var splice = html('select', { name: 'splice', 'aria-label': 'Splice' });
      B.splices.forEach(function (sp) { var o = html('option', { value: sp }, splice); o.textContent = sp; });
      if (m && m.kind === 'splice') splice.value = m.text;
      var spliceRow = row(pop, 'Splice', splice);
      var set = html('select', { name: 'set', 'aria-label': 'Set' });
      [''].concat(line.shielded).forEach(function (sn) { var o = html('option', { value: sn }, set); o.textContent = sn; });
      if (m) set.value = m.set || '';
      var setRow = row(pop, 'Set', set);
      var what = html('input', { type: 'text', name: 'definition', list: 'definitions', autocomplete: 'off' });
      what.value = m ? m.what || '' : '';
      var whatRow = row(pop, 'Item definition', what);
      var a = actions(pop, m ? 'Save' : 'Put it there');
      if (m) {
        var gone = html('button', { type: 'button', class: 'btn small' }, a.acts);
        gone.textContent = 'Take away';
        a.acts.insertBefore(gone, a.shut);
        gone.addEventListener('click', function () { send({ action: 'mark_delete', mark: m.id }, a.said); });
      }
      function fit() {   // what goes with which
        var k = kind.value;
        toRow.hidden = k !== 'sleeve' && k !== 'shrink';
        textRow.hidden = k === 'splice' || k === 'strip';
        spliceRow.hidden = k !== 'splice';
        setRow.hidden = k !== 'strip';
        whatRow.hidden = ['tie', 'sleeve', 'shrink'].indexOf(k) === -1;
      }
      kind.addEventListener('change', fit);
      fit();
      pop.addEventListener('submit', function (x) {
        x.preventDefault();
        send({ action: m ? 'mark_set' : 'mark_add', mark: m ? m.id : '', a_end: line.a.id, b_end: line.b.id, kind: kind.value,
               from: from.value, to: to.value, text: kind.value === 'splice' ? splice.value : words.value, set: set.value,
               definition: what.value }, a.said);
      });
      (kind.value === 'tie' && from.value !== '' ? a.ok : from).focus();
    }

    function modes() {   // View or Edit
      if (!state.editing) html('span', { class: 'spacer' }, bar);
      var seg = html('span', { class: 'segmented' }, bar);
      [['View', false], ['Edit', true]].forEach(function (m) {
        var b = html('button', { type: 'button', class: 'btn small' + (state.editing === m[1] ? ' on' : ''), 'data-mode': m[1] ? 'edit' : 'view' }, seg);
        b.textContent = m[0];
        b.addEventListener('click', function () {
          if (state.editing === m[1]) return;
          state.editing = m[1];
          state.said = '';
          render();
        });
      });
    }

    function toolbar() {   // the trunk's length; editing: it changed, the wires' lengths set from the bundle
      bar.textContent = '';
      var d = state.data;
      if (!state.editing) {
        var shown = html('span', { class: 'bd-trunk' }, bar);
        shown.textContent = d.bundle.trunk ? 'Trunk ' + d.bundle.trunk + ' mm' : '';
        modes();
        return;
      }
      var lab = html('label', { class: 'bd-trunk' }, bar), sp = html('span', {}, lab);
      sp.textContent = 'Trunk';
      var trunk = input('trunk', d.bundle.trunk);
      trunk.setAttribute('aria-label', 'Trunk (mm)');
      lab.appendChild(trunk);
      html('span', {}, lab).textContent = 'mm';
      var said = html('span', { class: 'bd-said small' }, bar);
      said.textContent = state.said;
      trunk.addEventListener('change', function () { send({ action: 'trunk', trunk: trunk.value }, said); });
      trunk.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); trunk.blur(); } });
      html('span', { class: 'spacer' }, bar);
      var lengths = html('button', { type: 'button', class: 'btn small' }, bar);
      lengths.textContent = 'Set the wires\' lengths';
      lengths.addEventListener('click', function () { send({ action: 'lengths' }, said); });
      modes();
    }

    function lines() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      svg.classList.toggle('editing', state.editing);
      var d = state.data, B = d.bundle, order = {}, byId = {}, editing = state.editing;
      d.ends.forEach(function (e, i) { order[e.id] = i; byId[e.id] = e; });
      var pairs = {}, used = {}, shieldedOf = {};
      d.wires.forEach(function (w) {   // each pair of connectors (the one first in the harness on the left)
        if (w.from === w.to || !byId[w.from] || !byId[w.to]) return;
        var a = order[w.from] < order[w.to] ? w.from : w.to, b = a === w.from ? w.to : w.from, key = a + '-' + b;
        var p = pairs[key] = pairs[key] || { a: byId[a], b: byId[b], wires: 0, shielded: [] };
        p.wires += 1;
        used[a] = used[b] = true;
        if (w.set && /shielded/i.test(w.type || '') && p.shielded.indexOf(w.set) === -1) p.shielded.push(w.set);
      });
      var list = Object.keys(pairs).map(function (k) { return pairs[k]; })
        .sort(function (p, q) { return order[p.a.id] - order[q.a.id] || order[p.b.id] - order[q.b.id]; });
      var lone = d.ends.filter(function (e) { return !used[e.id]; });

      var W = Math.max((root.clientWidth || 900) - 24, 640), probe = el('g', {}, svg), TAGH = 28;
      var tagW = Math.max.apply(null, [70].concat(d.ends.map(function (e) {
        return width(text(probe, 0, 0, e.designator, 'bd-tag-name'), e.designator.length * 8) + 28;
      })));
      svg.removeChild(probe);
      var x0 = 12 + tagW, x1 = W - 12 - tagW, y = 10, layer = el('g', {}, svg), tagsG = el('g', {}, svg);
      function placed(e) { return num(e.along) !== null; }

      list.forEach(function (line) {
        var A = { along: num(line.a.along), reach: num(line.a.reach) || 0 }, Z = { along: num(line.b.along), reach: num(line.b.reach) || 0 };
        var L = A.along !== null && Z.along !== null ? A.reach + Math.abs(Z.along - A.along) + Z.reach : null;
        var g = el('g', { class: 'pd-bline' + (L ? '' : ' pd-bline-unknown'), 'data-between': line.a.designator + '-' + line.b.designator }, layer);
        el('line', { x1: x0, y1: 0, x2: x1, y2: 0, class: 'pd-bline-core' }, g);
        var hit = el('rect', { x: x0, y: -13, width: x1 - x0, height: 26, class: 'pd-bline-hit' }, g);   // (editing: clicked)
        el('title', {}, hit).textContent = line.a.designator + ' – ' + line.b.designator + ' · ' + line.wires + ' wire' +
          (line.wires === 1 ? '' : 's') + (L ? ' · ' + mm(L) + ' mm' : '');
        function px(v) { return x0 + (L ? v / L : 0) * (x1 - x0); }
        if (editing) hit.addEventListener('click', function (ev) {
          if (!L) { placePop(placed(line.a) ? line.b : line.a, ev); return; }
          var pt = svg.createSVGPoint();
          pt.x = ev.clientX; pt.y = ev.clientY;
          var at = pt.matrixTransform(svg.getScreenCTM().inverse());
          markPop(null, line, Math.max(0, Math.min(L, Math.round((at.x - x0) / (x1 - x0) * L / 5) * 5)), ev);
        });
        var tags = [];   // the marks' texts (and the line's length), laid out once all are drawn
        if (L) {
          var lt = text(g, (x0 + x1) / 2, 0, mm(L) + ' mm', 'pd-bline-length');
          tags.push({ mg: g, t: lt, x: (x0 + x1) / 2, w: (mm(L) + ' mm').length * 7 + 8, bare: true });
          var lo = Math.min(A.along, Z.along), hi = Math.max(A.along, Z.along);
          var dist = function (m, v) {   // a mark on a's branch, the trunk between them, or b's branch: as far from a
            if (m.on === line.a.id) return v <= A.reach ? v : null;
            if (m.on === line.b.id) return v <= Z.reach ? L - v : null;
            if (m.on !== null && m.on !== undefined) return null;
            if (v < lo - 0.01 || v > hi + 0.01) return null;
            return A.reach + Math.abs(v - A.along);
          };
          B.marks.forEach(function (m) {
            if (m.kind === 'splice') {   // only on the lines of its own connector
              var own = String(m.text).split(':')[0].toLowerCase();
              if (line.a.designator.toLowerCase() !== own && line.b.designator.toLowerCase() !== own) return;
            }
            var v0 = num(m.start), v1 = m.end !== '' && m.end !== null ? num(m.end) : null, d0, d1;
            if (v1 !== null && m.on === null) {   // a stretch on the trunk: the part of it between them
              if (v1 < lo || v0 > hi) return;
              d0 = dist(m, Math.max(v0, lo)); d1 = dist(m, Math.min(v1, hi));
            } else {
              d0 = dist(m, v0); d1 = v1 !== null ? dist(m, v1) : null;
              if (d0 === null || (v1 !== null && d1 === null)) return;
            }
            if (d1 !== null && d1 < d0) { var t0 = d0; d0 = d1; d1 = t0; }
            var mg = el('g', { class: 'pd-bmark pd-bmark-' + m.kind, 'data-mark': m.id }, g), xa = px(d0), words;
            var where = d1 !== null ? Math.round(d0) + '–' + Math.round(d1) : String(Math.round(d0));
            if (d1 !== null) {
              el('line', { x1: xa, y1: 0, x2: px(d1), y2: 0, class: 'pd-bmark-band' }, mg);
              xa = (xa + px(d1)) / 2;
              words = (m.text || m.what || m.label) + ' ' + where;
            } else if (m.kind === 'tie') {
              el('line', { x1: xa, y1: -9, x2: xa, y2: 9, class: 'pd-bmark-tick' }, mg);
              words = 'Tie ' + where;
            } else if (m.kind === 'strip') {
              el('path', { d: 'M' + (m.on === line.a.id ? x0 : x1) + ',-9 H' + xa + ' M' + xa + ',-14 V6', class: 'pd-bmark-cut' }, mg);
              words = 'Strip' + (m.set ? ' ' + m.set : '') + ' ' + where;
            } else if (m.kind === 'splice') {
              el('polygon', { points: [[xa, -8], [xa + 8, 0], [xa, 8], [xa - 8, 0]].join(' '), class: 'pd-bmark-diamond' }, mg);
              words = 'Splice ' + m.text + ' ' + where;
            } else {
              el('circle', { cx: xa, cy: 0, r: 5, class: 'pd-bmark-dot' }, mg);
              words = (m.text || m.label) + ' ' + where;
            }
            var t = text(mg, xa, 0, words, 'pd-bmark-text');
            tags.push({ mg: mg, t: t, x: xa, w: width(t, words.length * 6.2) + 8 });
            el('title', {}, mg).textContent = m.label + (m.what ? ' · ' + m.what : '') + ' · ' + where + ' mm from ' + line.a.designator;
            if (editing) mg.addEventListener('click', function (ev) { markPop(m, line, d0, ev, d1); });
          });
        }
        // each text above or below the line, the first row free of the ones before it (left to right), else further out
        var rows = { up: [], down: [] };
        tags.sort(function (p, q) { return p.x - q.x; }).forEach(function (tg) {
          var left = tg.x - tg.w / 2, spot = null;
          for (var k = 0; !spot; k++) {
            ['up', 'down'].some(function (sd) {
              if (rows[sd][k] === undefined || rows[sd][k] < left - 6) { spot = { sd: sd, k: k }; return true; }
              return false;
            });
          }
          rows[spot.sd][spot.k] = tg.x + tg.w / 2;
          var ty = spot.sd === 'up' ? -16 - spot.k * 17 : 26 + spot.k * 17;
          tg.t.setAttribute('y', ty);
          if (!tg.bare) tg.mg.insertBefore(el('rect', { x: tg.x - tg.w / 2, y: ty - 11, width: tg.w, height: 15, rx: 3, class: 'pd-bmark-box' }), tg.t);
          if (spot.k) el('line', { x1: tg.x, y1: spot.sd === 'up' ? ty + 4 : ty - 11, x2: tg.x, y2: spot.sd === 'up' ? -8 : 8, class: 'pd-bmark-leader' }, tg.mg);
        });
        var up = Math.max(TAGH / 2, rows.up.length ? 16 + rows.up.length * 17 : 0), down = Math.max(TAGH / 2, rows.down.length ? 14 + rows.down.length * 17 : 0);
        y += up + 6;
        g.setAttribute('transform', 'translate(0,' + y + ')');
        line.y = y;
        y += down + 6;
      });

      // the connectors' name tags: at the ends of their lines (one tag for those next to each other)
      function tag(e, xL, top, low) {
        var g = el('g', { class: 'bd-tag' + (placed(e) ? '' : ' bd-tag-unplaced'), 'data-end': e.designator }, tagsG);
        el('rect', { x: xL, y: top, width: tagW, height: low - top }, g);
        text(g, xL + tagW / 2, (top + low) / 2 + 4, e.designator, 'bd-tag-name');
        el('title', {}, g).textContent = e.designator + (e.what ? ' · ' + e.what : '') +
          (placed(e) ? ' · breaks out at ' + mm(num(e.along)) + ' mm · branch ' + mm(num(e.reach) || 0) + ' mm' : '');
        if (editing) g.addEventListener('click', function (ev) { placePop(e, ev); });
      }
      ['a', 'b'].forEach(function (sd) {
        var xL = sd === 'a' ? 12 : W - 12 - tagW;
        for (var i = 0; i < list.length;) {
          var j = i;
          while (j + 1 < list.length && list[j + 1][sd] === list[i][sd]) j++;
          tag(list[i][sd], xL, list[i].y - TAGH / 2, list[j].y + TAGH / 2);
          i = j + 1;
        }
      });
      if (lone.length) {   // connectors with no wires: in a row of their own
        y += 10;
        lone.forEach(function (e, i) { tag(e, 12 + i * (tagW + 10), y, y + TAGH); });
        y += TAGH;
      }
      var H = Math.max(y + 12, 60);
      svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
      svg.style.width = W + 'px';
      svg.style.height = H + 'px';
    }

    function sketch() {   // the trunk to scale, the branches (their lengths written on them), the trunk's dimensions
      while (sketchSvg.firstChild) sketchSvg.removeChild(sketchSvg.firstChild);
      sketchSvg.classList.toggle('editing', state.editing);
      var d = state.data, trunk = num(d.bundle.trunk);
      var ends = d.ends.map(function (e) { return { e: e, along: num(e.along), reach: num(e.reach) || 0 }; })
        .filter(function (b) { return b.along !== null; });
      if (!trunk) trunk = Math.max.apply(null, [0].concat(ends.map(function (b) { return b.along; })));
      sketchRoot.hidden = !trunk;
      if (!trunk) return;
      var W = Math.max((root.clientWidth || 900) - 24, 600), BOXW = 96, BOXH = 30;

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
      var scale0 = (W - 320) / trunk;
      function long(b) { return b.reach > 0 ? Math.min(Math.max(b.reach * scale0, 46), 150) : (b.dir[0] && !b.dir[1] ? 0 : 30); }
      var side = { left: 30, right: 30, up: 30, down: 30 };
      ends.forEach(function (b) {
        var L = long(b);
        if (b.dir[0] < 0) side.left = Math.max(side.left, -b.dir[0] * L + BOXW + 10);
        if (b.dir[0] > 0) side.right = Math.max(side.right, b.dir[0] * L + BOXW + 10);
        if (b.dir[1] < 0) side.up = Math.max(side.up, -b.dir[1] * L + BOXH + 10);
        if (b.dir[1] > 0) side.down = Math.max(side.down, b.dir[1] * L + BOXH + 10);
      });
      var X0 = side.left + 20, X1 = W - side.right - 20, scale = (X1 - X0) / trunk, yT = side.up + 30;
      var dimY = yT + side.down + 30, H = dimY + 30;
      sketchSvg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
      sketchSvg.style.width = W + 'px';
      sketchSvg.style.height = H + 'px';

      var linesG = el('g', {}, sketchSvg), labels = el('g', {}, sketchSvg);
      ends.forEach(function (b) {
        var L = long(b);
        b.base = [X0 + b.along * scale, yT]; b.len = L;
        b.tip = [b.base[0] + b.dir[0] * L, b.base[1] + b.dir[1] * L];
      });
      el('line', { x1: X0, y1: yT, x2: X1, y2: yT, class: 'bd-line' }, linesG);
      ends.forEach(function (b) {
        if (b.len) el('line', { x1: b.base[0], y1: b.base[1], x2: b.tip[0], y2: b.tip[1], class: 'bd-line bd-branch' }, linesG);
        var cx = b.tip[0] + b.dir[0] * (BOXW / 2 + 2), cy = b.tip[1] + b.dir[1] * (BOXH / 2 + 2);
        var g = el('g', { class: 'bd-end', 'data-end': b.e.designator }, labels);
        el('rect', { x: cx - BOXW / 2, y: cy - BOXH / 2, width: BOXW, height: BOXH }, g);
        text(g, cx, cy + 4, b.e.designator, 'bd-name');
        if (state.editing) g.addEventListener('click', function (ev) { placePop(b.e, ev); });
        if (b.reach > 0) {   // its branch's length, beside it
          var m = [(b.base[0] + b.tip[0]) / 2, (b.base[1] + b.tip[1]) / 2];
          if (b.dir[1]) text(labels, m[0] + 10, m[1] + 4, mm(b.reach), 'bd-dim-text', 'start');
          else text(labels, m[0], m[1] - 10, mm(b.reach), 'bd-dim-text');
        }
      });
      var stops = [0, trunk].concat(ends.map(function (b) { return b.along; })).filter(function (v, i, all) {
        return all.indexOf(v) === i && v >= 0 && v <= trunk;
      }).sort(function (a, b) { return a - b; });
      el('line', { x1: X0, y1: dimY, x2: X1, y2: dimY, class: 'bd-dim' }, linesG);
      stops.forEach(function (v, i) {
        var xv = X0 + v * scale;
        el('line', { x1: xv, y1: yT + 6, x2: xv, y2: dimY + 6, class: 'bd-guide' }, linesG);
        text(labels, xv, dimY + 18, mm(v), 'bd-dim-text');
        if (i > 0) text(labels, X0 + (stops[i - 1] + v) / 2 * scale, dimY - 5, mm(v - stops[i - 1]), 'bd-dim-text bd-span');
      });
    }

    var last = -1;
    function render() {
      var stale = root.querySelector('.pd-mark-pop');
      if (stale) stale.remove();
      last = root.clientWidth;
      toolbar();
      lines();
      sketch();
    }
    render();
    var later;
    window.addEventListener('resize', function () {
      clearTimeout(later);
      later = setTimeout(function () { if (root.clientWidth && root.clientWidth !== last) render(); }, 150);
    });
    return { update: function (d) { state.data = d; state.said = ''; render(); } };   // (changed in the pinout drawing)
  }

  window.Bundle = { mount: mount };
})();
