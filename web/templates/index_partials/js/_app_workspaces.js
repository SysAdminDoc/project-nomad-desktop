/* ─── Maps ─── */
async function loadMaps() {
  const [regions, files] = await Promise.all([
    safeFetch('/api/maps/regions', {}, []),
    safeFetch('/api/maps/files', {}, []),
  ]);

  document.getElementById('region-grid').innerHTML = regions.map(r => `
    <div class="region-card">
      <div class="region-card-shell">
        <div class="region-card-copy">
          <div class="region-card-title">${r.name}</div>
          <div class="region-card-meta">${r.states}</div>
        </div>
        ${r.downloaded
          ? `<div class="region-card-actions">
              <span class="region-card-size">${r.size}</span>
              <button class="btn btn-sm btn-danger" type="button" data-map-action="delete-map" data-map-filename="${escapeAttr(r.id)}.pmtiles">x</button>
            </div>`
          : `<button class="btn btn-sm btn-primary btn-open-svc-compact" type="button" data-map-action="download-region" data-map-region="${escapeAttr(r.id)}">Download</button>`
        }
      </div>
    </div>
  `).join('');

  const filesEl = document.getElementById('map-files-list');
  if (!files.length) {
    filesEl.innerHTML = '<span class="map-files-empty">No maps downloaded yet.</span>';
  } else {
    filesEl.innerHTML = files.map(f => `
      <div class="model-item">
        <span class="model-name">${escapeHtml(f.filename)}</span>
        <span class="model-item-actions">
          <span class="model-size">${f.size}</span>
          <button class="btn btn-sm btn-danger" type="button" data-map-action="delete-map" data-map-filename="${escapeAttr(f.filename)}">Delete</button>
        </span>
      </div>
    `).join('');
  }
}

function deleteMap(filename, btn) {
  if (!btn) btn = event.target;
  if (!btn.dataset.confirm) {
    btn.dataset.confirm = '1';
    const orig = btn.textContent;
    btn.textContent = 'Confirm delete?';
      btn.style.background = 'var(--red)'; btn.style.color = getThemeCssVar('--text-inverse', '#fff');
    setTimeout(() => { btn.textContent = orig; btn.style.background = ''; btn.style.color = ''; delete btn.dataset.confirm; }, 3000);
    return;
  }
  fetch('/api/maps/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({filename})})
    .then(r => { if (!r.ok) throw new Error(); toast('Map deleted', 'warning'); loadMaps(); })
    .catch(() => toast('Failed to delete map', 'error'));
}

async function downloadMapRegion(regionId) {
  try {
    const resp = await fetch('/api/maps/download-region', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({region_id: regionId})
    });
    const data = await resp.json();
    if (!resp.ok) { toast(data.error || 'Download failed', 'error'); return; }
    toast(`Started downloading region "${regionId}". This may take a while — tiles are extracted from the Protomaps planet build.`, 'info');
    startMapDownloadPolling();
  } catch (e) { toast('Download request failed: ' + e.message, 'error'); }
}

async function downloadAllMaps() {
  if (!confirm('This will download ALL map regions. Each region is extracted from the Protomaps planet build and may be several GB. Continue?')) return;
  try {
    const regions = await (await fetch('/api/maps/regions')).json();
    const toDownload = regions.filter(r => !r.downloaded);
    if (!toDownload.length) { toast('All regions already downloaded!', 'info'); return; }
    // Start downloads sequentially (one at a time to avoid overload)
    for (const r of toDownload) {
      await fetch('/api/maps/download-region', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({region_id: r.id})
      });
    }
    toast(`Queued ${toDownload.length} regions for download.`, 'info');
    startMapDownloadPolling();
  } catch (e) { toast('Failed: ' + e.message, 'error'); }
}

let _mapDlPollTimer = null;
function startMapDownloadPolling() {
  if (_mapDlPollTimer) return;
  const statusEl = document.getElementById('map-download-status');
  if (statusEl) statusEl.style.display = 'block';
  _mapDlPollTimer = setInterval(async () => {
    try {
      const progress = await (await fetch('/api/maps/download-progress')).json();
      const active = Object.entries(progress).filter(([, v]) => v.progress > 0 && v.progress < 100);
      const errors = Object.entries(progress).filter(([, v]) => v.error);

      if (active.length > 0) {
        const label = document.getElementById('map-dl-label');
        const pct = document.getElementById('map-dl-pct');
        const bar = document.getElementById('map-dl-bar');
        // Show all active downloads, not just first
        if (active.length === 1) {
          const [id, info] = active[0];
          if (label) label.textContent = `${id}: ${info.status}`;
          if (pct) pct.textContent = `${info.progress}%`;
          if (bar) bar.style.width = `${info.progress}%`;
        } else {
          const avgPct = Math.round(active.reduce((s,[,v]) => s + v.progress, 0) / active.length);
          if (label) label.textContent = `Downloading ${active.length} regions: ${active.map(([id]) => id).join(', ')}`;
          if (pct) pct.textContent = `~${avgPct}%`;
          if (bar) bar.style.width = `${avgPct}%`;
        }
      } else {
        // No active downloads
        if (statusEl) statusEl.style.display = 'none';
        clearInterval(_mapDlPollTimer);
        _mapDlPollTimer = null;
        loadMaps(); // Refresh the map list
        // Show any errors
        for (const [id, info] of errors) {
          if (info.error) toast(`Map "${id}" failed: ${info.error}`, 'error');
        }
        // Check for completions
        const completed = Object.entries(progress).filter(([, v]) => v.progress === 100);
        if (completed.length > 0) toast(`${completed.length} map region(s) downloaded successfully!`, 'success');
      }
    } catch (e) { /* ignore polling errors */ }
  }, 2000);
}

async function downloadMapFromUrl() {
  const url = document.getElementById('map-url-input')?.value?.trim();
  if (!url) { toast('Enter a URL first', 'warning'); return; }
  // Auto-generate filename from URL, user can edit via the file path input field
  const filename = (document.getElementById('map-file-input')?.value?.trim()) || url.split('/').pop()?.split('?')[0] || 'download.pmtiles';
  if (!filename) { toast('Could not determine filename', 'warning'); return; }
  try {
    const resp = await fetch('/api/maps/download-url', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url, filename})
    });
    const data = await resp.json();
    if (!resp.ok) { toast(data.error || 'Failed', 'error'); return; }
    toast('Download started: ' + filename, 'info');
    startMapDownloadPolling();
  } catch (e) { toast('Failed: ' + e.message, 'error'); }
}

async function importMapFile() {
  const path = document.getElementById('map-file-input')?.value?.trim();
  if (!path) { toast('Enter a file path first', 'error'); return; }
  try {
    const resp = await fetch('/api/maps/import-file', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path})
    });
    const data = await resp.json();
    if (!resp.ok) { toast(data.error || 'Import failed', 'error'); return; }
    toast(`Imported ${data.filename} (${data.size})`, 'success');
    loadMaps();
  } catch (e) { toast('Import failed: ' + e.message, 'error'); }
}

async function loadMapSources() {
  try {
    const sources = await (await fetch('/api/maps/sources')).json();
    const catalog = document.getElementById('map-sources-catalog');
    if (!catalog) return;
    const categories = {};
    for (const s of sources) {
      if (!categories[s.category]) categories[s.category] = [];
      categories[s.category].push(s);
    }
    catalog.innerHTML = Object.entries(categories).map(([cat, items]) => `
      <div class="map-source-group">
        <h4 class="map-source-title">${escapeHtml(cat)}</h4>
        ${items.map(s => `
          <div class="map-source-row">
            <div class="map-source-copy">
              <span class="map-source-name">${escapeHtml(s.name)}</span>
              <span class="map-source-desc">${escapeHtml(s.desc)}</span>
            </div>
            <div class="map-source-actions">
              <span class="map-source-meta">${escapeHtml(s.est_size)} · ${escapeHtml(s.format.toUpperCase())}</span>
              ${s.direct
                ? `<button class="btn btn-sm btn-primary btn-open-svc-compact" data-map-download-url="${escapeAttr(s.url)}">Download</button>`
                : `<button class="btn btn-sm btn-open-svc-compact" data-app-frame-title="${escapeAttr(s.name)}" data-app-frame-url="${escapeAttr(s.url)}">Visit</button>`
              }
            </div>
          </div>
        `).join('')}
      </div>
    `).join('');
  } catch (e) { /* ignore */ }
}

/* ─── Notes ─── */
let allNotes = [];
async function loadNotes() {
  const notesList = document.getElementById('notes-list');
  if (notesList && (!allNotes || allNotes.length === 0)) notesList.innerHTML = Array(4).fill('<div class="skeleton skeleton-card notes-skeleton"></div>').join('');
  try {
    const resp = await fetch('/api/notes');
    if (resp.ok) allNotes = await resp.json();
  } catch(e) { allNotes = allNotes || []; }
  renderNotesList();
}
function renderNoteListHtml(items, emptyText) {
  return items.map(n => `
    <div class="note-item ${n.id===currentNoteId?'active':''}" data-note-action="select-note" data-note-id="${n.id}" role="button" tabindex="0">
      <div class="note-item-head">
        ${n.pinned ? '<span class="note-pin" title="Pinned">&#9733;</span>' : ''}
        <div class="note-title">${escapeHtml(n.title||'Untitled')}</div>
      </div>
      <div class="note-date">${n.tags ? '<span class="note-tag-list">' + n.tags.split(',').map(t=>t.trim()).filter(t=>t).map(t=>'<span class="note-tag-badge">'+escapeHtml(t)+'</span>').join('') + '</span> ' : ''}${new Date(n.updated_at).toLocaleDateString()}</div>
    </div>
  `).join('') || `<div class="notes-empty-state">${emptyText}</div>`;
}
function renderNotesList() {
  const list = document.getElementById('notes-list');
  const q = (document.getElementById('notes-search')?.value || '').toLowerCase();
  let filtered = q ? allNotes.filter(n => (n.title||'').toLowerCase().includes(q) || (n.tags||'').toLowerCase().includes(q)) : allNotes;
  list.innerHTML = renderNoteListHtml(filtered, 'No notes yet');
}
function selectNote(id) {
  currentNoteId = id;
  const n = allNotes.find(n => n.id === id);
  if (n) {
    document.getElementById('note-title').value = n.title||'';
    document.getElementById('note-content').value = n.content||'';
    document.getElementById('note-tags').value = n.tags||'';
    document.getElementById('note-pin-btn').textContent = n.pinned ? 'Unpin' : 'Pin';
  }
  renderNotesList();
  updateNoteWordCount();
  loadNoteBacklinks(id);
}
async function createNote() {
  const n = await (await fetch('/api/notes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:'New Note', content:''})})).json();
  await loadNotes();
  selectNote(n.id);
}
function exportCurrentNote() {
  if (!currentNoteId) { toast('No note selected', 'warning'); return; }
  window.location = `/api/notes/${currentNoteId}/export`;
}

function openWikiLink(title) {
  // Switch to notes tab and open the linked note
  document.querySelector('[data-tab="notes"]').click();
  setTimeout(() => {
    const note = (typeof allNotes !== 'undefined' ? allNotes : []).find(n => n.title === title);
    if (note) {
      selectNote(note.id);
    } else {
      // Create a new note with this title
      if (confirm('Note "' + title + '" does not exist. Create it?')) {
        createNoteWithTitle(title);
      }
    }
  }, 200);
}

async function createNoteWithTitle(title) {
  const r = await safeFetch('/api/notes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title, content:''})}, null);
  if (r && r.id) {
    loadNotes();
    setTimeout(() => selectNote(r.id), 300);
  }
}

let _noteTemplatesCache = [];
async function toggleNoteTemplates() {
  const dd = document.getElementById('note-template-dropdown');
  if (dd.style.display === 'block') { dd.style.display = 'none'; return; }
  dd.style.display = 'block';
  const list = document.getElementById('note-template-list');
  _noteTemplatesCache = await safeFetch('/api/notes/templates', {}, []);
  list.innerHTML = _noteTemplatesCache.map((t, idx) => `
    <div class="note-template-item" data-note-action="apply-note-template" data-note-template-index="${idx}" role="button" tabindex="0">
      <span class="note-template-item-icon">${escapeHtml(t.icon || '\u{1F4DD}')}</span>
      <span class="note-template-item-label">${escapeHtml(t.name)}</span>
    </div>
  `).join('');
  setTimeout(() => document.addEventListener('click', function closer(e) {
    if (!dd.contains(e.target)) { dd.style.display = 'none'; document.removeEventListener('click', closer); }
  }), 10);
}

async function applyNoteTemplateByIndex(idx) {
  const t = _noteTemplatesCache[idx];
  if (!t) return;
  document.getElementById('note-template-dropdown').style.display = 'none';
  const r = await safeFetch('/api/notes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title: t.name, content: t.content})}, null);
  if (r && r.id) {
    loadNotes();
    setTimeout(() => selectNote(r.id), 300);
  }
}

async function deleteNote() {
  if (!currentNoteId) return;
  await fetch(`/api/notes/${currentNoteId}`, {method:'DELETE'});
  currentNoteId = null;
  document.getElementById('note-title').value = '';
  document.getElementById('note-content').value = '';
  await loadNotes();
}
function filterNotes() {
  const q = document.getElementById('notes-search').value.toLowerCase();
  if (!q) { renderNotesList(); return; }
  const filtered = allNotes.filter(n => (n.title||'').toLowerCase().includes(q) || (n.content||'').toLowerCase().includes(q));
  const list = document.getElementById('notes-list');
  list.innerHTML = renderNoteListHtml(filtered, 'No matches');
}

function updateNoteWordCount() {
  const text = document.getElementById('note-content')?.value || '';
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const chars = text.length;
  const el = document.getElementById('note-word-count');
  if (el) el.textContent = words > 0 ? `${words} words | ${chars} chars` : '';
}

function autoSaveNote() {
  if (!currentNoteId) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    await fetch(`/api/notes/${currentNoteId}`, {method:'PUT', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title:document.getElementById('note-title').value, content:document.getElementById('note-content').value})});
    await loadNotes();
  }, 500);
}

