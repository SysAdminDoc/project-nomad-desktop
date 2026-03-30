/* ─── Prep Sub-Tab Navigation ─── */
// Preparedness lanes organize the workspace around common field situations.
const PREP_CATEGORIES = {
  coordinate: {label:'Coordinate', description:'Run checklists, capture incidents, and keep the operational picture current.', tabs:[
    {id:'checklists',label:'Checklists'},
    {id:'incidents',label:'Incidents'},
    {id:'ops',label:'Command Post'},
    {id:'analytics',label:'Trends'}
  ]},
  sustain:    {label:'Sustain', description:'Keep supplies, power, food production, and environmental awareness stable.', tabs:[
    {id:'inventory',label:'Supplies'},
    {id:'fuel',label:'Fuel'},
    {id:'power',label:'Power'},
    {id:'garden',label:'Food Production'},
    {id:'equipment',label:'Equipment'},
    {id:'weather',label:'Weather'}
  ]},
  care:       {label:'Care & People', description:'Support medical readiness, family planning, and the people network around you.', tabs:[
    {id:'medical',label:'Medical'},
    {id:'contacts',label:'Contacts'},
    {id:'family',label:'Family Plan'},
    {id:'community',label:'Community'},
    {id:'skills',label:'Skills'},
    {id:'journal',label:'Journal'}
  ]},
  protect:    {label:'Protect & Secure', description:'Manage security, comms discipline, exposure threats, and sensitive records.', tabs:[
    {id:'security',label:'Security'},
    {id:'radio',label:'Radio'},
    {id:'signals',label:'Signal Plan'},
    {id:'vault',label:'Vault'},
    {id:'ammo',label:'Ammo'},
    {id:'radiation',label:'Radiation'}
  ]},
  learn:      {label:'Reference & Planning', description:'Use decision guides, procedures, quick reference, and calculators to act fast.', tabs:[
    {id:'guides',label:'Guides'},
    {id:'protocols',label:'Protocols'},
    {id:'reference',label:'Quick Ref'},
    {id:'calculators',label:'Calculators'}
  ]},
};
let _currentPrepCat = 'coordinate';

function setPrepScenarioFocus(group) {
  const kicker = document.getElementById('prep-scenario-focus-kicker');
  const copy = document.getElementById('prep-scenario-focus-copy');
  if (kicker) kicker.textContent = group?.label || '';
  if (copy) copy.textContent = group?.description || '';
}

