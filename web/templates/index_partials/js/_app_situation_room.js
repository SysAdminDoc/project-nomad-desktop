/* ─── Situation Room — Global Intelligence Dashboard ─── */

let _sitroomMap = null;
let _sitroomMarkers = { earthquakes: [], weather: [], conflicts: [] };
let _sitroomNewsOffset = 0;
const SITROOM_NEWS_PAGE = 50;
let _sitroomAutoRefreshTimer = null;

/* ─── Initialization ─── */
function initSituationRoom() {
  loadSitroomSummary();
  initSitroomMap();
  loadSitroomNews();
  loadSitroomFeeds();
  // Auto-refresh summary every 60s
  if (_sitroomAutoRefreshTimer) clearInterval(_sitroomAutoRefreshTimer);
  _sitroomAutoRefreshTimer = setInterval(loadSitroomSummary, 60000);
}

/* ─── Map ─── */
function initSitroomMap() {
  const container = document.getElementById('sitroom-map');
  if (!container || _sitroomMap) return;

  // Dark-themed map tiles
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

  // Fallback to PMTiles if offline
  try {
    _sitroomMap = new maplibregl.Map({
      container: 'sitroom-map',
      style: darkStyle,
      center: [0, 20],
      zoom: 1.8,
      attributionControl: false,
    });
    _sitroomMap.on('load', () => {
      loadSitroomMapData();
    });
    // If tiles fail to load (offline), try PMTiles
    _sitroomMap.on('error', (e) => {
      if (e.error && e.error.status === 0) {
        _tryPMTilesFallback();
      }
    });
  } catch (err) {
    container.innerHTML = '<div class="sitroom-empty">Map unavailable — MapLibre failed to initialize</div>';
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
  } catch (e) {
    // Silent — map just won't have tiles
  }
}

function loadSitroomMapData() {
  if (!_sitroomMap) return;
  // Fetch events and plot them
  safeFetch('/api/sitroom/events')
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data) return;
      clearSitroomMarkers();
      (data.events || []).forEach(ev => {
        if (!ev.lat && !ev.lng) return;
        const layerType = ev.event_type === 'earthquake' ? 'earthquakes'
          : ev.event_type === 'weather_alert' ? 'weather' : 'conflicts';
        const checkbox = document.getElementById('sitroom-layer-' + (layerType === 'earthquakes' ? 'quakes' : layerType));
        if (checkbox && !checkbox.checked) return;
        addSitroomMarker(ev, layerType);
      });
    })
    .catch(() => {});
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
  if (ev.magnitude) {
    size = Math.max(6, Math.min(24, ev.magnitude * 3));
  }

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
  try {
    const resp = await safeFetch('/api/sitroom/summary');
    if (!resp.ok) return;
    const d = await resp.json();

    // Update stat counters
    const el = (id, val) => {
      const e = document.getElementById(id);
      if (e) e.textContent = val;
    };
    el('sitroom-stat-news', d.news_count || 0);
    el('sitroom-stat-quakes', d.earthquake_count || 0);
    el('sitroom-stat-weather', d.weather_alert_count || 0);
    el('sitroom-stat-conflicts', d.conflict_count || 0);
    el('sitroom-stat-markets', d.market_count || 0);

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
      if (latest) {
        const ago = _timeAgo(new Date(latest));
        ts.textContent = `Updated ${ago}`;
      }
    }

    // Render markets
    renderSitroomMarkets(d.markets || []);

    // Render top earthquakes inline
    renderSitroomQuakes();

    // Load weather alerts
    loadSitroomWeather();

    // Refresh map
    loadSitroomMapData();

  } catch (e) {
    // Offline — show cached indicator
  }
}