/* ─── Benchmark ─── */
async function runBenchmark(mode) {
  document.getElementById('bench-run-btn').disabled = true;
  document.getElementById('bench-progress').style.display = 'block';
  document.getElementById('bench-results').innerHTML = '';
  await fetch('/api/benchmark/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mode})});
  pollBenchmark();
}

let _benchPoll = null;
function pollBenchmark() {
  if (_benchPoll) clearInterval(_benchPoll);
  _benchPoll = setInterval(async () => {
    const s = await (await fetch('/api/benchmark/status')).json();
    document.getElementById('bench-fill').style.width = s.progress + '%';
    document.getElementById('bench-stage').textContent = s.stage;
    document.getElementById('bench-pct').textContent = s.progress + '%';

    if (s.status === 'complete' || s.status === 'error') {
      clearInterval(_benchPoll);
      _benchPoll = null;
      document.getElementById('bench-run-btn').disabled = false;
      document.getElementById('bench-progress').style.display = 'none';
      if (s.status === 'complete' && s.results) showBenchResults(s.results);
      if (s.status === 'error') toast('Benchmark failed: ' + s.stage, 'error');
      loadBenchHistory();
    }
  }, 1000);
}

function showBenchResults(r) {
  document.getElementById('bench-results').innerHTML = `
    <div class="benchmark-results-overview">
      <div class="benchmark-score-hero"><div class="bench-big"><span>${r.nomad_score}</span></div><div class="benchmark-score-caption">NOMAD Score</div></div>
      <div class="benchmark-run-summary">
        <div class="benchmark-run-summary-kicker">LATEST RUN</div>
        <div class="benchmark-run-summary-title">This snapshot covers system throughput and model responsiveness.</div>
        <div class="benchmark-run-summary-copy">Use the score cards below for the immediate picture, then compare against history to spot drift or a machine that is falling behind.</div>
      </div>
    </div>
    <div class="bench-scores benchmark-metric-grid">
      <div class="bench-score"><div class="score-val">${r.cpu_score||0}</div><div class="score-label">CPU ops/s</div></div>
      <div class="bench-score"><div class="score-val">${r.memory_score||0}</div><div class="score-label">Memory MB/s</div></div>
      <div class="bench-score"><div class="score-val">${r.disk_read_score||0}</div><div class="score-label">Disk Read MB/s</div></div>
      <div class="bench-score"><div class="score-val">${r.disk_write_score||0}</div><div class="score-label">Disk Write MB/s</div></div>
      <div class="bench-score"><div class="score-val">${r.ai_tps||0}</div><div class="score-label">AI Speed (tok/s)</div></div>
      <div class="bench-score"><div class="score-val">${r.ai_ttft||0}</div><div class="score-label">Response Time (ms)</div></div>
    </div>
    <div class="benchmark-result-note">Compare this run against Diagnostics History below before changing hardware, storage, or model expectations.</div>
  `;
}

async function loadBenchHistory() {
  try {
    const history = await (await fetch('/api/benchmark/history')).json();
    const el = document.getElementById('bench-history');
    if (!history.length) { el.innerHTML = '<span class="benchmark-empty-state">No benchmarks run yet.</span>'; return; }
    const latest = history[0];
    const oldest = history[history.length - 1];
    const totalDelta = oldest && latest ? latest.nomad_score - oldest.nomad_score : 0;
    function delta(curr, prev) {
      if (!prev || curr == null || prev == null) return '';
      const d = curr - prev;
      if (d === 0) return '';
      const tone = d > 0 ? 'benchmark-delta-up' : 'benchmark-delta-down';
      return ` <span class="benchmark-delta ${tone}">${d > 0 ? '+' : ''}${d.toFixed ? d.toFixed(1) : d}</span>`;
    }
    el.innerHTML = `<div class="benchmark-history-summary">
      <div class="benchmark-history-stat">
        <span class="benchmark-history-stat-label">Tracked runs</span>
        <strong class="benchmark-history-stat-value">${history.length}</strong>
      </div>
      <div class="benchmark-history-stat">
        <span class="benchmark-history-stat-label">Latest score</span>
        <strong class="benchmark-history-stat-value">${latest.nomad_score}</strong>
      </div>
      <div class="benchmark-history-stat">
        <span class="benchmark-history-stat-label">Long trend</span>
        <strong class="benchmark-history-stat-value ${totalDelta >= 0 ? 'benchmark-delta-up' : 'benchmark-delta-down'}">${totalDelta >= 0 ? '+' : ''}${totalDelta}</strong>
      </div>
    </div>
    <div class="benchmark-history-shell"><table class="benchmark-history-table">
      <tr><th>Date</th><th>Score</th><th>CPU</th><th>Mem</th><th>Disk R</th><th>Disk W</th><th>AI tok/s</th></tr>
      ${history.map((h, i) => {
        const prev = history[i + 1]; // previous run (older)
        return `<tr>
          <td>${new Date(h.created_at).toLocaleDateString()}</td>
          <td><strong class="benchmark-score-pill">${h.nomad_score}</strong>${delta(h.nomad_score, prev?.nomad_score)}</td>
          <td>${h.cpu_score}${delta(h.cpu_score, prev?.cpu_score)}</td>
          <td>${h.memory_score}${delta(h.memory_score, prev?.memory_score)}</td>
          <td>${h.disk_read_score}${delta(h.disk_read_score, prev?.disk_read_score)}</td>
          <td>${h.disk_write_score}${delta(h.disk_write_score, prev?.disk_write_score)}</td>
          <td>${h.ai_tps}${delta(h.ai_tps, prev?.ai_tps)}</td>
        </tr>`;
      }).join('')}
    </table></div>`;
    // Also load extended benchmark results (AI inference, storage)
    const extResults = await safeFetch('/api/benchmark/results', {}, []);
    if (extResults.length) {
      el.innerHTML += `<div class="benchmark-tests-block"><div class="benchmark-subheading">Individual Tests</div>
        <div class="benchmark-history-shell"><table class="benchmark-history-table benchmark-history-table-secondary">
        <tr><th>Date</th><th>Test</th><th>Result</th></tr>
        ${extResults.slice(0, 10).map(r => {
          const scores = JSON.parse(r.scores || '{}');
          let result = '';
          if (r.test_type === 'ai_inference') result = (scores.tps || 0) + ' tok/s (' + escapeHtml(scores.model || '') + ')';
          else if (r.test_type === 'storage') result = 'R: ' + (scores.read_mbps || 0) + ' MB/s, W: ' + (scores.write_mbps || 0) + ' MB/s';
          else result = JSON.stringify(scores).substring(0, 60);
          return '<tr><td>' + new Date(r.created_at).toLocaleDateString() + '</td><td class="benchmark-result-type">' + escapeHtml(r.test_type.replace('_', ' ')) + '</td><td class="benchmark-result-mono">' + result + '</td></tr>';
        }).join('')}
        </table></div></div>`;
    }
  } catch(e) {
    document.getElementById('bench-history').innerHTML = '<span class="benchmark-empty-state">Failed to load history</span>';
  }
}

async function runAIBenchmark() {
  const btn = document.getElementById('bench-ai-btn');
  if (btn) btn.disabled = true;
  const modelSel = document.getElementById('model-select');
  const model = modelSel ? modelSel.value : '';
  if (!model) { toast('Select an AI model first (go to AI Chat tab)', 'warning'); if (btn) btn.disabled = false; return; }
  toast('Running AI inference benchmark...', 'info');
  const r = await safeFetch('/api/benchmark/ai-inference', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model})}, null);
  if (btn) btn.disabled = false;
  if (r) {
    toast(`AI Benchmark: ${r.tokens_per_sec} tokens/sec (${r.model})`, 'success');
    loadBenchHistory();
  } else {
    toast('AI benchmark failed — is a model loaded?', 'error');
  }
}

async function runStorageBenchmark() {
  const btn = document.getElementById('bench-storage-btn');
  if (btn) btn.disabled = true;
  toast('Running storage I/O benchmark (32MB read/write)...', 'info');
  const r = await safeFetch('/api/benchmark/storage', {method:'POST'}, null);
  if (btn) btn.disabled = false;
  if (r) {
    toast(`Storage: Read ${r.read_mbps} MB/s, Write ${r.write_mbps} MB/s`, 'success');
    loadBenchHistory();
  } else {
    toast('Storage benchmark failed', 'error');
  }
}

/* ─── Settings ─── */
async function loadSettings() {
  try {
    const s = await (await fetch('/api/settings')).json();
    if (s.ai_name) {
      aiName = s.ai_name;
      document.getElementById('ai-name-input').value = aiName;
    }
    if (s.theme && !localStorage.getItem('nomad-theme')) {
      setTheme(s.theme);
    }
  } catch(e) {}

  try {
    const n = await (await fetch('/api/network')).json();
    document.getElementById('lan-url-setting').textContent = n.dashboard_url || '-';
  } catch(e) {}
}

let _saveNameTimer;
function saveAIName() {
  clearTimeout(_saveNameTimer);
  _saveNameTimer = setTimeout(async () => {
    aiName = document.getElementById('ai-name-input').value || 'AI';
    await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ai_name: aiName})});
  }, 500);
}

async function loadSystemInfo() {
  try {
    const s = await (await fetch('/api/system')).json();

    // Gauges
    function gaugeColor(pct) { return pct > 90 ? 'gauge-red' : pct > 70 ? 'gauge-orange' : 'gauge-green'; }
    document.getElementById('system-gauges').innerHTML = `
      <div class="gauge-card ${gaugeColor(s.cpu_percent)}">
        <div class="gauge-label">CPU</div>
        <div class="gauge-value">${s.cpu_percent}%</div>
        <div class="gauge-bar"><div class="fill" style="width:${s.cpu_percent}%"></div></div>
      </div>
      <div class="gauge-card ${gaugeColor(s.ram_percent)}">
        <div class="gauge-label">Memory</div>
        <div class="gauge-value">${s.ram_percent}%</div>
        <div class="gauge-bar"><div class="fill" style="width:${s.ram_percent}%"></div></div>
      </div>
      <div class="gauge-card ${gaugeColor(s.swap_percent)}">
        <div class="gauge-label">Swap</div>
        <div class="gauge-value">${s.swap_percent}%</div>
        <div class="gauge-bar"><div class="fill" style="width:${s.swap_percent}%"></div></div>
      </div>
      <div class="gauge-card gauge-blue">
        <div class="gauge-label">Uptime</div>
        <div class="gauge-value" style="font-size:16px;">${s.uptime}</div>
        <div class="gauge-bar"><div class="fill" style="width:100%"></div></div>
      </div>
    `;

    // System info
    document.getElementById('system-info').innerHTML = `
      <div class="setting-row"><span class="setting-label">Version</span><span class="setting-value">v${s.version}</span></div>
      <div class="setting-row"><span class="setting-label">Platform</span><span class="setting-value">${s.platform}</span></div>
      <div class="setting-row"><span class="setting-label">Hostname</span><span class="setting-value">${s.hostname}</span></div>
      <div class="setting-row"><span class="setting-label">CPU</span><span class="setting-value">${s.cpu}</span></div>
      <div class="setting-row"><span class="setting-label">Cores</span><span class="setting-value">${s.cpu_cores_physical} physical / ${s.cpu_cores} logical</span></div>
      <div class="setting-row"><span class="setting-label">RAM</span><span class="setting-value">${s.ram_used} / ${s.ram_total} (${s.ram_percent}%)</span></div>
      <div class="setting-row"><span class="setting-label">Swap</span><span class="setting-value">${s.swap_used} / ${s.swap_total}</span></div>
      <div class="setting-row"><span class="setting-label">GPU</span><span class="setting-value">${s.gpu}${s.gpu_vram ? ' ('+s.gpu_vram+')' : ''}</span></div>
      <div class="setting-row"><span class="setting-label">NOMAD Data</span><span class="setting-value">${s.nomad_disk_used}</span></div>
    `;
    document.getElementById('data-dir').textContent = s.data_dir;

    // Disk devices
    const dd = document.getElementById('disk-devices');
    if (s.disk_devices && s.disk_devices.length) {
      dd.innerHTML = s.disk_devices.map(d => {
        const color = d.percent > 90 ? 'var(--red)' : d.percent > 75 ? 'var(--orange)' : 'var(--accent)';
        return `<div class="disk-device">
          <div class="disk-label"><span>${d.mountpoint} (${d.fstype})</span><span>${d.used} / ${d.total} (${d.percent}%)</span></div>
          <div class="progress-bar"><div class="fill" style="width:${d.percent}%;background:${color};"></div></div>
        </div>`;
      }).join('');
    } else {
      dd.innerHTML = `<div class="setting-row"><span class="setting-label">Disk Free</span><span class="setting-value">${s.disk_free} / ${s.disk_total}</span></div>`;
    }
  } catch(e) { document.getElementById('system-info').innerHTML = '<span class="text-red">Failed to load</span>'; }
}

let _liveGaugeInt = null;
function startLiveGauges() {
  if (_liveGaugeInt) clearInterval(_liveGaugeInt);
  _liveGaugeInt = setInterval(async () => {
    if (!document.getElementById('tab-settings').classList.contains('active')) { clearInterval(_liveGaugeInt); _liveGaugeInt = null; return; }
    try {
      const l = await (await fetch('/api/system/live')).json();
      const gauges = document.querySelectorAll('#system-gauges .gauge-card');
      if (gauges.length >= 3) {
        function updateGauge(g, pct) {
          g.querySelector('.gauge-value').textContent = pct + '%';
          g.querySelector('.gauge-bar .fill').style.width = pct + '%';
          g.className = 'gauge-card ' + (pct > 90 ? 'gauge-red' : pct > 70 ? 'gauge-orange' : 'gauge-green');
        }
        updateGauge(gauges[0], l.cpu_percent);
        updateGauge(gauges[1], l.ram_percent);
        updateGauge(gauges[2], l.swap_percent);
      }
    } catch(e) {
      const vals = document.querySelectorAll('#system-gauges .gauge-card .gauge-value');
      vals.forEach(g => { if (!g.textContent.endsWith('?')) g.textContent += ' ?'; });
    }
  }, 3000);
}

async function loadModelManager() {
  try {
  const models = await (await fetch('/api/ai/models')).json();
  const el = document.getElementById('model-list');
  if (!models.length) {
    el.innerHTML = '<div class="settings-empty-state model-list-empty">No models downloaded</div>';
  } else {
    el.innerHTML = models.map(m => `
      <div class="model-item">
        <span class="model-name">${m.name}</span>
        <span class="model-item-actions">
          <span class="model-size">${(m.size/1e9).toFixed(1)} GB</span>
          <button class="btn btn-sm btn-danger" type="button" data-shell-action="delete-model" data-model-name="${escapeAttr(m.name)}">Delete</button>
        </span>
      </div>
    `).join('');
  }

  const rec = await (await fetch('/api/ai/recommended')).json();
  const installed = new Set(models.map(m => m.name));
  document.getElementById('recommended-models').innerHTML = rec.map(r => `
    <div class="model-item">
      <span><span class="model-name">${r.name}</span> <span class="model-size">${r.desc} (${r.size})</span></span>
      ${installed.has(r.name)
        ? '<span class="runtime-status-installed">Installed</span>'
        : `<button class="btn btn-sm btn-primary" type="button" data-shell-action="pull-settings-model" data-model-name="${escapeAttr(r.name)}">Pull</button>`}
    </div>
  `).join('');
  } catch(e) {}
}

function deleteModel(name, btn) {
  if (!btn) btn = event.target;
  if (!btn.dataset.confirm) {
    btn.dataset.confirm = '1';
    btn.textContent = 'Confirm?';
      btn.style.background = 'var(--red)'; btn.style.color = getThemeCssVar('--text-inverse', '#fff');
    setTimeout(() => { btn.textContent = 'Delete'; btn.style.background = ''; btn.style.color = ''; delete btn.dataset.confirm; }, 3000);
    return;
  }
  fetch('/api/ai/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model:name})})
    .then(r => r.json()).then(d => {
      if (d.error) { toast(`Failed to delete: ${d.error}`, 'error'); return; }
      toast(`Deleted ${name}`, 'warning');
      loadModelManager(); loadModels();
    }).catch(() => toast('Delete failed', 'error'));
}

async function pullFromSettings(name) {
  await fetch('/api/ai/pull', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model:name})});
  toast(`Pulling ${name}...`);
  document.querySelector('[data-tab="ai-chat"]').click();
  pollPullProgress();
}

