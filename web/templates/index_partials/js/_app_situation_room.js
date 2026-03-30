/* ─── Situation Room — Global Intelligence Dashboard ─── */

let _sitroomMap = null;
let _sitroomMarkers = { earthquakes: [], weather: [], conflicts: [] };
let _sitroomNewsOffset = 0;
const SITROOM_NEWS_PAGE = 50;
let _sitroomAutoRefreshTimer = null;
let _sitroomInitDone = false;

/* ─── Initialization ─── */
function initSituationRoom() {
  // Close utility panels (LAN chat, Timers, Quick Actions) to declutter
  _closeSitroomOverlays();
  // Re-close after a delay in case other init code opens them
  setTimeout(_closeSitroomOverlays, 500);
  setTimeout(_closeSitroomOverlays, 1500);

  if (_sitroomInitDone) {
    _sitroomLoadAll();
    return;
  }
  _sitroomInitDone = true;
  _sitroomLoadAll();
  initSitroomMap();
  // Auto-refresh on first visit if no data cached
  _sitroomAutoRefreshIfEmpty();
  // Auto-refresh every 60s
  if (_sitroomAutoRefreshTimer) clearInterval(_sitroomAutoRefreshTimer);
  _sitroomAutoRefreshTimer = setInterval(_sitroomLoadAll, 60000);
}

async function _sitroomAutoRefreshIfEmpty() {
  const d = await safeFetch('/api/sitroom/status', {}, null);
  if (d && d.feed_count > 0 && (!d.last_fetch || Object.keys(d.last_fetch).length === 0)) {
    // No data fetched yet — auto-trigger first refresh
    refreshSitroomFeeds();
  }
}

function _sitroomLoadAll() {
  loadSitroomSummary();
  loadSitroomNews();
  loadSitroomFeeds();
}

/* ─── Map ─── */
function initSitroomMap() {
  const container = document.getElementById('sitroom-map');
  if (!container || _sitroomMap) return;

  const darkStyle = {
    version: 8,
    sources: {
      'osm-tiles': {
        type: 'raster',
        tiles: ['https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'],
        tileSize: 256,
        attribution: 'CartoDB Dark Matter',
      }
    },
    layers: [{
      id: 'osm-tiles',
      type: 'raster',
      source: 'osm-tiles',
      minzoom: 0,
      maxzoom: 18,
    }]
  };

  try {
    _sitroomMap = new maplibregl.Map({
      container: 'sitroom-map',
      style: darkStyle,
      center: [0, 20],
      zoom: 1.8,
      attributionControl: false,
    });
    _sitroomMap.on('load', () => loadSitroomMapData());
    _sitroomMap.on('error', (e) => {
      if (e.error && e.error.status === 0) _tryPMTilesFallback();
    });
  } catch (err) {
    container.innerHTML = '<div class="sitroom-empty">Map unavailable</div>';
  }
}

function _tryPMTilesFallback() {
  if (!_sitroomMap) return;
  try {
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol('pmtiles', protocol.tile);
    _sitroomMap.setStyle({
      version: 8,
      sources: {
        'pmtiles': {
          type: 'vector',
          url: 'pmtiles://https://data.source.coop/protomaps/openstreetmap/v4.pmtiles',
        }
      },
      layers: [{
        id: 'background',
        type: 'background',
        paint: { 'background-color': '#0a0a14' }
      }]
    });
  } catch (e) {}
}

async function loadSitroomMapData() {
  if (!_sitroomMap) return;
  try {
    const data = await safeFetch('/api/sitroom/events', {}, null);
    if (!data || !data.events) return;
    clearSitroomMarkers();
    data.events.forEach(ev => {
      if (!ev.lat && !ev.lng) return;
      const layerType = ev.event_type === 'earthquake' ? 'earthquakes'
        : ev.event_type === 'weather_alert' ? 'weather' : 'conflicts';
      const checkId = layerType === 'earthquakes' ? 'quakes' : layerType;
      const checkbox = document.getElementById('sitroom-layer-' + checkId);
      if (checkbox && !checkbox.checked) return;
      addSitroomMarker(ev, layerType);
    });
  } catch (e) {}
}