/* ─── Markets ─── */
function renderSitroomMarkets(markets) {
  const container = document.getElementById('sitroom-market-ticker');
  if (!container) return;
  if (!markets.length) {
    container.innerHTML = '<div class="sitroom-empty">No market data — click Refresh</div>';
    return;
  }
  container.innerHTML = markets.map(m => {
    const isUp = m.change_24h >= 0;
    const arrow = isUp ? '&#9650;' : '&#9660;';
    const cls = isUp ? 'sitroom-market-up' : 'sitroom-market-down';
    const priceStr = m.market_type === 'sentiment'
      ? `${m.price}/100`
      : `$${Number(m.price).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    const label = m.label || m.symbol;
    return `<div class="sitroom-market-card ${cls}">
      <div class="sitroom-market-symbol">${escapeHtml(label)}</div>
      <div class="sitroom-market-price">${priceStr}</div>
      <div class="sitroom-market-change">${arrow} ${Math.abs(m.change_24h).toFixed(1)}%</div>
    </div>`;
  }).join('');
}

/* ─── Earthquakes ─── */
async function renderSitroomQuakes() {
  const minMag = parseFloat(document.getElementById('sitroom-quake-filter')?.value || '4');
  try {
    const resp = await safeFetch(`/api/sitroom/earthquakes?min_magnitude=${minMag}`);
    if (!resp.ok) return;
    const d = await resp.json();
    const list = document.getElementById('sitroom-quake-list');
    if (!list) return;
    if (!d.earthquakes?.length) {
      list.innerHTML = '<div class="sitroom-empty">No earthquakes above M' + minMag + '</div>';
      return;
    }
    list.innerHTML = d.earthquakes.map(q => {
      const magClass = q.magnitude >= 6 ? 'sitroom-mag-high' : q.magnitude >= 4.5 ? 'sitroom-mag-med' : 'sitroom-mag-low';
      const detail = q.detail_json ? JSON.parse(q.detail_json) : {};
      return `<div class="sitroom-event-item">
        <span class="sitroom-mag ${magClass}">M${q.magnitude ? q.magnitude.toFixed(1) : '?'}</span>
        <div class="sitroom-event-info">
          <div class="sitroom-event-title">${escapeHtml(q.title || 'Unknown location')}</div>
          <div class="sitroom-event-meta">Depth: ${q.depth_km ? q.depth_km.toFixed(0) + ' km' : 'N/A'}${detail.alert ? ' | Alert: ' + escapeHtml(detail.alert) : ''}${detail.felt ? ' | Felt: ' + detail.felt + ' reports' : ''}</div>
        </div>
        ${q.source_url ? `<a href="${escapeAttr(q.source_url)}" target="_blank" rel="noopener" class="sitroom-event-link" title="View details">&#8599;</a>` : ''}
      </div>`;
    }).join('');
  } catch (e) {}
}

/* ─── Weather Alerts ─── */
async function loadSitroomWeather() {
  try {
    const resp = await safeFetch('/api/sitroom/weather-alerts');
    if (!resp.ok) return;
    const d = await resp.json();
    const list = document.getElementById('sitroom-weather-list');
    if (!list) return;
    if (!d.alerts?.length) {
      list.innerHTML = '<div class="sitroom-empty">No severe weather alerts</div>';
      return;
    }
    list.innerHTML = d.alerts.slice(0, 30).map(a => {
      const detail = a.detail_json ? JSON.parse(a.detail_json) : {};
      const sevClass = detail.severity === 'Extreme' ? 'sitroom-sev-extreme' : 'sitroom-sev-severe';
      return `<div class="sitroom-event-item ${sevClass}">
        <div class="sitroom-event-info">
          <div class="sitroom-event-title">${escapeHtml(a.title || 'Weather Alert')}</div>
          <div class="sitroom-event-meta">${escapeHtml(detail.headline || '')}${detail.sender ? ' (' + escapeHtml(detail.sender) + ')' : ''}</div>
        </div>
      </div>`;
    }).join('');
  } catch (e) {}
}

/* ─── News Feed ─── */
async function loadSitroomNews(append) {
  if (!append) _sitroomNewsOffset = 0;
  const category = document.getElementById('sitroom-news-category')?.value || '';
  try {
    const resp = await safeFetch(`/api/sitroom/news?category=${encodeURIComponent(category)}&limit=${SITROOM_NEWS_PAGE}&offset=${_sitroomNewsOffset}`);
    if (!resp.ok) return;
    const d = await resp.json();
    const list = document.getElementById('sitroom-news-list');
    const moreBtn = document.getElementById('sitroom-news-more');
    if (!list) return;

    if (!d.articles?.length && !append) {
      list.innerHTML = '<div class="sitroom-empty">No news cached — click Refresh Feeds</div>';
      if (moreBtn) moreBtn.style.display = 'none';
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

    if (moreBtn) {
      moreBtn.style.display = _sitroomNewsOffset < d.total ? '' : 'none';
    }
  } catch (e) {}
}

/* ─── Populate Category Filter ─── */
async function loadSitroomFeeds() {
  try {
    const resp = await safeFetch('/api/sitroom/feeds');
    if (!resp.ok) return;
    const d = await resp.json();

    // Category dropdown
    const sel = document.getElementById('sitroom-news-category');
    if (sel) {
      const cats = [...new Set([...(d.categories || []), ...d.custom.map(f => f.category)])].sort();
      sel.innerHTML = '<option value="">All Categories</option>' + cats.map(c =>
        `<option value="${escapeAttr(c)}">${escapeHtml(c)}</option>`
      ).join('');
    }

    // Feed counts
    const be = document.getElementById('sitroom-builtin-count');
    const ce = document.getElementById('sitroom-custom-count');
    if (be) be.textContent = (d.builtin || []).length;
    if (ce) ce.textContent = (d.custom || []).length;

    // Custom feeds list
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
  } catch (e) {}
}

/* ─── AI Briefing ─── */
async function generateSitroomBriefing() {
  const btn = document.getElementById('sitroom-gen-briefing');
  const container = document.getElementById('sitroom-briefing-content');
  if (!container) return;
  if (btn) btn.disabled = true;
  container.innerHTML = '<div class="sitroom-loading">Generating intelligence briefing...</div>';

  try {
    const resp = await safeFetch('/api/sitroom/ai-briefing', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      container.innerHTML = `<div class="sitroom-empty">${escapeHtml(err.error || 'Briefing generation failed — ensure AI service is running')}</div>`;
      return;
    }
    const d = await resp.json();
    // Render markdown-ish content
    container.innerHTML = `<div class="sitroom-briefing-text">${_renderBriefing(d.briefing || '')}</div>`;
  } catch (e) {
    container.innerHTML = '<div class="sitroom-empty">Network error generating briefing</div>';
  } finally {
    if (btn) btn.disabled = false;
  }
}

function _renderBriefing(text) {
  // Simple markdown-like rendering
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
    const resp = await safeFetch('/api/sitroom/feeds', {
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
    const resp = await safeFetch(`/api/sitroom/feeds/${feedId}`, {method: 'DELETE'});
    if (resp.ok) {
      toast('Feed removed', 'success');
      loadSitroomFeeds();
    }
  } catch (e) {}
}

/* ─── Refresh ─── */
async function refreshSitroomFeeds() {
  const btn = document.getElementById('sitroom-refresh-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Refreshing...'; }

  try {
    const resp = await safeFetch('/api/sitroom/refresh', {method: 'POST'});
    if (resp.ok) {
      toast('Feed refresh started — data will appear shortly', 'info');
      // Poll for completion
      setTimeout(() => {
        loadSitroomSummary();
        loadSitroomNews();
        loadSitroomFeeds();
      }, 8000);
      setTimeout(() => {
        loadSitroomSummary();
        loadSitroomNews();
      }, 20000);
    }
  } catch (e) {
    toast('Refresh failed — check network connection', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Refresh Feeds'; }
  }
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
  if (action === 'filter-news') loadSitroomNews();
  if (action === 'filter-quakes') renderSitroomQuakes();
});

// Category filter change
document.getElementById('sitroom-news-category')?.addEventListener('change', () => loadSitroomNews());
document.getElementById('sitroom-quake-filter')?.addEventListener('change', () => renderSitroomQuakes());

// Map layer toggles
document.querySelectorAll('[data-sitroom-layer]').forEach(cb => {
  cb.addEventListener('change', () => loadSitroomMapData());
});