/* ─── Network Status ─── */
let _backendFailCount = 0;
async function checkNetwork() {
  try {
    const n = await (await fetch('/api/network')).json();
    _backendFailCount = 0;
    const el = document.getElementById('net-status');
    const label = n.online ? 'Online' : 'Offline';
    el.innerHTML = `<span class="network-status-inline ${n.online ? 'is-online' : 'is-offline'}"><span class="network-status-dot"></span><span>${label} &middot; ${escapeHtml(n.lan_ip)}</span></span>`;
    // Clear connection-lost banner if it was shown
    const lostBanner = document.getElementById('connection-lost');
    if (lostBanner) lostBanner.style.display = 'none';
    // LAN banner
    const banner = document.getElementById('lan-banner');
    if (n.lan_ip !== '127.0.0.1') {
      banner.style.display = 'flex';
      banner.innerHTML = `Access from other devices on your network: <a href="${escapeAttr(n.dashboard_url)}">${escapeHtml(n.dashboard_url)}</a>`;
    }
  } catch(e) {
    _backendFailCount++;
    if (_backendFailCount >= 2) {
      const el = document.getElementById('net-status');
      el.innerHTML = '<span class="network-status-inline is-offline"><span class="network-status-dot"></span><span>Disconnected</span></span>';
      // Show connection-lost banner
      let lostBanner = document.getElementById('connection-lost');
      if (!lostBanner) {
        lostBanner = document.createElement('div');
        lostBanner.id = 'connection-lost';
        lostBanner.className = 'connection-lost-banner';
        lostBanner.textContent = 'Connection to backend lost — retrying automatically...';
        const headerEl = document.querySelector('.status-strip') || document.querySelector('.main-content');
        if (headerEl) headerEl.prepend(lostBanner);
        else document.body.prepend(lostBanner);
      }
      lostBanner.style.display = 'block';
    }
  }
}

/* ─── Setup Wizard ─── */
let _wizDrivePath = '';
let _wizTier = 'essential';
let _wizTiers = {};

async function checkWizard() {
  if (new URLSearchParams(location.search).has('wizard')) {
    setShellVisibility(document.getElementById('wizard'), true);
  }
}

function wizGoPage(n) {
  for (let i = 1; i <= 5; i++) {
    const el = document.getElementById('wiz-page-' + i);
    if (el) el.style.display = i === n ? 'grid' : 'none';
  }
  if (n === 2) wizLoadDrives();
  if (n === 3) wizLoadTiers();
}

function setWizardStorageStatus(message, success = false) {
  const el = document.getElementById('wiz-storage-status');
  if (!el) return;
  el.textContent = message;
  el.classList.toggle('wizard-status-line-success', success);
}

async function wizLoadDrives() {
  const drives = await (await fetch('/api/drives')).json();
  const el = document.getElementById('wiz-drives');
  let bestDrive = drives[0];
  drives.forEach(d => {
    if (d.free > (bestDrive?.free || 0)) bestDrive = d;
  });
  if (!_wizDrivePath && bestDrive) _wizDrivePath = bestDrive.path;

  el.innerHTML = drives.map(d => {
    const sel = d.path === _wizDrivePath;
    const pct = d.percent;
    const color = pct > 90 ? 'var(--red)' : pct > 75 ? 'var(--orange)' : 'var(--green)';
    return `<button type="button" class="wizard-drive-card${sel ? ' is-selected' : ''}" data-shell-action="wiz-select-drive" data-drive-path="${escapeAttr(d.path)}">
      <span class="wizard-drive-title">${escapeHtml(d.path)}</span>
      <span class="wizard-drive-copy">${escapeHtml(d.free_str)} free of ${escapeHtml(d.total_str)}</span>
      <div class="progress-bar wizard-drive-progress"><div class="fill" style="width:${pct}%;background:${color};"></div></div>
    </button>`;
  }).join('');
  setWizardStorageStatus(
    _wizDrivePath ? 'Data will be stored at: ' + _wizDrivePath + 'NOMADFieldDesk\\' : 'Select a drive above',
    !!_wizDrivePath
  );
}

function wizSelectDrive(path) { _wizDrivePath = path; wizLoadDrives(); }

function wizSetCustomPath() {
  const path = document.getElementById('wiz-custom-path').value.trim();
  if (!path) return;
  _wizDrivePath = path.endsWith('\\') ? path : path + '\\';
  setWizardStorageStatus('Custom path: ' + _wizDrivePath + 'NOMADFieldDesk\\', true);
}

// Custom tier selection state
let _wizCustomServices = [];
let _wizCustomModels = [];
let _wizCustomZims = [];

async function wizLoadTiers() {
  _wizTiers = await (await fetch('/api/content-tiers')).json();
  const el = document.getElementById('wiz-tiers');
  const tierOrder = ['essential','standard','maximum','custom'];
  const tierIcons = {essential:'&#9733;', standard:'&#9733;&#9733;', maximum:'&#9733;&#9733;&#9733;', custom:'&#9881;'};
  const tierColors = {essential:'var(--green)', standard:'var(--accent)', maximum:'var(--purple)', custom:'var(--orange)'};
  // Add a virtual "custom" tier
  if (!_wizTiers['custom']) {
    _wizTiers['custom'] = {name:'Custom', desc:'Choose exactly which services, models, and content packs to install', services:[], zims:[], models:[], zim_count:0, est_size:'Varies'};
  }
  el.innerHTML = tierOrder.map(tid => {
    const t = _wizTiers[tid]; if (!t) return '';
    const sel = tid === _wizTier;
    const detail = tid === 'custom'
      ? '<div class="wizard-tier-meta">Pick individual items below</div>'
      : `<div class="wizard-tier-meta">${t.services.length} tools + ${t.zim_count || t.zims.length} content packs + ${t.models.length} AI model${t.models.length>1?'s':''}</div>`;
    return '<button type="button" class="wizard-tier-card' + (sel ? ' is-selected' : '') + '" data-shell-action="wiz-select-tier" data-tier-id="' + tid + '">'
      + '<div class="wizard-tier-copy">'
      + '<div class="wizard-tier-title" style="color:' + tierColors[tid] + ';">' + tierIcons[tid] + ' ' + t.name + '</div>'
      + '<div class="wizard-tier-desc">' + t.desc + '</div>'
      + detail
      + '</div>'
      + '<div class="wizard-tier-size">'
      + '<div class="wizard-tier-size-value" style="color:' + tierColors[tid] + ';">' + t.est_size + '</div>'
      + (tid !== 'custom' ? '<div class="wizard-tier-size-label">estimated</div>' : '')
      + '</div>'
      + '</button>';
  }).join('');
  // Show/hide custom panel and tier detail
  const customPanel = document.getElementById('wiz-custom-panel');
  if (_wizTier === 'custom') {
    customPanel.style.display = 'block';
    document.getElementById('wiz-tier-detail').style.display = 'none';
    wizBuildCustomPanel();
  } else {
    customPanel.style.display = 'none';
    wizShowTierDetail();
  }
}

function wizBuildCustomPanel() {
  // Populate custom checkboxes from the "maximum" tier (full list)
  const max = _wizTiers['maximum'] || _wizTiers['standard'] || {};
  const allServices = ['ollama','kiwix','cyberchef','kolibri','qdrant','stirling','flatnotes'];
  const allModels = ['qwen3:4b','qwen3:8b','alibayram/medgemma','deepseek-r1:8b','gemma3:4b','llama3.2:3b'];
  // If no custom selections yet, pre-select essentials
  if (!_wizCustomServices.length) _wizCustomServices = ['ollama','kiwix','cyberchef','stirling'];
  if (!_wizCustomModels.length) _wizCustomModels = ['qwen3:4b'];

  const svcEl = document.getElementById('wiz-custom-services');
  svcEl.innerHTML = allServices.map(s => {
    const checked = _wizCustomServices.includes(s);
    const name = (SVC[s] || {}).name || s;
    return '<label class="wizard-custom-chip">'
      + '<input type="checkbox" class="wizard-custom-check" ' + (checked?'checked':'') + ' data-change-action="wiz-toggle-custom" data-wiz-custom-type="service" data-wiz-custom-value="' + s + '">'
      + escapeHtml(name) + '</label>';
  }).join('');

  const modEl = document.getElementById('wiz-custom-models');
  modEl.innerHTML = allModels.map(m => {
    const checked = _wizCustomModels.includes(m);
    return '<label class="wizard-custom-chip">'
      + '<input type="checkbox" class="wizard-custom-check" ' + (checked?'checked':'') + ' data-change-action="wiz-toggle-custom" data-wiz-custom-type="model" data-wiz-custom-value="' + escapeHtml(m) + '">'
      + escapeHtml(m) + '</label>';
  }).join('');

  // Group ZIMs by category (from maximum tier)
  const allZims = max.zims || [];
  const cats = {};
  allZims.forEach(z => { const c = z.category || 'Other'; if (!cats[c]) cats[c] = []; cats[c].push(z); });
  // Default: select essential ZIMs only
  if (!_wizCustomZims.length) {
    const ess = _wizTiers['essential'];
    if (ess) _wizCustomZims = ess.zims.map(z => z.filename);
  }

  const zimEl = document.getElementById('wiz-custom-zims');
  zimEl.innerHTML = Object.entries(cats).map(([cat, items]) => {
    return '<div class="wizard-custom-zim-group">'
      + '<div class="wizard-custom-zim-group-title">' + escapeHtml(cat) + '</div>'
      + items.map(z => {
        const checked = _wizCustomZims.includes(z.filename);
        return '<label class="wizard-custom-zim-row">'
          + '<input type="checkbox" class="wizard-custom-check" ' + (checked?'checked':'') + ' data-change-action="wiz-toggle-custom" data-wiz-custom-type="zim" data-wiz-custom-value="' + escapeHtml(z.filename) + '">'
          + '<span class="wizard-custom-zim-name">' + escapeHtml(z.name) + '</span>'
          + '<span class="wizard-custom-zim-size">' + escapeHtml(z.size) + '</span>'
          + '</label>';
      }).join('')
      + '</div>';
  }).join('');
}

function wizToggleCustom(type, value, checked) {
  if (type === 'service') {
    if (checked) { if (!_wizCustomServices.includes(value)) _wizCustomServices.push(value); }
    else { _wizCustomServices = _wizCustomServices.filter(s => s !== value); }
  } else if (type === 'model') {
    if (checked) { if (!_wizCustomModels.includes(value)) _wizCustomModels.push(value); }
    else { _wizCustomModels = _wizCustomModels.filter(m => m !== value); }
  } else if (type === 'zim') {
    if (checked) { if (!_wizCustomZims.includes(value)) _wizCustomZims.push(value); }
    else { _wizCustomZims = _wizCustomZims.filter(z => z !== value); }
  }
}

function wizCustomSelectAll() {
  const max = _wizTiers['maximum'] || {};
  _wizCustomZims = (max.zims || []).map(z => z.filename);
  wizBuildCustomPanel();
}

function wizCustomDeselectAll() {
  _wizCustomZims = [];
  wizBuildCustomPanel();
}

function wizSelectTier(tid) { _wizTier = tid; wizLoadTiers(); }

function wizShowTierDetail() {
  const t = _wizTiers[_wizTier]; if (!t) return;
  const el = document.getElementById('wiz-tier-detail'); el.style.display = 'block';
  const cats = {};
  (t.zims || []).forEach(z => { if (!cats[z.category]) cats[z.category] = []; cats[z.category].push(z); });
  el.innerHTML = '<div class="wizard-tier-detail-shell">'
    + '<div class="wizard-tier-detail-title">What\'s included in ' + escapeHtml(t.name) + ':</div>'
    + '<div class="wizard-tier-detail-row"><span class="wizard-tier-detail-label">Services</span><span class="wizard-tier-detail-copy">' + t.services.map(function(s){return escapeHtml((SVC[s]||{}).name||s);}).join(', ') + '</span></div>'
    + '<div class="wizard-tier-detail-row"><span class="wizard-tier-detail-label">AI Models</span><span class="wizard-tier-detail-copy">' + t.models.map(escapeHtml).join(', ') + '</span></div>'
    + '<div class="wizard-tier-detail-row wizard-tier-detail-row-stack"><span class="wizard-tier-detail-label">Content Packs (' + (t.zim_count || t.zims.length) + ')</span></div>'
    + Object.entries(cats).map(function([cat, items]) {
      return '<div class="wizard-tier-group"><div class="wizard-tier-group-title">' + escapeHtml(cat) + '</div>'
      + items.map(function(z){return '<div class="wizard-tier-zim-row"><span class="wizard-tier-zim-name">' + escapeHtml(z.name) + '</span><span class="wizard-tier-zim-size">' + escapeHtml(z.size) + '</span></div>';}).join('')
      + '</div>';}).join('')
    + '</div>';
}

async function wizStartSetup() {
  let services, zims, models;
  if (_wizTier === 'custom') {
    services = _wizCustomServices;
    models = _wizCustomModels;
    // Resolve filenames to full ZIM objects
    const max = _wizTiers['maximum'] || _wizTiers['standard'] || {};
    const allZims = max.zims || [];
    zims = allZims.filter(z => _wizCustomZims.includes(z.filename));
  } else {
    const t = _wizTiers[_wizTier]; if (!t) return;
    services = t.services;
    zims = t.zims;
    models = t.models;
  }
  wizGoPage(4);
  if (_wizDrivePath) {
    await fetch('/api/settings/data-dir', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path: _wizDrivePath})});
  }
  await fetch('/api/wizard/setup', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({services: services, zims: zims, models: models})});
  wizPollProgress();
}

let _wizMinimized = false;

function wizMinimize() {
  _wizMinimized = true;
  setShellVisibility(document.getElementById('wizard'), false);
  setShellVisibility(document.getElementById('wiz-mini-banner'), true);
}

function wizRestore() {
  _wizMinimized = false;
  setShellVisibility(document.getElementById('wiz-mini-banner'), false);
  setShellVisibility(document.getElementById('wizard'), true);
}