function clearSitroomMarkers() {
  Object.values(_sitroomMarkers).forEach(arr => {
    arr.forEach(m => m.remove());
    arr.length = 0;
  });
}

function addSitroomMarker(ev, layerType) {
  if (!_sitroomMap) return;
  const colors = { earthquakes: '#ff4444', weather: '#ffaa00', conflicts: '#ff6600' };
  const color = colors[layerType] || '#ffffff';

  let size = 8;
  if (ev.magnitude) size = Math.max(6, Math.min(24, ev.magnitude * 3));

  const el = document.createElement('div');
  el.className = 'sitroom-marker sitroom-marker-' + layerType;
  el.style.cssText = `width:${size}px;height:${size}px;background:${color};border-radius:50%;border:1px solid rgba(255,255,255,0.3);cursor:pointer;box-shadow:0 0 ${size}px ${color}40;`;

  const popup = new maplibregl.Popup({ offset: 10, closeButton: false })
    .setHTML(`<div class="sitroom-popup">
      <strong>${escapeHtml(ev.title || 'Event')}</strong>
      ${ev.magnitude ? `<br>Magnitude: ${ev.magnitude}` : ''}
      ${ev.depth_km ? `<br>Depth: ${ev.depth_km} km` : ''}
      <br><small>${ev.event_type}</small>
    </div>`);

  const marker = new maplibregl.Marker({ element: el })
    .setLngLat([ev.lng, ev.lat])
    .setPopup(popup)
    .addTo(_sitroomMap);

  _sitroomMarkers[layerType].push(marker);
}

/* ─── Summary / Status ─── */
async function loadSitroomSummary() {
  const d = await safeFetch('/api/sitroom/summary', {}, null);
  if (!d) return;

  // Update stat counters
  const set = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
  set('sitroom-stat-news', d.news_count || 0);
  set('sitroom-stat-quakes', d.earthquake_count || 0);
  set('sitroom-stat-weather', d.weather_alert_count || 0);
  set('sitroom-stat-conflicts', d.conflict_count || 0);
  set('sitroom-stat-markets', d.market_count || 0);

  // Online badge
  const badge = document.getElementById('sitroom-online-badge');
  if (badge) {
    const hasData = (d.news_count || 0) > 0;
    badge.textContent = hasData ? 'DATA CACHED' : 'OFFLINE';
    badge.className = 'sitroom-badge ' + (hasData ? 'sitroom-badge-online' : 'sitroom-badge-offline');
  }

  // Last update
  const ts = document.getElementById('sitroom-last-update');
  if (ts && d.last_fetch) {
    const latest = Object.values(d.last_fetch).filter(Boolean).sort().pop();
    if (latest) ts.textContent = 'Updated ' + _timeAgo(new Date(latest));
  }

  // Render panels
  renderSitroomMarkets(d.markets || []);
  renderSitroomQuakes();
  loadSitroomWeather();
  loadSitroomMapData();
}

/* ─── Markets ─── */
function renderSitroomMarkets(markets) {
  const container = document.getElementById('sitroom-market-ticker');
  if (!container) return;
  if (!markets.length) {
    container.innerHTML = '<div class="sitroom-empty">No market data — click Refresh Feeds</div>';
    return;
  }
  container.innerHTML = markets.map(m => {
    const change = m.change_24h || 0;
    const isUp = change >= 0;
    const arrow = isUp ? '&#9650;' : '&#9660;';
    const cls = isUp ? 'sitroom-market-up' : 'sitroom-market-down';
    let priceStr;
    if (m.market_type === 'sentiment') {
      priceStr = m.price + '/100';
    } else if (m.price >= 1) {
      priceStr = '$' + Number(m.price).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    } else {
      priceStr = '$' + Number(m.price).toFixed(6);
    }
    const label = m.label || m.symbol;
    return `<div class="sitroom-market-card ${cls}">
      <div class="sitroom-market-symbol">${escapeHtml(label)}</div>
      <div class="sitroom-market-price">${priceStr}</div>
      <div class="sitroom-market-change">${arrow} ${Math.abs(change).toFixed(1)}%</div>
    </div>`;
  }).join('');
}

