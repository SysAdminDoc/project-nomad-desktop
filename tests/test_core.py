"""Tests for core API routes — services, alerts, activity, version."""

from pathlib import Path
import re
import os


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_get_data_dir_falls_back_when_custom_path_is_unavailable(monkeypatch, tmp_path):
    import config
    import platform_utils

    unavailable_dir = r'G:\nomad-missing-drive'

    monkeypatch.setattr(platform_utils, 'is_portable_mode', lambda: False)
    monkeypatch.setattr(platform_utils, 'get_data_base', lambda: str(tmp_path))
    monkeypatch.setattr(config, 'load_config', lambda: {'data_dir': unavailable_dir})

    real_makedirs = os.makedirs

    def fake_makedirs(path, exist_ok=False):
        if os.path.normpath(path) == os.path.normpath(unavailable_dir):
            raise FileNotFoundError('missing drive')
        return real_makedirs(path, exist_ok=exist_ok)

    monkeypatch.setattr(config.os, 'makedirs', fake_makedirs)

    resolved = config.get_data_dir()

    assert resolved == str(tmp_path / config.APP_STORAGE_DIRNAME)
    assert Path(resolved).is_dir()


class TestServicesEndpoint:
    def test_services_list(self, client):
        resp = client.get('/api/services')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        # Should have the 7 managed services
        ids = [s['id'] for s in data]
        for svc in ['ollama', 'kiwix', 'cyberchef', 'kolibri', 'qdrant', 'stirling', 'flatnotes']:
            assert svc in ids, f'{svc} missing from services list'

    def test_service_fields(self, client):
        resp = client.get('/api/services')
        svc = resp.get_json()[0]
        assert 'id' in svc
        assert 'installed' in svc
        assert 'running' in svc
        assert 'port' in svc


class TestAlertsEndpoint:
    def test_alerts_list(self, client):
        resp = client.get('/api/alerts')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestActivityLog:
    def test_activity_log_empty(self, client):
        resp = client.get('/api/activity')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_activity_log_limit(self, client):
        resp = client.get('/api/activity?limit=5')
        assert resp.status_code == 200

    def test_activity_log_filter(self, client):
        resp = client.get('/api/activity?filter=inventory')
        assert resp.status_code == 200


class TestVersionEndpoint:
    def test_version(self, client):
        resp = client.get('/api/version')
        if resp.status_code == 200:
            data = resp.get_json()
            assert 'version' in data


