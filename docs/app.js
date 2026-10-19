(() => {
  const CFG = window.WBW_CONFIG;
  const DEMO = !CFG.votesUrl;
  const HOVER = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const TOP_N = 10;                    // dashed line under the top 10 on the leaderboard
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const $ = id => document.getElementById(id);

  const state = {
    shops: new Map(),     // name -> {name, status, address, lat, lon, notes, visits: [], routes: []}
    votes: {},            // shop -> [voter names]
    voters: [],
    open: true,
    me: load('wbw_name') || '',
    pending: 0,
  };
  let map, heatLayer, highlightLayer, popupShop = null;
  const markers = new Map();

  // ---------- storage helpers (may be blocked in private windows) ----------
  function load(k) { try { return localStorage.getItem(k); } catch { return null; } }
  function save(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } }

  // ---------- data ----------
  const sheetCsv = tab => fetch(
    `https://docs.google.com/spreadsheets/d/${CFG.sheetId}/gviz/tq?tqx=out:csv&headers=1&sheet=${encodeURIComponent(tab)}`
  ).then(r => r.text()).then(t => Papa.parse(t, { header: true, skipEmptyLines: true }).data);

  const parseDate = s => { const [m, d, y] = String(s).split('/').map(Number); return new Date(y, m - 1, d); };
  const fmtDate = s => parseDate(s).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  const leaderName = s => { const n = String(s || '').trim(); return CFG.leaderAliases[n] || n; };
  const same = (a, b) => a.trim().toLowerCase() === b.trim().toLowerCase();

  async function loadData() {
    const [shopRows, logRows, routes] = await Promise.all([
      sheetCsv(CFG.shopsTab), sheetCsv(CFG.logTab), fetch('routes.json').then(r => r.json()),
    ]);
    shopRows.forEach(r => {
      const lat = parseFloat(r.lat), lon = parseFloat(r.lon);
      if (!r.shop || isNaN(lat) || isNaN(lon)) return;
      state.shops.set(r.shop.trim(), {
        name: r.shop.trim(), status: (r.status || 'open').trim().toLowerCase(),
        address: r.address || '', notes: r.notes || '', lat, lon, visits: [], routes: [],
      });
    });
    logRows.forEach(r => {
      const shop = state.shops.get((r.Location || '').trim());
      if (shop && r.Date) shop.visits.push({ date: r.Date, leader: leaderName(r.Leader), url: (r.Route || '').trim() });
    });
    state.shops.forEach(s => s.visits.sort((a, b) => parseDate(a.date) - parseDate(b.date)));
    routes.forEach(rt => {
      const shop = state.shops.get(rt.shop);
      if (shop) shop.routes.push(rt);
    });
    return routes;
  }

  // ---------- votes ----------
  const demoKey = 'wbw_demo_votes';
  async function fetchVotes() {
    if (DEMO) return JSON.parse(load(demoKey) || '{"open":true,"votes":{},"voters":[]}');
    const r = await fetch(CFG.votesUrl);
    return r.json();
  }

  async function sendVote(shop, vote) {
    if (DEMO) {
      const t = await fetchVotes();
      const list = (t.votes[shop] || []).filter(n => !same(n, state.me));
      if (vote) list.push(state.me);
      t.votes[shop] = list;
      if (!t.voters.some(n => same(n, state.me))) t.voters.push(state.me);
      save(demoKey, JSON.stringify(t));
      return t;
    }
    const r = await fetch(CFG.votesUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=utf-8' },  // simple request: no CORS preflight
      body: JSON.stringify({ voter: state.me, shop, vote }),
    });
    const t = await r.json();
    if (t.error) throw new Error(t.error);
    return t;
  }

  function applyTally(t) {
    state.votes = t.votes || {};
    state.voters = t.voters || [];
    state.open = t.open !== false;
    render();
  }

  const voteCount = name => (state.votes[name] || []).length;
  const iVoted = name => !!state.me && (state.votes[name] || []).some(n => same(n, state.me));

  async function toggleVote(name) {
    if (!state.me) { askName(() => toggleVote(name)); return; }
    const want = !iVoted(name);
    // optimistic update
    const list = (state.votes[name] || []).filter(n => !same(n, state.me));
    if (want) list.push(state.me);
    state.votes = { ...state.votes, [name]: list };
    state.pending++;
    render();
    try {
      applyTally(await sendVote(name, want));
      setNotice('');
    } catch (err) {
      setNotice(`Couldn't save that vote (${err.message}). Try again in a moment.`);
      applyTally(await fetchVotes().catch(() => ({ votes: state.votes, voters: state.voters })));
    } finally {
      state.pending--;
    }
  }

  // ---------- map ----------
  function initMap(allRoutes) {
    map = L.map('map', { renderer: L.canvas({ tolerance: 10 }) });  // tolerance = bigger tap target
    const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
    L.tileLayer(esri + 'World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 16, attribution: 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors',
    }).addTo(map);
    map.createPane('labels').style.zIndex = 400;
    map.getPane('labels').style.pointerEvents = 'none';
    L.tileLayer(esri + 'World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', { maxZoom: 16, pane: 'labels' }).addTo(map);

    map.createPane('heat').style.zIndex = 350;
    map.createPane('highlight').style.zIndex = 450;
    const heatRenderer = L.canvas({ pane: 'heat' });
    heatLayer = L.layerGroup(allRoutes.map(rt => L.polyline(rt.coords, {
      renderer: heatRenderer, color: css('--route'), weight: 3, opacity: 0.16, interactive: false,
    })));
    if ($('heatToggle').checked) heatLayer.addTo(map);
    highlightLayer = L.layerGroup().addTo(map);

    // On mouse devices a hover opens the popup; it stays open (so the 👍 is reachable) until another
    // pin is hovered or the map is clicked. Auto-pan is off there, or the map would slide under the cursor.
    let hoverTimer;
    const bounds = [];
    state.shops.forEach(shop => {
      const m = L.circleMarker([shop.lat, shop.lon], { bubblingMouseEvents: false })
        .bindPopup(() => popupContent(shop), { maxWidth: 300, autoPan: !HOVER, autoPanPadding: [20, 70] })
        .on('popupopen', () => { popupShop = shop; showRoutes(shop); })
        .on('popupclose', () => { if (popupShop === shop) popupShop = null; highlightLayer.clearLayers(); })
        .addTo(map);
      if (HOVER) {
        m.on('mouseover', () => {
          clearTimeout(hoverTimer);
          hoverTimer = setTimeout(() => { if (!m.isPopupOpen()) m.openPopup(); }, 120);  // skip pins swept past
        }).on('mouseout', () => clearTimeout(hoverTimer));
      } else {
        m.bindTooltip(shop.name, { direction: 'top', offset: [0, -6] });
      }
      markers.set(shop.name, m);
      bounds.push([shop.lat, shop.lon]);
    });
    // fit all shops, then one level closer: the dense core matters more than the outliers
    map.fitBounds(bounds, { padding: [30, 30], animate: false });
    map.setZoom(map.getZoom() + 1, { animate: false });

    $('heatToggle').addEventListener('change', e => e.target.checked ? heatLayer.addTo(map) : heatLayer.remove());
  }

  function styleMarker(shop) {
    const n = voteCount(shop.name);
    const r = 7 + 2.2 * Math.sqrt(n);
    if (shop.status === 'closed') {
      return { radius: 5, color: css('--closed'), weight: 2, fillColor: '#fff', fillOpacity: 0.9 };
    }
    return { radius: r, color: '#fff', weight: 1.5, fillOpacity: 0.95,
             fillColor: iVoted(shop.name) ? css('--mine') : css('--coffee') };
  }

  function showRoutes(shop) {
    highlightLayer.clearLayers();
    shop.routes.forEach(rt => L.polyline(rt.coords, {
      pane: 'highlight', color: css('--route'), weight: 4, opacity: 0.85, interactive: false,
    }).addTo(highlightLayer));
  }

  function el(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => k === 'class' ? (n.className = v) : n.setAttribute(k, v));
    kids.flat().forEach(k => n.append(k));
    return n;
  }

  function popupContent(shop) {
    const closed = shop.status === 'closed';
    const h = el('h3', {}, shop.name);
    if (closed) h.append(el('span', { class: 'closed-badge' }, 'CLOSED'));
    const box = el('div', { class: 'pop' }, h);
    if (shop.address) box.append(el('p', { class: 'addr' }, shop.address));
    if (shop.notes) box.append(el('p', { class: 'note' }, shop.notes));

    const runs = shop.visits.length;
    const routeNote = shop.routes.length ? ' · route shown in orange' : '';
    box.append(el('p', { class: 'addr' }, `${runs} club run${runs === 1 ? '' : 's'}${routeNote}`));
    box.append(el('ul', { class: 'visits' }, shop.visits.slice().reverse().map(v => {
      const li = el('li', {}, fmtDate(v.date), v.leader ? ` · led by ${v.leader}` : '');
      if (/^https?:/.test(v.url)) {
        li.append(' · ', el('a', { href: v.url, target: '_blank', rel: 'noopener' }, 'route ↗'));
      }
      return li;
    })));

    if (closed) {
      box.append(el('p', { class: 'closed-msg' }, 'Closed, so not on the ballot.'));
      return box;
    }
    const n = voteCount(shop.name);
    const btn = el('button', { class: 'vote-btn' + (iVoted(shop.name) ? ' on' : ''), type: 'button' },
      iVoted(shop.name) ? `👍 Voted · ${n}` : `👍 Vote${n ? ' · ' + n : ''}`);
    if (!state.open) btn.disabled = true;
    btn.addEventListener('click', () => toggleVote(shop.name));
    const who = (state.votes[shop.name] || []).join(', ');
    box.append(el('div', { class: 'vote-row' }, btn, el('span', { class: 'voters' }, who)));
    return box;
  }

  // leaderboard rows: hover previews the shop's routes and outlines its pin, click flies there
  function bindRow(li, shop) {
    li.addEventListener('click', () => focusShop(shop.name));
    if (!HOVER) return;
    li.addEventListener('mouseenter', () => {
      showRoutes(shop);
      markers.get(shop.name).setStyle({ color: css('--ink'), weight: 3 }).bringToFront();
    });
    li.addEventListener('mouseleave', () => {
      markers.get(shop.name).setStyle(styleMarker(shop));
      popupShop ? showRoutes(popupShop) : highlightLayer.clearLayers();
    });
  }

  function focusShop(name) {
    const m = markers.get(name);
    if (!m) return;
    if (window.matchMedia('(max-width: 720px)').matches) $('panel').classList.remove('open');
    map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 15), { duration: 0.6 });
    map.once('moveend', () => m.openPopup());
  }

  // ---------- panel ----------
  function render() {
    markers.forEach((m, name) => m.setStyle(styleMarker(state.shops.get(name))));
    if (popupShop) markers.get(popupShop.name).setPopupContent(popupContent(popupShop));

    const openShops = [...state.shops.values()].filter(s => s.status !== 'closed');
    const ranked = openShops.filter(s => voteCount(s.name)).sort((a, b) =>
      voteCount(b.name) - voteCount(a.name) || a.name.localeCompare(b.name));
    const max = ranked.length ? voteCount(ranked[0].name) : 1;

    const board = $('board');
    board.replaceChildren();
    if (!ranked.length) board.append(el('li', { class: 'empty' }, 'No votes yet. Be the first!'));
    ranked.forEach((s, i) => {
      const n = voteCount(s.name);
      const li = el('li', { class: (iVoted(s.name) ? 'mine' : '') + (i === TOP_N ? ' cutline' : ''), title: (state.votes[s.name] || []).join(', ') },
        el('span', { class: 'rank' }, i + 1),
        el('span', { class: 'name' }, s.name),
        el('span', { class: 'count' }, n),
        el('span', {}),
        el('div', { class: 'barwrap' }, Object.assign(el('div', { class: 'barfill' }), { style: `width:${(100 * n) / max}%` })));
      bindRow(li, s);
      board.append(li);
    });

    const unvoted = openShops.filter(s => !voteCount(s.name)).sort((a, b) => a.name.localeCompare(b.name));
    $('unvotedSummary').textContent = `${unvoted.length} open shops with no votes yet`;
    $('unvotedList').replaceChildren(...unvoted.map(s => {
      const li = el('li', {}, s.name);
      bindRow(li, s);
      return li;
    }));

    const mine = openShops.filter(s => iVoted(s.name)).length;
    $('myCount').textContent = state.me && mine ? `${mine} vote${mine === 1 ? '' : 's'}` : '';
    $('whoBtn').textContent = state.me ? `Voting as ${state.me}` : 'Set your name';
    $('voterList').replaceChildren(...state.voters.map(v => el('option', { value: v })));

    if (!state.open) setNotice('Voting is closed. These are the final results.');
    else if (DEMO) setNotice('Demo mode: the vote backend isn\'t connected yet, so votes are only saved in this browser.');
  }

  function setNotice(msg) {
    $('votingNotice').hidden = !msg;
    $('votingNotice').textContent = msg;
  }

  function askName(then) {
    const dlg = $('nameDialog');
    $('nameInput').value = state.me;
    dlg.onclose = () => {
      const v = $('nameInput').value.replace(/\s+/g, ' ').trim();
      if (dlg.returnValue !== 'ok' || !v) return;
      // reuse an existing spelling if it matches case-insensitively
      state.me = state.voters.find(n => same(n, v)) || v;
      save('wbw_name', state.me);
      render();
      if (then) then();
    };
    dlg.showModal();
  }

  // ---------- boot ----------
  async function boot() {
    const allRoutes = await loadData();
    const visits = [...state.shops.values()].reduce((n, s) => n + s.visits.length, 0);
    const first = [...state.shops.values()].flatMap(s => s.visits).map(v => parseDate(v.date)).sort((a, b) => a - b)[0];
    $('stats').textContent = `${state.shops.size} shops · ${visits} runs · since ${first.toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}`;
    initMap(allRoutes);
    applyTally(await fetchVotes().catch(() => ({ votes: {}, voters: [] })));

    $('whoBtn').addEventListener('click', () => askName());
    $('panelHandle').addEventListener('click', () => {
      const p = $('panel');
      p.classList.toggle('open');
      $('panelHandle').setAttribute('aria-expanded', p.classList.contains('open'));
    });

    if (!DEMO) {
      setInterval(async () => {
        if (document.hidden || state.pending) return;
        try { applyTally(await fetchVotes()); } catch { /* try again next tick */ }
      }, CFG.pollSeconds * 1000);
    }
  }

  boot().catch(err => {
    $('stats').textContent = 'Could not load the club data. Is the sheet still shared by link?';
    console.error(err);
  });
})();
