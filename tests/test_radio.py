"""Tests for radio/communications API routes."""


class TestFrequencies:
    def test_list_frequencies(self, client):
        resp = client.get('/api/comms/frequencies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        # Should auto-seed on first access
        assert len(data) > 100

    def test_frequency_fields(self, client):
        resp = client.get('/api/comms/frequencies')
        freq = resp.get_json()[0]
        assert 'frequency' in freq
        assert 'service' in freq
        assert 'mode' in freq

    def test_create_frequency(self, client):
        resp = client.post('/api/comms/frequencies', json={
            'frequency': 155.475,
            'mode': 'FM',
            'bandwidth': '12.5',
            'service': 'MURS Ch 6 (custom)',
            'description': 'Custom test frequency',
            'region': 'US',
            'license_required': 0,
            'priority': 5,
            'notes': 'Test',
        })
        assert resp.status_code in (200, 201)

    def test_delete_frequency(self, client):
        # Create then delete
        client.post('/api/comms/frequencies', json={
            'frequency': 999.999,
            'service': 'Test Delete',
            'mode': 'FM',
            'bandwidth': '12.5',
            'description': 'To be deleted',
            'region': 'US',
            'license_required': 0,
            'priority': 1,
            'notes': '',
        })
        freqs = client.get('/api/comms/frequencies').get_json()
        test_freq = next((f for f in freqs if f['frequency'] == 999.999), None)
        assert test_freq is not None
        resp = client.delete(f'/api/comms/frequencies/{test_freq["id"]}')
        assert resp.status_code == 200


class TestRadioProfiles:
    def test_list_profiles(self, client):
        resp = client.get('/api/comms/radio-profiles')
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_create_profile(self, client):
        resp = client.post('/api/comms/radio-profiles', json={
            'name': 'Field Team Alpha',
            'frequencies': '462.5625,462.5875',
            'notes': 'Primary comms for patrol',
        })
        assert resp.status_code in (200, 201)

    def test_delete_profile(self, client):
        client.post('/api/comms/radio-profiles', json={
            'name': 'Temp Profile',
        })
        profiles = client.get('/api/comms/radio-profiles').get_json()
        temp = next((p for p in profiles if p['name'] == 'Temp Profile'), None)
        assert temp is not None
        resp = client.delete(f'/api/comms/radio-profiles/{temp["id"]}')
        assert resp.status_code == 200


class TestPropagation:
    def test_propagation_prediction(self, client):
        resp = client.get('/api/radio/propagation')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'bands' in data or 'muf' in data or isinstance(data, dict)