function showPrepCategory(cat) {
  const group = PREP_CATEGORIES[cat];
  if (!group) return;
  _currentPrepCat = cat;
  // Update scenario cards
  document.querySelectorAll('.prep-cat-btn').forEach(b => {
    const isActive = b.dataset.cat === cat;
    b.classList.toggle('active', isActive);
    b.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
  setPrepScenarioFocus(group);
  // Render sub-tabs for this lane
  const bar = document.getElementById('prep-subtab-bar');
  bar.innerHTML = group.tabs.map(function(t) {
    const active = document.querySelector('.prep-sub.active');
    const isActive = active && active.id === 'psub-' + t.id;
    return '<button type="button" class="prep-subtab' + (isActive ? ' active' : '') + '" data-psub="' + t.id + '" data-prep-sub-switch="' + t.id + '">' + t.label + '</button>';
  }).join('');
  // If no tab in this category is active, activate the first one
  const activeInCat = group.tabs.find(function(t) {
    const el = document.getElementById('psub-' + t.id);
    return el && el.classList.contains('active');
  });
  if (!activeInCat && group.tabs.length) {
    switchPrepSub(group.tabs[0].id);
  }
}

// Find which category a sub-tab belongs to
function _findCategoryForSub(sub) {
  for (const [cat, group] of Object.entries(PREP_CATEGORIES)) {
    if (group.tabs.some(function(t) { return t.id === sub; })) return cat;
  }
  return 'coordinate';
}

// Initialize Preparedness lanes on first load
function initPrepNav() {
  showPrepCategory('coordinate');
}

function switchPrepSub(sub) {
  // Ensure correct category is shown
  const cat = _findCategoryForSub(sub);
  if (cat !== _currentPrepCat) showPrepCategory(cat);
  document.querySelectorAll('.prep-subtab').forEach(b => b.classList.toggle('active', b.dataset.psub === sub));
  document.querySelectorAll('.prep-sub').forEach(p => p.classList.toggle('active', p.id === 'psub-' + sub));
  if (sub === 'incidents') loadIncidents();
  if (sub === 'inventory') { loadInventory(); loadBurnRate(); loadInvViz(); }
  if (sub === 'contacts') { loadContacts(); loadSkillsMatrix(); }
  if (sub === 'calculators') { try { calcWater(); calcFood(); calcPower(); calcWatch(); document.getElementById('solar-date').value=new Date().toISOString().slice(0,10); calcSolar(); document.getElementById('moon-date').value=new Date().toISOString().slice(0,10); calcMoon(); convertCoords(); calcTravel(); calcBattery(); calcHorizon(); updateCalTracker(); calcPlan(); calcFoodStorage(); calcGenFuel(); calcRainwater(); calcRadioRange(); calcMedDose(); calcSolarSize(); renderBOBChecklist(); calcBOB(); calcBallistics(); calcCompost(); calcPastureRotation(); calcNaturalBuilding(); calcFallout(); calcCanning(); calcBurnArea(); calcIVDrip(); calcDeadReckoning(); calcShelterPF(); calcCropCalories(); calcNVIS(); calcWeightDose(); calcHypothermia(); calcORT(); calcAbxInventory(); calcRadDose(); calcWaterNeeds(); calcGenerator(); calcDehydration(); calcVitals(); calcAntenna(); } catch(e) { console.error('Calculator init error:', e); } }
  if (sub === 'vault' && _vaultKey) loadVaultList();
  if (sub === 'weather') { loadWeather(); loadZambretti(); loadPressureGraph(); loadWeatherRules(); }
  if (sub === 'radio') { loadFreqDatabase(); loadCommsStatusBoard(); loadPropagation(); }
  if (sub === 'signals') { loadSignalSchedule(); loadCommsLog(); }
  if (sub === 'ops') { loadInfraStatus(); renderVehicles(); calcBleach(); loadThreatMatrix(); renderHomeSecurity(); }
  if (sub === 'family') loadFEP();
  if (sub === 'journal') loadJournal();
  if (sub === 'security') { loadSecurityDashboard(); loadCameras(); loadPerimeterZones(); loadMotionStatus(); _startMotionPolling(); }
  if (sub === 'power') { loadPowerDashboard(); loadPowerDevices(); updatePowerSpecFields(); }
  if (sub === 'garden') { loadPlots(); lookupZone(); loadCompanions(); loadPestGuide(); }
  if (sub === 'medical') { loadPatients(); loadMedicalSupplies(); loadTriageBoard(); loadExpiringMeds(); loadDosageCalculator(); }
  if (sub === 'guides') renderGuideSelector();
  if (sub === 'reference') { convertUnit(); showPlantZone(); textToMorse(); morseToText(); loadPace(); showPhrases(); loadShelterAssess(); }
  if (sub === 'checklists') loadChecklists();
  if (sub === 'skills') loadSkills();
  if (sub === 'ammo') loadAmmo();
  if (sub === 'community') { loadCommunity(); loadFederationPeers(); }
  if (sub === 'radiation') loadRadiation();
  if (sub === 'fuel') loadFuel();
  if (sub === 'equipment') loadEquipment();
  if (sub === 'analytics') loadAnalyticsDashboard();
}

/* ─── Preparedness ─── */
let _prepLoaded = false;
let _currentChecklistId = null;
let _currentChecklistItems = [];

async function loadPrepTab() {
  if (!_prepLoaded) {
    initPrepNav();
    await loadPrepTemplates();
    await loadSitBoard();
    calcWater(); calcFood(); calcPower();
    loadPace();
    _prepLoaded = true;
  } else {
    // Ensure the category bar has tabs (in case it wasn't initialized)
    if (!document.getElementById('prep-subtab-bar').children.length) initPrepNav();
  }
  await loadChecklists();
}

async function loadPrepTemplates() {
  try {
    const templates = await (await fetch('/api/checklists/templates')).json();
    const el = document.getElementById('prep-template-btns');
    el.innerHTML = Object.entries(templates).map(([k, v]) =>
      `<button class="prep-template-btn" data-checklist-template="${escapeHtml(k)}" title="${v.item_count} items">+ ${v.name}</button>`
    ).join('');
  } catch(e) {}
}

async function loadChecklists() {
  try {
    const lists = await (await fetch('/api/checklists')).json();
    const el = document.getElementById('prep-list');
    if (!lists.length) {
      el.innerHTML = '<div class="prep-empty-block"><div class="prep-empty-copy">No checklists yet. Choose a template above.</div></div>';
      return;
    }
    el.innerHTML = lists.map(c => {
      const pct = c.item_count > 0 ? Math.round(c.checked_count / c.item_count * 100) : 0;
      const remaining = Math.max(c.item_count - c.checked_count, 0);
      const toneClass = pct === 100 ? 'prep-list-card-good' : pct >= 50 ? 'prep-list-card-watch' : 'prep-list-card-risk';
      return `<div class="prep-item prep-list-card ${toneClass} ${c.id === _currentChecklistId ? 'active' : ''}" data-cl-id="${c.id}" data-checklist-id="${c.id}" role="button" tabindex="0" aria-pressed="${c.id === _currentChecklistId ? 'true' : 'false'}">
        <div class="prep-list-card-main">
          <div class="prep-list-card-head">
            <span class="prep-item-name prep-list-card-title">${escapeHtml(c.name)}</span>
            <span class="prep-progress prep-list-card-progress">${pct}%</span>
          </div>
          <div class="prep-list-card-bar"><span class="prep-list-card-bar-fill" style="width:${pct}%;"></span></div>
          <div class="prep-list-card-meta">${c.checked_count}/${c.item_count} complete · ${remaining} remaining</div>
        </div>
        <button type="button" class="prep-del prep-list-card-delete" data-checklist-delete="${c.id}" title="Delete" aria-label="Delete ${escapeHtml(c.name)}">x</button>
      </div>`;
    }).join('');
  } catch(e) {
    document.getElementById('prep-list').innerHTML = '<div class="prep-error-state">Failed to load checklists</div>';
  }
}

async function createChecklist(template) {
  try {
    const r = await (await fetch('/api/checklists', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({template})
    })).json();
    toast(`Created: ${r.name}`, 'success');
    _currentChecklistId = r.id;
    await loadChecklists();
    await selectChecklist(r.id);
  } catch(e) { toast('Failed to create checklist', 'error'); }
}

async function selectChecklist(id) {
  _currentChecklistId = id;
  try {
    const c = await (await fetch(`/api/checklists/${id}`)).json();
    _currentChecklistItems = c.items || [];
    document.getElementById('prep-active-name').textContent = c.name;
    renderChecklist();
    // Update sidebar active state
    document.querySelectorAll('.prep-item').forEach(el => {
      el.classList.toggle('active', el.dataset.clId == id);
    });
    await loadChecklists();
  } catch(e) { toast('Failed to load checklist', 'error'); }
}

function renderChecklist() {
  const el = document.getElementById('prep-checklist');
  const total = _currentChecklistItems.length;
  const checked = _currentChecklistItems.filter(i => i.checked).length;
  const pct = total > 0 ? Math.round(checked / total * 100) : 0;
  document.getElementById('prep-active-stats').textContent = total ? `${checked}/${total} complete · ${pct}%` : 'No items yet';
  document.getElementById('prep-progress-fill').style.width = pct + '%';

  if (!total) {
    el.innerHTML = '<div class="prep-empty-block"><div class="prep-empty-copy">This checklist is empty. Add an item to start building the runbook.</div></div>';
    return;
  }

  // Group by category
  const cats = {};
  _currentChecklistItems.forEach((item, idx) => {
    const cat = item.cat || 'general';
    if (!cats[cat]) cats[cat] = [];
    cats[cat].push({...item, idx});
  });

  let html = '';
  for (const [cat, items] of Object.entries(cats)) {
    const groupChecked = items.filter(item => item.checked).length;
    html += `
      <section class="prep-checklist-group">
        <div class="checklist-group-head prep-checklist-group-head">
          <span class="check-cat">${cat}</span>
          <span class="prep-checklist-group-meta">${groupChecked}/${items.length} complete</span>
        </div>
        <div class="prep-checklist-group-items">
          ${items.map((item, itemIndex) =>
            `<label class="check-item prep-check-item ${item.checked ? 'checked is-checked' : ''}" data-check-item="${item.idx}">
              <input type="checkbox" ${item.checked ? 'checked' : ''}>
              <span class="prep-check-item-body">
                <span class="prep-check-item-title">${escapeHtml(item.text)}</span>
                <span class="prep-check-item-status">${item.checked ? 'Done' : `Item ${itemIndex + 1}`}</span>
              </span>
            </label>`
          ).join('')}
        </div>
      </section>
    `;
  }
  el.innerHTML = html;
}

async function toggleCheckItem(idx) {
  if (!_currentChecklistId || idx >= _currentChecklistItems.length) return;
  _currentChecklistItems[idx].checked = !_currentChecklistItems[idx].checked;
  renderChecklist();
  // Save
  await fetch(`/api/checklists/${_currentChecklistId}`, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({items: _currentChecklistItems})
  });
  loadChecklists();
}

async function deleteChecklist(id) {
  await fetch(`/api/checklists/${id}`, {method: 'DELETE'});
  toast('Checklist deleted', 'warning');
  if (_currentChecklistId === id) {
    _currentChecklistId = null;
    _currentChecklistItems = [];
    document.getElementById('prep-active-name').textContent = 'Select or create a checklist';
    document.getElementById('prep-active-stats').textContent = '';
    document.getElementById('prep-progress-fill').style.width = '0%';
    document.getElementById('prep-checklist').innerHTML = '<div class="empty-state empty-state-fill"><div class="icon empty-state-icon-muted">&#9745;</div><p>Choose a template above to create a checklist, or select an existing one.</p></div>';
  }
  await loadChecklists();
}