let _wizPollInt = null;
let _wizLastProgress = 0;
let _wizStallCount = 0;
function wizPollProgress() {
  if (_wizPollInt) clearInterval(_wizPollInt);
  _wizLastProgress = 0;
  _wizStallCount = 0;
  _wizPollInt = setInterval(async () => {
    try {
    const s = await (await fetch('/api/wizard/progress')).json();
    document.getElementById('wiz-overall-fill').style.width = s.overall_progress + '%';
    document.getElementById('wiz-overall-pct').textContent = s.overall_progress + '%';
    document.getElementById('wiz-current-item').textContent = s.current_item || '...';
    document.getElementById('wiz-item-fill').style.width = s.item_progress + '%';
    document.getElementById('wiz-item-pct').textContent = s.item_progress + '%';
    // Update mini banner too
    document.getElementById('wiz-mini-pct').textContent = s.overall_progress + '%';
    document.getElementById('wiz-mini-fill').style.width = s.overall_progress + '%';
    document.getElementById('wiz-mini-item').textContent = s.current_item || '...';
    const phaseNames = {services:'Installing tools...', starting:'Starting services...', content:'Downloading offline content...', models:'Downloading AI models...', done:'Complete!'};
    document.getElementById('wiz-phase-label').textContent = phaseNames[s.phase] || s.phase;
    // Detect stall — show help after 60 seconds of no progress change
    if (s.overall_progress === _wizLastProgress && s.item_progress === 0) {
      _wizStallCount++;
      if (_wizStallCount > 30) { // 30 polls * 2s = 60 seconds
        document.getElementById('wiz-stall-help').style.display = 'block';
      }
    } else {
      _wizStallCount = 0;
      _wizLastProgress = s.overall_progress;
      document.getElementById('wiz-stall-help').style.display = 'none';
    }
    if (s.completed.length) {
      document.getElementById('wiz-completed-list').innerHTML = s.completed.map(c =>
        `<div class="wizard-complete-row"><span class="wizard-complete-icon">&#10003;</span><span>${escapeHtml(c)}</span></div>`).join('');
    }
    if (s.errors.length) {
      const errEl = document.getElementById('wiz-errors'); errEl.style.display = 'block';
      errEl.innerHTML = s.errors.map(e => `<div class="wizard-error-row">&#10007; ${escapeHtml(e)}</div>`).join('');
    }
    if (s.status === 'complete') {
      clearInterval(_wizPollInt); _wizPollInt = null;
      setShellVisibility(document.getElementById('wiz-mini-banner'), false);
      if (_wizMinimized) { _wizMinimized = false; setShellVisibility(document.getElementById('wizard'), true); }
      setTimeout(() => wizShowComplete(s), 1000);
    }
    } catch(e) { /* poll error — server may be busy */ }
  }, 2000);
}

function wizSkipToComplete() {
  if (_wizPollInt) { clearInterval(_wizPollInt); _wizPollInt = null; }
  fetch('/api/settings/wizard-complete', {method:'POST'});
  wizShowComplete({completed:[], errors:['Setup was skipped — you can install services and content manually from the Services and Library tabs.']});
}

async function wizShowComplete(state) {
  wizGoPage(5);
  // Show LAN URL
  try { const net = await (await fetch('/api/network')).json(); document.getElementById('wiz-lan-url').textContent = net.dashboard_url; } catch(e) {}
  const svcCount = state.completed.filter(c => ['ollama','kiwix','cyberchef','kolibri','qdrant','stirling'].includes(c)).length;
  const contentCount = state.completed.length - svcCount;
  document.getElementById('wiz-summary').innerHTML = `
    <div class="wizard-summary-card">
      <div class="wizard-summary-number wizard-summary-number-green">${svcCount}</div><div class="wizard-summary-label">Tools Installed</div>
    </div>
    <div class="wizard-summary-card">
      <div class="wizard-summary-number wizard-summary-number-accent">${contentCount}</div><div class="wizard-summary-label">Content Packs</div>
    </div>
    <div class="wizard-summary-card">
      <div class="wizard-summary-number ${state.errors.length === 0 ? 'wizard-summary-number-green' : 'wizard-summary-number-warning'}">${state.errors.length===0?'All Clear':state.errors.length+' Issues'}</div><div class="wizard-summary-label">Status</div>
    </div>`;
  if (state.errors.length) {
    document.getElementById('wiz-error-summary').style.display = 'block';
    document.getElementById('wiz-error-summary').innerHTML = `<div class="wizard-error-summary-card">`
      + state.errors.map(e => `<div class="wizard-error-row">&#10007; ${escapeHtml(e)}</div>`).join('') + `</div>`;
  } else {
    document.getElementById('wiz-error-summary').style.display = 'none';
    document.getElementById('wiz-error-summary').innerHTML = '';
  }
}

function skipWizard() {
  setShellVisibility(document.getElementById('wizard'), false);
  history.replaceState(null, '', '/');
  fetch('/api/settings/wizard-complete', {method:'POST'});
}

function closeTourWizard() {
  setShellVisibility(document.getElementById('wizard'), false);
  history.replaceState(null, '', '/');
  loadServices();
}

/* ─── Guided Tour ─── */
const TOUR_STEPS = [
  { tab: 'services', title: 'Your Command Center', text: 'This is your dashboard. Live widgets show inventory, power, weather, and alerts at a glance. Click any widget to drill into that section.', pos: 'center' },
  { tab: 'ai-chat', title: 'AI Chat', text: 'Chat with a private AI that runs entirely on your computer. It knows your inventory, contacts, and situation. No internet needed, no data leaves your machine.', pos: 'center' },
  { tab: 'kiwix-library', title: 'Offline Encyclopedia', text: 'Download Wikipedia, medical references, survival guides, and more. Choose Essential (~10 GB), Standard (~80 GB), or pick individual packs.', pos: 'center' },
  { tab: 'preparedness', title: 'Preparedness Tools', text: '25 tools organized into 5 categories: Supplies, People, Readiness, Knowledge, and Operations. Click a category at the top, then choose a specific tool.', pos: 'center' },
  { tab: 'maps', title: 'Offline Maps', text: 'Download maps for your area. Add waypoints, draw zones, measure distances, and plan routes — all without internet.', pos: 'center' },
  { tab: 'settings', title: 'Settings & System Health', text: 'Manage AI models, run system health checks, schedule recurring tasks, back up your data, and configure multi-node sync.', pos: 'center' },
];
let _tourStep = 0;

function startTour() {
  setShellVisibility(document.getElementById('wizard'), false);
  history.replaceState(null, '', '/');
  _tourStep = 0;
  setShellVisibility(document.getElementById('tour-overlay'), true);
  showTourStep();
  loadServices();
}

function showTourStep() {
  const step = TOUR_STEPS[_tourStep];
  if (!step) { tourSkip(); return; }
  // Switch to the tab
  const tabBtn = document.querySelector(`[data-tab="${step.tab}"]`);
  if (tabBtn) tabBtn.click();

  document.getElementById('tour-content').innerHTML = `<h3 class="tour-content-title">${step.title}</h3><p class="tour-content-copy">${step.text}</p>`;
  document.getElementById('tour-step-num').textContent = `${_tourStep+1} of ${TOUR_STEPS.length}`;
  document.getElementById('tour-next-btn').textContent = _tourStep === TOUR_STEPS.length - 1 ? 'Done' : 'Next';

  const card = document.getElementById('tour-card');
  card.style.top = '50%';
  card.style.left = '50%';
  card.style.transform = 'translate(-50%, -50%)';
}

function tourNext() {
  _tourStep++;
  if (_tourStep >= TOUR_STEPS.length) {
    tourSkip();
  } else {
    showTourStep();
  }
}

function tourSkip() {
  setShellVisibility(document.getElementById('tour-overlay'), false);
  document.querySelector('[data-tab="services"]').click();
  fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tour_complete:'1'})});
}

/* ─── Inline Model Picker ─── */
let _modelPickerVisible = false;
function toggleModelPicker() {
  _modelPickerVisible = !_modelPickerVisible;
  const panel = document.getElementById('model-picker-panel');
  panel.style.display = _modelPickerVisible ? 'block' : 'none';
  if (_modelPickerVisible) loadModelPickerList();
}

async function loadModelPickerList() {
  const rec = await (await fetch('/api/ai/recommended')).json();
  const models = await (await fetch('/api/ai/models')).json();
  const installed = new Set(models.map(m => m.name));
  document.getElementById('model-picker-list').innerHTML = rec.map((r, idx) => `
    <div class="model-picker-card">
      <div class="model-picker-main">
        <div class="model-picker-title">${r.name}</div>
        <div class="model-picker-copy">${r.desc} (${r.size})</div>
        <div id="model-info-${idx}" class="model-picker-meta"></div>
      </div>
      <div class="model-picker-actions">
        <button class="btn btn-sm btn-ghost model-picker-info-btn" type="button" data-shell-action="show-model-info" data-model-name="${escapeAttr(r.name)}" data-model-info-id="model-info-${idx}" title="Model details">Info</button>
        ${installed.has(r.name)
          ? '<span class="model-picker-status">Ready</span>'
          : `<button class="btn btn-sm btn-primary" type="button" data-shell-action="pull-model" data-model-name="${escapeAttr(r.name)}">Get</button>`}
      </div>
    </div>
  `).join('');
}

async function showModelInfo(modelName, infoEl) {
  if (!infoEl) return;
  infoEl.textContent = 'Loading…';
  const info = await safeFetch('/api/ai/model-info/' + encodeURIComponent(modelName), {}, null);
  if (info && !info.error) {
    infoEl.innerHTML = '<span class="model-picker-meta">' + escapeHtml(info.parameters || '?') + ' params &middot; ' + escapeHtml(info.quantization || '?') + ' &middot; ' + escapeHtml(info.ram_estimate || '?') + ' RAM</span>';
  } else {
    infoEl.textContent = '';
  }
}

async function ensureOllamaReady() {
  // Auto-install and auto-start Ollama if needed — returns true when ready
  try {
    const svcs = await (await fetch('/api/services')).json();
    const svc = svcs.find(s => s.id === 'ollama');
    // Already running? Great, we're done
    if (svc?.installed && svc?.running) return true;
    // Not installed? Auto-install
    if (!svc?.installed) {
      toast('Installing AI Chat service...', 'info');
      await installService('ollama');
      // Wait for install (poll up to 3 min)
      for (let i = 0; i < 90; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const fresh = await (await fetch('/api/services')).json();
        if (fresh.find(s => s.id === 'ollama')?.installed) break;
      }
      const check = await (await fetch('/api/services')).json();
      if (!check.find(s => s.id === 'ollama')?.installed) {
        toast('AI Chat is still installing. Please wait and try again.', 'warning');
        return false;
      }
    }
    // Installed but not running? Auto-start
    toast('Starting AI Chat service...', 'info');
    await startService('ollama');
    // Wait for ready (up to 20 seconds)
    for (let i = 0; i < 10; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const fresh = await (await fetch('/api/services')).json();
      if (fresh.find(s => s.id === 'ollama')?.running) return true;
    }
    toast('AI Chat is starting up. Try again in a moment.', 'warning');
    return false;
  } catch(e) {
    toast('Could not check AI Chat status', 'error');
    return false;
  }
}

async function pullModel(name) {
  if (!await ensureOllamaReady()) return;
  try {
    const r = await fetch('/api/ai/pull', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({model:name})});
    if (!r.ok) { const d = await r.json().catch(()=>({})); toast(d.error || 'Failed to start download', 'error'); return; }
    toast(`Downloading ${name}...`, 'info');
    toggleModelPicker();
    pollPullProgress();
  } catch(e) { toast('Failed to connect to AI service', 'error'); }
}

function pullCustomModel() {
  const name = document.getElementById('custom-model-input').value.trim();
  if (!name) return;
  document.getElementById('custom-model-input').value = '';
  pullModel(name);
}

async function pullAllModels() {
  if (!await ensureOllamaReady()) return;
  // Get all recommended model names
  try {
    const rec = await (await fetch('/api/ai/recommended')).json();
    const models = rec.map(r => r.name);
    const totalSize = rec.reduce((s, r) => s + parseFloat(r.size), 0).toFixed(1);
    const r = await fetch('/api/ai/pull-queue', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({models})});
    const d = await r.json();
    if (d.error) { toast(d.error, 'warning'); return; }
    if (d.status === 'all_installed') { toast('All recommended models are already downloaded!', 'success'); return; }
    toast(`Queued ${d.count} models for download. They will download one at a time.`, 'info');
    toggleModelPicker();
    pollPullProgress();
  } catch(e) { toast('Failed to start model queue', 'error'); }
}

/* ─── Knowledge Base ─── */
let kbEnabled = false;

function toggleKB() {
  kbEnabled = document.getElementById('kb-toggle').checked;
  const docsEl = document.getElementById('kb-docs-list');
  docsEl.style.display = kbEnabled ? 'block' : 'none';
  if (kbEnabled) loadKBDocs();
}

async function loadKBDocs() {
  const el = document.getElementById('kb-docs-list');
  let docs;
  try {
    docs = await (await fetch('/api/kb/documents')).json();
  } catch(e) {
    el.innerHTML = '<span class="kb-doc-empty">Could not load documents. Document search may not be running.</span>';
    return;
  }
  if (!docs.length) { el.innerHTML = '<span class="kb-doc-empty">No documents uploaded yet.</span>'; return; }
  const catColors = {medical:'#e91e63',property:'#4caf50',vehicle:'#2196f3',financial:'#ff9800',legal:'#9c27b0',reference:'#00bcd4',personal:'#795548',other:'var(--text-muted)'};
  el.innerHTML = docs.map(d => {
    const statusClass = d.status === 'ready' ? 'kb-doc-status-success' : d.status === 'error' ? 'kb-doc-status-danger' : 'kb-doc-status-warning';
    const cat = d.doc_category || '';
    const catBadge = cat ? `<span class="kb-doc-category" style="--kb-doc-category-tone:${catColors[cat]||'var(--surface3)'};">${cat}</span>` : '';
    const summary = d.summary ? `<div class="kb-doc-summary" title="${escapeAttr(d.summary)}">${escapeHtml(d.summary.slice(0,100))}</div>` : '';
    const analyzeBtn = d.status === 'ready' && !d.doc_category ? `<button type="button" class="kb-doc-action" data-chat-action="analyze-kb-doc" data-doc-id="${d.id}" title="AI: classify, summarize, extract entities">Analyze</button>` : '';
    const detailBtn = d.doc_category ? `<button type="button" class="kb-doc-action" data-chat-action="show-doc-details" data-doc-id="${d.id}" title="View analysis details">Details</button>` : '';
    return `<div class="kb-doc-item kb-doc-item-stack">
      <div class="kb-doc-head">
        <span class="kb-doc-main">${escapeHtml(d.filename)} ${catBadge} <span class="kb-doc-status ${statusClass}">${d.status}${d.chunks_count ? ' ('+d.chunks_count+' chunks)' : ''}</span></span>
        <span class="kb-doc-actions">${analyzeBtn}${detailBtn}<button type="button" class="convo-action-btn convo-del" data-chat-action="delete-kb-doc" data-doc-id="${d.id}" title="Delete document" aria-label="Delete document">x</button></span>
      </div>
      ${summary}
    </div>`;
  }).join('');

  // Update badge
  const badge = document.getElementById('kb-status-badge');
  try {
    const status = await (await fetch('/api/kb/status')).json();
    if (status.qdrant_running) {
      const ct = status.collection?.points_count || 0;
      badge.textContent = ct > 0 ? `${ct} searchable passages` : 'Ready for documents';
      badge.style.color = 'var(--green)';
    } else {
      badge.textContent = 'Document search not running';
      badge.style.color = 'var(--red)';
    }
  } catch(e) {
    badge.textContent = 'Document search unavailable';
    badge.style.color = 'var(--text-muted)';
  }
}