/* ─── Earthquakes ─── */
async function renderSitroomQuakes() {
  const minMag = parseFloat(document.getElementById('sitroom-quake-filter')?.value || '4');
  const d = await safeFetch('/api/sitroom/earthquakes?min_magnitude=' + minMag, {}, null);
  const list = document.getElementById('sitroom-quake-list');
  if (!list) return;
  if (!d || !d.earthquakes?.length) {
    list.innerHTML = '<div class="sitroom-empty">No earthquakes above M' + minMag + '</div>';
    return;
  }
  list.innerHTML = d.earthquakes.map(q => {
    const magClass = q.magnitude >= 6 ? 'sitroom-mag-high' : q.magnitude >= 4.5 ? 'sitroom-mag-med' : 'sitroom-mag-low';
    let detail = {};
    try { detail = q.detail_json ? JSON.parse(q.detail_json) : {}; } catch(e) {}
    return `<div class="sitroom-event-item">
      <span class="sitroom-mag ${magClass}">M${q.magnitude ? q.magnitude.toFixed(1) : '?'}</span>
      <div class="sitroom-event-info">
        <div class="sitroom-event-title">${escapeHtml(q.title || 'Unknown location')}</div>
        <div class="sitroom-event-meta">Depth: ${q.depth_km ? q.depth_km.toFixed(0) + ' km' : 'N/A'}${detail.alert ? ' | Alert: ' + escapeHtml(detail.alert) : ''}${detail.felt ? ' | Felt: ' + detail.felt + ' reports' : ''}</div>
      </div>
      ${q.source_url ? `<a href="${escapeAttr(q.source_url)}" target="_blank" rel="noopener" class="sitroom-event-link" title="View details">&#8599;</a>` : ''}
    </div>`;
  }).join('');
}

/* ─── Weather Alerts ─── */
async function loadSitroomWeather() {
  const d = await safeFetch('/api/sitroom/weather-alerts', {}, null);
  const list = document.getElementById('sitroom-weather-list');
  if (!list) return;
  if (!d || !d.alerts?.length) {
    list.innerHTML = '<div class="sitroom-empty">No severe weather alerts</div>';
    return;
  }
  list.innerHTML = d.alerts.slice(0, 30).map(a => {
    let detail = {};
    try { detail = a.detail_json ? JSON.parse(a.detail_json) : {}; } catch(e) {}
    const sevClass = detail.severity === 'Extreme' ? 'sitroom-sev-extreme' : 'sitroom-sev-severe';
    return `<div class="sitroom-event-item ${sevClass}">
      <div class="sitroom-event-info">
        <div class="sitroom-event-title">${escapeHtml(a.title || 'Weather Alert')}</div>
        <div class="sitroom-event-meta">${escapeHtml(detail.headline || '')}${detail.sender ? ' (' + escapeHtml(detail.sender) + ')' : ''}</div>
      </div>
    </div>`;
  }).join('');
}

/* ─── News Feed ─── */
async function loadSitroomNews(append) {
  if (!append) _sitroomNewsOffset = 0;
  const category = document.getElementById('sitroom-news-category')?.value || '';
  const d = await safeFetch('/api/sitroom/news?category=' + encodeURIComponent(category) + '&limit=' + SITROOM_NEWS_PAGE + '&offset=' + _sitroomNewsOffset, {}, null);
  const list = document.getElementById('sitroom-news-list');
  const moreBtn = document.getElementById('sitroom-news-more');
  if (!list) return;

  if (!d || !d.articles?.length) {
    if (!append) {
      list.innerHTML = '<div class="sitroom-empty">No news cached — click Refresh Feeds to pull from RSS sources</div>';
      if (moreBtn) moreBtn.style.display = 'none';
    }
    return;
  }

  const html = d.articles.map(a => `<div class="sitroom-news-item">
    <span class="sitroom-news-cat">${escapeHtml(a.category || '')}</span>
    <div class="sitroom-news-body">
      <a href="${escapeAttr(a.link || '#')}" target="_blank" rel="noopener" class="sitroom-news-title">${escapeHtml(a.title)}</a>
      <div class="sitroom-news-meta">${escapeHtml(a.source_name || '')} ${a.published ? '| ' + escapeHtml(a.published) : ''}</div>
    </div>
  </div>`).join('');

  if (append) {
    list.insertAdjacentHTML('beforeend', html);
  } else {
    list.innerHTML = html;
  }
  _sitroomNewsOffset += d.articles.length;
  if (moreBtn) moreBtn.style.display = _sitroomNewsOffset < (d.total || 0) ? '' : 'none';
}

/* ─── Populate Category Filter ─── */
async function loadSitroomFeeds() {
  const d = await safeFetch('/api/sitroom/feeds', {}, null);
  if (!d) return;

  const sel = document.getElementById('sitroom-news-category');
  if (sel) {
    const customCats = (d.custom || []).map(f => f.category);
    const cats = [...new Set([...(d.categories || []), ...customCats])].sort();
    sel.innerHTML = '<option value="">All Categories</option>' + cats.map(c =>
      '<option value="' + escapeAttr(c) + '">' + escapeHtml(c) + '</option>'
    ).join('');
  }

  const be = document.getElementById('sitroom-builtin-count');
  const ce = document.getElementById('sitroom-custom-count');
  if (be) be.textContent = (d.builtin || []).length;
  if (ce) ce.textContent = (d.custom || []).length;

  const customList = document.getElementById('sitroom-custom-feeds-list');
  if (customList) {
    if (!d.custom?.length) {
      customList.innerHTML = '<div class="sitroom-empty">No custom feeds added</div>';
    } else {
      customList.innerHTML = d.custom.map(f => `<div class="sitroom-custom-feed-item">
        <span class="sitroom-news-cat">${escapeHtml(f.category)}</span>
        <span class="sitroom-custom-feed-name">${escapeHtml(f.name)}</span>
        <span class="sitroom-custom-feed-url">${escapeHtml(f.url)}</span>
        <button class="btn btn-sm btn-danger" data-sitroom-action="delete-feed" data-feed-id="${f.id}">Remove</button>
      </div>`).join('');
    }
  }
}

/* ─── AI Briefing ─── */
async function generateSitroomBriefing() {
  const btn = document.getElementById('sitroom-gen-briefing');
  const container = document.getElementById('sitroom-briefing-content');
  if (!container) return;
  if (btn) btn.disabled = true;
  container.innerHTML = '<div class="sitroom-loading">Generating intelligence briefing...</div>';

  try {
    const resp = await fetch('/api/sitroom/ai-briefing', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      container.innerHTML = '<div class="sitroom-empty">' + escapeHtml(err.error || 'Briefing generation failed') + '</div>';
      return;
    }
    const d = await resp.json();
    container.innerHTML = '<div class="sitroom-briefing-text">' + _renderBriefing(d.briefing || '') + '</div>';
  } catch (e) {
    container.innerHTML = '<div class="sitroom-empty">Network error generating briefing</div>';
  } finally {
    if (btn) btn.disabled = false;
  }
}

function _renderBriefing(text) {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/^### (.*?)$/gm, '<h4>$1</h4>')
    .replace(/^## (.*?)$/gm, '<h3>$1</h3>')
    .replace(/^# (.*?)$/gm, '<h2>$1</h2>')
    .replace(/\n/g, '<br>');
}

/* ─── Feed Management ─── */
async function addSitroomFeed() {
  const name = document.getElementById('sitroom-feed-name')?.value.trim();
  const url = document.getElementById('sitroom-feed-url')?.value.trim();
  const category = document.getElementById('sitroom-feed-category')?.value.trim() || 'Custom';
  if (!name || !url) { toast('Name and URL required', 'warning'); return; }

  try {
    const resp = await fetch('/api/sitroom/feeds', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, url, category}),
    });
    if (resp.ok) {
      toast('Feed added', 'success');
      document.getElementById('sitroom-feed-name').value = '';
      document.getElementById('sitroom-feed-url').value = '';
      loadSitroomFeeds();
    } else {
      const err = await resp.json().catch(() => ({}));
      toast(err.error || 'Failed to add feed', 'error');
    }
  } catch (e) {
    toast('Network error', 'error');
  }
}

async function deleteSitroomFeed(feedId) {
  try {
    await fetch('/api/sitroom/feeds/' + feedId, {method: 'DELETE'});
    toast('Feed removed', 'success');
    loadSitroomFeeds();
  } catch (e) {}
}

/* ─── Refresh ─── */
async function refreshSitroomFeeds() {
  const btn = document.getElementById('sitroom-refresh-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Refreshing...'; }

  try {
    const resp = await fetch('/api/sitroom/refresh', {method: 'POST'});
    if (resp.ok) {
      toast('Feed refresh started — data will appear shortly', 'info');
      // Poll at intervals while background fetch runs
      setTimeout(_sitroomLoadAll, 5000);
      setTimeout(_sitroomLoadAll, 12000);
      setTimeout(_sitroomLoadAll, 25000);
      setTimeout(_sitroomLoadAll, 40000);
    }
  } catch (e) {
    toast('Refresh failed — check network connection', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Refresh Feeds'; }
  }
}

/* ─── Close Overlays ─── */
function _closeSitroomOverlays() {
  // Force-nuke all utility panels — set hidden class AND inline display:none
  ['lan-chat-panel', 'timer-panel', 'quick-actions-menu'].forEach(id => {
    const panel = document.getElementById(id);
    if (panel) {
      panel.classList.add('is-hidden');
      panel.hidden = true;
    }
  });
  // Reset button states
  if (typeof setUtilityDockButtonExpanded === 'function') {
    setUtilityDockButtonExpanded('chat', false);
    setUtilityDockButtonExpanded('timer', false);
    setUtilityDockButtonExpanded('actions', false);
  }
  // Reset JS state flags
  if (typeof _lanChatOpen !== 'undefined') _lanChatOpen = false;
  if (typeof _timerPanelOpen !== 'undefined') _timerPanelOpen = false;
  if (typeof _qaOpen !== 'undefined') _qaOpen = false;

  // Hide the copilot dock on Situation Room — it has its own AI briefing
  const dock = document.getElementById('copilot-dock');
  if (dock) dock.style.display = 'none';
}

// Restore copilot dock when leaving Situation Room
function _restoreCopilotDock() {
  const dock = document.getElementById('copilot-dock');
  if (dock) dock.style.removeProperty('display');
  // Un-hide panels so they work from other tabs
  ['lan-chat-panel', 'timer-panel', 'quick-actions-menu'].forEach(id => {
    const panel = document.getElementById(id);
    if (panel) panel.hidden = false;
  });
}

/* ─── Utility ─── */
function _timeAgo(date) {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
  if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
  return Math.floor(seconds / 86400) + 'd ago';
}

/* ─── Event Delegation ─── */
document.addEventListener('click', e => {
  const ctrl = e.target.closest('[data-sitroom-action]');
  if (!ctrl) return;
  const action = ctrl.dataset.sitroomAction;
  if (action === 'refresh') refreshSitroomFeeds();
  if (action === 'generate-briefing') generateSitroomBriefing();
  if (action === 'add-feed') addSitroomFeed();
  if (action === 'delete-feed') deleteSitroomFeed(ctrl.dataset.feedId);
  if (action === 'load-more-news') loadSitroomNews(true);
});

document.getElementById('sitroom-news-category')?.addEventListener('change', () => loadSitroomNews());
document.getElementById('sitroom-quake-filter')?.addEventListener('change', () => renderSitroomQuakes());
document.querySelectorAll('[data-sitroom-layer]').forEach(cb => {
  cb.addEventListener('change', () => loadSitroomMapData());
});