class TestErrorHandler:
    def test_404_json_for_api(self, client):
        resp = client.get('/api/nonexistent-route-xyz')
        assert resp.status_code == 404
        data = resp.get_json()
        assert 'error' in data

    def test_index_page_loads(self, client):
        resp = client.get('/')
        assert resp.status_code == 200

    def test_index_page_shell_controls(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert '<title>NOMAD Field Desk v' in html
        assert 'src="/static/nomad-mark.svg"' in html
        assert 'alt="NOMAD logo"' in html
        assert 'class="sidebar-brand-kicker">Desktop Operations Workspace<' in html
        assert 'class="sidebar-group-title">Briefing<' in html
        assert 'Orient, assess, and decide what matters now.' in html
        assert 'class="sidebar-group-title">Operations<' in html
        assert 'Run field workflows, act on risk, and manage resources.' in html
        assert 'class="sidebar-group-title">Knowledge<' in html
        assert 'class="sidebar-group-title">Assistant<' in html
        assert 'Context-aware help, drafting, and operational copiloting.' in html
        assert 'class="sidebar-group-title">System<' in html
        assert '>Diagnostics</span>' in html
        assert '>Copilot</span>' in html
        assert 'Welcome to NOMAD' in html
        assert 'Start Using NOMAD' in html
        assert 'About NOMAD Field Desk' in html
        assert 'data-tab-target="services"' in html
        assert 'name="unified_search"' in html
        assert 'aria-label="Close preparedness needs detail"' in html
        assert 'name="conversation_search"' in html
        assert 'name="map_search"' in html
        assert 'type="url" id="media-url-input" name="media_url_input"' in html
        assert 'aria-label="Search media library"' in html
        assert 'id="inv-search" type="search" name="inv_search"' in html
        assert 'id="calc-search" type="search" name="calc_search"' in html
        assert 'name="interface_language"' in html
        assert 'name="dashboard_password"' in html
        assert 'autocomplete="new-password"' in html
        assert 'name="lan_channel"' in html
        assert 'name="copilot_query"' in html
        assert 'name="csv_target_table"' in html
        assert 'aria-labelledby="shortcuts-title"' in html
        assert 'id="mobile-bottom-nav"' not in html
        assert 'data-shell-action="open-mobile-drawer"' not in html
        assert 'class="sidebar-toggle"' not in html
        assert 'viewport-fit=cover' not in html
        assert 'Can my family use it from another computer on the network?' in html
        assert 'data-ai-memory-action="toggle"' in html
        assert 'id="system-health-results" class="settings-result-shell" aria-live="polite"' in html
        assert 'data-mode-select="command"' in html
        assert 'data-prep-category="coordinate"' in html
        assert 'Choose the situation you are managing' in html
        assert 'Choose a workspace inside this lane' in html
        assert 'Keep one checklist active, see what remains at a glance, and make handoffs easier when more than one person is involved.' in html
        assert 'Capture events in sequence so the next operator can understand risk, severity, and timing without reconstructing the timeline.' in html
        assert 'Track stock, burn rate, expiry pressure, and replenishment posture from one operating board instead of scattered lists.' in html
        assert 'data-tab-target="preparedness" data-prep-sub="checklists"' in html
        assert 'data-tab-target="preparedness" data-prep-sub="security"' in html
        assert 'data-protocol-toggle' in html
        assert 'data-checklist-template="' in html
        assert 'data-shell-action="open-widget-manager"' in html
        assert 'id="copilot-suggestions" class="copilot-suggestions" hidden' in html
        assert 'copilot-answer-shell' in html
        assert 'copilot-suggestion-list' in html
        assert 'data-install-service="ollama"' in html
        assert 'data-shell-action="install-service"' in html
        assert 'data-shell-action="reload-services"' in html
        assert 'data-shell-action="dismiss-broadcast"' in html
        assert 'id="broadcast-banner" class="broadcast-banner is-hidden"' in html
        assert 'class="search-bar home-search-shell home-search-shell-wide"' in html
        assert 'class="home-mode-rail home-surface-panel"' in html
        assert 'Jump into the lane that matches what you need to do next.' in html
        assert 'class="home-mode-card" data-tab-target="preparedness" data-prep-sub="checklists"' in html
        assert 'class="btn btn-primary welcome-banner-primary-action"' in html
        assert 'id="shortcuts-overlay" class="shortcuts-overlay" role="dialog" aria-modal="true" aria-labelledby="shortcuts-title" hidden' in html
        assert 'class="shortcuts-grid"' in html
        assert 'class="sidebar-footer-meta"' in html
        assert 'class="sidebar-footer-actions"' in html
        assert 'class="sidebar-footer-status"' in html
        assert 'class="sidebar-footer-row"' in html
        assert 'class="sidebar-empty-state"' in html
        assert 'id="copilot-utility-chat-btn" class="btn btn-sm btn-ghost copilot-utility-btn"' in html
        assert 'id="copilot-utility-timer-btn" class="btn btn-sm btn-ghost copilot-utility-btn"' in html
        assert 'id="copilot-utility-actions-btn" class="btn btn-sm btn-ghost copilot-utility-btn"' in html
        assert 'aria-controls="lan-chat-panel" aria-expanded="false"' in html
        assert 'aria-controls="timer-panel" aria-expanded="false"' in html
        assert 'aria-controls="quick-actions-menu" aria-expanded="false"' in html
        assert 'id="utility-hub"' not in html
        assert 'id="lan-chat-panel" class="utility-panel utility-panel-shell utility-panel-shell-wide utility-panel-shell-lan is-hidden"' in html
        assert 'id="lan-chat-compact-toggle" class="btn btn-sm btn-ghost utility-compact-btn"' in html
        assert 'id="lan-chat-messages" class="utility-panel-body utility-message-list"' in html
        assert 'id="burn-rate-dash" class="utility-summary-result"' in html
        assert 'id="map-sources-catalog" hidden' in html
        assert 'class="map-command-deck map-surface"' in html
        assert 'Build an offline map room that is useful when the network is not.' in html
        assert 'class="map-command-chip">Print-ready atlas<' in html
        assert 'class="region-card-shell"' in html
        assert 'id="geocode-results" class="map-geocode-results is-hidden"' in html
        assert 'id="map-download-status" class="map-download-status is-hidden"' in html
        assert 'id="map-url-input" type="url" name="map_download_url" class="map-import-input"' in html
        assert 'id="pdf-iframe" class="workspace-frame workspace-frame-light"' in html
        assert 'class="desc readiness-action-copy"' in html
        assert 'Know what breaks first, then fix it fast.' in html
        assert 'Run Operations Lane' in html
        assert 'class="readiness-action-kicker">Coordinate<' in html
        assert 'id="plant-calendar" class="plant-calendar-shell"' in html
        assert 'id="media-folder-list" class="media-scroll-region media-folder-list"' in html
        assert 'class="media-command-deck"' in html
        assert 'Curate channels, downloads, books, and local knowledge in one calm library.' in html
        assert 'class="media-command-pill">Offline first<' in html
        assert 'id="channel-browser" class="media-browser-region is-hidden"' in html
        assert 'id="media-book-reader" class="media-book-reader is-hidden"' in html
        assert 'class="library-command-deck workspace-panel"' in html
        assert 'Build a local reference shelf you can trust when the network disappears.' in html
        assert 'class="library-command-pill">Offline-first<' in html
        assert 'class="settings-command-deck workspace-panel"' in html
        assert 'Tune the platform without losing the operational picture.' in html
        assert 'Pull Recommended Models' in html
        assert 'Choose how this desk behaves under load' in html
        assert 'Plan recurring work, track due windows, and keep upkeep visible before it becomes a problem.' in html
        assert 'Generate clear rotations, print them fast, and keep shift coverage easy to review under pressure.' in html
        assert 'Review app-level warnings and errors without leaving the control workspace.' in html
        assert '5 Work Modes' in html
        assert '5 Preparedness Lanes' in html
        assert 'class="benchmark-command-deck workspace-panel"' in html
        assert 'Measure the machine, compare trends, and decide what to trust under load.' in html
        assert 'Compare runs over time to spot degradation before it turns into operational risk.' in html
        assert 'class="tools-command-deck workspace-panel"' in html
        assert 'Launch the specialized tools that support field work, training, and off-grid communication.' in html
        assert 'Prepare encrypted message files for physical handoff when you need discreet, offline exchange between systems.' in html
        assert 'Coordinate shared exercises with peers so training, decisions, and results stay visible across the network.' in html
        assert 'class="tools-subsection-head"' in html
        assert 'Waiting for a connected radio.' in html
        assert 'id="drill-summary" class="drill-summary-strip" hidden' in html
        assert 'id="drill-progress" class="progress-bar drill-active-progress" hidden' in html
        assert 'Review pace, completion quality, and recency so the next drill is easy to improve.' in html
        assert 'id="inv-viz" class="inventory-viz-shell"' in html
        assert 'id="rad-result"' in html
        assert 'id="wn-result"' in html
        assert 'id="cmd-dashboard" class="prep-dashboard-grid utility-summary-grid is-hidden"' in html
        assert 'class="map-popup-facts"' in html
        assert 'class="map-popup-list"' in html
        assert 'class="readiness-category-link readiness-category-row"' in html
        assert 'class="chat-status-badge"' in html
        assert 'chat-empty-state-compact' in html
        assert 'class="notes-template-list"' in html
        assert 'class="notes-command-deck"' in html
        assert 'Capture decisions, field observations, and reference material without losing the thread.' in html
        assert 'class="notes-command-pill">Backlinks<' in html
        assert 'class="note-item-head"' in html
        assert 'class="prep-guide-selector-grid"' in html
        assert 'class="prep-guide-card"' in html
        assert 'class="wizard-card wizard-card-shell"' in html
        assert 'class="tour-card-shell"' in html
        assert 'id="tccc-flow" class="prep-tccc-shell" hidden' in html
        assert 'id="tccc-prev-btn" hidden' in html
        assert 'data-tab-target="preparedness" data-prep-sub="inventory"' in html
        assert 'data-chat-action="new-conversation"' in html
        assert 'COPILOT WORKSPACE' in html
        assert 'Plan, analyze, and decide from one calm workspace.' in html
        assert 'Private + Local' in html
        assert 'class="chat-empty-highlights"' in html
        assert 'data-chat-action="select-conversation"' in html
        assert 'data-chat-dblclick="rename-conversation"' in html
        assert 'data-chat-action="copy-message"' in html
        assert 'data-chat-action="view-kb-document"' in html
        assert 'data-chat-action="analyze-kb-doc"' in html
        assert 'chat-source-chip' in html
        assert 'chat-citation-kicker' in html
        assert 'chat-kb-badge' in html
        assert 'data-convo-rename-id="' in html
        assert 'class="sidebar-empty-state convo-search-empty"' in html
        assert 'search-result-group-head' in html
        assert 'search-highlight' in html
        assert 'model-picker-card' in html
        assert 'kb-doc-item-stack' in html
        assert 'kb-detail-entity-list' in html
        assert 'data-click-target="chat-file-input"' in html
        assert 'data-change-action="apply-preset"' in html
        assert 'data-input-action="filter-calcs"' in html
        assert 'data-input-action="calc-ballistics"' in html
        assert 'class="calc-row-select-compact"' in html
        assert 'class="calc-row-select-wide"' in html
        assert 'class="calc-row-input-tight"' in html
        assert 'class="prep-calc-inline-form"' in html
        assert 'class="prep-calc-checklist-grid"' in html
        assert 'class="prep-calc-check-grid"' in html
        assert 'class="prep-calc-dynamic-list"' in html
        assert 'class="prep-reference-cards"' in html
        assert 'class="prep-reference-grid-wide"' in html
        assert 'class="prep-reference-panel-grid"' in html
        assert 'class="prep-triage-static-grid"' in html
        assert 'class="ref-table prep-reference-table-compact"' in html
        assert 'class="prep-reference-template-grid"' in html
        assert 'class="prep-reference-code-grid"' in html
        assert 'id="shelter-assess" class="prep-reference-assess-grid"' in html
        assert 'id="phrase-output" class="prep-reference-result-grid"' in html
        assert 'class="prep-reference-card-grid"' in html
        assert 'id="forage-output" class="prep-reference-result-grid prep-reference-result-grid-compact"' in html
        assert 'class="ref-table prep-reference-table-compact prep-reference-radio-table"' in html
        assert 'class="prep-reference-shell"' in html
        assert 'class="prep-reference-emphasis-grid"' in html
        assert 'class="ref-table prep-reference-table-compact prep-reference-shell-table"' in html
        assert 'class="prep-reference-shell-warning"' in html
        assert 'class="prep-reference-shell-lead"' in html
        assert 'class="prep-reference-shell-columns"' in html
        assert 'class="prep-reference-mini-grid prep-reference-mono-block"' in html
        assert 'class="prep-reference-wire-key"' in html
        assert 'class="prep-reference-scroll"' in html
        assert 'class="drill-steps drill-step-list"' in html
        assert 'class="map-bookmark-row"' in html
        assert 'class="library-pdf-row"' in html
        assert 'class="shopping-list-row"' in html
        assert 'class="planner-result-grid"' in html
        assert 'class="shareable-data-block"' in html
        assert 'class="guide-crumb' in html
        assert 'class="prep-reference-definition-list"' in html
        assert 'class="prep-reference-callout prep-reference-callout-danger"' in html
        assert 'class="prep-reference-callout prep-reference-callout-info"' in html
        assert 'class="prep-toolbar prep-toolbar-row"' in html
        assert 'class="prep-form-grid prep-form-grid-2 prep-ops-form-grid"' in html
        assert 'class="prep-inline-password-wrap"' in html
        assert 'class="prep-weather-canvas"' in html
        assert 'class="prep-scroll-shell"' in html
        assert 'id="signal-schedule-list" class="prep-table-wrap"' in html
        assert 'id="signal-next" class="prep-reference-note prep-reference-note-tight" hidden' in html
        assert 'id="skills-filter-btns" class="prep-chip-row"' in html
        assert 'id="ammo-list" class="prep-table-wrap"' in html
        assert 'class="media-browser-group-head"' in html
        assert 'class="media-browser-status-copy"' in html
        assert 'class="media-download-item"' in html
        assert 'class="media-browser-grid media-browser-grid-subscriptions"' in html
        assert 'class="media-status-chip media-status-chip-success"' in html
        assert 'media-continue-card' in html
        assert 'media-card-duration' in html
        assert 'media-list-thumb' in html
        assert 'inline-status-spinner' in html
        assert 'service-card-head' in html
        assert 'library-tier-card' in html
        assert 'catalog-action-group' in html
        assert 'settings-backup-item' in html
        assert 'live-widget-mini-row' in html
        assert 'class="torrent-card"' in html
        assert 'class="torrent-active-item"' in html
        assert 'class="utility-progress"' in html
        assert 'class="download-banner-entry"' in html
        assert 'settings-console-line' in html
        assert 'class="library-update-row"' in html
        assert 'class="contact-card wiki-tier-card"' in html
        assert 'generated-modal-overlay' in html
        assert 'vault-entry-row' in html
        assert 'saved-route-row' in html
        assert 'lan-qr-modal-card' in html
        assert 'utility-fab' not in html

    def test_shared_css_avoids_transition_all(self):
        css_root = REPO_ROOT / 'web' / 'static' / 'css'
        css_files = [
            css_root / 'app.css',
            css_root / 'premium.css',
            REPO_ROOT / 'web' / 'nukemap' / 'css' / 'styles.css',
            *sorted((css_root / 'app').glob('*.css')),
            *sorted((css_root / 'premium').glob('*.css')),
        ]
        for css_file in css_files:
            contents = css_file.read_text(encoding='utf-8')
            assert 'transition: all' not in contents, f'transition: all found in {css_file.name}'

    def test_gitignore_covers_legacy_binaries_and_runtime_artifacts(self):
        contents = (REPO_ROOT / '.gitignore').read_text(encoding='utf-8')

        assert 'NOMAD-Setup.exe' in contents
        assert 'NOMADFieldDesk.exe' in contents
        assert 'ProjectNOMAD-Setup.exe' in contents
        assert 'ProjectNOMAD.exe' in contents
        assert '.pytest_tmp/' in contents
        assert 'test_runtime/' in contents
        assert 'test_runtime_probe/' in contents

    def test_runtime_js_uses_shared_micro_ui_classes_instead_of_old_fixed_inline_styles(self):
        js_root = REPO_ROOT / 'web' / 'templates' / 'index_partials' / 'js'
        js_files = sorted(js_root.rglob('*.js'))
        combined = '\n'.join(path.read_text(encoding='utf-8') for path in js_files)
        style_count = sum(text.count('style="') + text.count('style=\\"') for text in [combined])

        assert 'class="runtime-empty-note"' in combined
        assert 'class="runtime-table-head-compact"' in combined
        assert 'class="weather-rule-condition"' in combined
        assert 'class="network-status-inline' in combined
        assert 'class="tour-content-title"' in combined
        assert 'class="note-template-item-icon"' in combined
        assert 'class="runtime-status-installed"' in combined
        assert 'class="coords-result-block"' in combined
        assert 'class="activity-service-tag"' in combined
        assert 'class="alert-dismiss alert-dismiss-link"' in combined
        assert 'class="antenna-result-value"' in combined
        assert 'note-backlink-link' in combined

        assert 'style="font-size:15px;color:${muted};"' not in combined
        assert 'style="display:block;margin-bottom:6px;column-span:all;"' not in combined
        assert 'style="color:var(--text-dim);font-size:12px;">No waypoints saved.' not in combined
        assert 'style="font-family:var(--font-data,monospace);font-weight:600;"' not in combined
        assert 'style="font-size:15px;margin-bottom:6px;"' not in combined
        assert 'style="font-size:13px;color:var(--text-dim);line-height:1.6;"' not in combined
        assert style_count <= 100, f'JS runtime inline style count regressed to {style_count}'

    def test_app_css_is_split_into_ordered_import_manifest(self):
        manifest = REPO_ROOT / 'web' / 'static' / 'css' / 'app.css'
        app_dir = REPO_ROOT / 'web' / 'static' / 'css' / 'app'
        manifest_text = manifest.read_text(encoding='utf-8')
        manifest_lines = manifest_text.count('\n') + 1
        parts = sorted(app_dir.glob('*.css'))

        assert manifest_lines < 20, f'app.css manifest still too large: {manifest_lines} lines'
        assert len(parts) >= 6, f'expected app css parts, found {len(parts)}'
        assert '@import url("./app/00_theme_tokens.css");' in manifest_text
        assert '@import url("./app/70_cleanup_utilities.css");' in manifest_text

    def test_premium_css_is_split_into_ordered_import_manifest(self):
        manifest = REPO_ROOT / 'web' / 'static' / 'css' / 'premium.css'
        premium_dir = REPO_ROOT / 'web' / 'static' / 'css' / 'premium'
        manifest_text = manifest.read_text(encoding='utf-8')
        manifest_lines = manifest_text.count('\n') + 1
        parts = sorted(premium_dir.glob('*.css'))

        assert manifest_lines < 20, f'premium.css manifest still too large: {manifest_lines} lines'
        assert len(parts) >= 6, f'expected premium css parts, found {len(parts)}'
        assert '@import url("./premium/00_base.css");' in manifest_text
        assert '@import url("./premium/70_layout_hardening.css");' in manifest_text

    def test_partial_controls_have_names(self):
        partial_dir = REPO_ROOT / 'web' / 'templates' / 'index_partials'
        control_pattern = re.compile(r'<(input|select|textarea)\b([^>]*)>', re.I)
        missing = []

        for partial in sorted(partial_dir.rglob('*.html')):
            text = partial.read_text(encoding='utf-8')
            for match in control_pattern.finditer(text):
                attrs = match.group(2).lower()
                if ' type="hidden"' in attrs or " type='hidden'" in attrs:
                    continue
                if ' name=' not in attrs:
                    missing.append(f'{partial.name}:{match.group(0)[:120]}')

        assert not missing, f'controls missing name attributes: {missing[:10]}'

    def test_split_partials_avoid_legacy_inline_hidden_and_layout_styles(self):
        html_root = REPO_ROOT / 'web' / 'templates' / 'index_partials'
        js_root = html_root / 'js'
        forbidden = [
            'style="display:none;"',
            'style="width:0%"',
            'style="display:none;width:100%;margin-top:4px;"',
            'style="grid-column:1/-1;"',
            'style="margin-left:auto;"',
        ]
        offenders = []

        for path in sorted(html_root.rglob('*.html')):
            text = path.read_text(encoding='utf-8')
            for token in forbidden:
                if token in text:
                    offenders.append(f'{path.name}:{token}')

        for path in sorted(js_root.rglob('*.js')):
            text = path.read_text(encoding='utf-8')
            for token in forbidden:
                if token in text:
                    offenders.append(f'{path.name}:{token}')

        assert not offenders, f'legacy inline style tokens found: {offenders[:10]}'

    def test_preparedness_tab_is_split_into_domain_partials(self):
        parent = REPO_ROOT / 'web' / 'templates' / 'index_partials' / '_tab_preparedness.html'
        prep_dir = REPO_ROOT / 'web' / 'templates' / 'index_partials' / 'preparedness'
        parent_text = parent.read_text(encoding='utf-8')
        parent_lines = parent_text.count('\n') + 1
        prep_partials = sorted(prep_dir.glob('*.html'))

        assert parent_lines < 40, f'preparedness parent partial still too large: {parent_lines} lines'
        assert len(prep_partials) >= 12, f'expected preparedness domain partials, found {len(prep_partials)}'
        assert '{% include "index_partials/preparedness/_overview.html" %}' in parent_text
        assert '{% include "index_partials/preparedness/_guides.html" %}' in parent_text
        assert '{% include "index_partials/preparedness/_analytics.html" %}' in parent_text

    def test_preparedness_runtime_is_split_into_domain_partials(self):
        parent = REPO_ROOT / 'web' / 'templates' / 'index_partials' / 'js' / '_app_preparedness_core.js'
        prep_dir = REPO_ROOT / 'web' / 'templates' / 'index_partials' / 'js' / 'preparedness'
        parent_text = parent.read_text(encoding='utf-8')
        parent_lines = parent_text.count('\n') + 1
        prep_partials = sorted(prep_dir.glob('*.js'))

        assert parent_lines < 20, f'preparedness runtime manifest still too large: {parent_lines} lines'
        assert len(prep_partials) >= 5, f'expected preparedness runtime partials, found {len(prep_partials)}'
        assert '{% include "index_partials/js/preparedness/_prep_nav_core.js" %}' in parent_text
        assert '{% include "index_partials/js/preparedness/_prep_inventory_flows.js" %}' in parent_text
        assert '{% include "index_partials/js/preparedness/_prep_calcs_misc.js" %}' in parent_text

    def test_index_page_runtime_shell_blocks(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'class="freq-table prep-data-table prep-reference-table-compact watch-result-table"' in html
        assert 'class="contact-card prep-skill-card"' in html
        assert 'class="freq-table prep-data-table prep-ammo-table"' in html
        assert 'class="widget-detail widget-detail-shell is-hidden"' in html
        assert 'class="cmd-dashboard-note"' in html
        assert 'class="need-card-head"' in html
        assert 'need-item-pill-list' in html
        assert 'need-detail-state' in html
        assert 'prep-morse-output' in html
        assert 'class="cmd-checklist-list"' in html
        assert 'class="journal-entry-copy"' in html
        assert 'class="scenario-complete-state"' in html
        assert 'scenario-result-card' in html
        assert 'alert-clear-state' in html
        assert 'gs-step-row' in html
        assert 'class="prep-tccc-header"' in html
        assert 'prep-tccc-action-btn' in html
        assert 'class="calc-result calc-result-tight"' in html
        assert 'class="prep-calc-checklist-card"' in html
        assert 'class="prep-calc-checklist-entry"' in html
        assert 'class="prep-modal-grid-two"' in html
        assert 'prep-quick-add-btn' in html
        assert 'id="peer-list" class="settings-toolbar-spacing prep-card-grid peer-list-grid"' in html
        assert 'class="contact-card peer-list-card"' in html
        assert 'id="training-datasets-list" class="training-list-shell training-list-shell-datasets"' in html
        assert 'id="training-jobs-list" class="training-list-shell training-list-shell-jobs"' in html
        assert 'class="training-record"' in html
        assert 'class="settings-summary-total"' in html
        assert 'class="settings-summary-note"' in html
        assert 'class="utility-summary-result utility-summary-grid fallout-result-summary"' in html
        assert 'class="prep-data-table prep-reference-table-compact fallout-result-table"' in html
        assert 'class="utility-summary-result utility-summary-grid canning-result-summary"' in html
        assert 'id="sync-log-list" class="settings-list-shell settings-scroll-shell settings-sync-log-shell"' in html
        assert 'id="conflict-list" class="settings-list-shell settings-scroll-shell settings-conflict-shell"' in html
        assert 'id="merge-editor-overlay" class="settings-result-shell settings-toolbar-spacing settings-merge-editor-shell" hidden' in html
        assert 'class="settings-conflict-card"' in html
        assert 'class="settings-merge-editor-row"' in html
        assert 'settings-exercise-card' in html
        assert 'settings-row-pill-dynamic' in html
        assert 'prep-calc-result-shell' in html
        assert 'settings-csv-select' in html
        assert 'prep-template-meta' in html
        assert 'chat-image-preview-row' in html
        assert 'fep-member-row' in html
        assert 'calorie-track-summary' in html
        assert 'settings-message-body' in html
        assert 'prep-calc-inline-builder' in html
        assert 'class="prep-calc-dynamic-row"' in html
        assert 'class="prep-data-table prep-reference-table-compact prep-calc-table prep-calc-table-center"' in html
        assert 'class="prep-summary-card utility-summary-card prep-summary-card-wide"' in html
        assert 'class="prep-calc-band-list"' in html
        assert 'class="prep-reference-callout prep-reference-callout-safe"' in html
        assert 'prep-calc-result-head' in html
        assert 'prep-calc-result-block' in html
        assert 'prep-calc-result-stage' in html
        assert 'prep-result-accent' in html
        assert 'prep-result-note-text' in html
        assert 'data-input-action="save-pace"' in html
        assert 'data-change-action="show-phrases"' in html
        assert 'data-change-action="wiz-toggle-custom"' in html
        assert 'data-change-action="toggle-home-security"' in html
        assert 'data-change-action="update-widget-field"' in html
        assert 'data-media-sub-switch="channels"' in html
        assert 'data-media-action="download-url"' in html
        assert 'data-media-action="select-folder"' in html
        assert 'data-media-action="download-ref-book"' in html
        assert 'data-media-action="toggle-favorite-item"' in html
        assert 'data-media-action="browse-channel-videos"' in html
        assert 'data-media-action="watch-download-yt"' in html
        assert 'data-media-action="download-torrent"' in html
        assert 'data-media-action="copy-torrent-magnet"' in html
        assert 'data-media-action="seek-audio-chapter"' in html
        assert 'data-media-action="unsubscribe-channel"' in html
        assert 'data-zim-tier="essential"' in html
        assert 'data-library-action="refresh-offline-content"' in html
        assert 'data-library-action="switch-tier"' in html
        assert 'data-library-action="download-zim-item"' in html
        assert 'data-library-action="update-zim-content"' in html
        assert 'data-map-action="toggle-map-view"' in html
        assert 'data-map-action="delete-map"' in html
        assert 'map-zone-panel' in html
        assert 'map-print-table' in html
        assert 'data-change-action="map-tile-source"' in html
        assert 'data-input-action="geocode-search"' in html
        assert 'data-note-action="create-note"' in html
        assert 'data-note-action="select-note"' in html
        assert 'data-note-action="apply-note-template"' in html
        assert 'data-benchmark-mode="full"' in html
        assert 'data-tool-action="start-compass"' in html
        assert 'data-drill-type="72hour"' in html
        assert 'data-prep-action="show-inv-form"' in html
        assert 'data-prep-action="adjust-inv-qty"' in html
        assert 'data-click-target="receipt-file-input"' in html
        assert 'data-change-action="handle-receipt-file-select"' in html
        assert 'data-prep-action="scan-receipt"' in html
        assert 'data-click-target="vision-file-input"' in html
        assert 'data-change-action="handle-vision-file-select"' in html
        assert 'data-prep-action="scan-vision-image"' in html
        assert 'data-prep-action="start-barcode-camera"' in html
        assert 'data-prep-action="add-upc-database"' in html
        assert 'data-prep-action="add-barcode-to-inventory"' in html
        assert 'data-shell-action="barcode-to-inventory"' in html
        assert 'data-shell-action="open-wiki-link"' in html
        assert 'data-shell-action="copy-code"' in html
        assert 'data-sit-domain="security"' in html
        assert 'data-change-action="import-checklist-json"' in html
        assert 'data-input-action="load-contacts"' in html
        assert 'data-prep-action="edit-contact"' in html
        assert 'data-prep-action="delete-incident"' in html
        assert 'data-prep-action="load-comms-status-board"' in html
        assert 'data-dtmf-key="1"' in html
        assert 'data-security-tab="cameras"' in html
        assert 'data-power-tab="devices"' in html
        assert 'data-med-ref="vital_signs"' in html
        assert 'data-change-action="update-power-spec-fields"' in html
        assert 'data-change-action="load-sensor-chart"' in html
        assert 'data-input-action="filter-companions"' in html
        assert 'data-prep-action="add-cal-entry"' in html
        assert 'data-input-action="calc-plan"' in html
        assert 'data-change-action="calc-solar-size"' in html
        assert 'data-prep-action="show-forage-month"' in html
        assert 'data-prep-action="send-broadcast"' in html
        assert 'data-enter-action="send-broadcast"' in html
        assert 'data-prep-action="generate-sitrep"' in html
        assert 'data-change-action="run-cipher"' in html
        assert 'data-change-action="calc-bleach"' in html
        assert 'data-prep-action="cycle-threat"' in html
        assert 'data-prep-action="gs-navigate"' in html
        assert 'data-shell-action="open-needs-detail"' in html
        assert 'data-shell-action="toggle-widget-expand"' in html
        assert 'data-shell-action="wiz-select-drive"' in html
        assert 'data-shell-action="run-training-job"' in html
        assert 'data-shell-action="run-gs-action"' in html
        assert 'data-shell-action="copy-text"' in html
        assert 'data-shell-action="snooze-alert"' in html
        assert 'data-library-action="view-pdf-item"' in html
        assert 'data-media-action="resume-media"' in html
        assert 'data-map-action="submit-drawn-zone"' in html
        assert 'data-map-action="load-elevation-profile"' in html
        assert 'data-prep-action="play-morse"' in html
        assert 'data-prep-action="complete-tccc-action"' in html
        assert 'data-prep-action="quick-add-inv-item"' in html
        assert 'data-prep-action="apply-inventory-template"' in html
        assert 'data-prep-action="submit-custom-checklist"' in html
        assert 'data-prep-action="submit-checklist-item"' in html
        assert 'data-prep-action="delete-journal-entry"' in html
        assert 'data-prep-action="submit-preservation"' in html
        assert 'data-prep-action="start-scenario"' in html
        assert 'data-prep-action="scenario-choose"' in html
        assert 'data-prep-action="show-ics-tab"' in html
        assert 'data-prep-action="export-journal"' in html
        assert 'data-ctrl-enter-action="submit-journal"' in html
        assert 'data-input-action="save-fep"' in html
        assert 'data-prep-action="open-skill-form"' in html
        assert 'data-prep-action="show-add-peer-form"' in html
        assert 'data-prep-action="open-fuel-form"' in html
        assert 'data-change-action="set-language"' in html
        assert 'data-input-action="save-ai-name"' in html
        assert 'data-shell-action="save-ollama-host"' in html
        assert 'data-shell-action="show-model-info"' in html
        assert 'data-shell-action="open-search-result"' in html
        assert 'data-change-action="toggle-startup"' in html
        assert 'data-shell-action="full-backup"' in html
        assert 'data-prep-action="show-wound-form"' in html
        assert 'data-enter-action="unlock-vault"' in html
        assert 'data-prep-action="unlock-vault"' in html
        assert 'data-prep-action="load-zambretti"' in html
        assert 'data-prep-action="load-comms-log"' in html
        assert 'data-enter-action="log-comms"' in html
        assert 'data-shell-action="discover-peers"' in html
        assert 'data-enter-action="sync-manual-peer"' in html
        assert 'data-shell-action="create-group-exercise"' in html
        assert 'data-change-action="configure-auto-backup"' in html
        assert 'data-input-action="update-ab-keep-display"' in html
        assert 'data-backdrop-close="csv-import-modal"' in html
        assert 'data-change-action="preview-csv-import"' in html
        assert 'data-shell-action="dismiss-copilot-answer"' in html
        assert 'data-shell-action="restore-legacy-backup"' in html
        assert 'data-shell-action="lookup-barcode"' in html
        assert 'data-shell-action="toggle-lan-chat"' in html
        assert 'data-input-action="save-lan-chat-name"' in html
        assert 'data-shell-action="toggle-quick-actions"' in html
        assert 'data-shell-action="toggle-timer-panel"' in html
        assert 'data-change-action="toggle-sidebar-item"' in html
        assert 'data-change-action="toggle-home-section"' in html
        assert 'data-input-action="debounce-search"' in html
        assert 'data-change-action="load-activity"' in html
        assert 'data-change-action="change-media-sort"' in html
        assert 'data-input-action="filter-media-list"' in html
        assert 'data-enter-action="search-youtube"' in html
        assert 'data-shell-action="wiz-go-page"' in html
        assert 'data-shell-action="wiz-minimize"' in html
        assert 'data-shell-action="tour-next"' in html
        assert 'data-stop-propagation' in html

    def test_manifest_uses_nomad_branding(self):
        manifest = (REPO_ROOT / 'web' / 'static' / 'manifest.json').read_text(encoding='utf-8')
        assert '"name": "NOMAD Field Desk"' in manifest
        assert '"short_name": "NOMAD"' in manifest
        assert '/static/nomad-mark.svg' in manifest

    def test_desktop_branding_assets_exist(self):
        assert (REPO_ROOT / 'icon.ico').is_file()
        assert (REPO_ROOT / 'nomad-mark.png').is_file()
        assert (REPO_ROOT / 'web' / 'static' / 'logo.png').is_file()

    def test_packaging_files_use_nomad_field_desk_branding(self):
        build_spec = (REPO_ROOT / 'build.spec').read_text(encoding='utf-8')
        installer = (REPO_ROOT / 'installer.iss').read_text(encoding='utf-8')
        workflow = (REPO_ROOT / '.github' / 'workflows' / 'build.yml').read_text(encoding='utf-8')
        readme = (REPO_ROOT / 'README.md').read_text(encoding='utf-8')
        package_json = (REPO_ROOT / 'package.json').read_text(encoding='utf-8')

        assert "name='NOMADFieldDesk'" in build_spec
        assert '#define MyAppName "NOMAD Field Desk"' in installer
        assert '#define MyAppExeName "NOMADFieldDesk.exe"' in installer
        assert 'OutputBaseFilename=NOMAD-Setup' in installer
        assert 'artifact: NOMADFieldDesk-Windows' in workflow
        assert 'release/NOMAD-Setup.exe' in workflow
        assert '# NOMAD Field Desk v1.0.0' in readme
        assert 'NOMADFieldDesk-Windows.exe' in readme
        assert 'NOMAD-Setup.exe' in readme
        assert '"name": "nomad-field-desk"' in package_json


class TestSettingsEndpoint:
    def test_get_settings(self, client):
        resp = client.get('/api/settings')
        assert resp.status_code == 200

    def test_save_setting(self, client):
        resp = client.put('/api/settings', json={
            'theme': 'dark',
        })
        assert resp.status_code == 200