async function uploadKBFile() {
  const input = document.getElementById('kb-file-input');
  if (!input.files.length) return;
  const file = input.files[0];
  const formData = new FormData();
  formData.append('file', file);
  toast(`Uploading ${file.name}...`);
  await fetch('/api/kb/upload', {method: 'POST', body: formData});
  input.value = '';
  toast('Processing document...');
  pollKBEmbed();
}

let _kbPoll = null;
function pollKBEmbed() {
  if (_kbPoll) return;
  _kbPoll = setInterval(async () => {
    const s = await (await fetch('/api/kb/status')).json();
    if (s.status === 'complete' || s.status === 'error' || s.status === 'idle') {
      clearInterval(_kbPoll); _kbPoll = null;
      if (s.status === 'complete') toast('Document embedded!', 'success');
      if (s.status === 'error') toast('Embedding failed: ' + s.detail, 'error');
      loadKBDocs();
    }
  }, 2000);
}

async function deleteKBDoc(id) {
  try {
    const r = await fetch(`/api/kb/documents/${id}`, {method:'DELETE'});
    if (!r.ok) throw new Error('Delete failed');
    toast('Document deleted', 'warning');
    loadKBDocs();
  } catch(e) { toast('Failed to delete document', 'error'); }
}

async function analyzeDoc(id) {
  toast('Analyzing document with AI...', 'info');
  await fetch(`/api/kb/documents/${id}/analyze`, {method:'POST'});
  // Poll for completion
  let polls = 0;
  const poll = setInterval(async () => {
    polls++;
    const d = await (await fetch(`/api/kb/documents/${id}/details`)).json();
    if (d.doc_category || polls > 30) {
      clearInterval(poll);
      toast(`Document analyzed: ${d.doc_category || 'complete'}`, 'success');
      loadKBDocs();
    }
  }, 2000);
}

async function showDocDetails(id) {
  try {
    const d = await (await fetch(`/api/kb/documents/${id}/details`)).json();
    const catColors = {medical:'#e91e63',property:'#4caf50',vehicle:'#2196f3',financial:'#ff9800',legal:'#9c27b0',reference:'#00bcd4',personal:'#795548',other:'var(--text-muted)'};
    const entities = d.entities || [];
    const linked = d.linked_records || [];
    let html = `<h3 class="kb-detail-title">${escapeHtml(d.filename)}</h3>`;
    html += `<div class="kb-detail-category-row"><span class="kb-doc-category kb-doc-category-strong" style="--kb-doc-category-tone:${catColors[d.doc_category]||'#666'};">${d.doc_category||'unclassified'}</span></div>`;
    if (d.summary) html += `<div class="kb-detail-summary"><strong>Summary:</strong> ${escapeHtml(d.summary)}</div>`;
    if (entities.length) {
      html += `<div class="kb-detail-section"><strong class="kb-detail-label">Extracted Entities (${entities.length}):</strong><div class="kb-detail-entity-list">`;
      entities.forEach(e => {
        const typeColors = {person:'#e91e63',date:'#ff9800',medication:'#4caf50',address:'#2196f3',phone:'#9c27b0',vehicle:'#00bcd4',amount:'#ff5722',coordinate:'#795548'};
        const tone = typeColors[e.type] || '#8a7f73';
        html += `<span class="kb-detail-entity-chip" style="--kb-entity-tone:${tone};--kb-entity-tone-soft:${tone}22;">${escapeHtml(e.type)}: ${escapeHtml(e.value)}</span>`;
      });
      html += `</div>`;
      const importableTypes = ['person','medication','coordinates','phone'];
      const hasImportable = entities.some(e => importableTypes.includes(e.type));
      if (hasImportable) {
        html += `<button class="btn btn-sm kb-detail-import-btn" type="button" data-chat-action="import-doc-entities" data-doc-id="${id}"><i class="bi bi-database-add"></i> Import Entities to Database</button>`;
      }
      html += `</div>`;
    }
    if (linked.length) {
      html += `<div class="kb-detail-section"><strong class="kb-detail-label">Cross-References:</strong><div class="kb-detail-linked-list">`;
      linked.forEach(l => {
        html += `<div class="kb-detail-linked-item">Linked to ${l.type}: <strong>${escapeHtml(l.name)}</strong></div>`;
      });
      html += `</div></div>`;
    }
    html += `<div class="kb-detail-meta">File size: ${d.file_size ? Math.round(d.file_size/1024) + ' KB' : '?'} | Chunks: ${d.chunks_count || 0} | Status: ${d.status}</div>`;
    html += `<div class="modal-footer"><button class="btn btn-sm" type="button" data-shell-action="close-modal-overlay">Close</button></div>`;
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
    const card = document.createElement('div');
    card.className = 'modal-card';
    card.innerHTML = html;
    overlay.appendChild(card);
    document.body.appendChild(overlay);
  } catch(e) { toast('Failed to load details', 'error'); }
}

async function importDocEntities(docId) {
  try {
    const r = await fetch(`/api/kb/documents/${docId}/import-entities`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})});
    const d = await r.json();
    if (r.ok) {
      const parts = [];
      if (d.results.contacts > 0) parts.push(`${d.results.contacts} contact(s)`);
      if (d.results.inventory > 0) parts.push(`${d.results.inventory} inventory item(s)`);
      if (d.results.waypoints > 0) parts.push(`${d.results.waypoints} waypoint(s)`);
      if (d.results.skipped > 0) parts.push(`${d.results.skipped} skipped`);
      toast(`Imported ${d.total_imported} entities: ${parts.join(', ') || 'none'}`, d.total_imported > 0 ? 'success' : 'info');
    } else {
      toast(d.error || 'Import failed', 'error');
    }
  } catch(e) { toast('Failed to import entities', 'error'); }
}

async function analyzeAllDocs() {
  const r = await fetch('/api/kb/analyze-all', {method:'POST'});
  const d = await r.json();
  toast(`Analyzing ${d.count} document(s)...`, 'info');
  // Refresh list after a delay
  setTimeout(loadKBDocs, 10000);
}

/* ─── Map Tile Themes ─── */
const MAP_TILE_THEMES = {
  dark: {
    url: 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
    name: 'Dark (CartoDB)'
  },
  light: {
    url: 'https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
    name: 'Light (CartoDB)'
  },
  tactical: {
    url: 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
    name: 'Dark Tactical'
  },
  eink: {
    url: 'https://stamen-tiles.a.ssl.fastly.net/toner/{z}/{x}/{y}.png',
    name: 'High Contrast B&W (Stamen Toner)'
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    name: 'Satellite (ESRI)'
  },
  terrain: {
    url: 'https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.png',
    name: 'Terrain (Stamen)'
  }
};

const THEME_TO_TILE = {
  nomad: 'light',
  nightops: 'dark',
  cyber: 'dark',
  redlight: 'dark',
  eink: 'eink'
};

const _offlineMapStyle = {
  version: 8,
  name: 'NOMAD Dark',
  sources: {},
  layers: [{id:'background', type:'background', paint:{'background-color':'#1a1a2e'}}],
  glyphs: 'https://fonts.openmaptiles.org/{fontstack}/{range}.pbf',
};

function applyRasterTileStyle(tileUrl, name) {
  if (!_map) return;
  const style = {
    version: 8,
    name: name,
    sources: {
      'raster-tiles': {
        type: 'raster',
        tiles: [tileUrl],
        tileSize: 256,
        attribution: ''
      }
    },
    layers: [{
      id: 'raster-layer',
      type: 'raster',
      source: 'raster-tiles',
      minzoom: 0,
      maxzoom: 19
    }],
    glyphs: 'https://fonts.openmaptiles.org/{fontstack}/{range}.pbf',
  };
  _map.setStyle(style);
}

function applyMapThemeTiles(themeName) {
  if (!_map) return;
  const tileKey = THEME_TO_TILE[themeName] || 'dark';
  const tileDef = MAP_TILE_THEMES[tileKey];
  if (tileDef) {
    applyRasterTileStyle(tileDef.url, tileDef.name);
  }
}

function setMapTileSource(value) {
  localStorage.setItem('nomad-map-tiles', value);
  if (!_map) return;
  if (value === 'auto') {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'nomad';
    applyMapThemeTiles(currentTheme);
    toast('Map tiles: Auto (matching app theme)', 'info');
  } else if (value === 'offline') {
    _map.setStyle(_offlineMapStyle);
    toast('Map tiles: Local / Offline', 'info');
  } else {
    const tileDef = MAP_TILE_THEMES[value];
    if (tileDef) {
      applyRasterTileStyle(tileDef.url, tileDef.name);
      toast(`Map tiles: ${tileDef.name}`, 'info');
    }
  }
}

/* ─── Map Viewer ─── */
let _map = null;
let _mapVisible = false;

function toggleMapView() {
  _mapVisible = !_mapVisible;
  document.getElementById('map-viewer').style.display = _mapVisible ? 'block' : 'none';
  document.getElementById('map-management').style.display = _mapVisible ? 'none' : 'block';
  document.getElementById('map-toggle-btn').textContent = _mapVisible ? 'Manage Maps' : 'Show Map';
  ['pin-btn','measure-btn','clear-pins-btn','save-wp-btn','draw-zone-btn','gpx-btn','property-btn','print-map-btn','bookmark-btn','bearing-btn','style-btn'].forEach(id => document.getElementById(id).style.display = _mapVisible ? '' : 'none');
  if (_mapVisible && !_map) initMap();
  if (_mapVisible && _map) loadWaypoints();
}

let _mapMarkers = [];
let _measurePoints = [];
let _measureMode = false;
let _measureActive = false;
let _measureMarkers = [];
let _measureLine = null;

let _mapStyleIdx = 0;
const MAP_STYLES = [
  {name: 'Default', filter: null},
  {name: 'Dark', filter: 'invert(1) hue-rotate(180deg)'},
  {name: 'Satellite', filter: 'saturate(1.3) contrast(1.1)'},
];

function cycleMapStyle() {
  _mapStyleIdx = (_mapStyleIdx + 1) % MAP_STYLES.length;
  const canvas = document.querySelector('#map-container canvas');
  if (canvas) {
    canvas.style.filter = MAP_STYLES[_mapStyleIdx].filter || 'none';
  }
  toast(`Map style: ${MAP_STYLES[_mapStyleIdx].name}`, 'info');
}

function toggleMapMeasure() {
  _measureActive = !_measureActive;
  const btn = document.getElementById('map-measure-btn');
  if (btn) btn.className = _measureActive ? 'btn btn-sm btn-primary' : 'btn btn-sm';
  if (!_measureActive) clearMeasure();
  if (typeof _map !== 'undefined' && _map) {
    _map.getCanvas().style.cursor = _measureActive ? 'crosshair' : '';
  }
}

function clearMeasure() {
  _measurePoints = [];
  _measureMarkers.forEach(m => m.remove());
  _measureMarkers = [];
  if (_measureLine && typeof _map !== 'undefined' && _map.getSource('measure-line')) {
    _map.getSource('measure-line').setData({type:'FeatureCollection',features:[]});
  }
  const el = document.getElementById('measure-result');
  if (el) el.style.display = 'none';
}

function calcMeasureDistance() {
  if (_measurePoints.length < 2) return 0;
  let total = 0;
  for (let i = 1; i < _measurePoints.length; i++) {
    const [lon1, lat1] = _measurePoints[i-1];
    const [lon2, lat2] = _measurePoints[i];
    const R = 6371;
    const dLat = (lat2-lat1)*Math.PI/180;
    const dLon = (lon2-lon1)*Math.PI/180;
    const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
    total += R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  }
  return total;
}

function printMap() {
  const mapEl = document.querySelector('.map-wrap');
  if (!mapEl) return;
  const canvas = mapEl.querySelector('canvas');
  if (!canvas) { toast('Map not loaded', 'warning'); return; }
  const win = window.open('', '_blank');
  win.document.write('<html><head><title>NOMAD Map Print</title><style>body{margin:0;text-align:center;}img{max-width:100%;height:auto;}h3{font-family:system-ui;margin:8px;}.print-meta{font-size:11px;color:#666;}</style></head><body>');
        win.document.write('<h3>NOMAD Field Desk — Map Export</h3>');
  win.document.write('<img src="' + canvas.toDataURL('image/png') + '">');
  win.document.write('<p class="print-meta">Printed ' + new Date().toLocaleString() + '</p>');
  win.document.write('</body></html>');
  win.document.close();
  setTimeout(() => win.print(), 500);
}

async function importGpxFile(input) {
  const file = input.files?.[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const r = await fetch('/api/waypoints/import-gpx', {method:'POST', body: formData});
    const d = await r.json();
    toast(`Imported ${d.count || 0} waypoints from GPX`, 'success');
    loadWPDistances();
  } catch(e) { toast('GPX import failed', 'error'); }
  input.value = '';
}

function initMap() {
  if (typeof maplibregl === 'undefined') {
    toast('MapLibre GL JS not loaded (requires internet on first use)');
    return;
  }

  if (typeof pmtiles !== 'undefined') {
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol('pmtiles', protocol.tile);
  }

  // Offline-first dark basemap — no CDN dependency
  const offlineStyle = {
    version: 8,
    name: 'NOMAD Dark',
    sources: {},
    layers: [{id:'background', type:'background', paint:{'background-color':'#1a1a2e'}}],
    glyphs: 'https://fonts.openmaptiles.org/{fontstack}/{range}.pbf',
  };

  _map = new maplibregl.Map({
    container: 'map-container',
    style: offlineStyle,
    center: [-98.5, 39.8],
    zoom: 4,
    attributionControl: true,
  });

  // Restore saved tile preference or auto-match app theme
  const savedTiles = localStorage.getItem('nomad-map-tiles') || 'auto';
  const tileSelector = document.getElementById('map-tile-selector');
  if (tileSelector) tileSelector.value = savedTiles;
  if (savedTiles === 'offline') {
    // Keep the offline basemap style as-is
  } else {
    const tileKey = (savedTiles === 'auto')
      ? (THEME_TO_TILE[document.documentElement.getAttribute('data-theme') || 'nomad'] || 'dark')
      : savedTiles;
    const tileDef = MAP_TILE_THEMES[tileKey];
    if (tileDef) {
      // Connectivity check: probe tile z/0/0, then apply raster tiles or stay offline
      fetch(tileDef.url.replace('{z}','0').replace('{x}','0').replace('{y}','0'), {signal: AbortSignal.timeout(3000)})
        .then(() => { if (_map) applyRasterTileStyle(tileDef.url, tileDef.name); })
        .catch(() => {}); // offline — keep the dark background
    }
  }

  _map.addControl(new maplibregl.NavigationControl(), 'top-right');
  _map.addControl(new maplibregl.FullscreenControl(), 'top-right');
  _map.addControl(new maplibregl.ScaleControl({maxWidth: 200}), 'bottom-left');
  _map.addControl(new maplibregl.GeolocateControl({
    positionOptions: {enableHighAccuracy: true},
    trackUserLocation: true,
  }));

  // Coordinate display on mouse move
  const coordEl = document.getElementById('map-coords');
  _map.on('mousemove', (e) => {
    if (coordEl) coordEl.textContent = `${e.lngLat.lat.toFixed(5)}, ${e.lngLat.lng.toFixed(5)}`;
  });

  // Load saved waypoints and zones after map loads
  _map.on('load', () => { loadWaypoints(); renderMapZones(); loadMeshMapOverlay(); loadGardenOverlay(); loadSupplyChainOverlay(); });

  // Click to drop pin, draw zone, property boundary, or bearing
  _map.on('click', (e) => {
    if (_measureMode) { addMeasurePoint(e.lngLat); return; }
    if (_drawingGarden) { _gardenPoints.push([e.lngLat.lng, e.lngLat.lat]); new maplibregl.Marker({color:'#4caf50',scale:0.4}).setLngLat(e.lngLat).addTo(_map); return; }
    if (_drawingZone) { _zonePoints.push([e.lngLat.lng, e.lngLat.lat]); new maplibregl.Marker({color:'#ff9800',scale:0.4}).setLngLat(e.lngLat).addTo(_map); return; }
    if (_drawingProperty) { _propertyPoints.push([e.lngLat.lng, e.lngLat.lat]); new maplibregl.Marker({color:'#5b9fff',scale:0.4}).setLngLat(e.lngLat).addTo(_map); return; }
    if (handleBearingClick(e.lngLat)) return;
  });

  _map.on('dblclick', (e) => {
    if (_drawingGarden && _gardenPoints.length >= 3) { e.preventDefault(); finishGardenDraw(); }
  });
}

