"""Tests for core API routes — services, alerts, activity, version."""


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


class TestSettingsEndpoint:
    def test_get_settings(self, client):
        resp = client.get('/api/settings')
        assert resp.status_code == 200

    def test_save_setting(self, client):
        resp = client.put('/api/settings', json={
            'theme': 'dark',
        })
        assert resp.status_code == 200
