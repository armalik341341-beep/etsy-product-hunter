/* Etsy Product Hunter — dashboard SPA (vanilla JS, no build step) */
let CACHE = {results: [], keywords: [], ran_at: null};
let FILTER = {minOpp: 0, maxComp: 100};
let WATCHED = new Set();

const PLACEHOLDER = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">' +
  '<rect width="400" height="400" fill="#1a1e25"/>' +
  '<g fill="none" stroke="#3a4250" stroke-width="10">' +
  '<rect x="110" y="140" width="180" height="140" rx="12"/>' +
  '<circle cx="155" cy="185" r="16"/><path d="M110 250l55-55 40 40 30-30 55 55z" fill="#3a4250" stroke="none"/>' +
  '</g><text x="200" y="310" fill="#5b6472" font-size="20" text-anchor="middle" font-family="sans-serif">no image</text></svg>');

async function api(method, url, body) {
  const o = {method, headers: {'Content-Type': 'application/json'}};
  if (body) o.body = JSON.stringify(body);
  const r = await fetch(url, o);
  return r.json();
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}
function img(url) { return url || PLACEHOLDER; }
function fmtMoney(v) { return (v == null || v === '') ? '?' : '$' + Number(v).toFixed(2).replace(/\.00$/, ''); }
function oppClass(v) { return v >= 1.2 ? 'good' : (v >= 0.7 ? 'mid' : 'low'); }
function toast(msg, isErr) {
  const t = document.createElement('div');
  t.className = 'toast' + (isErr ? ' err' : '');
  t.textContent = msg;
  document.getElementById('toasts').appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

/* ---------------- status chips ---------------- */
async function loadStatus() {
  let s = {};
  try { s = await api('GET', '/api/status'); } catch (e) { /* offline */ }
  const el = document.getElementById('statusChips');
  const chip = (label, on, fix) =>
    '<span class="chip' + (on ? ' on' : '') + (fix ? ' fix' : '') + '"><span class="dot"></span>' +
    esc(label) + '</span>';
  el.innerHTML =
    chip('Etsy API ' + (s.etsy_api ? 'live' : 'off'), !!s.etsy_api) +
    chip('eBay ' + (s.ebay ? 'live' : 'off'), !!s.ebay) +
    (s.fixture ? chip('fixture mode', false, true) : '');
}

/* ---------------- run pipeline ---------------- */
async function startRun() {
  const kw = document.getElementById('kw').value.trim();
  if (!kw) { toast('Enter at least one keyword', true); return; }
  const body = {
    keywords: kw,
    geo: document.getElementById('geo').value,
    price_lo: +document.getElementById('plo').value || 15,
    price_hi: +document.getElementById('phi').value || 60,
    max_cards: +document.getElementById('mc').value || 24,
    include_digital: document.getElementById('dig').checked
  };
  const btn = document.getElementById('runBtn');
  btn.disabled = true; btn.classList.add('loading');
  btn.querySelector('.btn-label').textContent = 'Running…';
  document.getElementById('results').innerHTML =
    '<div class="skel"><div></div><div></div><div></div><div></div></div>';
  try {
    const r = await api('POST', '/api/run', body);
    if (r.error) throw new Error(r.error);
    poll();
  } catch (e) {
    setStatus('<span class="err">start failed: ' + esc(e.message) + '</span>');
    btn.disabled = false; btn.classList.remove('loading');
    btn.querySelector('.btn-label').textContent = 'Run pipeline';
  }
}
function setStatus(html) { document.getElementById('jobStatus').innerHTML = html; }
async function poll() {
  try {
    const s = await api('GET', '/api/run/status');
    setStatus(esc(s.status) + (s.detail ? ': ' + esc(s.detail) : ''));
    if (s.status === 'running') { setTimeout(poll, 3000); return; }
    if (s.status === 'error') setStatus('<span class="err">' + esc(s.detail) + '</span>');
  } catch (e) { setStatus('<span class="err">status check failed</span>'); }
  const btn = document.getElementById('runBtn');
  btn.disabled = false; btn.classList.remove('loading');
  btn.querySelector('.btn-label').textContent = 'Run pipeline';
  await loadResults();
}

/* ---------------- results ---------------- */
async function loadResults() {
  const d = await api('GET', '/api/results');
  CACHE = d || {results: [], keywords: [], ran_at: null};
  document.getElementById('filterRow').hidden = !(CACHE.results && CACHE.results.length);
  applyFilters();
}
function applyFilters() {
  FILTER.minOpp = +document.getElementById('fMinOpp').value || 0;
  FILTER.maxComp = +document.getElementById('fMaxComp').value;
  if (isNaN(FILTER.maxComp)) FILTER.maxComp = 100;
  renderResults();
}
function bar(label, value, cls) {
  const v = Math.max(0, Math.min(100, value || 0));
  return '<div class="bar-row"><span class="bl">' + label + '</span>' +
    '<span class="bar ' + cls + '"><i style="width:' + v.toFixed(0) + '%"></i></span>' +
    '<span class="bv">' + v.toFixed(0) + '</span></div>';
}
function renderResults() {
  const el = document.getElementById('results');
  const meta = document.getElementById('resultMeta');
  const all = CACHE.results || [];
  if (!all.length) {
    el.innerHTML = '<div class="empty">No results yet — start a hunt above.</div>';
    meta.textContent = ''; return;
  }
  const rows = all.filter(r => !r.error &&
    (r.opportunity_score || 0) >= FILTER.minOpp &&
    (r.competition_score == null || r.competition_score <= FILTER.maxComp));
  meta.textContent = rows.length + ' of ' + all.length + ' keywords' +
    (CACHE.ran_at ? ' · ran ' + new Date(CACHE.ran_at * 1000).toLocaleString() : '');
  if (!rows.length) {
    el.innerHTML = '<div class="empty">No keywords pass the current filters.</div>';
    return;
  }
  el.innerHTML = '<div class="kw-grid">' + rows.map((r, i) => kwCard(r, i)).join('') + '</div>';
}
function kwCard(r, i) {
  const gid = 'kw' + i;
  const ebayLine = r.ebay_error
    ? '<span class="tag">eBay: unavailable</span>'
    : (r.ebay_total_sold != null
      ? '<span class="tag">eBay sold ' + Number(r.ebay_total_sold).toLocaleString() +
        ' · sell-through ' + (r.ebay_sell_through != null ? (r.ebay_sell_through * 100).toFixed(1) + '%' : '?') + '</span>'
      : '');
  return '<article class="kw-card">' +
    '<div class="kw-top">' +
      '<img class="kw-hero" src="' + img(r.hero_image_url) + '" alt="" loading="lazy" onerror="this.src=PLACEHOLDER">' +
      '<div class="kw-body">' +
        '<div class="kw-key">' + esc(r.keyword) + '</div>' +
        '<div class="kw-src">' + esc(r.source || '') + '</div>' +
        '<div class="opp-row"><span class="opp ' + oppClass(r.opportunity_score || 0) + '">' +
          (r.opportunity_score != null ? r.opportunity_score.toFixed(2) : '–') + '</span>' +
          '<span class="opp-label">opportunity<br>score</span></div>' +
        '<div class="bars">' + bar('Demand', r.demand_score, 'demand') + bar('Competition', r.competition_score, 'comp') + '</div>' +
      '</div>' +
    '</div>' +
    '<div class="chips" style="padding:0 14px">' +
      '<span class="tag">~' + Number(r.total_results || 0).toLocaleString() + ' results</span>' +
      '<span class="tag">avg ' + fmtMoney(r.avg_price) + '</span>' +
      '<span class="tag">' + (r.in_price_band || 0) + '/' + (r.physical_sampled || 0) + ' in band</span>' +
      (r.trend_avg_interest != null ? '<span class="tag">trend ' + r.trend_avg_interest + '</span>' : '') +
      ebayLine +
    '</div>' +
    '<div class="kw-actions">' +
      '<button class="btn ghost sm" onclick="toggleListings(\'' + gid + '\')">Top listings (' + (r.top_listings || []).length + ')</button>' +
      '<button class="btn ghost sm" onclick="openKwModal(' + i + ')">Score breakdown</button>' +
    '</div>' +
    '<div class="listing-wrap" id="lw-' + gid + '"><div class="l-grid">' +
      (r.top_listings || []).map((l, j) => listingCard(i, j, l)).join('') +
    '</div></div>' +
  '</article>';
}
function listingCard(ki, li, l) {
  const watched = WATCHED.has(l.row_id);
  return '<div class="l-card" onclick="openListing(' + ki + ',' + li + ')">' +
    '<img src="' + img(l.image_url) + '" alt="" loading="lazy" onerror="this.src=PLACEHOLDER">' +
    '<div class="l-info"><div class="l-title">' + esc(l.title) + '</div>' +
    '<div class="l-price">' + fmtMoney(l.price) + '</div>' +
    '<div class="l-meta"><span>♥ ' + (l.favorites == null ? '?' : l.favorites) + '</span>' +
    '<span>' + esc(l.shop_name || '') + '</span></div>' +
    '<div class="l-actions">' +
      '<button class="icon-btn' + (watched ? ' saved' : '') + '" onclick="event.stopPropagation();watch(' + l.row_id + ',this)">' +
        (watched ? '✓ Watched' : '+ Watch') + '</button>' +
      '<button class="icon-btn" onclick="event.stopPropagation();window.open(\'' + esc(l.url || '#') + '\',\'_blank\')">Open ↗</button>' +
    '</div></div></div>';
}
function toggleListings(gid) {
  document.getElementById('lw-' + gid).classList.toggle('open');
}
function getKw(i) {
  const all = (CACHE.results || []).filter(r => !r.error);
  const rows = all.filter(r => (r.opportunity_score || 0) >= FILTER.minOpp &&
    (r.competition_score == null || r.competition_score <= FILTER.maxComp));
  return rows[i];
}

/* ---------------- modal ---------------- */
function openKwModal(i) {
  const r = getKw(i); if (!r) return;
  const rising = (r.trend_rising || []).map(q => '<span class="tag">' + esc(q) + '</span>').join(' ');
  document.getElementById('modalBody').innerHTML =
    '<div class="m-grid"><div><img src="' + img(r.hero_image_url) + '" alt="" onerror="this.src=PLACEHOLDER"></div><div>' +
    '<div class="m-title">' + esc(r.keyword) + '</div>' +
    '<div class="m-shop">' + esc(r.source || '') + ' · ~' + Number(r.total_results || 0).toLocaleString() + ' results</div>' +
    '<div class="m-rows">' +
    mrow('Opportunity', (r.opportunity_score != null ? r.opportunity_score.toFixed(3) : '–') + ' = demand ÷ (competition + 1)') +
    mrow('Demand', (r.demand_score != null ? r.demand_score.toFixed(1) : '–') + ' / 100') +
    mrow('Competition', (r.competition_score != null ? r.competition_score.toFixed(1) : '–') + ' / 100 (lower is better)') +
    mrow('Trend interest', r.trend_avg_interest != null ? r.trend_avg_interest + ' / 100' : '–') +
    mrow('Avg price', fmtMoney(r.avg_price)) +
    mrow('In price band', (r.in_price_band || 0) + ' of ' + (r.physical_sampled || 0) + ' sampled') +
    (r.ebay_total_sold != null ? mrow('eBay sold (real)', Number(r.ebay_total_sold).toLocaleString() +
      ' · sell-through ' + (r.ebay_sell_through * 100).toFixed(1) + '% · avg ' + fmtMoney(r.ebay_avg_sold_price)) : '') +
    '</div>' +
    (rising ? '<div class="chips">' + rising + '</div>' : '') +
    '</div></div>';
  document.getElementById('modalBackdrop').hidden = false;
}
function mrow(k, v) { return '<div class="r"><span class="muted">' + esc(k) + '</span><span>' + esc(v) + '</span></div>'; }
function openListing(ki, li) {
  const r = getKw(ki); if (!r) return;
  const l = (r.top_listings || [])[li]; if (!l) return;
  const band = 'price band ' + fmtMoney(+document.getElementById('plo').value || 15) + '–' +
    fmtMoney(+document.getElementById('phi').value || 60);
  document.getElementById('modalBody').innerHTML =
    '<div class="m-grid"><div><img src="' + img(l.image_url) + '" alt="" onerror="this.src=PLACEHOLDER"></div><div>' +
    '<div class="m-title">' + esc(l.title) + '</div>' +
    '<div class="m-shop">' + esc(l.shop_name || '') + '</div>' +
    '<div class="m-price">' + fmtMoney(l.price) + '</div>' +
    '<div class="m-rows">' +
    mrow('Favorites', l.favorites == null ? '?' : l.favorites) +
    mrow('Keyword opportunity', r.opportunity_score != null ? r.opportunity_score.toFixed(3) : '–') +
    mrow('Keyword demand / competition',
      (r.demand_score != null ? r.demand_score.toFixed(0) : '–') + ' / ' +
      (r.competition_score != null ? r.competition_score.toFixed(0) : '–')) +
    mrow('Band fit', band) +
    '</div>' +
    '<div class="m-actions">' +
      '<button class="btn primary sm" onclick="watch(' + l.row_id + ',this)">+ Watchlist</button>' +
      '<button class="btn ghost sm" onclick="window.open(\'' + esc(l.url || '#') + '\',\'_blank\')">Open on Etsy ↗</button>' +
    '</div></div></div>';
  document.getElementById('modalBackdrop').hidden = false;
}
function closeModal() { document.getElementById('modalBackdrop').hidden = true; }
document.getElementById('modalBackdrop').addEventListener('click', e => {
  if (e.target.id === 'modalBackdrop') closeModal();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

/* ---------------- watchlist ---------------- */
async function watch(row_id, btn) {
  if (!row_id) { toast('Run the pipeline first — no listing id yet', true); return; }
  if (WATCHED.has(row_id)) { toast('Already on the watchlist'); return; }
  const r = await api('POST', '/api/watchlist', {row_id});
  if (r.error) { toast(r.error, true); return; }
  WATCHED.add(row_id);
  if (btn) { btn.classList.add('saved'); btn.textContent = '✓ Watched'; }
  toast('Added to watchlist');
  loadWatch();
}
async function unwatch(row_id) {
  await api('DELETE', '/api/watchlist/' + row_id);
  WATCHED.delete(row_id);
  loadWatch();
}
async function snap() {
  toast('Snapshotting prices…');
  await api('POST', '/api/snapshot');
  toast('Snapshot done');
  loadWatch();
}
function sparkline(history) {
  const pts = (history || []).map(h => h.price).filter(p => p != null);
  if (pts.length < 2) return '<span class="muted" style="font-size:11px">not enough history</span>';
  const w = 110, h = 28, mn = Math.min(...pts), mx = Math.max(...pts);
  const rng = (mx - mn) || 1;
  const path = pts.map((p, i) =>
    ((i / (pts.length - 1)) * w).toFixed(1) + ',' + (h - 2 - ((p - mn) / rng) * (h - 4)).toFixed(1)
  ).join(' ');
  const up = pts[pts.length - 1] >= pts[0];
  return '<svg class="w-spark" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
    '<polyline points="' + path + '" fill="none" stroke="' + (up ? '#34d399' : '#f87171') +
    '" stroke-width="2" stroke-linecap="round"/></svg>';
}
function deltaTxt(d, money) {
  if (d == null) return '<span class="muted">–</span>';
  const cls = d > 0 ? 'delta-up' : (d < 0 ? 'delta-dn' : 'muted');
  const sign = d > 0 ? '+' : '';
  return '<span class="' + cls + '">' + sign + (money ? '$' + d.toFixed(2) : d) + '</span>';
}
async function loadWatch() {
  const d = await api('GET', '/api/watchlist');
  const items = (d && d.items) || [];
  WATCHED = new Set(items.map(w => w.row_id));
  const el = document.getElementById('watch');
  if (!items.length) {
    el.innerHTML = '<div class="empty">Watchlist empty — add listings from the results above.</div>';
    return;
  }
  el.innerHTML = '<div class="w-grid">' + items.map(w => {
    const h = w.history || [];
    const first = h[0] || {}, last = h[h.length - 1] || {};
    const pd = (last.price != null && first.price != null) ? last.price - first.price : null;
    const fd = (last.favorites != null && first.favorites != null) ? last.favorites - first.favorites : null;
    return '<div class="w-card">' +
      '<img src="' + img(w.image_url) + '" alt="" loading="lazy" onerror="this.src=PLACEHOLDER">' +
      '<div class="w-body"><div class="w-title">' + esc(w.title) + '</div>' +
      '<div class="muted" style="font-size:11px">' + esc(w.shop_name || '') + '</div>' +
      '<div class="w-nums"><span>' + fmtMoney(w.price) + ' ' + deltaTxt(pd, true) + '</span>' +
      '<span>♥ ' + (w.favorites == null ? '?' : w.favorites) + ' ' + deltaTxt(fd, false) + '</span></div>' +
      sparkline(h) +
      '<div class="w-foot"><span class="muted" style="font-size:11px">' + h.length + ' snapshots</span>' +
      '<button class="linklike" onclick="unwatch(' + w.row_id + ')">remove</button></div>' +
      '</div></div>';
  }).join('') + '</div>';
}

/* ---------------- init ---------------- */
loadStatus();
loadResults();
loadWatch();