function dropPin() {
  if (!_map) return;
  const center = _map.getCenter();
  const note = '';
  const marker = new maplibregl.Marker({color: '#5b9fff'})
    .setLngLat(center)
    .setPopup(new maplibregl.Popup().setHTML(
      renderMapPopupShell({
        title: note ? escapeHtml(note) : 'Dropped pin',
        meta: 'Manual marker',
        coords: `${center.lat.toFixed(4)}, ${center.lng.toFixed(4)}`
      })
    ))
    .addTo(_map);
  marker.togglePopup();
  _mapMarkers.push(marker);
  toast('Pin dropped');
}

function clearPins() {
  _mapMarkers.forEach(m => m.remove());
  _mapMarkers = [];
  toast('Pins cleared');
}

function toggleMeasure() {
  _measureMode = !_measureMode;
  document.getElementById('measure-btn').textContent = _measureMode ? 'Stop Measuring' : 'Measure';
  if (!_measureMode) {
    _measurePoints = [];
    if (_map.getSource('measure-line')) { _map.removeLayer('measure-line'); _map.removeSource('measure-line'); }
  }
  toast(_measureMode ? 'Click points on map to measure distance' : 'Measurement mode off');
}

function addMeasurePoint(lngLat) {
  _measurePoints.push([lngLat.lng, lngLat.lat]);
  new maplibregl.Marker({color: '#ff9800', scale: 0.5}).setLngLat(lngLat).addTo(_map);

  if (_measurePoints.length >= 2) {
    // Calculate total distance
    let totalKm = 0;
    for (let i = 1; i < _measurePoints.length; i++) {
      totalKm += haversineKm(_measurePoints[i-1], _measurePoints[i]);
    }
    const miles = totalKm * 0.621371;
    toast(`Distance: ${totalKm.toFixed(2)} km (${miles.toFixed(2)} mi)`);

    // Draw line
    const geojson = {type:'Feature', geometry:{type:'LineString', coordinates: _measurePoints}};
    if (_map.getSource('measure-line')) {
      _map.getSource('measure-line').setData(geojson);
    } else {
      _map.addSource('measure-line', {type:'geojson', data: geojson});
      _map.addLayer({id:'measure-line', type:'line', source:'measure-line', paint:{'line-color':'#ff9800','line-width':2,'line-dasharray':[2,2]}});
    }
  }
}

function haversineKm(a, b) {
  const R = 6371;
  const dLat = (b[1]-a[1])*Math.PI/180;
  const dLon = (b[0]-a[0])*Math.PI/180;
  const lat1 = a[1]*Math.PI/180, lat2 = b[1]*Math.PI/180;
  const x = Math.sin(dLat/2)**2 + Math.cos(lat1)*Math.cos(lat2)*Math.sin(dLon/2)**2;
  return R*2*Math.atan2(Math.sqrt(x), Math.sqrt(1-x));
}

