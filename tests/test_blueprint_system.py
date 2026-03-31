"""Tests for system-level routes: settings, i18n, system info, etc."""

import json


class TestSettingsEndpoint:
    def test_get_settings(self, client):
        resp = client.get('/api/settings')
        assert resp.status_code == 200

    def test_save_setting(self, client):
        resp = client.put('/api/settings', json={'theme': 'dark'})
        assert resp.status_code == 200

    def test_save_and_read_setting(self, client):
        client.put('/api/settings', json={'dashboard_mode': 'compact'})
        resp = client.get('/api/settings')
        assert resp.status_code == 200

    def test_save_and_read_workspace_memory(self, client):
        payload = {'current': {'key': 'preparedness:checklists', 'tab': 'preparedness'}, 'recent': [], 'pinned': []}
        resp = client.put('/api/settings', json={'workspace_memory': json.dumps(payload)})
        assert resp.status_code == 200
        data = client.get('/api/settings').get_json()
        assert 'workspace_memory' in data


class TestOllamaHostSettings:
    def test_get_ollama_host(self, client):
        resp = client.get('/api/settings/ollama-host')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'host' in data

    def test_set_ollama_host(self, client):
        resp = client.put('/api/settings/ollama-host', json={'host': 'http://192.168.1.100:11434'})
        assert resp.status_code == 200


class TestI18nLanguages:
    def test_list_languages(self, client):
        resp = client.get('/api/i18n/languages')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'languages' in data
        assert 'en' in data['languages']

    def test_get_translations(self, client):
        resp = client.get('/api/i18n/translations/en')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'translations' in data
        assert data['language'] == 'en'

    def test_translations_not_found(self, client):
        resp = client.get('/api/i18n/translations/zz')
        assert resp.status_code == 404

    def test_get_current_language(self, client):
        resp = client.get('/api/i18n/language')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'language' in data

    def test_set_language(self, client):
        resp = client.post('/api/i18n/language', json={'language': 'es'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['language'] == 'es'

    def test_set_invalid_language(self, client):
        resp = client.post('/api/i18n/language', json={'language': 'zz'})
        assert resp.status_code == 400


class TestSystemInfo:
    def test_system_self_test(self, client):
        resp = client.get('/api/system/self-test')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'checks' in data or isinstance(data, dict)

    def test_system_db_check(self, client):
        resp = client.post('/api/system/db-check')
        assert resp.status_code == 200

    def test_system_db_vacuum(self, client):
        resp = client.post('/api/system/db-vacuum')
        assert resp.status_code == 200


class TestVersionEndpoint:
    def test_version(self, client):
        resp = client.get('/api/version')
        if resp.status_code == 200:
            data = resp.get_json()
            assert 'version' in data


class TestStatusReport:
    def test_status_report(self, client):
        resp = client.get('/api/status-report')
        assert resp.status_code == 200
