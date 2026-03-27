"""Tests for radiation dose log API routes."""


class TestRadiationList:
    def test_list_radiation(self, client):
        resp = client.get('/api/radiation')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'readings' in data
        assert 'total_rem' in data


class TestRadiationCreate:
    def test_create_reading(self, client):
        resp = client.post('/api/radiation', json={
            'dose_rate_rem': 0.05,
            'location': 'West perimeter',
            'notes': 'Test reading',
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['dose_rate_rem'] == 0.05
        assert data['cumulative_rem'] == 0.05

    def test_cumulative_tracking(self, client):
        before = client.get('/api/radiation').get_json()['total_rem']
        client.post('/api/radiation', json={'dose_rate_rem': 0.1})
        client.post('/api/radiation', json={'dose_rate_rem': 0.2})
        after = client.get('/api/radiation').get_json()['total_rem']
        assert round(after - before, 4) == 0.3

    def test_bad_dose_rate_handled(self, client):
        resp = client.post('/api/radiation', json={
            'dose_rate_rem': 'not-a-number',
        })
        assert resp.status_code == 201
        # Should default to 0.0


class TestRadiationClear:
    def test_clear_radiation(self, client):
        client.post('/api/radiation', json={'dose_rate_rem': 1.0})
        resp = client.post('/api/radiation/clear')
        assert resp.status_code == 200
        # Verify cleared
        data = client.get('/api/radiation').get_json()
        assert data['total_rem'] == 0
        assert len(data['readings']) == 0