async function searchMap() {
  const q = document.getElementById('map-search-input').value.trim();
  if (!q || !_map) return;
  // Check if input is coordinates (lat,lng or lat lng)
  const coordMatch = q.match(/^(-?\d+\.?\d*)[,\s]+(-?\d+\.?\d*)$/);
  if (coordMatch) {
    const lat = parseFloat(coordMatch[1]);
    const lng = parseFloat(coordMatch[2]);
    if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
      _map.flyTo({center: [lng, lat], zoom: 14});
      new maplibregl.Marker({color: 'var(--accent)'}).setLngLat([lng, lat])
        .setPopup(new maplibregl.Popup().setHTML(
          renderMapPopupShell({
            title: 'Coordinate jump',
            meta: 'Offline navigation',
            coords: `${lat.toFixed(5)}, ${lng.toFixed(5)}`
          })
        ))
        .addTo(_map).togglePopup();
      toast(`Navigated to ${lat.toFixed(5)}, ${lng.toFixed(5)}`, 'success');
      return;
    }
  }
  // Online geocoding search
  try {
    const r = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(q)}&limit=1`);
    const results = await r.json();
    if (results.length) {
      const {lat, lon, display_name} = results[0];
      _map.flyTo({center: [parseFloat(lon), parseFloat(lat)], zoom: 12});
      new maplibregl.Marker().setLngLat([parseFloat(lon), parseFloat(lat)])
        .setPopup(new maplibregl.Popup().setHTML(
          renderMapPopupShell({
            title: escapeHtml(display_name),
            meta: 'Search result',
            coords: `${parseFloat(lat).toFixed(5)}, ${parseFloat(lon).toFixed(5)}`
          })
        ))
        .addTo(_map).togglePopup();
    } else { toast('Location not found', 'warning'); }
  } catch(e) { toast('Location search requires internet. Enter coordinates (lat,lng) for offline navigation.', 'warning'); }
}

/* ─── Notes Preview ─── */
let _notePreviewVisible = false;

function toggleNotePreview() {
  _notePreviewVisible = !_notePreviewVisible;
  document.getElementById('note-preview').style.display = _notePreviewVisible ? 'block' : 'none';
  document.getElementById('note-preview-btn').textContent = _notePreviewVisible ? 'Editor' : 'Preview';
  if (_notePreviewVisible) updateNotePreview();
}

function updateNotePreview() {
  if (!_notePreviewVisible) return;
  const content = document.getElementById('note-content').value;
  document.getElementById('note-preview').innerHTML = renderMarkdown(content);
}

/* ─── Builder Tag ─── */
let _builderTagTimer;
function saveBuilderTag() {
  clearTimeout(_builderTagTimer);
  _builderTagTimer = setTimeout(async () => {
    const tag = document.getElementById('builder-tag').value;
    await fetch('/api/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({builder_tag: tag})});
  }, 500);
}

async function loadBuilderTag() {
  try {
    const s = await (await fetch('/api/settings')).json();
    if (s.builder_tag) document.getElementById('builder-tag').value = s.builder_tag;
  } catch(e) {}
}

/* ─── System Prompt Presets ─── */
const PRESETS = {
  assistant: 'You are a helpful, knowledgeable assistant. Be concise and accurate.',
  medical: 'You are a medical information advisor. Provide evidence-based health information. Always recommend consulting a healthcare professional for medical decisions. Reference medical terminology accurately.',
  coding: 'You are an expert software engineer. Write clean, efficient code. Explain your reasoning. Suggest best practices and potential pitfalls. Support multiple programming languages.',
  survival: 'You are a survival and preparedness expert. Provide practical, actionable advice for emergency situations, outdoor survival, first aid, and disaster preparedness. Cover shelter, water, fire, food, navigation, and signaling.',
  teacher: 'You are a patient, encouraging teacher. Explain concepts clearly with examples. Break complex topics into digestible parts. Ask follow-up questions to check understanding. Adapt your teaching style to the student.',
  analyst: 'You are a data analyst. Help interpret data, create queries, explain statistical concepts, and provide analytical frameworks. Be precise with numbers.',
  field_medic: 'You are a field medic / tactical medicine advisor. Provide step-by-step trauma care guidance: tourniquet application, wound packing, chest seals, airway management, shock treatment, triage. Reference TCCC (Tactical Combat Casualty Care) and TECC protocols. Include drug dosages when relevant. Always emphasize scene safety and personal protective equipment.',
  ham_radio: 'You are an amateur radio (HAM) expert. Help with radio operations, antenna design, propagation, frequency planning, emergency communications (ARES/RACES), radio programming, Winlink, digital modes (FT8, JS8Call, APRS). Explain band plans, license requirements, and equipment selection. Cover both VHF/UHF and HF operations.',
  homesteader: 'You are a homesteading and self-sufficiency expert. Advise on gardening (seasonal planting, soil prep, seed saving), animal husbandry (chickens, goats, rabbits), food preservation (canning, dehydrating, smoking, fermenting, root cellaring), off-grid living, rainwater harvesting, composting, and traditional crafts. Be practical and regionally adaptable.',
  water_specialist: 'You are a water treatment and sanitation expert. Advise on water purification methods (boiling, chemical, filtration, UV, distillation), water source assessment, well drilling and maintenance, rainwater collection systems, greywater recycling, emergency sanitation (latrines, waste disposal), and waterborne illness prevention. Include specific measurements, ratios, and procedures.',
  tactical: 'You are a security and operational security (OPSEC) advisor for preparedness. Cover home security hardening, perimeter defense, situational awareness, threat assessment, communications security, travel security, gray man concepts, community defense organization, and neighborhood watch coordination. Focus on legal, defensive, and preventive measures.',
  forager: 'You are a wild food and foraging expert. Help identify edible plants, mushrooms, insects, and wild game. Cover safe foraging practices, poisonous look-alikes, seasonal availability, preparation methods, and nutritional value. Include preservation techniques for wild-harvested food. Always emphasize positive identification and the rule: when in doubt, do NOT eat it.',
  scenario_grid: 'You are an emergency planning advisor. The power grid has been down for 3 days with no estimated restoration. Help me prioritize: water procurement and purification, food preservation from thawing freezers, alternative heating/cooling, communication with family and neighbors, security considerations, medical needs, fuel conservation. Ask about my specific situation (how many people, location, supplies on hand, season/weather) and provide a detailed hour-by-hour and day-by-day action plan.',
  scenario_medical: 'You are a remote/austere medicine advisor. There is a medical emergency and professional medical help is not available. Help me assess and treat the situation using available supplies. Ask about: the patient (age, weight, conditions, medications), the injury/illness symptoms, what medical supplies are available, distance to nearest medical facility. Provide step-by-step treatment, monitoring instructions, warning signs to watch for, and when to escalate. Reference TCCC and wilderness medicine protocols.',
  nuclear: 'You are a nuclear preparedness and civil defense expert. Advise on: blast radius effects by yield (thermal, overpressure, radiation), optimal shelter locations (PF ratings, basement vs above-ground), fallout protection (shelter-in-place timing, 7-10 rule of decay), decontamination procedures, potassium iodide dosing, EMP effects on electronics (Faraday protection), evacuation vs shelter-in-place decision criteria based on distance from ground zero, long-term fallout zone mapping, food/water contamination assessment. Reference Glasstone & Dolan nuclear effects data. Be specific about distances, timeframes, and protection factors.',
  scenario_evacuation: 'You are an evacuation planning expert. Help me plan an emergency evacuation. Ask about: number of people (ages, mobility), vehicles available, fuel levels, distance to destinations, current threats (fire, flood, civil unrest, chemical), time available, supplies already packed. Provide: route planning (primary + 2 alternates), vehicle loading priority, communication plan, rally points, go/no-go decision criteria, and what to grab in the last 5 minutes.',
  solar_expert: 'You are an off-grid solar power expert. Help design and troubleshoot solar systems: panel sizing, battery bank calculations (LiFePO4 vs lead-acid), charge controllers (MPPT vs PWM), inverter selection (pure vs modified sine), wiring (series vs parallel, wire gauge), mounting, tilt angles, and maintenance. Calculate loads, autonomy days, and system costs. Cover both portable (camping/bug-out) and permanent (homestead) installations. Include safety: grounding, overcurrent protection, disconnect switches.',
  land_nav: 'You are a land navigation instructor with military and wilderness experience. Teach map reading (topographic contour interpretation, UTM/MGRS grid coordinates, distance estimation), compass use (declination adjustment, triangulation, backstighting), celestial navigation (Polaris, sun methods, Southern Cross), natural navigation (vegetation, wind, animal behavior, terrain association), GPS alternatives, route planning, terrain association, pace counting, and dead reckoning. Provide practical exercises.',
  herbalist: 'You are a medicinal herbalist and ethnobotanist. Advise on growing, harvesting, preparing, and using medicinal plants for common ailments when modern medicine is unavailable. Cover: anti-inflammatory herbs (willow bark, turmeric), antimicrobial plants (garlic, oregano, goldenseal), wound care (yarrow, plantain, aloe), digestive remedies (ginger, peppermint, chamomile), pain relief (valerian, white willow), and immune support (elderberry, echinacea). Include preparation methods: tinctures, teas, poultices, salves, and proper dosing. Always note contraindications and when professional care is critical.',
  cbrn_specialist: 'You are a CBRN (Chemical, Biological, Radiological, Nuclear) defense specialist. Cover: nuclear blast effects by yield (fireball radius, overpressure zones, thermal radiation, initial nuclear radiation, fallout projection), fallout decay using the 7-10 Rule, shelter protection factors (below-grade concrete PF 100-1000, above-grade frame house PF 3-10), KI dosing by age (adult 130mg, teen 65mg, child 1-12yr 65mg, infant 16-32mg), self-decontamination (remove outer clothing removes 80% of contamination, shower with soap), chemical agent recognition (nerve/blister/choking/blood agents and their antidotes), biological threat indicators, hot zone / warm zone / cold zone protocols, improvised protective equipment, re-entry timing after fallout events. Reference Glasstone & Dolan Effects of Nuclear Weapons, FM 3-11 series, and FEMA 2022 Nuclear Detonation Planning Guide.',
  comms_planner: 'You are an emergency communications planner specializing in grid-down and austere communications. Cover the PACE model (Primary/Alternate/Contingency/Emergency): help users build layered communication plans. Advise on: local VHF/UHF simplex (146.520 national calling, 446.000 FM), GMRS/FRS for family comms, CB radio for vehicle travel corridors, HF for regional/national reach (40m daytime, 80m nighttime), JS8Call for store-and-forward HF messaging, Winlink P2P for email without internet, APRS for position tracking, Meshtastic LoRa for encrypted neighborhood mesh, signal mirrors and ground-to-air for aircraft, runner protocols for foot messenger plans. Include frequency planning, net check-in procedures, authentication codes, traffic handling, and how to integrate ICS/NIMS radio procedures into group operations.',
};
// Load saved custom prompt
(function() { const cp = localStorage.getItem('nomad-custom-prompt'); if (cp) PRESETS.custom = cp; })();
let activePreset = '';

function applyPreset() {
  activePreset = document.getElementById('system-preset').value;
  if (activePreset === 'custom') {
    toggleCustomPrompt(true);
  } else {
    toggleCustomPrompt(false);
  }
}

function toggleCustomPrompt(show) {
  const panel = document.getElementById('custom-prompt-panel');
  if (show === undefined) show = panel.style.display === 'none';
  panel.style.display = show ? 'block' : 'none';
  if (show) {
    // Load saved custom prompt
    const saved = localStorage.getItem('nomad-custom-prompt') || '';
    document.getElementById('custom-prompt-text').value = saved;
  }
}

function saveCustomPrompt() {
  const text = document.getElementById('custom-prompt-text').value.trim();
  localStorage.setItem('nomad-custom-prompt', text);
  PRESETS.custom = text;
  activePreset = 'custom';
  document.getElementById('system-preset').value = 'custom';
  toggleCustomPrompt(false);
  toast('Custom prompt saved', 'success');
}

function clearCustomPrompt() {
  document.getElementById('custom-prompt-text').value = '';
  localStorage.removeItem('nomad-custom-prompt');
  delete PRESETS.custom;
  activePreset = '';
  document.getElementById('system-preset').value = '';
  toggleCustomPrompt(false);
}

function exportConversation() {
  if (!currentConvoId) { toast('No conversation selected', 'warning'); return; }
  window.location=`/api/conversations/${currentConvoId}/export`;
}

/* ─── Conversation Search ─── */
function filterConvos() {
  const q = document.getElementById('convo-search').value.toLowerCase();
  if (!q) { renderConvoList(); return; }
  const filtered = allConvos.filter(c => c.title.toLowerCase().includes(q));
  const el = document.getElementById('convo-list');
  if (!filtered.length) { el.innerHTML = '<div class="sidebar-empty-state convo-search-empty">No matches</div>'; return; }
  el.innerHTML = filtered.map(c => {
    const branchBadge = (c.branch_count && c.branch_count > 0) ? `<span class="convo-branch-badge" title="${c.branch_count} branch${c.branch_count>1?'es':''}">${c.branch_count}</span>` : '';
    return `
    <div class="convo-item ${c.id===currentConvoId?'active':''}" data-convo-id="${c.id}" data-chat-action="select-conversation" data-chat-dblclick="rename-conversation" role="button" tabindex="0">
      <span class="convo-title">${escapeHtml(c.title)}${branchBadge}</span>
      <span class="convo-actions">
        <button type="button" class="convo-action-btn" data-chat-action="rename-conversation" data-convo-id="${c.id}" data-stop-propagation aria-label="Rename conversation" title="Rename">&#9998;</button>
        <button type="button" class="convo-action-btn convo-del" data-chat-action="delete-conversation" data-convo-id="${c.id}" data-stop-propagation aria-label="Delete conversation" title="Delete">x</button>
      </span>
    </div>`;
  }).join('');
}

/* ─── Unified Search ─── */
let _searchTimer;
function debounceSearch() {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(doUnifiedSearch, 300);
}

function highlightMatch(text, query) {
  if (!query) return escapeHtml(text);
  const escaped = escapeHtml(text);
  const re = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  return escaped.replace(re, '<mark class="search-highlight">$1</mark>');
}

async function doUnifiedSearch() {
  const q = document.getElementById('unified-search').value.trim();
  const el = document.getElementById('search-results');
  if (!q) { el.classList.remove('active'); return; }
  try {
    const resp = await fetch(`/api/search/all?q=${encodeURIComponent(q)}`);
    if (!resp.ok) { el.classList.remove('active'); return; }
    const r = await resp.json();
    const items = [
      ...r.conversations.map(c => ({...c, type: 'conversation'})),
      ...r.notes.map(n => ({...n, type: 'note'})),
      ...r.documents.map(d => ({...d, type: 'document'})),
      ...(r.inventory||[]).map(i => ({...i, type: 'inventory'})),
      ...(r.contacts||[]).map(c => ({...c, type: 'contact'})),
      ...(r.checklists||[]).map(c => ({...c, type: 'checklist'})),
      ...(r.skills||[]).map(s => ({...s, type: 'skill'})),
      ...(r.ammo||[]).map(a => ({...a, type: 'ammo'})),
      ...(r.equipment||[]).map(e => ({...e, type: 'equipment'})),
      ...(r.waypoints||[]).map(w => ({...w, type: 'waypoint'})),
      ...(r.frequencies||[]).map(f => ({...f, type: 'frequency'})),
      ...(r.patients||[]).map(p => ({...p, type: 'patient'})),
      ...(r.incidents||[]).map(i => ({...i, type: 'incident'})),
      ...(r.fuel||[]).map(f => ({...f, type: 'fuel'})),
    ];
    if (!items.length) {
      el.innerHTML = '<div class="search-result-empty">No results for "' + escapeHtml(q) + '" across ' + Object.keys(r).length + ' modules</div>';
    } else {
      const typeIcons = {inventory:'&#128230;',contact:'&#128100;',note:'&#128196;',conversation:'&#128172;',document:'&#128206;',checklist:'&#9745;',skill:'&#127919;',ammo:'&#128299;',equipment:'&#128295;',waypoint:'&#128205;',frequency:'&#128225;',patient:'&#9829;',incident:'&#9888;',fuel:'&#9981;'};
      const typeLabels = {inventory:'Supply',contact:'Contact',note:'Note',conversation:'Chat',document:'Document',checklist:'Checklist',skill:'Skill',ammo:'Ammo',equipment:'Equipment',waypoint:'Waypoint',frequency:'Frequency',patient:'Patient',incident:'Incident',fuel:'Fuel'};
      // Group by type
      const groups = {};
      items.forEach(i => { if (!groups[i.type]) groups[i.type] = []; groups[i.type].push(i); });
      let html = '';
      for (const [type, list] of Object.entries(groups)) {
        html += `<div class="search-result-group-head"><span>${typeIcons[type]||''} ${typeLabels[type]||type}</span><span class="search-result-count">${list.length}</span></div>`;
        html += list.map(i => `
          <div class="search-result-item" data-shell-action="open-search-result" data-result-type="${escapeAttr(i.type)}" data-result-id="${parseInt(i.id)||0}" data-prevent-mousedown role="button" tabindex="0">
            <span class="search-result-title">${highlightMatch(i.title, q)}</span>
          </div>
        `).join('');
      }
      el.innerHTML = html;
    }
    el.classList.add('active');
  } catch(e) { el.classList.remove('active'); }
}

function showSearchResults() {
  const q = document.getElementById('unified-search').value.trim();
  if (q) document.getElementById('search-results').classList.add('active');
}
function hideSearchResults() { document.getElementById('search-results').classList.remove('active'); }

function openSearchResult(type, id) {
  hideSearchResults();
  document.getElementById('unified-search').value = '';
  if (type === 'conversation') {
    document.querySelector('[data-tab="ai-chat"]').click();
    setTimeout(() => selectConvo(id), 200);
  } else if (type === 'note') {
    document.querySelector('[data-tab="notes"]').click();
    setTimeout(() => { loadNotes().then(() => selectNote(id)); }, 200);
  } else if (type === 'document') {
    document.querySelector('[data-tab="kiwix-library"]').click();
    setTimeout(() => { loadPDFList(); toast('Document found in library', 'info'); }, 200);
  } else if (type === 'inventory') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => switchPrepSub('inventory'), 200);
  } else if (type === 'contact') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => switchPrepSub('contacts'), 200);
  } else if (type === 'checklist') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => { switchPrepSub('checklists'); selectChecklist(id); }, 200);
  } else if (type === 'skill') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => switchPrepSub('skills'), 200);
  } else if (type === 'ammo') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => switchPrepSub('ammo'), 200);
  } else if (type === 'equipment') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => switchPrepSub('equipment'), 200);
  } else if (type === 'waypoint') {
    document.querySelector('[data-tab="maps"]').click();
    toast('Waypoint: navigate to it on the map', 'info');
  } else if (type === 'frequency') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => switchPrepSub('radio'), 200);
  } else if (type === 'patient') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => switchPrepSub('medical'), 200);
  } else if (type === 'incident') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => switchPrepSub('incidents'), 200);
  } else if (type === 'fuel') {
    document.querySelector('[data-tab="preparedness"]').click();
    setTimeout(() => switchPrepSub('fuel'), 200);
  }
}

/* ─── Content Summary ─── */
async function loadContentSummary() {
  try {
    const s = await (await fetch('/api/content-summary')).json();
    document.getElementById('content-summary').innerHTML = `
      <div>
        <div class="cs-total">${s.total_size}</div>
        <div class="cs-label">Offline Knowledge</div>
      </div>
      <div class="cs-stat"><div class="cs-val">${s.ai_models}</div><div class="cs-label">AI Models</div></div>
      <div class="cs-stat"><div class="cs-val">${s.zim_files}</div><div class="cs-label">Content Packs</div></div>
      <div class="cs-stat"><div class="cs-val">${s.documents}</div><div class="cs-label">Documents</div></div>
      <div class="cs-stat"><div class="cs-val">${s.conversations}</div><div class="cs-label">Conversations</div></div>
      <div class="cs-stat"><div class="cs-val">${s.notes}</div><div class="cs-label">Notes</div></div>
    `;
  } catch(e) {
    document.getElementById('content-summary').innerHTML = '<div class="cs-label content-summary-empty">Content summary unavailable</div>';
  }
}

/* ─── Log Viewer ─── */
async function loadLogViewer() {
  const level = document.getElementById('log-level-filter').value;
  try {
    const items = await (await fetch('/api/activity?limit=100')).json();
    const filtered = level ? items.filter(a => a.level === level) : items;
    const el = document.getElementById('log-viewer');
    if (!filtered.length) { el.innerHTML = '<span class="settings-empty-state log-viewer-empty">No log entries.</span>'; return; }
    el.innerHTML = filtered.map(a => {
      const t = new Date(a.created_at);
      const ts = t.toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'});
      const badge = a.level === 'error' ? 'ERR' : a.level === 'warning' ? 'WRN' : 'INF';
      const badgeClass = a.level === 'error' ? 'settings-log-badge-error' : a.level === 'warning' ? 'settings-log-badge-warning' : 'settings-log-badge-info';
      return `<div class="settings-log-row">
        <span class="settings-log-time">${ts}</span>
        <span class="settings-log-badge ${badgeClass}">${badge}</span>
        <span class="settings-log-service">${a.service||'-'}</span>
        <span>${escapeHtml(a.event.replace(/_/g,' '))}${a.detail ? ' — '+escapeHtml(a.detail) : ''}</span>
      </div>`;
    }).join('');
  } catch(e) {}
}

/* ─── Disk Monitor ─── */
async function loadDataSummary() {
  try {
    const d = await (await fetch('/api/data-summary')).json();
    const el = document.getElementById('data-summary');
    if (!d.tables.length) {
      el.innerHTML = '<div class="settings-empty-state">No data yet. Start adding inventory, contacts, and notes to see your data summary.</div>';
      return;
    }
    el.innerHTML = `
      <div class="settings-summary-total"><strong>${d.total_records.toLocaleString()}</strong> total records across ${d.tables.length} tables</div>
      <div class="utility-summary-result settings-summary-grid">
        ${d.tables.map(t => `<div class="prep-summary-card utility-summary-card">
          <div class="prep-summary-meta">${escapeHtml(t.label)}</div>
          <div class="prep-summary-value prep-summary-value-compact">${t.count.toLocaleString()}</div>
        </div>`).join('')}
      </div>`;
  } catch(e) {}
}

async function loadDiskMonitor() {
  try {
    const sys = await (await fetch('/api/system')).json();
    const summary = await (await fetch('/api/content-summary')).json();
    const el = document.getElementById('disk-monitor');

    // Calculate usage breakdown
    const totalBytes = summary.total_bytes || 0;
    const freeStr = sys.disk_free || 'Unknown';
    const totalStr = sys.disk_total || 'Unknown';

    let warn = '';
    const devices = sys.disk_devices || [];
    const criticalDisk = devices.find(d => d.percent > 90);
    if (criticalDisk) {
      warn = `<div class="prep-reference-callout prep-reference-callout-danger settings-summary-alert">
        Drive ${criticalDisk.mountpoint} is ${criticalDisk.percent}% full. Consider freeing space or moving data.
      </div>`;
    }

    el.innerHTML = `${warn}
      <div class="utility-summary-result settings-summary-grid">
        <div class="prep-summary-card utility-summary-card">
<div class="prep-summary-meta">NOMAD Data</div>
          <div class="prep-summary-value prep-summary-value-compact">${summary.total_size}</div>
        </div>
        <div class="prep-summary-card utility-summary-card">
          <div class="prep-summary-meta">ZIM Content</div>
          <div class="prep-summary-value prep-summary-value-compact">${summary.zim_size}</div>
        </div>
        <div class="prep-summary-card utility-summary-card">
          <div class="prep-summary-meta">Disk Free</div>
          <div class="prep-summary-value prep-summary-value-compact">${freeStr}</div>
        </div>
        <div class="prep-summary-card utility-summary-card">
          <div class="prep-summary-meta">Disk Total</div>
          <div class="prep-summary-value prep-summary-value-compact">${totalStr}</div>
        </div>
      </div>
      <div class="settings-summary-note">
        Tip: Large ZIM files (Wikipedia Full, Stack Overflow) can be deleted from the Library tab when not needed.
      </div>`;
  } catch(e) {}
}

/* ─── Mission Readiness ─── */
async function loadReadiness() {
  try {
    const services = await (await fetch('/api/services')).json();
    const caps = [
      {id:'ollama', label:'AI Chat', need:['ollama']},
      {id:'kiwix', label:'Library', need:['kiwix']},
      {id:'cyberchef', label:'Data Tools', need:['cyberchef']},
      {id:'kolibri', label:'Education', need:['kolibri']},
      {id:'qdrant', label:'Knowledge Base', need:['qdrant','ollama']},
      {id:'stirling', label:'PDF Tools', need:['stirling']},
    ];
    const svcMap = {};
    services.forEach(s => svcMap[s.id] = s);

    document.getElementById('readiness-bar').innerHTML = caps.map(c => {
      const allInstalled = c.need.every(n => svcMap[n]?.installed);
      const allRunning = c.need.every(n => svcMap[n]?.running);
      const cls = allRunning ? 'ready' : allInstalled ? 'partial' : 'offline';
      const label = allRunning ? 'Ready' : allInstalled ? 'Stopped' : 'Not Installed';
      return `<div class="readiness-pill ${cls}"><span class="rdot"></span>${c.label}: ${label}</div>`;
    }).join('');
  } catch(e) {
    document.getElementById('readiness-bar').innerHTML = '';
  }
}

/* ─── Activity Feed ─── */
async function loadActivity() {
  try {
    const filter = document.getElementById('activity-filter')?.value || '';
    const url = filter ? `/api/activity?limit=30&filter=${encodeURIComponent(filter)}` : '/api/activity?limit=30';
    const items = await (await fetch(url)).json();
    const el = document.getElementById('activity-feed');
    if (!items.length) { el.innerHTML = '<span class="text-muted">No activity yet.</span>'; return; }
    el.innerHTML = items.map(a => {
      const t = new Date(a.created_at);
      const time = t.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
      const date = t.toLocaleDateString([], {month:'short',day:'numeric'});
      const event = a.event.replace(/_/g, ' ');
      const eventToneClass = a.level === 'error' ? 'activity-event-error' : a.level === 'warning' ? 'activity-event-warning' : 'activity-event-info';
      return `<div class="activity-item">
        <span class="activity-time">${date} ${time}</span>
        <span class="activity-event ${eventToneClass}">${event}</span>
        ${a.service ? `<span class="activity-service-tag">${a.service}</span>` : ''}
        ${a.detail ? `<span class="activity-detail">${escapeHtml(a.detail)}</span>` : ''}
      </div>`;
    }).join('');
  } catch(e) {
    document.getElementById('activity-feed').innerHTML = '<span class="text-muted">Activity unavailable</span>';
  }
}

/* ─── Update Checker ─── */
async function checkForUpdate() {
  try {
    const u = await (await fetch('/api/update-check')).json();
    if (u.update_available) {
      const banner = document.getElementById('update-banner');
      banner.style.display = 'inline-flex';
      banner.textContent = `Update: v${u.latest}`;
      banner.href = u.download_url;
      // Show download button in Settings About section
      const dlBtn = document.getElementById('update-download-btn');
      if (dlBtn) { dlBtn.style.display = 'inline-flex'; }
      const statusEl = document.getElementById('update-status-text');
      if (statusEl) { statusEl.textContent = `v${u.latest} available`; statusEl.style.color = 'var(--green)'; }
    }
  } catch(e) {}
}

/* ─── Self-Update Download ─── */
async function downloadUpdate() {
  const btn = document.getElementById('update-download-btn');
  btn.disabled = true; btn.textContent = 'Downloading…';
  document.getElementById('update-progress-bar').style.display = 'block';
  await fetch('/api/update-download', {method:'POST'});
  pollUpdateProgress();
}

function pollUpdateProgress() {
  const poll = setInterval(async () => {
    try {
      const s = await (await fetch('/api/update-download/status')).json();
      document.getElementById('update-progress-pct').textContent = s.progress + '%';
      document.getElementById('update-progress-fill').style.width = s.progress + '%';
      document.getElementById('update-progress-label').textContent =
        s.status === 'checking' ? 'Checking for update…' :
        s.status === 'downloading' ? 'Downloading update…' : s.status;
      if (s.status === 'complete') {
        clearInterval(poll);
        document.getElementById('update-progress-bar').style.display = 'none';
        document.getElementById('update-complete-msg').style.display = 'block';
        document.getElementById('update-download-btn').style.display = 'none';
        toast('Update downloaded successfully', 'success');
      } else if (s.status === 'error') {
        clearInterval(poll);
        document.getElementById('update-progress-bar').style.display = 'none';
        document.getElementById('update-download-btn').disabled = false;
        document.getElementById('update-download-btn').textContent = 'Retry Download';
        toast('Update failed: ' + (s.error || 'Unknown error'), 'error');
      }
    } catch(e) { clearInterval(poll); }
  }, 1000);
}

async function openUpdateFolder() {
  await fetch('/api/update-download/open', {method:'POST'});
}

/* ─── Startup Toggle ─── */
async function loadStartupState() {
  try {
    const s = await (await fetch('/api/startup')).json();
    document.getElementById('startup-toggle').checked = s.enabled;
  } catch(e) {}
}

async function toggleStartup() {
  const enabled = document.getElementById('startup-toggle').checked;
  await fetch('/api/startup', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled})});
  toast(enabled ? 'Will start at login' : 'Removed from startup', enabled ? 'success' : 'info');
}

/* ─── Unified Download Queue ─── */
async function pollDownloadQueue() {
  try {
    const downloads = await (await fetch('/api/downloads/active')).json();
    const banner = document.getElementById('download-queue-banner');
    const itemsEl = document.getElementById('download-queue-items');
    if (!downloads.length) { banner.style.display = 'none'; return; }
    banner.style.display = 'block';
    itemsEl.innerHTML = downloads.map(d => {
      const icon = d.type === 'service' ? '&#9881;' : d.type === 'content' ? '&#128218;' : d.type === 'model' ? '&#129302;' : d.type === 'map' ? '&#127758;' : '&#128229;';
      return '<div class="download-banner-entry">' +
        '<span class="download-banner-icon">' + icon + '</span>' +
        '<div class="download-banner-body">' +
          '<div class="download-banner-head">' +
            '<span class="download-banner-label">' + escapeHtml(d.label) + '</span>' +
            '<span class="download-banner-meta">' + escapeHtml(String(d.percent || 0)) + '% ' + escapeHtml(d.speed || '') + '</span>' +
          '</div>' +
          '<div class="utility-progress">' +
            '<div class="utility-progress-bar" style="--utility-progress-width:' + d.percent + '%;"></div>' +
          '</div>' +
        '</div>' +
      '</div>';
    }).join('');
  } catch(e) {}
}

/* ─── Service Process Logs ─── */
async function loadServiceLogs() {
  const svc = document.getElementById('svc-log-select').value;
  const el = document.getElementById('svc-log-viewer');
  if (!svc) { el.innerHTML = '<span class="settings-console-hint">Select a service above to view its process output.</span>'; return; }
  try {
    const data = await (await fetch('/api/services/' + svc + '/logs?tail=200')).json();
    if (!data.lines || !data.lines.length) {
      el.innerHTML = '<span class="settings-console-hint">No log output captured for ' + svc + '. Logs appear when the service is running.</span>';
      return;
    }
    el.innerHTML = data.lines.map(line => {
      const tone = /error|fail|exception/i.test(line) ? ' settings-console-line-danger' : /warn/i.test(line) ? ' settings-console-line-warn' : '';
      return '<div class="settings-console-line' + tone + '">' + escapeHtml(line) + '</div>';
    }).join('');
    el.scrollTop = el.scrollHeight;
  } catch(e) {
    el.innerHTML = '<span class="settings-console-line-danger">Failed to load service logs.</span>';
  }
}

/* ─── Content Update Checker ─── */
async function checkContentUpdates() {
  try {
    const updates = await (await fetch('/api/kiwix/check-updates')).json();
    const panel = document.getElementById('content-updates-panel');
    const itemsEl = document.getElementById('content-update-items');
    if (!updates.length) { panel.style.display = 'none'; toast('All content is up to date', 'success'); return; }
    panel.style.display = 'block';
    itemsEl.innerHTML = updates.map(u =>
      '<div class="library-update-row">' +
        '<div class="library-update-copy">' +
          '<div class="library-update-title">' + escapeHtml(u.name) + '</div>' +
          '<div class="library-update-meta">' + escapeHtml(u.installed) + ' &#8594; ' + escapeHtml(u.available) + ' (' + escapeHtml(u.size) + ')</div>' +
        '</div>' +
        '<button class="btn btn-sm btn-primary" type="button" data-library-action="update-zim-content" data-zim-url="' + escapeAttr(u.url) + '" data-zim-filename="' + escapeAttr(u.available) + '">Update</button>' +
      '</div>'
    ).join('');
  } catch(e) { toast('Failed to check for updates', 'error'); }
}

async function updateZimContent(url, filename) {
  await fetch('/api/kiwix/download-zim', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url, filename})});
  toast('Downloading updated content...', 'info');
  loadZimDownloads();
}

/* ─── Wikipedia Tier Selector ─── */
async function loadWikipediaTiers() {
  try {
    const options = await (await fetch('/api/kiwix/wikipedia-options')).json();
    const installed = await (await fetch('/api/kiwix/zims')).json();
    const installedNames = new Set(installed.map(z => typeof z === 'string' ? z : z.name || ''));
    const el = document.getElementById('wiki-tier-options');
    if (!options.length) { el.innerHTML = '<div class="settings-empty-state">Install Kiwix first to download Wikipedia.</div>'; return; }
    el.innerHTML = options.map(o => {
      const isInstalled = installedNames.has(o.filename);
      const tierColor = o.tier === 'essential' ? 'var(--green)' : o.tier === 'standard' ? 'var(--accent)' : 'var(--orange)';
      return '<div class="contact-card wiki-tier-card" style="--wiki-tier-tone:' + tierColor + ';">' +
        '<div class="wiki-tier-topline"></div>' +
        '<div class="wiki-tier-title">' + escapeHtml(o.name) + '</div>' +
        '<div class="wiki-tier-copy">' + escapeHtml(o.desc) + '</div>' +
        '<div class="wiki-tier-footer">' +
          '<span class="wiki-tier-size">' + escapeHtml(o.size) + '</span>' +
          (isInstalled
            ? '<span class="wiki-tier-installed">&#10003; Installed</span>'
            : '<button class="btn btn-sm btn-primary" type="button" data-library-action="download-wiki-tier" data-zim-url="' + escapeAttr(o.url) + '" data-zim-filename="' + escapeAttr(o.filename) + '">Download</button>') +
        '</div>' +
      '</div>';
    }).join('');
  } catch(e) {}
}

async function downloadWikiTier(url, filename) {
  await fetch('/api/kiwix/download-zim', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url, filename})});
  toast('Downloading Wikipedia...', 'info');
  loadZimDownloads();
}

/* ─── Export / Import Config ─── */
function exportConfig() {
  window.location='/api/export-config';
  toast('Config exported');
}
function doFullBackup() {
  window.location='/api/export-all';
  localStorage.setItem('nomad-last-backup', new Date().toISOString());
  updateLastBackup();
  toast('Backup downloaded', 'success');
}
function doExportConfig() {
  exportConfig();
  localStorage.setItem('nomad-last-backup', new Date().toISOString());
  updateLastBackup();
}
async function showBackupList() {
  try {
    const backups = await (await fetch('/api/backups')).json();
    if (!backups.length) { toast('No automatic backups found', 'info'); return; }
    const html = backups.map(b => {
      const d = new Date(b.modified * 1000);
      const ts = d.toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
      return '<div class="settings-action-row">'
        + '<div class="settings-stack">'
        + '<div class="settings-row-title">' + escapeHtml(b.filename) + '</div>'
        + '<div class="settings-row-detail">' + ts + ' — ' + escapeHtml(b.size) + '</div></div>'
        + '<span class="settings-row-spacer"></span>'
        + '<button class="btn btn-sm btn-primary" type="button" data-shell-action="restore-legacy-backup" data-backup-filename="' + escapeAttr(b.filename) + '">Restore</button>'
        + '</div>';
    }).join('');
    const modal = document.createElement('div');
    modal.className = 'generated-modal-overlay';
    modal.dataset.backdropClose = 'generated-modal';
    modal.innerHTML = '<div class="modal-card settings-modal-card settings-modal-card-md generated-modal-card">'
      + '<div class="generated-modal-head">'
      + '<h3>Restore from Backup</h3>'
      + '<button class="btn btn-sm btn-ghost" type="button" data-shell-action="close-generated-modal" aria-label="Close restore backup modal">x</button></div>'
      + '<div class="generated-modal-copy">Current database will be backed up first. Restart the app after restoring.</div>'
      + '<div class="generated-modal-list">' + html + '</div></div>';
    document.body.appendChild(modal);
  } catch(e) { toast('Failed to load backups', 'error'); }
}
async function restoreBackup(filename) {
  if (!confirm('Restore database from ' + filename + '? Current data will be backed up first.')) return;
  try {
    const r = await fetch('/api/backups/restore', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({filename})});
    const d = await r.json();
    if (r.ok) {
      toast(d.message || 'Database restored', 'success');
      document.querySelectorAll('.generated-modal-overlay').forEach(m => m.remove());
    } else {
      toast(d.error || 'Restore failed', 'error');
    }
  } catch(e) { toast('Restore failed', 'error'); }
}
function updateLastBackup() {
  const el = document.getElementById('last-backup-time');
  if (!el) return;
  const ts = localStorage.getItem('nomad-last-backup');
  if (ts) {
    const d = new Date(ts);
    const ago = Math.round((Date.now() - d.getTime()) / (1000*60*60*24));
    const toneClass = ago > 30 ? 'text-red' : ago > 7 ? 'text-orange' : 'text-green';
    el.innerHTML = `Last: ${d.toLocaleDateString()} <span class="${toneClass}">(${ago === 0 ? 'today' : ago + 'd ago'})</span>`;
  } else {
    el.innerHTML = '<span class="text-orange">Never backed up</span>';
  }
}

async function importConfig() {
  const input = document.getElementById('import-file');
  if (!input.files.length) return;
  const formData = new FormData();
  formData.append('file', input.files[0]);
  const r = await (await fetch('/api/import-config', {method:'POST', body:formData})).json();
  input.value = '';
  toast(r.message || r.error || 'Import complete');
}

/* ─── In-App Frame ─── */
function openAppFrame(title, url) {
  document.getElementById('app-frame-title').textContent = title;
  document.getElementById('app-frame-iframe').src = url;
  document.getElementById('app-frame-overlay').style.display = 'flex';
}

function openAppFrameHTML(title, html, scrollTo) {
  const iframe = document.getElementById('app-frame-iframe');
  document.getElementById('app-frame-title').textContent = title;
  document.getElementById('app-frame-overlay').style.display = 'flex';
  iframe.src = 'about:blank';
  setTimeout(() => {
    iframe.contentDocument.open();
    iframe.contentDocument.write(html);
    iframe.contentDocument.close();
    if (scrollTo) {
      setTimeout(() => {
        const el = iframe.contentDocument.getElementById(scrollTo);
        if (el) el.scrollIntoView({behavior:'smooth',block:'start'});
      }, 100);
    }
  }, 50);
}

function closeAppFrame() {
  document.getElementById('app-frame-overlay').style.display = 'none';
  document.getElementById('app-frame-iframe').src = 'about:blank';
}
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && document.getElementById('app-frame-overlay').style.display === 'flex') {
    closeAppFrame();
  }
  if (e.key === 'Escape' && document.getElementById('needs-detail-modal').style.display === 'flex') {
    closeNeedsDetail();
  }
  const tcccModal = document.getElementById('tccc-modal');
  if (e.key === 'Escape' && tcccModal && tcccModal.style.display === 'flex') {
    tcccModal.style.display = 'none';
  }
});

/* ─── Global Keyboard Shortcuts ─── */
document.addEventListener('keydown', e => {
  // Skip if user is typing in an input/textarea
  const tag = document.activeElement?.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

  // Ctrl+K — Focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const search = document.getElementById('unified-search');
    if (search) { search.focus(); search.select(); }
  }
  // Ctrl+/ — Focus copilot dock (available on all tabs)
  if ((e.ctrlKey || e.metaKey) && e.key === '/') {
    e.preventDefault();
    const copilot = document.getElementById('copilot-input');
    if (copilot) { copilot.focus(); copilot.select(); }
  }
  // Alt+1-9 handled in second keydown listener below
});

function printAppFrame() {
  try {
    document.getElementById('app-frame-iframe').contentWindow.print();
  } catch(e) {
    toast('Cannot print this content — try opening it in a new browser tab instead', 'warning');
  }
}

